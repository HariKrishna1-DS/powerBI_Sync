import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid

import requests

from preview_store import PreviewStore
from shared_backend import CloudError, CloudOutbox, SupabaseRpc
from workspace_backup import make_backup, restore_backup
from cloud_backend.processor import process_capture

PROJECT = 'https://qontoybecrqpbjzoajqf.supabase.co'


def response(code=200, body=None, headers=None):
    return Mock(status_code=code, headers=headers or {}, json=Mock(return_value=body))


class RpcTests(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.rpc = SupabaseRpc(PROJECT, 'sb_publishable_test', lambda: 'test-token', self.session)

    def test_rejects_admin_keys_and_redirect_targets(self):
        for url, key in [(PROJECT, 'sb_secret_test'), ('http://localhost', 'sb_publishable_test'),
                         (PROJECT + '.evil.example', 'sb_publishable_test')]:
            with self.assertRaises(ValueError):
                SupabaseRpc(url, key, lambda: '')
        self.session.post.return_value = response(302)
        with self.assertRaises(CloudError):
            self.rpc.call('tv_snapshot', {})
        self.assertFalse(self.session.post.call_args.kwargs['allow_redirects'])

    def test_failures_are_classified_and_do_not_expose_server_content(self):
        for code, body, kind in [(401, {}, 'auth'), (403, {}, 'auth'), (429, {}, 'retry'),
                                 (503, {}, 'retry'), (409, {'code': '40001'}, 'conflict'),
                                 (500, {'code': '40001'}, 'conflict'), (500, {'code': '40P01'}, 'conflict'),
                                 (409, {'code': 'PT409'}, 'conflict'),
                                 (400, {'message': 'private record'}, 'review')]:
            self.session.post.return_value = response(code, body, {'Retry-After': '120'})
            with self.assertRaises(CloudError) as failure:
                self.rpc.call('tv_submit_capture', {})
            self.assertEqual(failure.exception.kind, kind)
            self.assertNotIn('private record', str(failure.exception))
        self.session.post.side_effect = requests.Timeout('secret URL details')
        with self.assertRaises(CloudError) as failure:
            self.rpc.call('tv_snapshot', {})
        self.assertEqual(failure.exception.kind, 'retry')
        self.assertNotIn('secret', str(failure.exception))

    def test_paginated_snapshot_restarts_from_first_page_on_revision_change(self):
        row = {'order_key': 'a', 'version': 1, 'data': {'Order Number': 'A'}}
        page = {'revision': 1, 'orders': [row], 'next_cursor': 'a'}
        self.session.post.side_effect = [response(body=page), response(409, {'code': '40001'}),
            response(body={'revision': 2, 'orders': [dict(row, version=2)], 'next_cursor': None})]
        result = self.rpc.snapshot(str(uuid.uuid4()))
        self.assertEqual(result['revision'], 2)
        self.assertEqual([r['version'] for r in result['orders']], [2])
        self.assertEqual(self.session.post.call_args_list[2].kwargs['json']['p_after'], '')

    def test_invalid_pagination_never_returns_a_partial_snapshot(self):
        self.session.post.return_value = response(body={'revision': 1, 'orders': [], 'next_cursor': 'unverified'})
        with self.assertRaises(CloudError):
            self.rpc.snapshot(str(uuid.uuid4()))


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = PreviewStore(Path(self.folder.name) / 'previews')
        self.workspace = str(uuid.uuid4())
        self.preview = {'id': 1, 'created': '2026-10-01T09:00:00Z', 'columns': ['Order Number', 'Product'],
            'rows': [{'Order Number': 'A', 'Product': 'Full Title'}],
            'metadata': {'kind': 'portal', 'complete': True, 'expected_rows': 1, 'actual_rows': 1}}
        with self.store.connect() as db:
            db.execute('INSERT INTO previews VALUES(?,?,?,?,?)', (1, self.preview['created'], 'QA',
                json.dumps(self.preview['columns']), json.dumps(self.preview['rows'])))
        self.outbox = CloudOutbox(self.store)
        self.receipt = {'capture_id': str(uuid.uuid4()), 'sequence': 44, 'state': 'accepted'}

    def test_timeout_then_restart_reuses_id_and_does_not_mark_sheets_synced(self):
        operation = self.outbox.enqueue(self.workspace, self.preview, 'queue')
        rpc = Mock()
        rpc.call.side_effect = [CloudError('Lost reply', 'retry'), self.receipt]
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=0))
        self.outbox = CloudOutbox(self.store)
        self.assertEqual(self.outbox.enqueue(self.workspace, self.preview, 'queue'), operation)
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=29))
        self.assertTrue(self.outbox.drain_one(self.workspace, rpc, now=30))
        self.assertEqual([call.args[1]['p_operation'] for call in rpc.call.call_args_list], [operation, operation])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sync_receipts').fetchone()[0], 0)

    def test_authentication_pauses_in_order_until_sign_in(self):
        self.outbox.enqueue(self.workspace, self.preview, 'queue')
        self.outbox.enqueue(self.workspace, dict(self.preview, id=2), 'queue')
        rpc = Mock()
        rpc.call.side_effect = CloudError('Sign in', 'auth')
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=0))
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=1000))
        self.assertEqual(rpc.call.call_count, 1)
        self.outbox.resume_auth(self.workspace)
        rpc.call.side_effect = None
        rpc.call.return_value = self.receipt
        self.assertTrue(self.outbox.drain_one(self.workspace, rpc, now=1000))

    def test_payload_change_or_unverified_capture_requires_review(self):
        self.outbox.enqueue(self.workspace, self.preview, 'queue')
        with self.assertRaises(ValueError):
            self.outbox.enqueue(self.workspace, dict(self.preview, rows=[{'Order Number': 'B'}]), 'queue')
        for patch in ({'metadata': {}}, {'metadata': dict(self.preview['metadata'], expected_rows=9)},
                      {'rows': []}, {'created': '2026-10-01T09:00:00'}):
            with self.assertRaises(ValueError):
                self.outbox.enqueue(self.workspace, dict(self.preview, id=2, **patch), 'queue')

    def test_backup_restores_operation_id_and_unresolved_capture_cannot_be_deleted(self):
        operation = self.outbox.enqueue(self.workspace, self.preview, 'queue')
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            self.store.delete(1)
        other = PreviewStore(Path(self.folder.name) / 'restored' / 'previews')
        restore_backup(other, make_backup(self.store).getvalue())
        restored = CloudOutbox(other)
        self.assertEqual(restored.enqueue(self.workspace, self.preview, 'queue'), operation)
        self.assertEqual(restored.status(self.workspace)[0]['state'], 'pending')

    def test_unverifiable_receipt_keeps_capture_pending(self):
        self.outbox.enqueue(self.workspace, self.preview, 'queue')
        rpc = Mock()
        rpc.call.return_value = dict(self.receipt, sequence=0)
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=0))
        self.assertEqual(self.outbox.status(self.workspace)[0]['state'], 'pending')

    def test_corrupted_outbox_blocks_network_and_restore(self):
        self.outbox.enqueue(self.workspace, self.preview, 'queue')
        with self.store.connect() as db:
            db.execute("UPDATE cloud_outbox SET body='{}'")
        rpc = Mock()
        self.assertFalse(self.outbox.drain_one(self.workspace, rpc, now=0))
        rpc.call.assert_not_called()
        self.assertEqual(self.outbox.status(self.workspace)[0]['state'], 'review')
        other = PreviewStore(Path(self.folder.name) / 'other' / 'previews')
        with self.assertRaisesRegex(ValueError, 'invalid shared upload'):
            restore_backup(other, make_backup(self.store).getvalue())

    def test_retention_preserves_unresolved_cloud_capture_even_if_legacy_sync_succeeded(self):
        from report_workspace import ReportWorkspace
        from workspace_retention import archive_history
        ReportWorkspace(self.store)
        self.outbox.enqueue(self.workspace, self.preview, 'queue')
        with self.store.connect() as db:
            for number in (2, 3, 4):
                db.execute('INSERT INTO previews SELECT ?,created,source,columns_json,rows_json FROM previews WHERE id=1', (number,))
        for number in (1, 2, 3, 4):
            self.store.mark_synced(number)
        result = archive_history(self.store, keep_captures=2)
        self.assertEqual(result['archived_captures'], 1)
        self.assertEqual({row['id'] for row in self.store.list()}, {1, 3, 4})


