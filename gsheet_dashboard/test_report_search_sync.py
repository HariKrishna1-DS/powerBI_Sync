from copy import deepcopy
from pathlib import Path
from threading import Lock
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask
from import_excel_changes import editable_frames, reconcile, sync_imported_tabs
from monthly_production import decode
from preview_store import PreviewStore
from report_workspace import ReportWorkspace, imported_snapshot, read_report_files, register_report_routes
from status_updates import sync_tracker_status_tabs
from sla_status import preview_snapshot
from test_order_status_updates import StatusBook, StatusSheet, COLUMNS
from test_pdf_report_workspace import ReportBook, excel, row


def set_cell(frames, title, number, column, value):
    values = frames[title]
    cells = next(cells for cells in values[1:] if cells[values[0].index('Order Number')] == number)
    cells[values[0].index(column)] = value


class ReportSearchSyncTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = ReportWorkspace(PreviewStore(Path(self.folder.name) / 'previews'))
        self.imported = read_report_files([('full.xlsx', excel([
            row('A', 'Completed and Delivered', **{'Out Time': '10/20/2026 03:24 PM'}),
            row('B', 'Assign to ABS'), row('BA', 'QC in Progress')]))])
        self.workspace.save(mode='excel', imported=self.imported, cloud_reset=False)

    def test_lost_publication_reply_is_not_a_conflicting_manual_edit(self):
        baseline = editable_frames(imported_snapshot(self.imported), {'mode': 'excel'})
        remote = deepcopy(baseline)
        # One tab was published, while the saved baseline still has its old copy.
        set_cell(baseline, 'Full_Search_OCT_2026', 'A', 'Status', 'Search In Progress')
        set_cell(baseline, 'Full_Search_OCT_2026', 'A', 'Out Time', '')
        # The actual new edit clears Out Time and reopens A in All Products.
        set_cell(remote, 'All Products', 'A', 'Status', 'Search In Progress')
        set_cell(remote, 'All Products', 'A', 'Out Time', '')
        set_cell(remote, 'All Products', 'B', 'Status', 'Completed and Delivered')
        saved = deepcopy(self.imported)
        updated, events = reconcile(self.imported, baseline, remote)
        orders = {r['Order Number']: r for r in updated['rows']}
        self.assertEqual((orders['A']['Status'], orders['A']['Out Time']), ('Search In Progress', ''))
        self.assertEqual(orders['B']['Status'], 'Completed and Delivered')
        self.assertEqual(self.imported, saved)
        self.assertTrue(any(event['Order Number'] == 'B' for event in events))

    def test_two_different_new_manual_statuses_still_require_resolution(self):
        baseline = editable_frames(imported_snapshot(self.imported), {'mode': 'excel'})
        remote = deepcopy(baseline)
        set_cell(remote, 'All Products', 'B', 'Status', 'Typing in Progress')
        set_cell(remote, 'Full_Search_OCT_2026', 'B', 'Status', 'Cancelled')
        with self.assertRaisesRegex(ValueError, 'conflicting Status'):
            reconcile(self.imported, baseline, remote)

    def test_older_imported_order_tab_status_is_read_and_republished(self):
        book = ReportBook()
        baseline = editable_frames(imported_snapshot(self.imported), {'mode': 'excel'})
        for title, values in baseline.items():
            book.add(title, decode(values), headers=values[0])
        older = book.add('Full_Search_SEP_2026', self.imported['rows'], headers=self.imported['columns'])
        self.workspace.save(cloud_baseline=baseline, synced_at='2026-10-20')
        self.assertFalse(sync_imported_tabs(self.workspace, book, self.workspace.read()))
        older.values[2][older.values[0].index('Status')] = 'Completed and Delivered'
        self.assertTrue(sync_imported_tabs(self.workspace, book, self.workspace.read()))
        self.assertEqual(self.workspace.read()['imported']['rows'][1]['Status'], 'Completed and Delivered')
        frames = editable_frames(imported_snapshot(self.workspace.read()['imported']), {'mode': 'excel'})
        for title in ('All Products', 'Full_Search_OCT_2026'):
            self.assertEqual(decode(frames[title])[1]['Status'], 'Completed and Delivered')

    def test_tracker_edit_propagates_to_all_monthly_order_copies(self):
        orders = [dict(zip(COLUMNS, ['001', 'Full Title', 'Assign to ABS', '10/13/2026', '10/21/2026', '']))]
        book = StatusBook(orders)
        book.sheets.append(StatusSheet('Full_Search_SEP_2026', 6, orders))
        self.workspace.save(mode='tracker')
        sync_tracker_status_tabs(self.workspace, book)
        book.worksheet('Full_Search_SEP_2026').values[1][2] = 'Completed and Delivered'
        self.assertTrue(sync_tracker_status_tabs(self.workspace, book))
        for sheet in book.sheets:
            if len(sheet.values) > 1:
                self.assertEqual(sheet.values[1][2], 'Completed and Delivered')
        self.assertFalse(sync_tracker_status_tabs(self.workspace, book))

    def test_order_search_matches_exact_number_before_partial_and_searches_all_dates(self):
        app = Flask(__name__)
        register_report_routes(app, self.workspace, Lock(),
            lambda **kwargs: imported_snapshot(self.workspace.read()['imported']), lambda: (None, None), lambda: None)
        client = app.test_client()
        self.assertEqual(client.get('/api/report-order-search?search=b').json['total'], 1)
        self.assertEqual(client.get('/api/report-order-search?search=b').json['rows'][0]['Status'], 'Assign to ABS')
        self.assertEqual(client.get('/api/report-order-search?search=missing').json['total'], 0)
        self.assertEqual(client.get('/api/report-order-search').json['rows'], [])

    def test_google_sheet_status_is_visible_in_sla_despite_the_saved_queue_rule(self):
        store = self.workspace.store
        captured = {'Order Number': '001', 'Task Status': 'Available', 'Last User': '', 'Product': 'Full Title'}
        store.restore(1, list(captured), [captured], created='2026-10-20T09:00:00Z')
        snapshot = preview_snapshot(store, {'sheet_status_overrides': {'001': 'Completed and Delivered'}})
        self.assertEqual(snapshot['sheets']['Overview']['rows'][0]['Status'], 'Completed and Delivered')
        self.assertEqual(store.get(1)['rows'][0], captured)

    def test_consistent_capture_updates_do_not_become_manual_sla_overrides(self):
        orders = [dict(zip(COLUMNS, ['001', 'Full Title', 'Assign to ABS', '10/13/2026', '10/21/2026', '']))]
        book = StatusBook(orders)
        self.workspace.save(mode='tracker')
        sync_tracker_status_tabs(self.workspace, book)
        for sheet in book.sheets:
            if len(sheet.values) > 1:
                sheet.values[1][2] = 'Typing in Progress'
        sync_tracker_status_tabs(self.workspace, book)
        self.assertNotIn('001', self.workspace.read()['sheet_status_overrides'])

    def test_new_capture_reevaluates_status_instead_of_reusing_old_sheet_override(self):
        store = self.workspace.store
        raw = {'Order Number': '001', 'Product': 'Full Title', 'Task Name': 'Search',
               'Task Status': 'Available', 'ETA Comments': 'Assigned to the abstractor'}
        store.restore(1, list(raw), [raw], created='2026-10-20T09:00:00Z')
        book = StatusBook([dict(zip(COLUMNS, ['001', 'Full Title', 'Assign to ABS', '10/13/2026', '10/21/2026', '']))])
        self.workspace.save(mode='tracker')
        sync_tracker_status_tabs(self.workspace, book)
        book.worksheet('All Products').values[1][2] = 'Completed and Delivered'
        sync_tracker_status_tabs(self.workspace, book)
        settings = self.workspace.read()
        self.assertEqual(settings['sheet_status_override_previews']['001'], 1)
        self.assertEqual(preview_snapshot(store, settings)['sheets']['Overview']['rows'][0]['Status'], 'Completed and Delivered')
        store.restore(2, list(raw), [raw], created='2026-10-20T10:00:00Z')
        fresh = preview_snapshot(store, settings)['sheets']['Overview']['rows'][0]
        self.assertEqual(fresh['Status'], 'Assign to ABS')
        self.assertIn('abstractor', fresh['Status Reason'])
        self.assertEqual(store.get(1)['rows'], [raw])
        self.assertEqual(store.get(2)['rows'], [raw])


if __name__ == '__main__':
    unittest.main()
