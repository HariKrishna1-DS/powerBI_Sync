"""Bulk removal, recoverable local reset and empty first-run profiles."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from preview_store import PreviewStore
from report_workspace import ReportWorkspace
from server import create_app
from tracker_sync import load_defaults
from workspace_backup import restore_backup


class CaptureManagementTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.store = PreviewStore(self.root / 'previews')
        for number in range(1, 4):
            self.store.save(pd.DataFrame([{'Order Number': f'ORDER-{number}'}]))
            self.store.mark_failed(number, 'test')
        self.app = create_app(self.store.root)
        self.client = self.app.test_client()

    def test_bulk_delete_keeps_unselected_and_sequence_with_one_backup(self):
        response = self.client.post('/api/previews/delete', json={'ids': [1, 3]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['deleted'], [1, 3])
        self.assertEqual([item['id'] for item in self.store.list()], [2])
        self.assertEqual([item['preview_id'] for item in self.store.failed_syncs()], [2])
        self.assertFalse((self.store.root / 'preview1.xlsx').exists())
        self.assertTrue((self.store.root / 'preview2.xlsx').exists())
        self.assertEqual(len(list((self.root / 'backups').glob('*.zip'))), 1)
        self.assertEqual(self.store.save(pd.DataFrame([{'Order Number': 'NEXT'}]))['id'], 4)
        self.assertFalse(self.store.recovery_enabled())

    def test_invalid_or_stale_selection_never_partially_deletes(self):
        for ids in ([], [1, 1], [True], ['1'], [0], [1, 999]):
            response = self.client.post('/api/previews/delete', json={'ids': ids})
            self.assertIn(response.status_code, (422, 404))
            self.assertEqual(len(self.store.list()), 3)
        self.assertFalse((self.root / 'backups').exists())

    def test_backup_failure_blocks_deletion_and_reset(self):
        with patch('workspace_backup.save_safety_backup', side_effect=OSError('disk full')):
            self.assertEqual(self.client.post('/api/previews/delete', json={'ids': [1, 2]}).status_code, 503)
            self.assertEqual(self.client.post('/api/workspace/reset', json={'confirmation': 'RESET LOCAL WORKSPACE'}).status_code, 503)
        self.assertEqual(len(self.store.list()), 3)

    def test_export_move_failure_restores_files_and_database(self):
        original = Path.replace
        def replace(path, target):
            if path.name == 'preview2.csv':
                raise PermissionError('locked export')
            return original(path, target)
        with patch.object(Path, 'replace', replace):
            with self.assertRaises(PermissionError):
                self.store.delete_many([1, 2])
        self.assertEqual(len(self.store.list()), 3)
        self.assertTrue((self.store.root / 'preview1.csv').exists())
        self.assertTrue((self.store.root / 'preview1.xlsx').exists())

    def test_reset_starts_empty_at_preview1_and_backup_restores_previous_report(self):
        workspace = ReportWorkspace(self.store)
        workspace.save(mode='excel', imported={'rows': [{'Order Number': 'PRIVATE'}], 'columns': ['Order Number']})
        (self.root / 'sync_schedule.json').write_text(json.dumps({'enabled': True, 'times': ['09:00']}))
        (self.root / 'production-cache.json').write_text('{}')
        with patch('server.target_worksheet', side_effect=AssertionError('Reset must stay local')):
            response = self.client.post('/api/workspace/reset', json={'confirmation': 'RESET LOCAL WORKSPACE'})
            self.assertEqual(response.status_code, 200)
            state = self.client.get('/api/state').json
            self.assertEqual(state['previews'], [])
            self.assertFalse(state['schedule']['enabled'])
            self.assertEqual(self.client.get('/api/live-sheets').json['sheets']['Overview']['rows'], [])
        self.assertFalse((self.root / 'production-cache.json').exists())
        self.assertFalse(PreviewStore(self.store.root).recovery_enabled())
        self.assertEqual(self.store.save(pd.DataFrame([{'Order Number': 'FRESH'}]))['name'], 'preview1')
        backup = self.root / 'backups' / response.json['recovery_backup']
        restore_backup(self.store, backup.read_bytes())
        self.assertEqual(len(self.store.list()), 3)
        self.assertEqual(workspace.read()['imported']['rows'][0]['Order Number'], 'PRIVATE')

    def test_reset_requires_confirmation_and_does_not_touch_another_profile(self):
        other = PreviewStore(self.root / 'another-profile' / 'previews')
        other.save(pd.DataFrame([{'Order Number': 'OTHER'}]))
        self.assertEqual(self.client.post('/api/workspace/reset', json={}).status_code, 422)
        self.assertEqual(len(self.store.list()), 3)
        self.client.post('/api/workspace/reset', json={'confirmation': 'RESET LOCAL WORKSPACE'})
        self.assertEqual(len(other.list()), 1)

    def test_shipped_default_orders_are_empty(self):
        self.assertTrue(all(not rows for rows in load_defaults().values()))


if __name__ == '__main__':
    unittest.main()
