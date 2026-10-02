import unittest
from order_reporting import monthly_orders


class MonthlySlaHistoryTests(unittest.TestCase):
    def test_completions_use_actual_out_time_across_months(self):
        row = {'Order Number': 'A', 'Date': '09/30/2026', 'Status': 'Completed and Delivered',
               'Out Time': '10/01/2026 12:30 PM', 'Free Site': 'On Time'}
        reports = {r['Month']: r for r in monthly_orders(sheet_rows=[row])}
        self.assertEqual(reports['2026-09']['Month Orders'], 1)
        self.assertEqual(reports['2026-09']['SLA On Time'], 0)
        self.assertEqual(reports['2026-10']['Month Orders'], 0)
        self.assertEqual(reports['2026-10']['SLA On Time'], 1)

    def test_live_sheet_values_and_blanks_are_authoritative(self):
        row = {'Order Number': 'A', 'Date': '09/29/2026', 'Out Time': '09/30/2026', 'Free Site': 'Missing'}
        self.assertEqual(monthly_orders(sheet_rows=[row])[0]['SLA Missed'], 1)
        row['Free Site'] = 'On Time'
        self.assertEqual(monthly_orders(sheet_rows=[row])[0]['SLA On Time'], 1)
        row['Free Site'] = ''
        self.assertEqual(monthly_orders(sheet_rows=[row])[0]['sla_rows'], [])

    def test_duplicate_tracker_orders_are_reported(self):
        with self.assertRaises(ValueError):
            monthly_orders(sheet_rows=[{'Order Number': 'A'}, {'Order Number': ' a '}])
