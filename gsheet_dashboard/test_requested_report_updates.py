"""Regression coverage for Arrival Time SLA and completion-date capacity counts."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from preview_store import PreviewStore
from sla_status import build_sla_status, preview_snapshot, queue_rule
from status_updates import status_name
from report_workspace import imported_snapshot, read_report_files, capacity_report
from capacity_calculations import capacity_details
from test_capacity_calculations import order
from test_pdf_report_workspace import excel


class RequestedReportUpdatesTests(unittest.TestCase):
    def test_portal_arrival_sets_today_without_changing_capture_countdowns(self):
        rows = [
            {'Order Number': 'latest', 'Arrival Time': '10/22/2026 10:47 PM', 'Task Status': 'Available',
             'SLA Expiration*': '2026-10-22T23:59:00-07:00'},
            {'Order Number': 'older', 'Arrival Time': '10/21/2026 08:00 PM', 'Task Status': 'Available',
             'SLA Expiration*': '2026-10-21T23:59:00-07:00'},
            {'Order Number': 'countdown', 'Arrival Time': '10/20/2026 08:00 PM', 'Task Status': 'Available',
             'SLA Expiration*': '2h'},
        ]
        original = deepcopy(rows)
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            # India is already October 23, while the latest portal arrival is October 22.
            store.restore(1, list(rows[0]), rows, created='2026-10-22T20:00:00+00:00')
            snapshot = preview_snapshot(store)
            report = build_sla_status(snapshot)
        self.assertEqual(report['as_of'], '2026-10-22')
        self.assertEqual(report['date_basis'], 'arrival_time')
        actual = {row['Order Number']: row for row in report['rows']}
        self.assertEqual(actual['latest']['SLA Category'], 'Today SLA')
        self.assertEqual(actual['older']['SLA Category'], 'Negative SLA')
        self.assertEqual(actual['countdown']['SLA Expiration'], '2026-10-23 03:30:00')
        self.assertEqual(rows, original)

    def test_removed_abs_status_merges_automatic_saved_and_custom_groups(self):
        for comments in ('We apologize for the delay', 'ETA 10/22 EOD or sooner', 'Assigned to the abstractor'):
            self.assertEqual(queue_rule({'ETA Comments': comments}, datetime(2026, 10, 22))[1], 'Assign to ABS')
        self.assertEqual(status_name('  NEED TO ASSIGN ABS '), 'Assign to ABS')
        rows = [{'Order Number': name, 'Status': status, 'SLA Expiration': '2026-10-22'}
                for name, status in [('old', 'Need to Assign ABS'), ('new', 'Assign to ABS')]]
        report = build_sla_status({'custom_statuses': ['Need to Assign ABS'],
                                  'sheets': {'Overview': {'rows': rows}}}, datetime(2026, 10, 22))
        self.assertEqual(report['summary'], [{'Status': 'Assign to ABS', 'Today SLA': 2,
                                             'Future SLA': 0, 'Negative SLA': 0, 'Grand Total': 2}])

    def test_uploaded_prior_month_orders_count_on_out_time_and_match_all_drilldowns(self):
        rows = [order('old', 'Completed and Delivered', received='09/30/2026', completed='10/05/2026'),
                order('future', 'Completed and Delivered', received='10/01/2026', completed='11/02/2026'),
                order('pending', 'Assign to ABS', received='10/05/2026')]
        imported = read_report_files([('full.xlsx', excel(rows))])
        before = deepcopy(imported)
        reports = imported_snapshot(imported)['reports']
        report = capacity_report(reports, {'mode': 'excel', 'capacity_month': '2026-10'})
        self.assertEqual([(day['Date'], day['Received'], day['Completed']) for day in report['daily']],
                         [('2026-10-01', 1, 0), ('2026-10-05', 1, 1)])
        for month in report['monthly']:
            detail = capacity_details(reports, month=month['Date'])
            for group in detail['groups']:
                self.assertEqual(len(group['rows']), month[group['label']])
        yearly = capacity_details(reports, year='2026')
        self.assertEqual(yearly['counts']['Received'], 3)
        self.assertEqual(yearly['counts']['Completed'], 2)
        october = capacity_details(reports, month='2026-10')
        completed = next(group['rows'] for group in october['groups'] if group['key'] == 'completed')
        self.assertEqual([row['Order Number'] for row in completed], ['old'])
        self.assertEqual(imported, before)

    def test_empty_year_opens_zero_counts_and_empty_tables(self):
        details = capacity_details({'daily': []}, year='2026')
        self.assertTrue(all(value == 0 for value in details['counts'].values()))
        self.assertTrue(all(not group['rows'] for group in details['groups']))


if __name__ == '__main__':
    unittest.main()
