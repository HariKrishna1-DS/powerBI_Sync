"""Run against a disposable PostgreSQL container, never a production URL."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = (ROOT / '.desktop-build/supabase-qa-container.txt').read_text().strip()
DATABASE = os.environ.get('TVTRACKER_QA_DATABASE', 'postgres')
if not CONTAINER.startswith('tvtracker-db-qa-'):
    raise RuntimeError('Use an isolated Tv Tracker QA container')
OWNER = '00000000-0000-0000-0000-000000000001'
VIEWER = '00000000-0000-0000-0000-000000000002'
OTHER = '00000000-0000-0000-0000-000000000003'


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def sql(statement, role='postgres', user=None, fails=False):
    prefix = f'set role {role};'
    if user:
        prefix += f"set request.jwt.claim.sub={quote(user)};"
    result = subprocess.run(['docker', 'exec', '-i', CONTAINER, 'psql', '-XAtq', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', DATABASE],
                            input=prefix + statement, text=True, capture_output=True, timeout=60)
    if fails:
        if result.returncode == 0:
            raise AssertionError('Unexpected database authorization/validation success')
        return result.stderr
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def rpc(name, args, role='authenticated', user=OWNER, fails=False):
    values = ','.join('null' if v is None else quote(json.dumps(v) if isinstance(v, (dict, list)) else v) for v in args)
    value = sql(f'select public.{name}({values});', role, user, fails)
    if fails:
        return value
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


class BackendDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.workspace = rpc('tv_create_workspace', [str(uuid.uuid4()), 'QA', 'queue-23656'])
        sql(f"insert into tv_tracker.members values({quote(self.workspace)},{quote(VIEWER)},'viewer');")
        self.payload = {'columns': ['Order Number', 'Product'], 'rows': [{'Order Number': '001', 'Product': 'Full Title'}],
                        'metadata': {'kind': 'portal', 'complete': True, 'expected_rows': 1, 'actual_rows': 1}, 'queue_scope': 'queue-23656'}

    def submit(self, op=None, payload=None, **kwargs):
        return rpc('tv_submit_capture', [self.workspace, op or str(uuid.uuid4()), '2026-01-01T09:00:00Z', payload or self.payload], **kwargs)

    def test_access_is_enforced_for_anonymous_viewer_and_other_workspace(self):
        self.assertIn('permission denied', rpc('tv_snapshot', [self.workspace], role='anon', user=None, fails=True))
        self.assertIn('access denied', rpc('tv_snapshot', [self.workspace], user=OTHER, fails=True))
        self.assertIn('access denied', self.submit(user=VIEWER, fails=True))
        self.assertEqual(rpc('tv_snapshot', [self.workspace], user=VIEWER)['orders'], [])
        self.assertIn('permission denied', sql('select * from tv_tracker.orders;', role='authenticated', user=OWNER, fails=True))
        self.assertIn('permission denied', rpc('tv_claim_job', [self.workspace, str(uuid.uuid4())], fails=True))

    def test_simultaneous_duplicate_submission_is_exactly_one_capture(self):
        operation = str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.submit(operation), range(4)))
        self.assertTrue(all(item == results[0] for item in results))
        self.assertEqual(sql(f'select count(*) from tv_tracker.captures where workspace_id={quote(self.workspace)};'), '1')
        changed = dict(self.payload, rows=[{'Order Number': '002'}])
        self.assertIn('different content', self.submit(operation, changed, fails=True))

    def test_parallel_clients_receive_unique_shared_sequence(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.submit(), range(4)))
        self.assertEqual(sorted(item['sequence'] for item in results), [1, 2, 3, 4])

    def test_incomplete_empty_duplicate_and_wrong_queue_are_rejected(self):
        for patch in ({'metadata': {'complete': False}}, {'metadata': dict(self.payload['metadata'], expected_rows=9)},
                      {'rows': []}, {'rows': self.payload['rows'] * 2}, {'queue_scope': 'another-queue'}):
            self.assertTrue(self.submit(payload=dict(self.payload, **patch), fails=True))

    def test_job_ownership_survives_disconnect_and_cannot_be_stolen(self):
        self.submit()
        token = str(uuid.uuid4())
        job = rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        self.assertEqual(job, rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None))
        contender = rpc('tv_claim_job', [self.workspace, str(uuid.uuid4())], role='service_role', user=None)
        self.assertTrue(contender['busy'])
        self.assertIn('ownership', rpc('tv_commit_capture', [self.workspace, str(uuid.uuid4()), [], {}, False], role='service_role', user=None, fails=True))
        result = rpc('tv_commit_capture', [self.workspace, token, [{'Order Number': '001', 'Comments': ''}], {}, False], role='service_role', user=None)
        self.assertEqual(result['revision'], 1)
        self.assertEqual(rpc('tv_snapshot', [self.workspace])['orders'][0]['data']['Order Number'], '001')

    def test_stale_order_edits_fail_and_retry_is_idempotent(self):
        self.submit()
        token = str(uuid.uuid4())
        rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        rpc('tv_commit_capture', [self.workspace, token, [{'Order Number': '001'}], {}, False], role='service_role', user=None)
        operation = str(uuid.uuid4())
        args = [self.workspace, operation, '001', 1, {'Comments': 'Reviewed'}]
        result = rpc('tv_edit_order', args)
        self.assertEqual(result, rpc('tv_edit_order', args))
        args[1] = str(uuid.uuid4())
        self.assertIn('Order changed', rpc('tv_edit_order', args, fails=True))
        self.assertIn('revision changed', rpc('tv_snapshot', [self.workspace, 1], fails=True))

    def test_late_capture_requires_review_and_does_not_roll_state_back(self):
        self.test_job_ownership_survives_disconnect_and_cannot_be_stolen()
        self.submit()
        token = str(uuid.uuid4())
        rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        self.assertIn('Late capture', rpc('tv_commit_capture', [self.workspace, token, [], {}, False], role='service_role', user=None, fails=True))
        rpc('tv_commit_capture', [self.workspace, token, [], {'reason': 'late capture'}, True], role='service_role', user=None)
        self.assertEqual(rpc('tv_snapshot', [self.workspace])['revision'], 1)

    def test_lost_commit_response_retries_without_reprocessing(self):
        self.submit()
        token = str(uuid.uuid4())
        rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        args = [self.workspace, token, [{'Order Number': '001'}], {'changed': 1}, False]
        receipt = rpc('tv_commit_capture', args, role='service_role', user=None)
        self.assertEqual(receipt, rpc('tv_commit_capture', args, role='service_role', user=None))
        recovered = rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        self.assertTrue(recovered['completed'])
        self.assertEqual(recovered['result'], receipt)
        args[2] = [{'Order Number': '002'}]
        self.assertIn('different content', rpc('tv_commit_capture', args, role='service_role', user=None, fails=True))
        self.assertEqual(rpc('tv_snapshot', [self.workspace])['revision'], 1)

    def test_duplicate_canonical_rows_roll_back_and_retain_claim(self):
        self.submit()
        token = str(uuid.uuid4())
        rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        self.assertIn('duplicate canonical', rpc('tv_commit_capture', [self.workspace, token,
            [{'Order Number': '001'}, {'Order Number': ' 001 '}], {}, False], role='service_role', user=None, fails=True))
        self.assertEqual(rpc('tv_snapshot', [self.workspace])['orders'], [])
        self.assertEqual(rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)['job']['token'], token)

    def test_publication_acknowledgment_and_lost_response_are_idempotent(self):
        self.test_job_ownership_survives_disconnect_and_cannot_be_stolen()
        sql(f"update tv_tracker.workspaces set mode='active' where id={quote(self.workspace)};")
        token = str(uuid.uuid4())
        claim = rpc('tv_claim_job', [self.workspace, token], role='service_role', user=None)
        self.assertEqual(claim['job']['kind'], 'publish')
        self.assertIn('in progress', rpc('tv_edit_order', [self.workspace, str(uuid.uuid4()), '001', 1,
            {'Comments': 'Cannot change snapshot while publishing'}], fails=True))
        args = [self.workspace, token, 1]
        first = rpc('tv_ack_publication', args, role='service_role', user=None)
        self.assertEqual(first, rpc('tv_ack_publication', args, role='service_role', user=None))
        self.assertEqual(rpc('tv_snapshot', [self.workspace])['published_revision'], 1)
        self.assertIsNone(rpc('tv_claim_job', [self.workspace, str(uuid.uuid4())], role='service_role', user=None))

    def test_workspace_creation_is_idempotent_and_private(self):
        self.assertEqual(self.workspace, rpc('tv_create_workspace', [self.workspace, 'QA', 'queue-23656']))
        self.assertIn('different content', rpc('tv_create_workspace', [self.workspace, 'Changed', 'queue-23656'], fails=True))
        self.assertIn('access denied', rpc('tv_create_workspace', [self.workspace, 'QA', 'queue-23656'], user=OTHER, fails=True))
        self.assertNotIn(self.workspace, [w['id'] for w in rpc('tv_list_workspaces', [], user=OTHER)])
        self.assertIn(self.workspace, [w['id'] for w in rpc('tv_list_workspaces', [], user=VIEWER)])

    def test_only_owner_can_grant_and_revoke_membership_with_audit_receipt(self):
        args = [self.workspace, str(uuid.uuid4()), OTHER, 'editor']
        self.assertIn('access denied', rpc('tv_set_member', args, user=VIEWER, fails=True))
        receipt = rpc('tv_set_member', args)
        self.assertEqual(receipt, rpc('tv_set_member', args))
        self.assertEqual(self.submit(user=OTHER)['state'], 'accepted')
        rpc('tv_set_member', [self.workspace, str(uuid.uuid4()), OTHER, None])
        self.assertIn('access denied', self.submit(user=OTHER, fails=True))
        self.assertIn('valid role', rpc('tv_set_member', [self.workspace, str(uuid.uuid4()), OWNER, None], fails=True))


if __name__ == '__main__':
    unittest.main()