def order(identity='A', **fields):
    return dict({'Order Number': identity, 'Product': 'Full Title', 'Status': 'Search In Progress',
        'In-Time': '10/05/2026 08:00 AM', 'Out Time': '', 'SLA Expiration': '10/05/2026 11:00 AM'}, **fields)


def capture(rows, hour=11):
    return {'captured_at': f'2026-10-05T{hour:02}:00:00+05:30',
        'payload': {'rows': rows, 'metadata': {'kind': 'portal', 'complete': True,
            'expected_rows': len(rows), 'actual_rows': len(rows)}}}


def claim(rows, incoming, previous=None):
    return {'orders': [{'order_key': row['Order Number'].lower(), 'data': row} for row in rows],
        'capture': capture(incoming), 'previous': capture(previous, 9) if previous is not None else None}


class CanonicalProcessorTests(unittest.TestCase):
    def test_manual_fields_and_input_objects_are_preserved(self):
        row = order(Comments='Reviewed', Assignee='Alex', Searcher='Sam', Shift='Day')
        data = claim([row], [order(Status='Awaiting for Clarification')])
        before = json.dumps(data, sort_keys=True)
        changed, report, review = process_capture(data)
        self.assertFalse(review)
        self.assertEqual(json.dumps(data, sort_keys=True), before)
        self.assertEqual(changed[0]['Comments'], 'Reviewed')
        self.assertEqual(changed[0]['Assignee'], 'Alex')
        self.assertEqual(report['canonical_changes'][0]['Old Status'], 'Search In Progress')

    def test_first_absence_is_inferred_at_capture_time_with_deadline_equality(self):
        rows, _, review = process_capture(claim([order(), order('B')], [order('B')], [order(), order('B')]))
        row = next(row for row in rows if row['Order Number'] == 'A')
        self.assertFalse(review)
        self.assertEqual(row['Out Time'], '10/05/2026 11:00:00 AM')
        self.assertEqual(row['Free Site'], 'On Time')
        self.assertEqual(row['Completion Evidence'], 'Inferred from queue absence')
        from report_metrics import completion_inferred
        self.assertTrue(completion_inferred(row))

    def test_reappearance_reopens_inferred_but_not_recorded_completion(self):
        inferred = order(Status='Completed and Delivered', **{'Out Time': '10/05/2026 10:00 AM',
            'Completion Evidence': 'Inferred from queue absence'})
        rows, _, _ = process_capture(claim([inferred], [order()], [order('B')]))
        row = next(row for row in rows if row['Order Number'] == 'A')
        self.assertEqual((row['Status'], row['Out Time'], row['Completion Evidence']), ('Search In Progress', '', ''))

    def test_cancelled_and_suspended_orders_never_gain_inferred_completion(self):
        existing = [order(Status='Cancelled'), order('B', Status='Task Suspended'), order('C')]
        rows, _, _ = process_capture(claim(existing, [order('C')], existing))
        for row in rows:
            if row['Order Number'] in ('A', 'B'):
                self.assertNotEqual(row['Status'], 'Completed and Delivered')
                self.assertEqual(row.get('Out Time'), '')

    def test_late_or_incomplete_capture_cannot_mutate_orders(self):
        data = claim([order()], [order('B')], [order()])
        data['last_capture_at'] = data['capture']['captured_at']
        rows, _, review = process_capture(data)
        self.assertEqual(rows, [])
        self.assertTrue(review)
        del data['last_capture_at']
        data['capture']['payload']['metadata']['complete'] = False
        self.assertTrue(process_capture(data)[2])


if __name__ == '__main__':
    unittest.main()
