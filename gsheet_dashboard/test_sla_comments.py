import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd
from preview_store import PreviewStore
from server import create_app
from production_rules import TRACKER_COLUMNS
from sync_config import TRACKER_TITLES
from test_production_sync import Book


class SlaCommentsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = PreviewStore(Path(self.folder.name) / 'previews')
        def row(identity, product, status):
            return {'Order Number': identity, 'Date': '09/30/2026', 'Product': product,
                    'Status': 'Completed and Delivered', 'In-Time': '09/30/2026 09:00 AM',
                    'Out Time': '09/30/2026 12:00 PM', 'SLA Expiration': '09/30/2026 11:00 AM', 'Free Site': status}
        self.book = Book([[row('001', 'Full Title', 'Missing'), row('003', 'Full Title', 'Missing')],
                          [row('002', 'Update', 'On Time')]])
        def write(body):
            for update in body['data']:
                match = re.fullmatch(r"'([^']+)'!W(\d+)", update['range'])
                self.book.worksheet(match[1]).values[int(match[2]) - 1][22] = update['values'][0][0]
        def read(ranges):
            results = []
            for address in ranges:
                match = re.fullmatch(r"'([^']+)'!W(\d+)(?::W(\d+))?", address)
                values = self.book.worksheet(match[1]).values
                start, end = int(match[2]), int(match[3] or match[2])
                results.append({'values': [[values[index - 1][22]] for index in range(start, end + 1)]})
            return {'valueRanges': results}
        self.book.values_batch_update = Mock(side_effect=write)
        self.book.values_batch_get = Mock(side_effect=read)
        target = patch('server.target_worksheet', return_value=(self.book, self.book.sheets[0]))
        target.start()
        self.addCleanup(target.stop)
        records = [dict(zip(sheet.values[0], values)) for sheet in self.book.sheets for values in sheet.values[1:]]
        self.store.restore(1, TRACKER_COLUMNS, records, created='2026-09-30T12:00:00+05:30')
        self.store.save_sla_correction('002', '2026-09-30', 'On Time')
        self.client = create_app(self.store.root).test_client()
        self.threads = patch('threading.Thread.start')
        self.threads.start()
        self.addCleanup(self.threads.stop)

    def save(self, identity='001', status='On Time', expected='Missed'):
        return self.client.post('/api/sla-comments', json={'order_number': identity, 'completion_date': '2026-09-30',
                               'status': status, 'expected_status': expected})

    def report(self):
        return self.client.get('/api/monthly-orders').json['rows'][0]

    def test_bulk_updates_local_preview_report_totals_without_changing_cloud_source(self):
        orders = [{'order_number': number, 'completion_date': '2026-09-30', 'expected_status': 'Missed'} for number in ('001', '003')]
        response = self.client.post('/api/sla-comments/bulk', json={'orders': orders, 'status': 'On Time'})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['rows'][0]['SLA On Time'], 3)
        self.book.values_batch_update.assert_not_called()
        self.assertEqual(self.store.sla_corrections()[('001', '2026-09-30')], 'On Time')

    def test_missed_ui_value_uses_canonical_missing_in_local_report(self):
        response = self.save('002', 'Missed', 'On Time')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.store.sla_corrections()[('002', '2026-09-30')], 'Missed')
        self.assertEqual(next(row for row in self.report()['sla_rows'] if row['Order Number'] == '002')['Free Site'], 'Missing')
        self.assertEqual(self.report()['SLA Missed'], 3)

    def test_unknown_selection_is_rejected_before_any_write(self):
        self.assertEqual(self.save('unknown').status_code, 409)
        self.book.values_batch_update.assert_not_called()

    def test_failed_local_write_never_reports_success(self):
        before = self.store.sla_corrections()
        with patch('preview_store.PreviewStore.save_sla_corrections', side_effect=OSError('disk full')):
            self.assertEqual(self.save().status_code, 503)
        self.assertEqual(self.store.sla_corrections(), before)

    def test_direct_sheet_edits_cannot_override_saved_preview_corrections(self):
        self.assertEqual(self.save().status_code, 200)
        self.book.worksheet(TRACKER_TITLES[0]).values[1][22] = 'Missing'
        self.assertEqual(self.report()['SLA Missed'], 1)
        self.book.worksheet(TRACKER_TITLES[0]).values[1][22] = ''
        self.assertIn('001', [r['Order Number'] for r in self.report()['sla_rows']])

    def test_local_cache_bulk_transaction_rolls_back(self):
        import sqlite3
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON sla_corrections WHEN NEW.order_number = '002' BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save_sla_corrections([('001', '2026-09-30', 'On Time'), ('002', '2026-09-30', 'Missed')])
        self.assertEqual(self.store.sla_corrections(), {('002', '2026-09-30'): 'On Time'})

    def test_cross_origin_writes_and_overlapping_edit_are_blocked(self):
        # This test explicitly exercises a running worker.
        self.threads.stop()
        release, entered = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        p = self.store.save(pd.DataFrame([{'Order Number': 'A', 'Product': 'Full Title'}]))
        def syncer(frame):
            entered.set()
            release.wait(3)
            return []
        client = create_app(self.store.root, syncer=syncer).test_client()
        client.post('/api/sync', json={'preview': p['id']})
        self.assertTrue(entered.wait(2))
        self.assertEqual(client.post('/api/sla-comments', json={'order_number':'001','completion_date':'2026-09-30','status':'On Time','expected_status':'Missed'}).status_code, 409)
        release.set()
        for _ in range(100):
            if not client.get('/api/state').json['job']['running']:
                break
            time.sleep(.01)
        self.assertEqual(client.post('/api/sla-comments', json={}, headers={'Origin':'https://other.example'}).status_code, 403)
