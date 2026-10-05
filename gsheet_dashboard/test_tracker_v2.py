"""Regression coverage for the user's September tracker specification."""
from contextlib import nullcontext
from datetime import datetime
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import pandas as pd

from tracker_sync import (FULL, REMAINING, HEADERS, merge_trackers, free_site, deadline,
                          sync_trackers, sheet_reports, records)
from preview_store import PreviewStore, compare
from order_reporting import automatic_sync_frame


def order(number, status='In Progress', **extra):
    return {'No': 1, 'Order Number': number, 'Product': 'Full Title', 'Status': status,
            'Searcher': 'Manual searcher', 'Review/QC': '=A1', **extra}


class Sheet:
    def __init__(self, title, number, values=None):
        self.title, self.id, self.values = title, number, values or []
        self.row_count, self.col_count = 100, 30
        self.conditional_formats = []

    def get_all_values(self, value_render_option=None):
        values = [[v if value_render_option == 'UNFORMATTED_VALUE' else str(v)
                   if v is not None else '' for v in r] for r in self.values]
        for row in values:
            while row and row[-1] == '':
                row.pop()
        while values and not values[-1]:
            values.pop()
        return values

    def update_title(self, title):
        self.title = title


class Book:
    def __init__(self):
        self.sheets, self.batches = [], []
        self.fail_after_commit = False

    def worksheets(self):
        return self.sheets

    def worksheet(self, title):
        return next(s for s in self.sheets if s.title == title)

    def add_worksheet(self, title, rows, cols):
        sheet = Sheet(title, len(self.sheets))
        self.sheets.append(sheet)
        return sheet

    def fetch_sheet_metadata(self, params=None):
        return {'sheets': [{'properties': {'sheetId': s.id, 'title': s.title}, 'conditionalFormats': s.conditional_formats} for s in self.sheets]}

    def batch_update(self, body):
        self.batches.append(body)
        for request in body['requests']:
            if 'addConditionalFormatRule' in request:
                data = request['addConditionalFormatRule']
                sheet = next(s for s in self.sheets if s.id == data['rule']['ranges'][0]['sheetId'])
                sheet.conditional_formats.insert(data['index'], data['rule'])
            if 'deleteConditionalFormatRule' in request:
                data = request['deleteConditionalFormatRule']
                sheet = next(s for s in self.sheets if s.id == data['sheetId'])
                sheet.conditional_formats.pop(data['index'])
            if 'updateCells' not in request:
                continue
            update = request['updateCells']
            if 'userEnteredValue' not in update['fields']:
                continue
            region = update.get('start', update.get('range'))
            sheet = next(s for s in self.sheets if s.id == region['sheetId'])
            start = region.get('rowIndex', region.get('startRowIndex', 0))
            left = region.get('columnIndex', region.get('startColumnIndex', 0))
            for i, row in enumerate(update['rows'], start):
                while len(sheet.values) <= i:
                    sheet.values.append([])
                for j, cell in enumerate(row['values'], left):
                    while len(sheet.values[i]) <= j:
                        sheet.values[i].append('')
                    sheet.values[i][j] = next(iter(cell.get('userEnteredValue', {}).values()), '')
        if self.fail_after_commit:
            self.fail_after_commit = False
            from requests.exceptions import Timeout
            raise Timeout('Reply lost after commit')


