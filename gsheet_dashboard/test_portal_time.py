from datetime import datetime
import unittest

from datatrace_sync import capture_anchor, sla_expiration
from sla_status import local_time, category


class PortalTimeTests(unittest.TestCase):
    def test_capture_converts_to_central_in_summer_and_winter(self):
        for instant, expected in [
            ('2026-10-29T09:15:00Z', datetime(2026, 10, 29, 4, 15)),
            ('2026-12-29T09:15:00+00:00', datetime(2026, 12, 29, 3, 15)),
            ('2026-10-29T02:00:00Z', datetime(2026, 10, 28, 21)),
            ('2026-11-01T06:30:00Z', datetime(2026, 11, 1, 1, 30)),
            ('2026-11-01T07:30:00Z', datetime(2026, 11, 1, 1, 30)),
        ]:
            with self.subTest(instant=instant):
                self.assertEqual(capture_anchor(instant), expected)
                self.assertEqual(local_time(instant), expected)

    def test_countdown_uses_central_date_not_indian_date(self):
        row = {'Sync Timestamp': '2026-10-29T09:15:00Z', 'SLA Expiration*': '12h'}
        due = sla_expiration(row)
        self.assertEqual(due, datetime(2026, 10, 29, 16, 15))
        self.assertEqual(category(due.isoformat(), datetime(2026, 10, 29)), 'Today SLA')

    def test_absolute_portal_deadline_and_arrival_wall_clock_stay_unchanged(self):
        row = {'Sync Timestamp': '2026-10-29T09:15:00Z', 'SLA Expiration*': '10/30 01:00 PM'}
        self.assertEqual(sla_expiration(row), datetime(2026, 10, 30, 13))
        self.assertEqual(local_time('10/29/2026 05:05 AM'), datetime(2026, 10, 29, 5, 5))
