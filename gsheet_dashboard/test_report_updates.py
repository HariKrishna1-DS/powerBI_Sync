import unittest
import pandas as pd
from datatrace_sync import report_frames, sla_result


class ReportUpdatesTests(unittest.TestCase):
    def test_sla_requires_capture_anchor_for_relative_values(self):
        row = {'Out Time': '09/28/2026 12:00 PM', 'Sync Timestamp': '2026-09-28T06:30:00Z'}
        for sla, expected in [('09/29 01:34 PM', 'On Time'), ('09/27 01:34 PM', 'Missing'),
                              ('6h 6m', 'On Time'), ('-2d 3h', 'Missing'), ('PAUSED', '')]:
            with self.subTest(sla=sla):
                self.assertEqual(sla_result(dict(row, **{'SLA Expiration*': sla})), expected)
        self.assertEqual(sla_result({'Out Time': '', 'SLA Expiration*': '-2d'}), '')
        self.assertEqual(sla_result({'Out Time': row['Out Time'], 'SLA Expiration*': '6h'}), '')

    def test_report_layout_preserves_time_of_day(self):
        frame = pd.DataFrame([{'Product': p, 'Arrival Time': '09/25/2026 09:35 AM',
                              'Arrival Date': '2026-09-25', 'Out Time': '09/28/2026 12:00 PM',
                              'SLA Expiration*': '09/29/2026 01:34 PM'} for p in ('Full Title', 'Current Owner')])
        for report in report_frames(frame)[1:]:
            self.assertEqual(report.iloc[0]['Out Time'], '09/28/2026 12:00:00 PM')
            self.assertEqual(report.iloc[0]['In-Time'], '09/25/2026 09:35:00 AM')
            self.assertEqual(report.iloc[0]['Free Site'], 'On Time')