class TrackerRulesTests(unittest.TestCase):
    def setUp(self):
        self.anchor = datetime(2026, 10, 2, 9, 0)

    def merge(self, rows, incoming, previous=()):
        return merge_trackers({FULL: rows, REMAINING: []}, incoming, previous, self.anchor)

    def test_missing_order_preserves_entire_row(self):
        row = order('ABC', **{'Out Time': '', 'Free Site': 'manual'})
        merged, report = self.merge([row], [], [{'Order Number': 'abc'}])
        self.assertEqual(merged[FULL], [dict(row, **{'Free Site': ''})])
        self.assertEqual(report['not_in_latest'], ['abc'])
        self.assertEqual(report['updated'], 0)

    def test_new_orders_and_suspension_precedence(self):
        rows = [{'Order Number': 'A', 'Product': 'Full Title', 'Task Status': 'Completed'},
                {'Order Number': 'B', 'Product': 'Other', 'Task Name': 'Search', 'Task Status': 'Available', 'WorkflowSuspended': True}]
        merged, report = self.merge([], rows)
        self.assertEqual(merged[FULL][0]['Status'], 'Search In Progress')
        self.assertEqual(merged[REMAINING][0]['Status'], 'Awaiting for Clarification')
        self.assertEqual(merged[FULL][0]['Searcher'], '')
        self.assertEqual(report['added'], 2)

    def test_case_trim_match_manual_columns_and_no_invented_completion(self):
        for task in ('TypingModule', 'SearchFix', 'CRSP2', 'N/A'):
            merged, report = self.merge([order('AbC')], [{'Order Number': ' abc ', 'Task Name': task, 'Task Status': 'Completed', 'Searcher': 'Overwrite'}])
            self.assertEqual(merged[FULL][0]['Status'], 'In Progress')
            self.assertEqual(merged[FULL][0]['Searcher'], 'Manual searcher')
            self.assertEqual(merged[FULL][0]['Review/QC'], '=A1')
            self.assertEqual(report['added'], 0)

    def test_unchanged_drivers_preserve_manually_completed_status(self):
        raw = {'Order Number': 'A', 'Task Name': 'Search', 'Task Status': 'Available'}
        result, _ = self.merge([order('A', 'Completed and Delivered')], [raw], [raw])
        self.assertEqual(result[FULL][0]['Status'], 'Completed and Delivered')

    def test_changed_drivers_apply_mapping(self):
        old = {'Order Number': 'A', 'Task Name': 'Search', 'Task Status': 'In Progress'}
        new = dict(old, **{'Task Status': 'Available'})
        result, _ = self.merge([order('A')], [new], [old])
        self.assertEqual(result[FULL][0]['Status'], 'Search In Progress')

    def test_ambiguous_duplicates_are_skipped(self):
        result, report = self.merge([], [{'Order Number': 'A'}, {'Order Number': ' a '}])
        self.assertEqual(report['unprocessed'], 2)
        self.assertFalse(result[FULL])

    def test_completed_timestamp_retains_time_of_day(self):
        result, _ = self.merge([order('A', 'Completed and Delivered')], [{'Order Number': 'A', 'Completed Time': '10/02/2026 09:30 AM', 'SLA Expiration': '10/02 09:30 AM'}])
        self.assertEqual(result[FULL][0]['Free Site'], 'On Time')
        self.assertIn('09:30', result[FULL][0]['Out Time'])

    def test_countdown_sla_and_ambiguity(self):
        self.assertEqual(deadline('7h 41m', self.anchor), datetime(2026, 10, 2, 16, 41))
        self.assertEqual(deadline('-1d 4h 0m', self.anchor), datetime(2026, 10, 1, 5))
        self.assertEqual(free_site({'Out Time': '', 'SLA Expiration': '-1d'}, self.anchor)[0], '')
        self.assertEqual(free_site({'Out Time': '10/02/2026 08:00 AM', 'SLA Expiration': 'PAUSED'}, self.anchor)[0], '')

    def test_reports_use_all_retained_tracker_orders(self):
        data = {FULL: [order('A', **{'Date': '10/01/2026'}), order('B', 'Completed and Delivered', Date='10/01/2026')], REMAINING: []}
        reports = sheet_reports(data)
        self.assertEqual(reports['daily'][0]['Today Orders'], 2)
        self.assertEqual(reports['monthly'][0]['Completed Orders'], 1)

    def test_comparison_is_case_insensitive(self):
        a = {'name': 'preview1', 'columns': ['Order Number', 'Status'], 'rows': [{'Order Number': ' AbC ', 'Status': 'In Progress'}]}
        b = {'name': 'preview2', 'columns': a['columns'], 'rows': [{'Order Number': 'abc', 'Status': 'Completed and Delivered'}]}
        result = compare(a, b, ['Order Number'])
        self.assertEqual(result['counts']['modified'], 1)
        self.assertEqual(result['counts']['removed'], 0)

    def test_recovered_sheet_booleans_are_not_false_changes(self):
        a = {'name': 'preview1', 'columns': ['Order Number', 'Is Available', 'WorkflowSuspended'],
             'rows': [{'Order Number': '001', 'Is Available': 'TRUE', 'WorkflowSuspended': 'FALSE'}]}
        b = {'name': 'preview2', 'columns': a['columns'],
             'rows': [{'Order Number': '001', 'Is Available': True, 'WorkflowSuspended': False}]}
        self.assertEqual(compare(a, b)['counts']['unchanged'], 1)
        b['rows'][0]['WorkflowSuspended'] = True
        result = compare(a, b)
        self.assertEqual(result['counts']['modified'], 1)
        self.assertEqual([r['Column'] for r in result['rows']], ['WorkflowSuspended'])
        b['rows'][0]['Order Number'] = '1'
        result = compare(a, b)
        self.assertEqual((result['counts']['added'], result['counts']['removed']), (1, 1))

    def test_boolean_recovery_comparison_without_unique_keys(self):
        a = {'name': 'preview1', 'columns': ['Is Available'], 'rows': [{'Is Available': 'FALSE'}]}
        b = {'name': 'preview2', 'columns': a['columns'], 'rows': [{'Is Available': False}]}
        self.assertEqual(compare(a, b)['counts']['unchanged'], 1)

    def test_remote_database_environment_cannot_enable_access(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'DATABASE_URL': 'postgresql://invalid'}):
            store = PreviewStore(folder)
            self.assertFalse(hasattr(store, 'database_url'))
            self.assertEqual(store.pending_syncs(), [])


