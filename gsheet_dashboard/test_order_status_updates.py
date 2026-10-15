from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
import threading
from preview_store import PreviewStore
from report_workspace import ReportWorkspace, imported_snapshot, report_frames, register_report_routes
from sla_status import build_sla_status
from status_updates import sync_tracker_status_tabs, rename_status, tracker_state
from tracker_sync import FULL, REMAINING


COLUMNS = ['Order Number', 'Product', 'Status', 'In-Time', 'SLA Expiration', 'Free Site']


class StatusSheet:
    def __init__(self, title, number, rows):
        self.title, self.id = title, number
        self.values = [COLUMNS] + [[row.get(column, '') for column in COLUMNS] for row in rows]

    def get_all_values(self, value_render_option=None):
        return deepcopy(self.values)


class StatusBook:
    def __init__(self, rows):
        self.sheets = [StatusSheet(FULL, 1, rows), StatusSheet(REMAINING, 2, []),
                       StatusSheet('All Products', 3, rows),
                       StatusSheet('Full_Search_OCT_2026', 4, [r for r in rows if r['Product'] == 'Full Title']),
                       StatusSheet('Remaining_Search_OCT_2026', 5, [r for r in rows if r['Product'] != 'Full Title'])]
        self.batches = []

    def worksheets(self):
        return self.sheets

    def worksheet(self, title):
        return next(sheet for sheet in self.sheets if sheet.title == title)

    def batch_update(self, body):
        self.batches.append(body)
        for request in body['requests']:
            change = request['updateCells']
            start = change['start']
            sheet = next(s for s in self.sheets if s.id == start['sheetId'])
            sheet.values[start['rowIndex']][start['columnIndex']] = next(iter(change['rows'][0]['values'][0]['userEnteredValue'].values()), '')


class OrderStatusUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = ReportWorkspace(PreviewStore(Path(self.directory.name) / 'previews'))
        self.rows = [dict(zip(COLUMNS, [number, product, status, '09/30/2026 09:00 AM', '-1d', '']))
                     for number, product, status in [('001', 'Full Title', 'Cancelled'),
                         ('002', 'Full Title', 'QC in Progress'), ('003', 'Two Owner', 'Need judgement details'),
                         ('004', 'Two Owner', 'Search In Progress')]]
        self.book = StatusBook(self.rows)

    def tearDown(self):
        self.directory.cleanup()

    def snapshot(self):
        owners, _ = tracker_state(self.book)
        rows = [items[0][3] for items in owners.values()]
        return imported_snapshot({'rows': rows, 'columns': COLUMNS, 'files': [], 'created': '2026-10-14'})

    def test_google_sheet_status_edit_updates_owner_and_unchanged_copies_do_not_revert_it(self):
        self.assertFalse(sync_tracker_status_tabs(self.workspace, self.book))
        self.book.worksheet('All Products').values[4][2] = 'AESearch'
        self.assertTrue(sync_tracker_status_tabs(self.workspace, self.book))
        self.assertEqual(self.book.worksheet(FULL).values[4][2], 'AESearch')
        self.assertFalse(sync_tracker_status_tabs(self.workspace, self.book))
        self.assertEqual(self.book.worksheet(FULL).values[4][2], 'AESearch')
        self.book.worksheet(FULL).values[4][2] = 'Typing in Progress'
        self.assertTrue(sync_tracker_status_tabs(self.workspace, self.book))

    def test_conflicting_tabs_reject_all_writes(self):
        sync_tracker_status_tabs(self.workspace, self.book)
        self.book.worksheet('All Products').values[1][2] = 'SearchFix'
        self.book.worksheet('Full_Search_OCT_2026').values[1][2] = 'QC in Progress'
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            sync_tracker_status_tabs(self.workspace, self.book)
        self.assertEqual(self.book.batches, [])
        self.assertEqual(self.book.worksheet(FULL).values[1][2], 'Cancelled')

    def test_status_edit_preserves_physical_row_positions_after_empty_rows(self):
        self.book.worksheet(FULL).values.insert(1, ['']*len(COLUMNS))
        rename_status(self.workspace, self.book, self.snapshot(), 'Cancelled', 'QC in Progress', ['001'])
        self.assertEqual(self.book.worksheet(FULL).values[1], ['']*len(COLUMNS))
        self.assertEqual(self.book.worksheet(FULL).values[2][2], 'QC in Progress')

    def test_renaming_cancelled_merges_into_single_existing_qc_summary(self):
        snapshot = self.snapshot()
        self.assertEqual(rename_status(self.workspace, self.book, snapshot, 'Cancelled', 'QC in Progress', ['001']), 1)
        summary = build_sla_status(self.snapshot())['summary']
        self.assertNotIn('Cancelled', [r['Status'] for r in summary])
        self.assertEqual(next(r for r in summary if r['Status'] == 'QC in Progress')['Grand Total'], 2)
        with self.assertRaisesRegex(ValueError, 'changed since'):
            rename_status(self.workspace, self.book, self.snapshot(), 'QC in Progress', 'SearchFix', ['001'])

    def test_product_views_partition_all_products_including_previous_month_two_owner(self):
        snapshot = self.snapshot()
        snapshot['mode'] = 'tracker'
        frames, _ = report_frames(snapshot, {})
        for title in frames:
            if title.startswith('Remaining_Search_'):
                self.assertEqual({row[2] for row in frames[title][1:]}, {'003', '004'})
        self.assertEqual(len(snapshot['sheets']['Full Title']['rows']), 2)
        self.assertEqual(len(snapshot['sheets']['Remaining Products']['rows']), 2)

    def test_editor_route_updates_imported_rows_and_checks_stale_selection(self):
        self.workspace.save(mode='excel', imported={'rows': self.rows, 'columns': COLUMNS, 'files': [], 'created': '2026-10-14'}, cloud_reset=True)
        app = Flask(__name__)
        register_report_routes(app, self.workspace, threading.Lock(), lambda **kwargs: self.snapshot(), lambda: (self.book, None), lambda: None)
        with patch('threading.Thread.start'):
            client = app.test_client()
            result = client.post('/api/order-status', json={'status':'Need judgement details', 'replacement':'SearchFix', 'order_numbers':['003']})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['updated'], 1)
            self.assertEqual(self.workspace.read()['imported']['rows'][2]['Status'], 'SearchFix')
            stale = client.post('/api/order-status', json={'status':'Cancelled', 'replacement':'QC in Progress', 'order_numbers':['other']})
            self.assertEqual(stale.status_code, 409)


if __name__ == '__main__':
    unittest.main()
