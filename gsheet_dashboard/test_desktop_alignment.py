"""Desktop upgrade, ordering and uncertain-write regressions for tracker v2."""
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from order_reporting import automatic_sync_frame
from preview_store import PreviewStore
from production_cache import ProductionCache
from server import create_app
from test_tracker_v2 import Book, order
from tracker_sync import FULL, REMAINING, OLD_FULL, OLD_REMAINING, sync_trackers, read_tracker_rows, read_preview_history
from workspace_backup import make_backup, restore_backup


class DesktopAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = PreviewStore(self.root / 'previews')
        self.book = Book()
        patcher = patch('tracker_sync.load_defaults', return_value={FULL: [order('BASE')], REMAINING: []})
        patcher.start()
        self.addCleanup(patcher.stop)

    def frame(self, rows):
        saved = self.store.save(pd.DataFrame(rows, columns=['Order Number', 'Product', 'Task Status']))
        return automatic_sync_frame(saved, store=self.store)[0]

    def wait_idle(self, client):
        until = time.monotonic() + 10
        while time.monotonic() < until:
            state = client.get('/api/state').json
            if not state['job']['running']:
                return state
            time.sleep(.02)
        self.fail('Sync worker did not finish')

    def test_v20_receipts_and_backup_upgrade_do_not_resync(self):
        self.frame([{'Order Number': 'A'}])
        self.store.mark_synced(1)
        with self.store.connect() as db:
            for table in ('sync_jobs', 'sync_reports', 'sync_failures'):
                db.execute(f'DROP TABLE {table}')
        old_backup = make_backup(self.store).getvalue()
        upgraded = PreviewStore(self.store.root)
        self.assertEqual(upgraded.pending_count(), 0)
        restore_backup(upgraded, old_backup)
        self.assertEqual(upgraded.unsynced_ids(), [])
        upgraded.mark_failed(1, 'fixture')
        self.assertEqual(upgraded.failed_syncs()[0]['preview_id'], 1)

    def test_new_receipts_and_failures_survive_backup_without_private_api_data(self):
        frame = self.frame([{'Order Number': 'A', 'Product': 'Full Title'}])
        sync_trackers(frame, book=self.book)
        self.store.mark_synced(1, frame.attrs['pass_report'])
        self.frame([{'Order Number': 'B'}])
        self.store.mark_failed(2, 'permission denied')
        raw = make_backup(self.store).getvalue()
        self.store.mark_synced(2)
        restore_backup(self.store, raw)
        self.assertEqual(self.store.failed_syncs()[0]['error'], 'permission denied')
        self.assertTrue(self.store.get_sync_report(1)['committed'])
        report = create_app(self.store.root).test_client().get('/api/sync-reports').json['report']
        self.assertEqual(report['added'], 1)
        self.assertNotIn('_expected_tracker_cells', report)
        self.assertNotIn('_expected_tracker_cells', frame.attrs['pass_report'])

    def test_empty_capture_archive_replay_and_recovery(self):
        frame = self.frame([])
        sync_trackers(frame, book=self.book)
        batches = len(self.book.batches)
        sync_trackers(frame, book=self.book)
        self.assertEqual(len(self.book.batches), batches)
        recovered = read_preview_history(self.book)
        self.assertEqual(recovered[0]['rows'], [])
        self.assertEqual(recovered[0]['columns'], list(frame.columns))

    def test_same_order_ids_with_wrong_readback_are_not_acknowledged(self):
        frame = self.frame([{'Order Number': 'A', 'Product': 'Full Title'}])
        original = self.book.batch_update
        def corrupt(body):
            original(body)
            if any(s.title == FULL and s.values for s in self.book.sheets):
                sheet = self.book.worksheet(FULL)
                sheet.values[1][sheet.values[0].index('Status')] = 'CORRUPTED'
        self.book.batch_update = corrupt
        with self.assertRaisesRegex(RuntimeError, 'readback values differ'):
            sync_trackers(frame, book=self.book)
        self.assertIsNone(self.store.get_sync_report(1))
        self.book.batch_update = original
        with self.assertRaisesRegex(RuntimeError, 'readback values differ'):
            sync_trackers(frame, book=self.book)
        self.assertIsNone(self.store.get_sync_report(1))

    def test_legacy_read_is_nonmutating_and_custom_tabs_are_respected(self):
        for title in (OLD_FULL, OLD_REMAINING):
            self.book.add_worksheet(title, 10, 2).values = [['Order Number'], [title]]
        rows = read_tracker_rows(self.book)
        self.assertEqual([r['_tracker'] for r in rows], [FULL, REMAINING])
        self.assertEqual([s.title for s in self.book.sheets], [OLD_FULL, OLD_REMAINING])
        with patch('tracker_sync.FULL', 'Custom Full'), patch('tracker_sync.REMAINING', 'Custom Rest'), patch('tracker_sync.TRACKERS', ('Custom Full', 'Custom Rest')):
            with self.assertRaises(ValueError):
                read_tracker_rows(self.book)
            for title in ('Custom Full', 'Custom Rest'):
                self.book.add_worksheet(title, 10, 2).values = [['Order Number']]
            self.assertEqual(read_tracker_rows(self.book), [])

    def test_reserved_headers_rejected_before_any_remote_write(self):
        saved = self.store.save(pd.DataFrame([{'Order Number': 'A', 'Preview': 'spoof'}]))
        with self.assertRaises(ValueError):
            sync_trackers(automatic_sync_frame(saved, store=self.store)[0], book=self.book)
        self.assertEqual(self.book.sheets, [])
        self.assertEqual(self.book.batches, [])

    def test_failure_blocks_newer_import_until_explicit_ordered_retry(self):
        self.frame([{'Order Number': 'A'}])
        self.store.mark_failed(1, 'Earlier failure')
        syncer = Mock(return_value=[FULL])
        client = create_app(self.store.root, syncer=syncer).test_client()
        response = client.post('/api/import', data={'file': (BytesIO(b'Order Number,Product\nB,Full Title\n'), 'queue.csv')})
        self.assertEqual(response.status_code, 201)
        state = self.wait_idle(client)
        syncer.assert_not_called()
        self.assertEqual(state['pending_sync'], 2)
        self.assertEqual(client.post('/api/sync', json={'preview': 2}).status_code, 202)
        self.wait_idle(client)
        self.assertEqual([call.args[0].attrs['preview_id'] for call in syncer.call_args_list], [1, 2])
        self.assertEqual(self.store.unsynced_ids(), [])
        self.assertEqual(self.store.failed_syncs(), [])

    def test_exact_default_name_upgrade_preserves_offline_cache_identity(self):
        path = self.root / 'cache.json'
        path.write_text(json.dumps({'identity': f'sheet-id|{OLD_FULL}|{OLD_REMAINING}',
                                    'sheets': {}, 'updated_at': '2026-10-01T00:00:00Z'}))
        result = ProductionCache(path, f'sheet-id|{FULL}|{REMAINING}').get(Mock(side_effect=OSError('offline')))
        self.assertTrue(result['offline'])
        self.assertEqual(result['updated_at'], '2026-10-01T00:00:00Z')
        with self.assertRaises(RuntimeError):
            ProductionCache(path, f'other-sheet|{FULL}|{REMAINING}').get(Mock(side_effect=OSError('offline')))
