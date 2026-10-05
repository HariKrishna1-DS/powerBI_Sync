from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from operation_journal import OperationJournal, failure_kind
from preview_store import PreviewStore
from server import create_app
from workspace_backup import make_backup, restore_backup


class OperationHistoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'previews'
        self.store = PreviewStore(self.root)

    def test_restart_marks_incomplete_work_and_preserves_completed_history(self):
        journal = OperationJournal(self.store)
        first = journal.begin('capture')
        journal.finish(first, {'preview_id': 1})
        second = journal.begin('sync')
        restarted = OperationJournal(self.store)
        rows = restarted.list()
        self.assertEqual([row['status'] for row in rows], ['interrupted', 'completed'])
        self.assertEqual(rows[0]['id'], second)
        self.assertEqual(rows[1]['preview_id'], 1)

    def test_receipts_keep_only_failure_category(self):
        journal = OperationJournal(self.store)
        number = journal.begin('sync')
        journal.finish(number, {'error': 'connection failed token=do-not-save password=private-value'})
        value = json.dumps(journal.list())
        self.assertIn('connection', value)
        self.assertNotIn('do-not-save', value)
        self.assertNotIn('private-value', value)

    def test_history_is_bounded_and_backups_restore_it(self):
        journal = OperationJournal(self.store)
        for _ in range(205):
            journal.finish(journal.begin('sync'), {})
        self.assertEqual(len(journal.list()), 200)
        raw = make_backup(self.store).getvalue()
        restore_backup(self.store, raw)
        self.assertEqual(len(OperationJournal(self.store).list()), 200)

    def test_order_history_uses_exact_normalized_identity(self):
        self.store.save(pd.DataFrame([{'Order Number':' Ab/01 ', 'Status':'Available'}, {'Order Number':'AB/010','Status':'Wrong'}]))
        self.store.save(pd.DataFrame([{'Order Number':'ab/01', 'Status':'Completed'}]))
        client = create_app(root=self.root).test_client()
        result = client.get('/api/order-history', query_string={'order':'AB/01'}).json
        self.assertEqual([row['status'] for row in result['events']], ['Completed', 'Available'])
        self.assertEqual(client.get('/api/order-history').status_code, 422)
        self.assertEqual(client.get('/api/order-history',query_string={'order':"' OR 1=1 --"}).json['events'], [])

    def test_diagnostics_are_authenticated_and_exclude_content(self):
        self.store.save(pd.DataFrame([{'Order Number':'PRIVATE-ORDER'}]))
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'test-only'}):
            client = create_app(root=self.root).test_client()
        self.assertEqual(client.get('/api/desktop/diagnostics').status_code, 401)
        result = client.get('/api/desktop/diagnostics',headers={'X-DataTrace-Token':'test-only'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['captures'], 1)
        self.assertNotIn('PRIVATE-ORDER', result.get_data(as_text=True))
        self.assertNotIn(str(self.root), result.get_data(as_text=True))

    def test_schedule_rejects_invalid_container_and_excessive_times(self):
        client = create_app(root=self.root).test_client()
        for times in (13, {}, ['09:00']*49):
            self.assertEqual(client.post('/api/sync-schedule',json={'times':times}).status_code,422)

    def test_update_shutdown_creates_recoverable_backup_before_stopping(self):
        self.store.save(pd.DataFrame([{'Order Number':'LOCAL-1'}]))
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'test-only'}):
            client = create_app(root=self.root).test_client()
        response = client.post('/api/desktop/shutdown',json={'backup':True},headers={'X-DataTrace-Token':'test-only'})
        self.assertEqual(response.status_code,200)
        backups = list((self.root.parent/'backups').glob('before-update-*.zip'))
        self.assertEqual(len(backups),1)
        restore_backup(self.store,backups[0].read_bytes())
        self.assertEqual(self.store.get(1)['rows'][0]['Order Number'],'LOCAL-1')

    def test_failed_update_backup_does_not_shut_down_or_lock_workspace(self):
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'test-only'}):
            client = create_app(root=self.root).test_client()
        headers = {'X-DataTrace-Token':'test-only'}
        with patch('workspace_backup.make_backup',side_effect=OSError('disk full')):
            response=client.post('/api/desktop/shutdown',json={'backup':True},headers=headers)
        self.assertEqual(response.status_code,503)
        self.assertEqual(client.get('/api/state',headers=headers).status_code,200)
        self.assertEqual(client.get('/api/desktop/backup',headers=headers).status_code,200)

    def test_failure_categories_do_not_pretend_to_diagnose_unknown_errors(self):
        self.assertEqual(failure_kind('unexpected failure'), 'operation_failed')
        self.assertEqual(failure_kind('queue pagination repeated a page'), 'portal_results')
        self.assertEqual(failure_kind('429 quota exceeded'), 'rate_limit')


if __name__ == '__main__':
    unittest.main()
