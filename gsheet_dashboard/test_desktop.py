from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import pandas as pd
from preview_store import PreviewStore
from production_cache import ProductionCache
from server import create_app
from workspace_backup import make_backup, restore_backup


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_desktop_requests_require_token_and_health_never_calls_google(self):
        with patch.dict(os.environ, {'DATATRACE_DESKTOP': '1', 'DATATRACE_DESKTOP_TOKEN': 'test-secret'}):
            app = create_app(self.root / 'previews')
        client = app.test_client()
        with patch('server.target_worksheet', side_effect=AssertionError('Health must be local')):
            self.assertEqual(client.get('/api/state').status_code, 401)
            self.assertEqual(client.get('/api/health', headers={'X-DataTrace-Token': 'wrong'}).status_code, 401)
            response = client.get('/api/health', headers={'X-DataTrace-Token': 'test-secret'})
            self.assertTrue(response.json['ready'])
            self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])
        callback = Mock()
        app.config['DESKTOP_SHUTDOWN'] = callback
        self.assertEqual(client.post('/api/desktop/shutdown').status_code, 401)
        callback.assert_not_called()

    def test_web_cannot_use_native_data_endpoints(self):
        client = create_app(self.root / 'previews').test_client()
        self.assertEqual(client.get('/api/desktop/backup').status_code, 404)
        self.assertEqual(client.post('/api/desktop/restore', data=b'invalid').status_code, 404)

    def test_cache_coalesces_reads_and_labels_offline_copy_with_original_time(self):
        file = self.root / 'cache.json'
        cache = ProductionCache(file, 'sheet-one', ttl=60)
        loader = Mock(return_value={'sheets': {'Overview': {'columns': ['Order Number'], 'rows': [{'Order Number': 'A'}]}}})
        first = cache.get(loader)
        self.assertEqual(cache.get(loader)['sheets'], first['sheets'])
        self.assertEqual(loader.call_count, 1)
        restarted = ProductionCache(file, 'sheet-one')
        offline = restarted.get(Mock(side_effect=OSError('offline')))
        self.assertTrue(offline['offline'])
        self.assertEqual(offline['updated_at'], first['updated_at'])
        self.assertEqual(offline['sheets'], first['sheets'])
        with self.assertRaises(RuntimeError):
            ProductionCache(file, 'a-different-sheet').get(Mock(side_effect=OSError('offline')))

    def test_backups_round_trip_and_exclude_credentials(self):
        store = PreviewStore(self.root / 'previews')
        first = store.save(pd.DataFrame([{'Order Number': '001'}]))
        store.mark_synced(first['id'], {'added': 1})
        (self.root / '.env').write_text('DATATRACE_PASSWORD=secret')
        (self.root / 'service_account.json').write_text('{"private_key":"secret"}')
        raw = make_backup(store).getvalue()
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            self.assertEqual(set(archive.namelist()), {'manifest.json', 'previews.sqlite'})
        store.save(pd.DataFrame([{'Order Number': '002'}]))
        safety = restore_backup(store, raw)
        self.assertTrue(Path(safety).is_file())
        self.assertEqual(len(store.list()), 1)
        self.assertEqual(store.get(first['id'])['rows'][0]['Order Number'], '001')
        self.assertEqual(store.pending_count(), 0)
        self.assertEqual((self.root / '.env').read_text(), 'DATATRACE_PASSWORD=secret')

    def test_restore_rejects_traversal_and_keeps_current_data(self):
        store = PreviewStore(self.root / 'previews')
        store.save(pd.DataFrame([{'Order Number': 'SAFE'}]))
        stream = BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('../outside', 'bad')
        with self.assertRaises(ValueError):
            restore_backup(store, stream.getvalue())
        self.assertEqual(store.get(1)['rows'][0]['Order Number'], 'SAFE')

    def test_state_poll_does_not_deserialize_preview_history(self):
        store = PreviewStore(self.root / 'previews')
        store.save(pd.DataFrame([{'Order Number': f'{i:05}'} for i in range(5000)]))
        client = create_app(store.root).test_client()
        with patch.object(PreviewStore, 'history', side_effect=AssertionError('No full history on polling')):
            state = client.get('/api/state').json
            self.assertEqual(state['previews'][0]['row_count'], 5000)
            self.assertEqual(state['pending_sync'], 1)


if __name__ == '__main__':
    unittest.main()
