from io import BytesIO
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from openpyxl import load_workbook

from preview_store import PreviewStore, compare
from server import create_app
import datatrace_sync as sync


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = PreviewStore(self.root / 'previews')

    def frame(self, status='Available'):
        return pd.DataFrame([{'OPON': '0001', 'Arrival Time': '09/22/2026 01:00 PM',
                              'Task Name': 'Search', 'Task Status': status, 'Time Since Arrival': '1h 0m'}])

    def test_durable_sequential_exports_and_no_seed(self):
        self.assertEqual(self.store.list(), [])
        a = self.store.save(self.frame())
        b = PreviewStore(self.root / 'previews').save(self.frame('Completed'))
        self.assertEqual([a['name'], b['name']], ['preview1', 'preview2'])
        self.assertEqual(self.store.get(1)['rows'][0]['Task Status'], 'Available')
        for number in [1, 2]:
            self.assertTrue((self.root / 'previews' / f'preview{number}.xlsx').exists())
        self.assertEqual(self.store.get(1)['rows'][0]['OPON'], '0001')

    def test_changed_added_removed_and_ignored_clock(self):
        a = self.store.save(pd.concat([self.frame(), self.frame().assign(OPON='2')]))
        b = self.store.save(pd.concat([self.frame('Completed').assign(**{'Time Since Arrival': '2h 0m'}), self.frame().assign(OPON='3')]))
        result = compare(a, b)
        self.assertEqual(result['counts'], {'added': 1, 'removed': 1, 'modified': 1, 'unchanged': 0})
        modified = [r for r in result['rows'] if r['Change'] == 'Modified']
        self.assertEqual(len(modified), 1)
        self.assertEqual(modified[0]['Column'], 'Task Status')

    def test_duplicates_preserved_and_invalid_keys_rejected(self):
        a = self.store.save(pd.concat([self.frame(), self.frame()]))
        b = self.store.save(self.frame())
        result = compare(a, b)
        self.assertEqual(result['counts']['removed'], 1)
        self.assertEqual(result['counts']['unchanged'], 1)
        self.assertIn('No unique', result['method'])
        with self.assertRaises(ValueError):
            compare(a, b, keys=['OPON'])

    def test_second_real_pipeline_run_creates_preview_after_sync_failure(self):
        calls = []
        def scrape(*args, **kwargs):
            calls.append(1)
            Path(kwargs['env']['DATATRACE_OUTPUT_JSON']).write_text(
                self.frame('Available' if len(calls) == 1 else 'Completed').to_json(orient='records'))
            return Mock(returncode=0)
        with patch.object(sync, 'BASE_DIR', self.root), patch.dict(sync.os.environ, {'DATATRACE_USERNAME':'test', 'DATATRACE_PASSWORD':'test'}), \
                patch.object(sync.subprocess, 'run', side_effect=scrape), \
                patch.object(sync, 'sync_dataframe', side_effect=RuntimeError('No sheet credentials')):
            a, b = sync.run_sync(), sync.run_sync()
        self.assertEqual(len(calls), 2)
        self.assertEqual([a['preview_id'], b['preview_id']], [1, 2])
        self.assertEqual(b['google_sheet'], 'failed')
        self.assertEqual(self.store.get(2)['rows'][0]['Task Status'], 'Completed')

    def test_api_import_compare_excel_and_initial_empty(self):
        client = create_app(self.root / 'api').test_client()
        self.assertEqual(client.get('/api/state').json['previews'], [])
        for status in ['Available', 'Completed']:
            response = client.post('/api/import', data={'file': (BytesIO(self.frame(status).to_csv(index=False).encode()), 'queue.csv')})
            self.assertEqual(response.status_code, 201)
        result = client.post('/api/compare', json={'previous':1,'latest':2}).json
        self.assertEqual(result['counts']['modified'], 1)
        response = client.post('/api/compare', json={'previous':1,'latest':2,'download':True})
        workbook = load_workbook(BytesIO(response.data))
        self.assertIn('DataTraceChanges', workbook.active.tables)
        with client.get('/api/previews/1/download/xlsx') as downloaded:
            self.assertEqual(downloaded.status_code, 200)
        self.assertEqual(client.post('/api/extract', headers={'Origin':'https://other.example'}).status_code, 403)

    def test_job_lock_released_after_failure_and_repeat_click(self):
        release = threading.Event()
        calls = []
        def runner(on_progress):
            calls.append(1)
            release.wait(timeout=2)
            raise RuntimeError('test failure')
        client = create_app(self.root / 'jobs', runner).test_client()
        self.assertEqual(client.post('/api/extract').status_code, 202)
        self.assertEqual(client.post('/api/extract').status_code, 409)
        release.set()
        for _ in range(100):
            if not client.get('/api/state').json['job']['running']:
                break
            time.sleep(.01)
        self.assertEqual(client.post('/api/extract').status_code, 202)
        for _ in range(100):
            if not client.get('/api/state').json['job']['running']:
                break
            time.sleep(.01)
        self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
