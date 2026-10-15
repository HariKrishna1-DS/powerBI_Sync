"""Selected report sources must never inherit historical cloud orders."""
from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from preview_store import PreviewStore
from preview_reporting import build_preview_snapshot, PreviewReports
from report_workspace import ReportWorkspace
from server import create_app


def capture(number, identities, hour=9):
    rows = [{'Order Number': identity, 'Product': 'Full Title', 'Task Name': 'Search',
             'Task Status': 'Available', 'Arrival Time': '10/05/2026 08:00 AM',
             'SLA Expiration*': '2h', 'Borrower': 'Example', 'St': 'IL'} for identity in identities]
    return {'id': number, 'name': f'preview{number}', 'created': f'2026-10-05T{hour:02}:00:00+05:30',
            'columns': list(rows[0]) if rows else ['Order Number'], 'rows': rows}


class PreviewReportingTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = PreviewStore(Path(folder.name) / 'previews')
        self.workspace = ReportWorkspace(self.store)
        threads = patch('threading.Thread.start')
        threads.start()
        self.addCleanup(threads.stop)

    def restore(self, data):
        return self.store.restore(data['id'], data['columns'], data['rows'], created=data['created'])

    def test_union_uses_latest_capture_state_and_preserves_raw_details(self):
        first, second = capture(1, ['A', 'B']), capture(2, ['B', 'C'], 10)
        second['rows'][0].update({'Task Name': 'Typing', 'Task Status': 'Completed', 'Borrower': 'Changed'})
        before = deepcopy([first, second])
        snapshot = build_preview_snapshot([first, second])
        rows = {row['Order Number']: row for row in snapshot['sheets']['Overview']['rows']}
        self.assertEqual(set(rows), {'A', 'B', 'C'})
        self.assertEqual(snapshot['preview_count'], 2)
        self.assertEqual(snapshot['source'], 'Saved previews')
        self.assertEqual(rows['B']['Borrower'], 'Changed')
        self.assertEqual(rows['B']['State'], 'IL')
        self.assertEqual(rows['B']['First preview'], 'preview1')
        self.assertEqual(rows['B']['Latest preview'], 'preview2')
        self.assertNotEqual(rows['B']['Status'], 'Completed and Delivered')
        self.assertEqual(rows['A']['Status'], 'Completed and Delivered')
        self.assertEqual(rows['A']['Out Time'], '10/05/2026 10:00:00 AM')
        self.assertEqual(rows['A']['Free Site'], 'On Time')
        self.assertEqual(sum(day['Today Orders'] for day in snapshot['reports']['daily']), 3)
        self.assertEqual(sum(len(month['rows']) for month in snapshot['reports']['monthly']), 3)
        self.assertEqual([first, second], before)

    def test_empty_history_is_empty_and_missing_product_does_not_drop_order(self):
        empty = build_preview_snapshot([])
        self.assertEqual(empty['sheets']['Overview']['rows'], [])
        self.assertEqual(empty['reports']['daily'], [])
        data = capture(1, ['A'])
        data['rows'][0].pop('Product')
        self.assertEqual(len(build_preview_snapshot([data])['sheets']['Overview']['rows']), 1)

    def test_reappearance_and_repeated_absence_use_the_correct_capture_timestamp(self):
        history = [capture(1, ['A', 'B']), capture(2, ['B'], 10),
                   capture(3, ['A', 'B'], 11), capture(4, ['B'], 12), capture(5, ['B'], 13)]
        reopened = build_preview_snapshot(history[:3])['sheets']['Overview']['rows']
        self.assertEqual(next(row for row in reopened if row['Order Number'] == 'A')['Out Time'], '')
        final = build_preview_snapshot(history)['sheets']['Overview']['rows']
        self.assertEqual(next(row for row in final if row['Order Number'] == 'A')['Out Time'], '10/05/2026 12:00:00 PM')

    def test_revision_follows_capture_addition_deletion_and_local_edits(self):
        cache = PreviewReports(self.store)
        first = cache.get(self.workspace.read())
        self.restore(capture(1, ['A']))
        second = cache.get(self.workspace.read(), first['revision'])
        self.assertNotIn('unchanged', second)
        self.assertTrue(cache.get(self.workspace.read(), second['revision'])['unchanged'])
        self.workspace.save(preview_edits={'a': {'Comments': 'Local edit'}})
        third = cache.get(self.workspace.read())
        self.assertNotEqual(second['revision'], third['revision'])
        self.assertEqual(third['sheets']['Overview']['rows'][0]['Comments'], 'Local edit')
        self.assertNotIn('preview_edits', self.workspace.public())
        self.store.delete(1)
        self.assertEqual(cache.get(self.workspace.read())['sheets']['Overview']['rows'], [])

    def test_upgrade_restores_imported_orders_and_excludes_old_cloud_additions(self):
        from report_workspace import combine_sources
        source = {'name': 'full.xlsx', 'rows': [{'Order Number': number, 'Product': 'Full Title'} for number in ('A', 'B')],
                  'columns': ['Order Number', 'Product'], 'files': [{'file': 'full.xlsx', 'sheet': 'TV Orders', 'rows': 2}], 'reviews': []}
        imported = combine_sources([source])
        first = dict(imported['rows'][0], Comments='Keep my edit')
        imported['rows'] = [first, dict(first, **{'Order Number': 'CLOUD-ONLY'})]
        self.workspace.save(mode='excel', imported=imported)
        upgraded = ReportWorkspace(self.store).read()
        self.assertEqual({row['Order Number'] for row in upgraded['imported']['rows']}, {'A', 'B'})
        self.assertEqual(upgraded['imported']['rows'][0]['Comments'], 'Keep my edit')
        self.assertEqual(upgraded['row_count'], 2)
        self.assertTrue(list((self.store.root.parent / 'backups').glob('*.zip')))

    def test_all_report_reads_and_refresh_stay_local_in_both_modes(self):
        self.restore(capture(1, ['PREVIEW']))
        app = create_app(self.store.root)
        self.addCleanup(app.extensions['stop_scheduler'].set)
        client = app.test_client()
        imported = {'rows': [{'Order Number': 'EXCEL', 'Product': 'Update', 'Status': 'Search In Progress',
                             'Date': '10/06/2026'}], 'columns': ['Order Number', 'Product', 'Status', 'Date'], 'files': [], 'created': '2026-10-06'}
        with patch('server.target_worksheet', side_effect=AssertionError('Cloud reads must not supply report orders')) as cloud:
            for mode, expected in [('tracker', 'PREVIEW'), ('excel', 'EXCEL'), ('tracker', 'PREVIEW')]:
                self.workspace.save(mode=mode, imported=imported, enabled=False)
                response = client.get('/api/live-sheets')
                self.assertEqual(response.status_code, 200, response.json)
                snapshot = response.json
                self.assertEqual([row['Order Number'] for row in snapshot['sheets']['Overview']['rows']], [expected])
                for endpoint in ('/api/daily-orders', '/api/monthly-orders', '/api/capacity-report', '/api/sla-status'):
                    response = client.get(endpoint)
                    self.assertEqual(response.status_code, 200, (endpoint, response.json))
                    self.assertNotIn('6947', response.get_data(as_text=True))
                self.assertEqual(client.post('/api/report-refresh').status_code, 200)
            cloud.assert_not_called()

    def test_preview_order_edits_do_not_modify_capture_or_import(self):
        self.restore(capture(1, ['A']))
        self.workspace.save(enabled=False, imported={'rows': [{'Order Number': 'EXCEL'}], 'columns': []})
        app = create_app(self.store.root)
        self.addCleanup(app.extensions['stop_scheduler'].set)
        client = app.test_client()
        original = self.store.get(1)
        response = client.get('/api/order-details?order=A&mode=tracker')
        self.assertEqual(response.status_code, 200, response.json)
        editor = response.json
        result = client.post('/api/order-details', json={'order_number': 'A', 'mode': 'tracker',
            'version': editor['version'], 'month': editor['month'], 'report_date': '2026-10-05',
            'changes': {'Status': 'Awaiting for Clarification', 'Comments': 'Needs review'}})
        self.assertEqual(result.status_code, 200, result.json)
        row = client.get('/api/live-sheets').json['sheets']['Overview']['rows'][0]
        self.assertEqual(row['Status'], 'Awaiting for Clarification')
        self.assertEqual(row['Comments'], 'Needs review')
        self.assertEqual(self.store.get(1), original)
        self.assertEqual(self.workspace.read()['imported']['rows'], [{'Order Number': 'EXCEL'}])

    def test_sla_correction_remains_in_preview_reports_and_raw_history_is_immutable(self):
        self.restore(capture(1, ['A', 'B']))
        self.restore(capture(2, ['B'], 10))
        self.workspace.save(enabled=False)
        app = create_app(self.store.root)
        self.addCleanup(app.extensions['stop_scheduler'].set)
        client = app.test_client()
        original = self.store.history()
        result = client.post('/api/sla-comments', json={'order_number': 'A', 'completion_date': '2026-10-05',
            'status': 'Missing', 'expected_status': 'On Time'})
        self.assertEqual(result.status_code, 200, result.json)
        monthly = client.get('/api/monthly-orders').json['rows'][0]
        self.assertEqual(monthly['SLA Missed'], 1)
        self.assertEqual(self.store.history(), original)


if __name__ == '__main__':
    unittest.main()
