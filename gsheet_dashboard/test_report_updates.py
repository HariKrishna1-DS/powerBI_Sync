import tempfile
import unittest
from pathlib import Path

import pandas as pd

from datatrace_sync import report_frames, sla_result
from order_reporting import daily_orders, monthly_orders
from preview_store import PreviewStore


class ReportUpdatesTests(unittest.TestCase):
    def test_sla_rules(self):
        row = {'Arrival Time': '09/25/2026 09:35 AM', 'Out Time': '2026-09-28'}
        for sla, expected in [('09/29 01:34 PM', 'On Time'),
                              ('09/27 01:34 PM', 'Missed'),
                              ('6h 6m', 'On Time'), ('-2d 3h', 'Missed'),
                              ('09/28/2026', 'Missed'), ('invalid', 'Missed')]:
            with self.subTest(sla=sla):
                self.assertEqual(sla_result(dict(row, **{'SLA Expiration*': sla})), expected)
        self.assertEqual(sla_result({'Out Time': '', 'SLA Expiration*': '-2d'}), '')
        self.assertEqual(sla_result({'Arrival Time': '12/31/2026', 'Out Time': '01/01/2027',
                                     'SLA Expiration*': '01/02 01:00 PM'}), 'On Time')

    def test_product_dates_and_free_site(self):
        frame = pd.DataFrame([{'Product': product, 'Arrival Time': '09/25/2026 09:35 AM',
                               'Arrival Date': '2026-09-25', 'Out Time': '2026-09-28',
                               'SLA Expiration*': '09/29 01:34 PM'}
                              for product in ['Full Title', 'Current Owner']])
        for report in report_frames(frame)[1:]:
            self.assertEqual(report.iloc[0]['Out Time'], '09/28/2026')
            self.assertEqual(report.iloc[0]['Date'], '09/25/2026')
            self.assertEqual(report.iloc[0]['SLA Expiration'], '09/29/2026 01:34 PM')
            self.assertEqual(report.iloc[0]['Free Site'], 'On Time')

    def test_preview_cutoff_and_sheet_sla_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder))
            first = store.save(pd.DataFrame([{'Order Number': '1', 'Task Status': 'Available',
                                             'Arrival Time': '09/29/2026 10:00 AM'}]))
            store.save(pd.DataFrame([{'Order Number': '2', 'Task Status': 'Available',
                                     'Arrival Time': '09/29/2026 11:00 AM'}]))
            report = daily_orders(store, first['id'])[0]
            self.assertEqual(report['Previews'], [first['name']])
            self.assertEqual(report['missing_ids'], [])
            self.assertEqual([r['Order Number'] for r in report['rows']], ['1'])
            sheet_rows = [{'Out Time': '09/29/2026', 'Free Site': 'On time'},
                          {'Out Time': '09/30/2026', 'Free Site': 'Missed'},
                          {'Out Time': '', 'Free Site': 'Missed'},
                          {'Out Time': '10/01/2026', 'Free Site': 'Missed'}]
            report = monthly_orders(store, sheet_rows)[0]
            self.assertEqual(report['SLA On Time'], 1)
            self.assertEqual(report['SLA Missed'], 2)
            self.assertEqual(report['Completed Orders'], 1)


if __name__ == '__main__':
    unittest.main()
