"""Production invariants exercised through real Sheets batch planning and API jobs."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from openpyxl import load_workbook
from requests.exceptions import ReadTimeout

from production_rules import expiration, free_site, merge_trackers, TRACKER_COLUMNS
from sheets_repository import sync_production, read_preview_history, INDEX_TITLE
from sync_config import TRACKER_TITLES
from order_reporting import daily_orders, monthly_orders, automatic_sync_frame
from preview_store import PreviewStore
from server import create_app


class Sheet:
    def __init__(self, title, number, values=None):
        self.title, self.id = title, number
        self.row_count, self.col_count = 1000, 30
        self.values = deepcopy(values or [])

    def get_all_values(self):
        rows = deepcopy(self.values)
        while rows and not any(str(v) for v in rows[-1]):
            rows.pop()
        return [[str(v) for v in row] for row in rows]


class Book:
    def __init__(self, rows=None):
        self.sheets = [Sheet('Sheet1', 0)]
        for index, title in enumerate(TRACKER_TITLES, start=1):
            self.sheets.append(Sheet(title, index, [TRACKER_COLUMNS] +
                                     [[r.get(c, '') for c in TRACKER_COLUMNS] for r in (rows or [[], []])[index - 1]]))
        self.batches = []
        self.timeout_after_commit = False

    def worksheets(self):
        return self.sheets

    def worksheet(self, title):
        return next(s for s in self.sheets if s.title == title)

    def batch_update(self, body):
        self.batches.append(deepcopy(body))
        for request in body['requests']:
            if 'addSheet' in request:
                prop = request['addSheet']['properties']
                self.sheets.append(Sheet(prop['title'], prop['sheetId']))
            elif 'updateSheetProperties' in request:
                prop = request['updateSheetProperties']['properties']
                sheet = next(s for s in self.sheets if s.id == prop['sheetId'])
                sheet.title = prop.get('title', sheet.title)
            elif 'updateCells' in request and 'userEnteredValue' in request['updateCells']['fields']:
                update = request['updateCells']
                start = update['start']
                sheet = next(s for s in self.sheets if s.id == start['sheetId'])
                for index, row in enumerate(update['rows'], start=start.get('rowIndex', 0)):
                    while len(sheet.values) <= index:
                        sheet.values.append([])
                    for col, cell in enumerate(row['values'], start=start.get('columnIndex', 0)):
                        while len(sheet.values[index]) <= col:
                            sheet.values[index].append('')
                        value = cell.get('userEnteredValue', {})
                        sheet.values[index][col] = next(iter(value.values()), '')
        if self.timeout_after_commit:
            self.timeout_after_commit = False
            raise ReadTimeout('Response lost after commit')


def preview(number, rows):
    return {'id': number, 'name': f'preview{number}', 'created': f'2026-10-02T0{number}:00:00+00:00',
            'source': 'Test', 'columns': list(dict.fromkeys(c for row in rows for c in row)), 'rows': rows}


def raw(identity, **extra):
    return dict({'Order Number': identity, 'Product': 'Full Title', 'Task Name': 'Search',
                 'Task Status': 'Available', 'Arrival Time': '10/02/2026 09:00 AM'}, **extra)


class ProductionRulesTests(unittest.TestCase):
    def test_append_keep_missing_and_preserve_manual_fields(self):
        first = preview(1, [raw('A'), raw('B', Product='Current Owner')])
        trackers, _ = merge_trackers(first, None, [[], []])
        trackers[0][0].update(Searcher='Human', Shift='Night', **{'Review/QC': '=A1', 'Status': 'Typing in Progress'})
        second = preview(2, [raw(' a ', **{'Task Status': 'In Progress', 'Comment': 'Updated'}), raw('C')])
        merged, report = merge_trackers(second, first, trackers)
        self.assertEqual([r['Order Number'] for r in merged[0]], ['A', 'C'])
        self.assertEqual(merged[0][0]['Status'], 'Typing in Progress')
        self.assertEqual(merged[0][0]['Searcher'], 'Human')
        self.assertEqual(merged[0][0]['Review/QC'], '=A1')
        self.assertEqual(merged[1], trackers[1])
        self.assertEqual(report['not_in_latest'], ['B'])
        self.assertEqual(report['added'], 1)
        self.assertEqual(report['updated'], 1)
        repeated, again = merge_trackers(second, second, merged)
        self.assertEqual(repeated, merged)
        self.assertEqual(again['updated'], 0)

    def test_new_completed_and_task_suspended_are_not_guessed(self):
        p = preview(1, [raw('A', **{'Task Status': 'Completed and Delivered'}),
                        raw('B', **{'Task Status': 'Task Suspended'}), raw('C', WorkflowSuspended='True')])
        rows, _ = merge_trackers(p, None, [[], []])
        self.assertEqual([r['Status'] for r in rows[0]], ['Search In Progress', 'Search In Progress', 'Awaiting for Clarification'])
        self.assertTrue(all(not r['Out Time'] for r in rows[0]))
        frame, completed = automatic_sync_frame(preview(2, [raw('A')]), p)
        self.assertEqual(len(frame), 1)
        self.assertEqual(completed, [])

    def test_duplicate_inputs_quarantined_and_other_rows_continue(self):
        result, report = merge_trackers(preview(1, [raw('A'), raw(' a '), raw('B'), raw('')]), None, [[], []])
        self.assertEqual([r['Order Number'] for r in result[0]], ['B'])
        self.assertEqual(len(report['unprocessed']), 3)

    def test_sla_anchor_sign_equality_and_ambiguous_values(self):
        anchor = datetime(2026, 10, 2, 12)
        self.assertEqual(expiration('7h 41m', anchor), datetime(2026, 10, 2, 19, 41))
        self.assertEqual(expiration('-1d 4h 0m', anchor), datetime(2026, 10, 1, 8))
        self.assertEqual(expiration('10/02 12:14 PM', anchor), datetime(2026, 10, 2, 12, 14))
        self.assertIsNone(expiration('PAUSED', anchor))
        self.assertEqual(free_site({'Out Time': '10/02/2026 12:14 PM', 'SLA Expiration': '10/02/2026 12:14 PM'})[0], 'On Time')
        self.assertEqual(free_site({'Out Time': '', 'SLA Expiration': '-1h'})[0], '')
        self.assertEqual(free_site({'Out Time': '10/02/2026 12:14 PM', 'SLA Expiration': 'PAUSED'})[0], '')

    def test_sheet_reports_count_all_retained_orders_and_actual_completions(self):
        rows, _ = merge_trackers(preview(1, [raw('A'), raw('B')]), None, [[], []])
        rows[0][0].update(Status='Completed and Delivered', **{'Out Time': '10/02/2026 11:00 AM', 'Free Site': 'On Time'})
        daily = daily_orders(sheet_rows=rows[0])
        monthly = monthly_orders(sheet_rows=rows[0])
        self.assertEqual(sum(r['Today Orders'] for r in daily), 2)
        self.assertEqual(monthly[0]['Completed Orders'], 1)
        self.assertEqual(monthly[0]['SLA On Time'], 1)
        with self.assertRaises(ValueError):
            monthly_orders(PreviewStore)


class AtomicSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lock_patch = patch('sheets_repository.BASE_DIR', self.root)
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)

    def sync(self, book, p):
        frame, _ = automatic_sync_frame(p)
        with patch('datatrace_sync.target_worksheet', return_value=(book, book.sheets[0])):
            sync_production(frame)
        return frame.attrs['pass_report']

    def test_atomic_history_reports_and_idempotent_retry(self):
        book = Book()
        first = preview(1, [raw('A'), raw('B', Product='Current Owner')])
        self.sync(book, first)
        second = preview(2, [raw('A'), raw('C')])
        report = self.sync(book, second)
        before = deepcopy([sheet.values for sheet in book.sheets])
        repeated = self.sync(book, second)
        self.assertEqual(len(book.batches), 2)
        self.assertEqual(before, [sheet.values for sheet in book.sheets])
        self.assertEqual(repeated['added'], 0)
        self.assertEqual(report['not_in_latest'], ['B'])
        self.assertEqual(len(book.worksheet('Overview').get_all_values()) - 1, 3)
        self.assertEqual(len(read_preview_history(book)), 2)
        self.assertEqual([len(p['rows']) for p in read_preview_history(book)], [2, 2])
        self.assertEqual(book.worksheet(TRACKER_TITLES[1]).get_all_values()[1][TRACKER_COLUMNS.index('Status')], 'Search In Progress')

    def test_timeout_after_commit_does_not_replay_sheet_creation(self):
        book = Book()
        book.timeout_after_commit = True
        self.sync(book, preview(1, [raw('A')]))
        self.assertEqual(len(book.batches), 1)
        self.assertEqual(len(book.worksheet(INDEX_TITLE).get_all_values()), 2)

    def test_legacy_tracker_rename_keeps_rows_and_unrelated_tabs(self):
        book = Book()
        book.sheets[1].title = 'Full Title'
        book.sheets[2].title = 'Remaining Products'
        book.sheets.append(Sheet('Escalations', 20, [['Manual'], ['Keep me']]))
        self.sync(book, preview(1, [raw('A')]))
        self.assertEqual(book.worksheet('Escalations').get_all_values(), [['Manual'], ['Keep me']])
        self.assertTrue(all(book.worksheet(title) for title in TRACKER_TITLES))

    def test_existing_manual_cells_never_appear_in_update_requests(self):
        initial, _ = merge_trackers(preview(1, [raw('A')]), None, [[], []])
        initial[0][0].update(Searcher='Human', **{'Review/QC': '=FORMULA()'})
        book = Book(initial)
        self.sync(book, preview(2, [raw('A', Comment='Changed')]))
        tracker_id = book.worksheet(TRACKER_TITLES[0]).id
        for request in book.batches[0]['requests']:
            update = request.get('updateCells', {})
            if update.get('start', {}).get('sheetId') == tracker_id and update.get('start', {}).get('rowIndex') == 1:
                self.assertNotEqual(update['start']['columnIndex'], TRACKER_COLUMNS.index('Searcher'))
                self.assertNotEqual(update['start']['columnIndex'], TRACKER_COLUMNS.index('Review/QC'))

    def test_import_automatically_syncs_and_failure_retains_preview(self):
        syncer = Mock(return_value=['Full Title'])
        app = create_app(self.root / 'previews', syncer=syncer)
        client = app.test_client()
        result = client.post('/api/import', data={'file': (BytesIO(b'Order Number,Product,Task Status\nA,Full Title,Available\n'), 'new.csv')})
        self.assertEqual(result.status_code, 201)
        for _ in range(100):
            if not client.get('/api/state').json['job']['running']:
                break
            time.sleep(.01)
        syncer.assert_called_once()
        self.assertEqual(PreviewStore(self.root / 'previews').pending(), [])

    def test_export_reads_current_tracker_edits_and_applies_colors(self):
        book = Book()
        self.sync(book, preview(1, [raw('A')]))
        values = book.worksheet(TRACKER_TITLES[0]).values
        values[1][TRACKER_COLUMNS.index('Status')] = 'Completed and Delivered'
        values[1][TRACKER_COLUMNS.index('Out Time')] = '10/02/2026 11:00 AM'
        values[1][TRACKER_COLUMNS.index('Free Site')] = 'On Time'
        with patch('server.target_worksheet', return_value=(book, book.sheets[0])):
            response = create_app(self.root / 'previews').test_client().get('/api/export/google-sheets')
        self.assertEqual(response.status_code, 200)
        wb = load_workbook(BytesIO(response.data))
        self.assertNotIn(TRACKER_TITLES[0], wb.sheetnames)
        self.assertEqual(wb['Full Title']['J2'].value, 'Completed and Delivered')
        self.assertEqual(wb['Full Title']['J2'].fill.fgColor.rgb, '00FFF2CC')
        self.assertEqual(wb['Full Title']['W2'].fill.fgColor.rgb, '0000B050')
        self.assertEqual(wb['Full Title']['U2'].value, '10/02/2026 11:00 AM')

    def test_sync_failure_retains_saved_preview_for_retry(self):
        app = create_app(self.root / 'previews', syncer=Mock(side_effect=RuntimeError('Offline')))
        client = app.test_client()
        response = client.post('/api/import', data={'file': (BytesIO(b'Order Number,Product\nA,Full Title\n'), 'new.csv')})
        self.assertEqual(response.status_code, 201)
        for _ in range(100):
            job = client.get('/api/state').json['job']
            if not job['running']:
                break
            time.sleep(.01)
        self.assertIn('Offline', job['result']['error'])
        self.assertEqual(len(PreviewStore(self.root / 'previews').pending()), 1)

    def test_manual_extraction_automatically_syncs_new_capture(self):
        store = PreviewStore(self.root / 'previews')
        def runner(on_progress):
            saved = store.save(pd.DataFrame([raw('A')]))
            return {'preview_id': saved['id'], 'preview_name': saved['name'], 'error': None}
        syncer = Mock(return_value=['Full Title'])
        client = create_app(store.root, runner=runner, syncer=syncer).test_client()
        self.assertEqual(client.post('/api/extract').status_code, 202)
        for _ in range(100):
            job = client.get('/api/state').json['job']
            if not job['running']:
                break
            time.sleep(.01)
        self.assertEqual(job['result']['google_sheet'], 'success')
        syncer.assert_called_once()


if __name__ == '__main__':
    unittest.main()
