from io import BytesIO
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from preview_store import PreviewStore
from server import create_app
import server


class SyncPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'previews'
        self.store = PreviewStore(self.root)
        self.saved = self.store.save(pd.DataFrame([{
            'Order Number': '001', 'Task Status': 'Available', 'Task Name': 'Search',
        }]))

    def test_polls_reuse_reports_and_import_invalidates_cache(self):
        client = create_app(self.root, syncer=Mock(return_value=[])).test_client()
        with patch('server.daily_orders', wraps=server.daily_orders) as reports:
            first = client.get('/api/state').json
            self.assertEqual(client.get('/api/state').json['previews'], first['previews'])
            self.assertEqual(reports.call_count, 0)
            response = client.post('/api/import', data={'file': (
                BytesIO(b'Order Number,Task Status\n002,Available\n'), 'new.csv')})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(len(client.get('/api/state').json['previews']), 2)
            self.assertEqual(reports.call_count, 0)
            for _ in range(100):
                if not client.get('/api/state').json['job']['running']:
                    break
                time.sleep(.01)
            self.assertEqual(client.delete('/api/previews/2').status_code, 200)
            self.assertEqual(len(client.get('/api/state').json['previews']), 1)
            self.assertEqual(reports.call_count, 0)

    def test_sync_is_accepted_before_slow_preparation_and_rejects_duplicate(self):
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_history = PreviewStore.history

        def slow_history(store):
            entered.set()
            release.wait(5)
            return original_history(store)

        syncer = Mock(return_value=['Sheet1'])
        client = create_app(self.root, syncer=syncer).test_client()
        responses = []

        def submit():
            responses.append(client.post('/api/sync', json={'preview': self.saved['id']}))
            returned.set()

        with patch.object(PreviewStore, 'history', slow_history):
            submitter = threading.Thread(target=submit)
            submitter.start()
            try:
                self.assertTrue(returned.wait(1), 'Sync waited for preparation before returning.')
                self.assertEqual(responses[0].status_code, 202)
                self.assertTrue(entered.wait(1))
                self.assertEqual(client.post('/api/sync', json={'preview': self.saved['id']}).status_code, 409)
                syncer.assert_not_called()
            finally:
                release.set()
                submitter.join(6)
            for _ in range(100):
                state = client.get('/api/state').json
                if not state['job']['running']:
                    break
                time.sleep(.01)
            self.assertEqual(state['job']['result']['google_sheet'], 'success')
            self.assertEqual(state['job']['result']['preview_id'], self.saved['id'])
            syncer.assert_called_once()

    def test_preparation_failure_releases_job_lock(self):
        client = create_app(self.root, syncer=Mock(return_value=['Sheet1'])).test_client()
        self.assertEqual(client.post('/api/sync', json={'preview': 999}).status_code, 202)
        for _ in range(100):
            job = client.get('/api/state').json['job']
            if not job['running']:
                break
            time.sleep(.01)
        self.assertEqual(job['result']['google_sheet'], 'failed')
        self.assertEqual(client.post('/api/sync', json={'preview': self.saved['id']}).status_code, 202)
        for _ in range(100):
            job = client.get('/api/state').json['job']
            if not job['running']:
                break
            time.sleep(.01)
        self.assertEqual(job['result']['google_sheet'], 'success')


if __name__ == '__main__':
    unittest.main()
