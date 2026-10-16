from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from flask import Flask
from capacity_calculations import capacity_details
from order_details import editor_details, recorded_changes
from preview_store import PreviewStore
from report_workspace import ReportWorkspace, capacity_report, imported_snapshot, register_report_routes
from test_capacity_calculations import order
from test_order_status_updates import StatusBook
from tracker_sync import FULL


class ReportDateDetailsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = ReportWorkspace(PreviewStore(Path(self.folder.name) / 'previews'))
        self.rows = [order('A', 'Awaiting for Clarification', received='09/30/2026 09:00 AM'),
                     order('B', 'Assign to ABS', received='09/30/2026 10:00 AM'),
                     order('C', 'Completed and Delivered', received='10/02/2026 09:00 AM', completed='10/04/2026 01:00 PM'),
                     order('E', 'Completed and Delivered', received='10/05/2026 09:00 AM', completed='10/05/2026 10:00 AM'),
                     order('D', received='10/02/2026 10:00 AM')]
        self.workspace.save(mode='excel', cloud_reset=True, imported={
            'rows': self.rows, 'columns': list(self.rows[0]), 'files': [], 'created': '2026-10-14'})
        self.book = None
        self.app = Flask(__name__)
        register_report_routes(self.app, self.workspace, threading.Lock(), self.snapshot, lambda: (self.book, None), lambda: None)
        self.client = self.app.test_client()

    def snapshot(self, **kwargs):
        if self.workspace.read()['mode'] == 'excel':
            return imported_snapshot(self.workspace.read()['imported'])
        from status_updates import tracker_state
        owners, _ = tracker_state(self.book)
        rows = [dict(items[0][3], _sheet=items[0][0].title) for items in owners.values()]
        return imported_snapshot({'rows': rows, 'columns': list(rows[0]), 'files': [], 'created': '2026-10-14'})

    def editor(self, number='D'):
        mode = self.workspace.read()['mode']
        result = self.client.get('/api/order-details', query_string={'order': number, 'mode': mode})
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def save(self, editor, changes, report_date='2026-10-02'):
        with patch('threading.Thread.start'):
            return self.client.post('/api/order-details', json={'order_number': editor['order']['Order Number'],
                'month': editor['month'], 'mode': editor['mode'], 'version': editor['version'],
                'report_date': report_date, 'changes': changes})

    def test_capacity_groups_reconcile_with_summary_and_next_available_dates(self):
        reports = self.snapshot()['reports']
        original = deepcopy(reports)
        details = capacity_details(reports, '2026-10-02')
        groups = {group['key']: group['rows'] for group in details['groups']}
        self.assertEqual(details['previous_date'], '2026-09-30')
        self.assertEqual(details['next_date'], '2026-10-05')
        self.assertEqual(len(groups['received']), details['counts']['Received'])
        self.assertEqual(len(groups['received']), 4)
        self.assertEqual({row['Order Number'] for row in groups['rollover']}, {'A', 'B'})
        self.assertEqual([row['Order Number'] for row in groups['completed']], ['C'])
        self.assertEqual([row['Order Number'] for row in groups['next_added']], ['E'])
        self.assertEqual([row['Order Number'] for row in groups['next_completed']], ['E'])
        final = capacity_details(reports, '2026-10-05')
        self.assertIsNone(final['next_date'])
        self.assertEqual(len(next(group['rows'] for group in final['groups'] if group['key'] == 'completed')), 1)
        self.assertEqual(reports, original)

    def test_date_reads_preserve_workspace_and_daily_returns_all_source_columns(self):
        before = self.workspace.read()
        capacity = self.client.get('/api/capacity-report/details?date=2026-10-02')
        daily = self.client.get('/api/daily-orders/details?date=2026-10-02')
        self.assertEqual(capacity.status_code, 200)
        self.assertEqual(daily.status_code, 200)
        self.assertEqual([row['Order Number'] for row in daily.json['groups'][0]['rows']], ['C', 'D'])
        self.assertIn('Out Time', daily.json['columns'])
        self.assertEqual(self.workspace.read(), before)
        self.assertEqual(self.client.get('/api/capacity-report/details?date=bad').status_code, 400)
        self.assertEqual(self.client.get('/api/capacity-report/details?date=2026-10-31').status_code, 404)

    def test_month_popup_returns_daily_dates_and_editable_orders_without_changing_live_month(self):
        imported=deepcopy(self.workspace.read()['imported'])
        imported['rows'] += [order('August',received='08/20/2026'),order('September weekend',received='09/26/2026')]
        self.workspace.save(imported=imported)
        before=self.workspace.read()
        for month,dates in [('2026-08',['2026-08-20']),('2026-09',['2026-09-25','2026-09-30'])]:
            result=self.client.get('/api/capacity-report/details',query_string={'month':month})
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual([row['Date'] for row in result.json['daily']],dates)
            self.assertEqual(result.json['date'],dates[0])
            self.assertTrue(result.json['groups'][0]['rows'])
        second=self.client.get('/api/capacity-report/details?month=2026-09&date=2026-09-30')
        self.assertEqual(second.json['date'],'2026-09-30')
        self.assertEqual(self.workspace.read(),before)
        saved=self.save(self.editor('September weekend'),{'Status':'Cancelled'},report_date='2026-09-25')
        self.assertEqual(saved.status_code,200,saved.json)
        refreshed=self.client.get('/api/capacity-report/details?month=2026-09&date=2026-09-25')
        self.assertEqual(refreshed.json['groups'][0]['rows'][0]['Status'],'Cancelled')
        self.assertEqual(len(refreshed.json['groups'][-1]['rows']),1)
        self.assertEqual(self.client.get('/api/capacity-report/details?month=2026-13').status_code,400)
        self.assertEqual(self.client.get('/api/capacity-report/details?month=2026-09&date=2026-10-02').status_code,400)
        empty=self.client.get('/api/capacity-report/details?month=2026-07')
        self.assertEqual(empty.status_code,200)
        self.assertEqual(empty.json['daily'],[])

    def test_edit_updates_actual_completion_counts_and_records_before_after(self):
        editor = self.editor()
        result = self.save(editor, {'Status': 'Completed and Delivered', 'Out Time': '10/04/2026 02:00 PM'})
        self.assertEqual(result.status_code, 200, result.json)
        self.assertTrue(result.json['publication']['queued'])
        self.assertTrue((Path(self.folder.name) / 'backups' / result.json['recovery_backup']).exists())
        report = capacity_report(self.snapshot()['reports'], self.workspace.read())
        self.assertEqual(next(day['Completed'] for day in report['daily'] if day['Date'] == '2026-10-02'), 2)
        history = recorded_changes(self.workspace, 'excel', '2026-10-02')
        self.assertEqual({row['Column'] for row in history}, {'Status', 'Out Time'})
        status = next(row for row in history if row['Column'] == 'Status')
        self.assertEqual(status['Previous Value'], 'QC in Progress')
        self.assertEqual(status['New Value'], 'Completed and Delivered')
        self.assertEqual(recorded_changes(self.workspace, 'tracker', '2026-10-02'), [])

    def test_stale_source_switch_and_invalid_fields_cannot_overwrite_orders(self):
        editor = self.editor()
        for changes in ({'Order Number': 'other'}, {'Out Time': 'not a date'}, {'Status': ''}):
            self.assertEqual(self.save(editor, changes).status_code, 409)
        changed = deepcopy(self.workspace.read()['imported'])
        changed['rows'][-1]['Status'] = 'Cancelled'
        self.workspace.save(imported=changed)
        stale = self.save(editor, {'Status': 'Search In Progress'})
        self.assertEqual(stale.status_code, 409)
        self.assertIn('changed since', stale.json['error'])
        self.workspace.save(mode='tracker')
        result = self.save(editor, {'Status': 'Search In Progress'})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.workspace.read()['imported']['rows'][-1]['Status'], 'Cancelled')

    def test_tracker_edit_preserves_physical_rows_and_writes_only_selected_owner(self):
        row = dict(self.rows[-1], Product='Full Title', **{'Free Site': ''})
        self.book = StatusBook([row])
        for sheet in self.book.sheets:
            sheet.values[0].append('Out Time')
            for cells in sheet.values[1:]:
                cells.append('')
        self.book.worksheet(FULL).values.insert(1, [''] * len(self.book.worksheet(FULL).values[0]))
        self.workspace.save(mode='tracker')
        editor = self.editor()
        result = self.save(editor, {'Status': 'Completed and Delivered', 'Out Time': '10/04/2026 02:00 PM'})
        self.assertEqual(result.status_code, 200, result.json)
        values = self.book.worksheet(FULL).values
        self.assertEqual(values[1], [''] * len(values[0]))
        self.assertEqual(values[2][values[0].index('Status')], 'Completed and Delivered')
        self.assertEqual(values[2][values[0].index('Out Time')], '10/04/2026 02:00 PM')
        self.assertTrue(list((Path(self.folder.name) / 'backups' / 'reports').glob('order-edit-*.json.gz')))
        self.assertEqual(len(recorded_changes(self.workspace, 'tracker', '2026-10-02')), 2)

    def test_editor_finds_archived_orders_outside_the_current_overview(self):
        archived = dict(self.rows[0], _month='2026-09', _sheet='September tracker')
        snapshot = {'mode': 'tracker', 'sheets': {'Overview': {'columns': ['Order Number', 'Status', 'Missing column'], 'rows': []}},
                    'reports': {'daily': [{'Date': '2026-09-30', 'rows': [archived]}]}}
        result = editor_details(snapshot, {'mode': 'tracker'}, 'A', '2026-09')
        self.assertEqual(result['order']['Order Number'], 'A')
        self.assertNotIn('Missing column', result['editable_columns'])
        self.assertNotIn('Order Number', result['editable_columns'])

    def test_failed_backup_cannot_change_the_imported_order(self):
        before = deepcopy(self.workspace.read()['imported'])
        with patch('workspace_backup.save_safety_backup', side_effect=OSError('Disk full')):
            self.app.config['TESTING'] = True
            with self.assertRaisesRegex(OSError, 'Disk full'):
                self.save(self.editor(), {'Status': 'Cancelled'})
        self.assertEqual(self.workspace.read()['imported'], before)
        self.assertEqual(recorded_changes(self.workspace, 'excel', '2026-10-02'), [])

    def test_sheet_change_detection_dates_use_india_time(self):
        import json
        event = {'Changed At': '2026-10-01T20:30:00+00:00', 'Order Number': 'D', 'Change': 'Updated',
                 'Column': 'Status', 'Previous Value': 'QC in Progress', 'New Value': 'Cancelled', 'After': self.rows[-1]}
        with self.workspace.store.connect() as db:
            db.execute('INSERT INTO import_excel_changes(action,order_number,payload) VALUES (?,?,?)', ('Updated', 'D', json.dumps(event)))
        self.assertEqual(len(recorded_changes(self.workspace, 'excel', '2026-10-02')), 1)
        self.assertEqual(recorded_changes(self.workspace, 'excel', '2026-10-01'), [])

    def test_moving_the_last_order_off_a_date_keeps_its_change_history_visible(self):
        imported = deepcopy(self.workspace.read()['imported'])
        imported['rows'] = [self.rows[-1]]
        self.workspace.save(imported=imported)
        result = self.save(self.editor(), {'In-Time': '10/05/2026 10:00 AM'})
        self.assertEqual(result.status_code, 200, result.json)
        for endpoint in ('capacity-report', 'daily-orders'):
            details = self.client.get(f'/api/{endpoint}/details?date=2026-10-02')
            self.assertEqual(details.status_code, 200, details.json)
            groups = {group['key']: group['rows'] for group in details.json['groups']}
            self.assertEqual(groups['received'], [])
            self.assertEqual(len(groups['changes']), 1)


if __name__ == '__main__':
    unittest.main()