class SheetTransactionTests(unittest.TestCase):
    def setUp(self):
        self.book = Book()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.defaults = {FULL: [order('BASE', **{'Date': '09/01/2026'})], REMAINING: []}
        self.patch_defaults = patch('tracker_sync.load_defaults', return_value=self.defaults)
        self.patch_lock = patch('tracker_sync.sync_lock', return_value=nullcontext())
        self.patch_defaults.start()
        self.patch_lock.start()
        self.addCleanup(self.patch_defaults.stop)
        self.addCleanup(self.patch_lock.stop)

    def frame(self, number, rows):
        preview = {'id': number, 'name': f'preview{number}', 'created': '2026-10-02T03:30:00+00:00',
                   'columns': list(rows[0]) if rows else ['Order Number', 'Product', 'Task Status'], 'rows': rows}
        frame = automatic_sync_frame(preview)[0]
        frame.attrs['store_root'] = self.folder.name
        return frame

    def test_second_preview_keeps_first_and_all_tracker_rows(self):
        a = self.frame(1, [{'Order Number': 'A', 'Product': 'Full Title', 'Task Status': 'Available'}])
        sync_trackers(a, book=self.book)
        old = self.book.worksheet('Sheet1').get_all_values()
        b = self.frame(2, [{'Order Number': 'B', 'Product': 'Full Title', 'Task Status': 'In Progress'}])
        sync_trackers(b, book=self.book)
        rows = records(self.book.worksheet(FULL).get_all_values())
        self.assertEqual([r['Order Number'] for r in rows], ['A', 'B', 'BASE'])  # Missing arrivals tie-break by order.
        self.assertEqual(self.book.worksheet('Sheet1').get_all_values()[:len(old)], old)
        self.assertFalse(any(s.title.startswith('preview') for s in self.book.worksheets()))
        self.assertFalse(any(s.title in ('Preview History', 'Default conflicts', 'Changes', 'Ambiguous - Needs review')
                             for s in self.book.worksheets()))
        self.assertEqual(len(records(self.book.worksheet('All Products').get_all_values())), 2)
        self.assertEqual(b.attrs['pass_report']['not_in_latest'], ['A'])

    def test_committed_preview_is_a_noop(self):
        frame = self.frame(1, [{'Order Number': 'A', 'Product': 'Full Title'}])
        sync_trackers(frame, book=self.book)
        count = len(self.book.batches)
        sync_trackers(frame, book=self.book)
        self.assertEqual(len(self.book.batches), count+1)  # Formatting is reapplied without rewriting data.
        self.assertFalse(any('updateCells' in r for r in self.book.batches[-1]['requests']))

    def test_numeric_archive_round_trip_retry_does_not_duplicate(self):
        frame = self.frame(1, [{'Order Number': '001', 'Product': 'Full Title',
                               'Queue Age Hours': 240.0, 'WorkflowSuspended': False}])
        sync_trackers(frame, book=self.book)
        archive = self.book.worksheet('Sheet1')
        archive.values[1][archive.values[0].index('Queue Age Hours')] = 240
        count = len(self.book.batches)
        sync_trackers(frame, book=self.book)
        self.assertEqual(len(self.book.batches), count+1)
        self.assertFalse(any('updateCells' in r for r in self.book.batches[-1]['requests']))
        self.assertEqual(len(records(archive.get_all_values())), 1)

    def test_numeric_change_or_text_identifier_change_still_blocks_retry(self):
        frame = self.frame(1, [{'Order Number': '001', 'Product': 'Full Title',
                               'Queue Age Hours': 240.125}])
        sync_trackers(frame, book=self.book)
        archive = self.book.worksheet('Sheet1')
        age = archive.values[0].index('Queue Age Hours')
        archive.values[1][age] = 240.126
        with self.assertRaisesRegex(ValueError, 'different saved snapshot'):
            sync_trackers(frame, book=self.book)
        archive.values[1][age] = 240.125
        archive.values[1][archive.values[0].index('Order Number')] = '1'
        with self.assertRaisesRegex(ValueError, 'different saved snapshot'):
            sync_trackers(frame, book=self.book)

    def test_retry_after_lost_reply_does_not_duplicate_appends(self):
        self.book.fail_after_commit = True
        with patch('datatrace_sync.time.sleep'):
            sync_trackers(self.frame(1, [{'Order Number': 'A', 'Product': 'Full Title'}]), book=self.book)
        self.assertEqual(len(records(self.book.worksheet('All Products').get_all_values())), 1)
        self.assertEqual(len(records(self.book.worksheet('Sheet1').get_all_values())), 1)

    def test_old_unsynced_preview_cannot_regress_tracker(self):
        sync_trackers(self.frame(2, [{'Order Number': 'A', 'Product': 'Full Title'}]), book=self.book)
        with self.assertRaisesRegex(ValueError, 'older preview'):
            sync_trackers(self.frame(1, [{'Order Number': 'B', 'Product': 'Full Title'}]), book=self.book)

    def test_manual_formula_never_written_when_syncing_existing_order(self):
        frame = self.frame(1, [{'Order Number': 'BASE', 'Product': 'Full Title'}])
        sync_trackers(frame, book=self.book)
        frame2 = self.frame(2, [{'Order Number': 'BASE', 'Product': 'Full Title', 'Task Name': 'Search', 'Task Status': 'Available'}])
        sync_trackers(frame2, book=self.book)
        tracker = self.book.worksheet(FULL)
        manual_col = tracker.values[0].index('Review/QC')
        for request in self.book.batches[-1]['requests']:
            update = request.get('updateCells', {})
            region = update.get('start', {})
            if region.get('sheetId') == tracker.id and 'userEnteredValue' in update.get('fields', ''):
                self.assertNotEqual(region.get('columnIndex'), manual_col)


class AutomaticApiTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name) / 'previews'
        self.store = PreviewStore(self.root)

    def wait_synced(self, count):
        for _ in range(400):
            if len(self.store.list()) == count and not self.store.pending_syncs():
                return
            time.sleep(.02)
        self.fail('Automatic sync did not complete')

    def test_import_syncs_without_click_and_waits_behind_another_sync(self):
        from io import BytesIO
        from server import create_app
        entered, release = threading.Event(), threading.Event()
        calls = []
        def syncer(frame):
            calls.append(frame.attrs['preview_id'])
            if len(calls) == 1:
                entered.set()
                release.wait(5)
            return [FULL, REMAINING]
        client = create_app(root=self.root, syncer=syncer).test_client()
        for name in ('A', 'B'):
            response = client.post('/api/import', data={'file': (BytesIO(f'Order Number,Product\n{name},Full Title\n'.encode()), 'queue.csv')})
            self.assertEqual(response.status_code, 201)
            if name == 'A':
                self.assertTrue(entered.wait(5))
        release.set()
        self.wait_synced(2)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(len(self.store.list()), 2)

    def test_manual_extraction_also_syncs_automatically(self):
        from server import create_app
        calls = []
        def runner(on_progress):
            preview = self.store.save(pd.DataFrame([{'Order Number': 'A', 'Product': 'Full Title'}]))
            return {'preview_id': preview['id'], 'preview_name': preview['name'], 'error': None}
        client = create_app(root=self.root, runner=runner, syncer=lambda frame: calls.append(frame.attrs['preview_id']) or [FULL]).test_client()
        self.assertEqual(client.post('/api/extract').status_code, 202)
        self.wait_synced(1)
        self.assertEqual(calls, [1])

    def test_live_sheet_failure_is_not_replaced_by_preview_totals(self):
        from server import create_app
        client = create_app(root=self.root).test_client()
        with patch('server.target_worksheet', side_effect=RuntimeError('offline')):
            for route in ('/api/live-sheets', '/api/daily-orders', '/api/monthly-orders'):
                response = client.get(route)
                self.assertEqual(response.status_code, 502)
                self.assertNotIn('rows', response.json)


if __name__ == '__main__':
    unittest.main()
