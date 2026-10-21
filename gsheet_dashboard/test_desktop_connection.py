"""Read-only connection recovery and safe update shutdown regressions."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from server import create_app
from preview_store import PreviewStore
from test_tracker_v2 import Book, Sheet


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.headers = {'X-DataTrace-Token': 'fixture'}
        self.environment = patch.dict(os.environ, {'DATATRACE_DESKTOP': '1', 'DATATRACE_DESKTOP_TOKEN': 'fixture', 'GOOGLE_SERVICE_ACCOUNT_JSON': 'fixture'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.base = patch('server.BASE_DIR', self.root)
        self.base.start()
        self.addCleanup(self.base.stop)

    def test_connection_recovers_gaps_without_cloud_writes_or_pending_sync(self):
        book = Book()
        book.sheets.append(Sheet('Sheet1', 0, [['Preview', 'Preview Timestamp', 'Order Number'], ['preview6', '2026-09-30T09:00:00+05:30', 'A'], ['preview34', '2026-10-02T09:00:00+05:30', 'B']]))
        app = create_app()
        snapshot = {'sheets': {'Overview': {'rows': []}}, 'reports': {}, 'offline': False}
        with patch('server.target_worksheet', return_value=(book, book.sheets[0])), patch.object(app.extensions['production_cache'], 'get', return_value=snapshot):
            client = app.test_client()
            response = client.post('/api/desktop/check-connection', headers=self.headers)
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['next_preview'], 35)
            self.assertEqual(response.json['recovered_previews'], 2)
            self.assertEqual(client.post('/api/desktop/check-connection', headers=self.headers).json['next_preview'], 35)
        self.assertEqual(book.batches, [])
        self.assertEqual(PreviewStore(self.root / 'previews').pending_count(), 0)

    def test_missing_key_gives_setup_action_without_creating_preview(self):
        with patch.dict(os.environ, {'GOOGLE_SERVICE_ACCOUNT_JSON': ''}), patch('server.target_worksheet', side_effect=RuntimeError('missing key')):
            response = create_app().test_client().post('/api/desktop/check-connection', headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertIn('import the service-account JSON key', response.json['error'])
        self.assertEqual(PreviewStore(self.root / 'previews').list(), [])

    def test_network_failure_does_not_claim_connection_or_allocate_preview(self):
        with patch('server.SPREADSHEET_ID', 'fixture'), patch('server.target_worksheet', side_effect=RuntimeError('network failed')):
            response = create_app().test_client().post('/api/desktop/check-connection', headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertIn('No new capture was created', response.json['error'])
        self.assertIn('network failed', response.json['error'])
        self.assertEqual(PreviewStore(self.root / 'previews').list(), [])

    def test_empty_workspace_preserves_authentication_error_and_key_id(self):
        message = 'Google Sheets authentication failed: Invalid JWT Signature. Key ID fixture-key-id.'
        with patch('server.target_worksheet', side_effect=RuntimeError(message)):
            response = create_app().test_client().post('/api/desktop/check-connection', headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertIn(message, response.json['error'])
        self.assertEqual(PreviewStore(self.root / 'previews').list(), [])

    def test_shutdown_rejects_active_work_and_blocks_new_work_after_accepting(self):
        entered, release = threading.Event(), threading.Event()
        def runner(on_progress):
            entered.set()
            release.wait(5)
            return {'error': 'fixture stopped'}
        app = create_app(self.root / 'previews', runner=runner)
        client = app.test_client()
        client.post('/api/extract', headers=self.headers)
        self.assertTrue(entered.wait(3))
        self.assertEqual(client.post('/api/desktop/shutdown', json={'force': False}, headers=self.headers).status_code, 409)
        release.set()
        import time
        for _ in range(100):
            if not client.get('/api/health', headers=self.headers).json['running']:
                break
            time.sleep(.02)
        self.assertEqual(client.post('/api/desktop/shutdown', json={'force': False}, headers=self.headers).status_code, 200)
        self.assertEqual(client.post('/api/extract', headers=self.headers).status_code, 503)
