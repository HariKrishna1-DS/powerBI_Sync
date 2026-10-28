"""Tracker receipts, status drilldowns, freshness and conflict recovery."""
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
import os
from unittest.mock import Mock, patch

from monthly_production import tab_name
from order_reporting import automatic_sync_frame
from preview_store import PreviewStore
from report_workspace import capacity_report
from server import create_app, sync_retry_delay
from test_tracker_v2 import Book
from tracker_sync import FULL, REMAINING, HEADERS, sheet_reports, sync_trackers, records


def row(number, status='Search In Progress', **extra):
    return {'Order Number': number, 'Product': 'Full Title', 'Status': status,
            'In-Time': '10/22/2026 09:00 AM', **extra}


class TrackerReportConsistencyTests(unittest.TestCase):
    def test_catchup_keeps_trackers_and_archive_without_intermediate_report_copies(self):
        with tempfile.TemporaryDirectory() as folder, patch('tracker_sync.load_defaults', return_value={FULL: [], REMAINING: []}), patch('tracker_formatting.ensure_tracker_formatting') as formatting:
            store = PreviewStore(Path(folder) / 'previews')
            columns = ['Order Number', 'Product', 'Arrival Time', 'Task Name', 'Task Status']
            first = {'Order Number': 'A', 'Product': 'Full Title', 'Arrival Time': '10/22/2026 09:00 AM',
                     'Task Name': 'Search', 'Task Status': 'Available'}
            store.restore(1, columns, [first], created='2026-10-22T04:30:00+00:00')
            store.restore(2, columns, [dict(first, **{'Order Number': 'B'})], created='2026-10-22T05:30:00+00:00')
            book = Book()
            frame, _ = automatic_sync_frame(store.get(1), store=store)
            frame.attrs['defer_report_views'] = True
            sync_trackers(frame, book=book)
            formatting.assert_not_called()
            self.assertEqual({sheet.title for sheet in book.worksheets()}, {FULL, REMAINING, 'Sheet1'})
            self.assertEqual(records(book.worksheet('Sheet1').get_all_values())[0]['Order Number'], 'A')
            frame, _ = automatic_sync_frame(store.get(2), store=store)
            sync_trackers(frame, book=book)
            formatting.assert_called_once_with(book)
            self.assertTrue({'Status Report', 'Monthly Orders', 'PR Excel'} <= {sheet.title for sheet in book.worksheets()})
            self.assertEqual({row['Preview'] for row in records(book.worksheet('Sheet1').get_all_values())}, {'preview1', 'preview2'})
            self.assertEqual({row['Order Number'] for row in records(book.worksheet(FULL).get_all_values())}, {'A', 'B'})

    def test_sheet_quota_retry_waits_for_the_per_minute_window(self):
        self.assertEqual(sync_retry_delay(RuntimeError('Google Sheets returned HTTP 429'), 0), 60)
        self.assertEqual(sync_retry_delay(RuntimeError('Quota exceeded for read requests'), 1), 60)
        self.assertEqual(sync_retry_delay(RuntimeError('Temporary network error'), 1), 2)

    def test_archived_copy_is_not_a_second_daily_or_capacity_receipt(self):
        archive = row('A', 'Search In Progress', **{'In-Time': '09/30/2026 09:00 AM'})
        active = dict(archive, Status='Completed and Delivered', **{'Out Time': '10/22/2026 10:00 AM'})
        trackers = {tab_name(FULL, '2026-09'): [archive], tab_name(FULL, '2026-10'): [active, row('B')]}
        before = deepcopy(trackers)
        reports = sheet_reports(trackers)
        self.assertEqual(sum(day['Received'] for day in reports['daily']), 2)
        september = next(day for day in reports['daily'] if day['Date'] == '2026-09-30')
        self.assertEqual(september['Completed'], 1)
        self.assertEqual(len(september['rows']), 1)
        # Monthly ownership preserves the historical archive and active month.
        self.assertEqual({period['Month']: period['Month Orders'] for period in reports['monthly']},
                         {'2026-09': 1, '2026-10': 2})
        capacity = capacity_report(reports, {'mode': 'tracker', 'capacity_month': '2026-10'})
        self.assertEqual(sum(month['Received'] for month in capacity['monthly']), 2)
        self.assertEqual(sum(month['Completed'] for month in capacity['monthly']), 1)
        self.assertEqual(trackers, before)

    def test_status_counts_partition_the_same_rows_with_spaces_and_task_status_fallback(self):
        rows = [row('done', '  COMPLETED  AND DELIVERED  '),
                row('clarify', '', **{'Task Status': ' Awaiting   for Clarification '}),
                row('vendor', ' Assign  to ABS '), row('cancelled', 'Canceled'), row('pending')]
        reports = sheet_reports({FULL: rows})
        for kind in ('daily', 'monthly'):
            period = reports[kind][0]
            self.assertEqual([period[name] for name in ('Received', 'Completed', 'Clarification', 'Cancelled',
                                                        'Vendor Pending', 'In-House Pending')], [5, 1, 1, 1, 1, 1])
            self.assertEqual(period['completed_keys'], ['done'])
            self.assertEqual(period['Awaiting for Clarification'], 1)
        capacity = capacity_report(reports, {'mode': 'tracker', 'capacity_month': '2026-10'})
        self.assertEqual([capacity['daily'][0][name] for name in ('Received', 'Completed', 'Clarification',
                                                                 'Cancelled', 'Vendor Pending', 'In-House Pending')],
                         [5, 1, 1, 1, 1, 1])

    def test_tracker_apis_expose_pending_captures_without_presenting_them_as_synced(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            store.restore(1, ['Order Number'], [{'Order Number': 'saved'}], created='2026-10-22T03:30:00+00:00')
            book = Book()
            book.add_worksheet(FULL, 10, len(HEADERS)).values = [HEADERS, [row('cloud').get(c, '') for c in HEADERS]]
            book.add_worksheet(REMAINING, 10, len(HEADERS)).values = [HEADERS]
            with patch('server.target_worksheet', return_value=(book, None)):
                app = create_app(store.root)
                app.extensions['refresh_imported_reports'] = lambda **kwargs: {'changed': False}
                client = app.test_client()
                for endpoint in ('/api/live-sheets', '/api/daily-orders', '/api/monthly-orders'):
                    response = client.get(endpoint)
                    self.assertEqual(response.status_code, 200, response.json)
                    self.assertEqual(response.json['pending_sync'], 1)
                    self.assertEqual(response.json['latest_capture_at'], '2026-10-22T03:30:00+00:00')
                    self.assertIsNone(response.json['latest_synced_capture_at'])
                capacity = client.get('/api/capacity-report').json
                self.assertEqual(capacity['source'], 'Imported Excel')
                self.assertEqual(capacity['daily'], [])
                self.assertNotIn('pending_sync', capacity)

    def test_old_offline_cache_rebuilds_reports_from_saved_tracker_rows(self):
        rows = [row('A', 'QC in Progress', **{'Out Time': '10/22/2026 10:00 AM'}), row('B')]
        cached = {'sheets': {FULL: {'columns': HEADERS, 'rows': rows},
                             'Overview': {'columns': HEADERS, 'rows': rows},
                             'Full Title': {'columns': HEADERS, 'rows': rows},
                             'Remaining Products': {'columns': HEADERS, 'rows': []}},
                  'reports': {'daily': [{'Date': '2026-10-16', 'Received': 999}], 'monthly': []},
                  'offline': True, 'source': 'Saved Google Sheets copy'}
        for legacy in (cached, dict(cached, sheets={'Overview': cached['sheets']['Overview']})):
            with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {
                    'DATATRACE_DESKTOP': '1', 'DATATRACE_DESKTOP_TOKEN': 'test-only-token'}):
                app = create_app(Path(folder) / 'previews')
                app.extensions['refresh_imported_reports'] = lambda **kwargs: {'changed': False}
                with patch.object(app.extensions['production_cache'], 'get', return_value=deepcopy(legacy)):
                    response = app.test_client().get('/api/daily-orders', headers={'X-DataTrace-Token': 'test-only-token'})
                    overview = app.test_client().get('/api/live-sheets', headers={'X-DataTrace-Token': 'test-only-token'})
                self.assertEqual(response.status_code, 200, response.json)
                self.assertEqual([(day['Date'], day['Received'], day['Completed']) for day in response.json['rows']],
                                 [('2026-10-22', 2, 1)])
                self.assertTrue(response.json['offline'])
                self.assertEqual(overview.json['sheets']['Overview']['rows'][0]['Status'], 'Completed and Delivered')

    def test_capture_sync_keeps_imported_source_and_capacity_separate(self):
        from report_workspace import ReportWorkspace, imported_snapshot, read_report_files
        from test_pdf_report_workspace import excel
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            imported = read_report_files([('full.xlsx', excel([row('same', 'Search In Progress')]))])
            workspace = ReportWorkspace(store)
            workspace.save(mode='excel', imported=imported, enabled=True, cloud_reset=True)
            store.restore(1, ['Order Number', 'Product', 'Task Status'],
                          [{'Order Number': 'same', 'Product': 'Full Title', 'Task Status': 'Available'}],
                          created='2026-10-20T10:00:00+00:00')
            before = deepcopy(workspace.read()['imported'])
            with patch('server.target_worksheet', return_value=(Book(), None)), patch('server.sync_workbook', return_value=[FULL, REMAINING]) as sync:
                app = create_app(store.root)
                publish = Mock()
                app.extensions['publish_active_reports'] = publish
                client = app.test_client()
                response = client.post('/api/sync', json={'preview': 1})
                self.assertEqual(response.status_code, 202, response.json)
                until = time.monotonic() + 10
                while time.monotonic() < until:
                    state = client.get('/api/state?light=1').json
                    if not state['job']['running']:
                        break
                    time.sleep(.02)
                self.assertFalse(state['job']['running'])
                self.assertEqual(state['job']['stage'], 'Finished')
                self.assertTrue(sync.call_args.args[0].attrs['defer_report_views'])
                publish.assert_not_called()
                self.assertEqual(workspace.read()['imported'], before)
                self.assertEqual(imported_snapshot(before)['reports']['daily'][0]['Completed'], 0)
                app.extensions['stop_scheduler'].set()

    def test_manual_sync_recovers_conflicting_suffix_and_drains_it_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            for number in range(1, 8):
                store.restore(number, ['Order Number', 'Product'],
                              [{'Order Number': f'local-{number}', 'Product': 'Full Title'}],
                              created=f'2026-10-{number+10:02}T03:30:00+00:00')
                if number < 4:
                    store.mark_synced(number)
            store.mark_failed(4, 'This preview name already identifies a different saved snapshot.')
            original = {number: store.get(number)['rows'] for number in range(4, 8)}
            book = Book()
            book.add_worksheet('Sheet1', 10, 3).values = [['Preview', 'Order Number', 'Product']] + [
                [f'preview{number}', f'cloud-{number}', 'Full Title'] for number in range(1, 9)]
            calls = []

            def sync(frame, **kwargs):
                calls.append(frame.attrs['preview_id'])
                self.assertTrue(frame.attrs.get('defer_report_views'))
                self.assertEqual(frame.to_dict('records'), original[frame.attrs['preview_id'] - 5])
                return [FULL, REMAINING]

            with patch('server.target_worksheet', return_value=(book, None)), patch('server.sync_workbook', side_effect=sync):
                app = create_app(store.root)
                publish = Mock(return_value={'synced': True})
                app.extensions['publish_active_reports'] = publish
                client = app.test_client()
                response = client.post('/api/sync', json={'preview': 7, 'previous': 6})
                self.assertEqual(response.status_code, 202)
                until = time.monotonic() + 10
                while time.monotonic() < until:
                    state = client.get('/api/state?light=1').json
                    if not state['job']['running']:
                        break
                    time.sleep(.02)
                else:
                    self.fail('Sync did not finish')
                self.assertEqual(calls, [9, 10, 11, 12])
                self.assertEqual(store.unsynced_ids(), [])
                self.assertEqual(store.failed_syncs(), [])
                self.assertEqual(state['job']['result']['preview_id'], 12)
                self.assertEqual(state['job']['result']['previous_id'], 11)
                self.assertTrue(list((store.root.parent / 'backups').glob('*.zip')))
                publish.assert_called_once()
                app.extensions['stop_scheduler'].set()


if __name__ == '__main__':
    unittest.main()
