import unittest
import pandas as pd
from order_reporting import automatic_sync_frame, daily_orders, monthly_orders
from production_rules import merge_trackers
from test_production_sync import preview, raw


class OrderReportingTests(unittest.TestCase):
    def test_queue_exit_keeps_status_and_does_not_invent_out_time(self):
        before = preview(1, [raw('A'), raw('B')])
        after = preview(2, [raw('A')])
        trackers, _ = merge_trackers(before, None, [[], []])
        merged, report = merge_trackers(after, before, trackers)
        self.assertEqual(merged[0][1], trackers[0][1])
        self.assertEqual(report['not_in_latest'], ['B'])
        self.assertEqual(daily_orders(sheet_rows=merged[0])[0]['Completed Orders'], 0)

    def test_preview_preparation_preserves_original_statuses_and_rows(self):
        before = preview(1, [raw('A', **{'Task Status': 'Task Suspended'})])
        after = preview(2, [raw('B', **{'Task Name': 'CRSP2', 'Task Status': 'Available'})])
        frame, completed = automatic_sync_frame(after, before)
        self.assertEqual(completed, [])
        self.assertEqual(frame.to_dict('records'), after['rows'])

    def test_daily_and_monthly_require_google_sheet_data(self):
        for function in (daily_orders, monthly_orders):
            with self.assertRaises(ValueError):
                function()

    def test_unknown_dates_are_included_without_guessing(self):
        rows = [{'Order Number': 'A', 'Date': '', 'Status': 'Search In Progress'}]
        self.assertEqual(daily_orders(sheet_rows=rows)[0]['Date'], 'Undated')
        self.assertEqual(monthly_orders(sheet_rows=rows)[0]['Month Orders'], 1)
