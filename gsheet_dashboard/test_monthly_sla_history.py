import unittest
from unittest.mock import Mock, patch
from order_reporting import monthly_orders


class MonthlySlaHistoryTests(unittest.TestCase):
    def test_all_captures_deduplicated_with_actual_completion_day(self):
        def row(identity, sla, out=''):
            return {'Order Number': identity, 'Task Status': 'Available',
                    'Arrival Time': '09/01/2026 10:00 AM', 'SLA Expiration*': sla, 'Out Time': out}
        rows = [
            [row('early', '09/03 01:00 PM'), row('late', '-2d 3h'), row('open', '6h')],
            [row('late', '-2d 3h'), row('open', '6h')],
            [row('open', '6h'), row('explicit', '6h', '09/04/2026')],
            [row('open', '6h'), row('explicit', '6h', '09/04/2026')],
        ]
        previews = [{'id': i+1, 'name': f'preview{i+1}', 'created': f'2026-09-0{i+1}T10:00:00Z',
                     'columns': list(items[0]), 'rows': items} for i, items in enumerate(rows)]
        store = Mock()
        store.list.return_value = list(reversed(previews))
        store.get.side_effect = lambda identity: previews[identity-1]
        with patch('order_reporting.reporting_date', side_effect=lambda p: p['created'][:10]):
            report = monthly_orders(store)[0]
        self.assertEqual(report['SLA On Time'], 2)
        self.assertEqual(report['SLA Missed'], 1)
        self.assertEqual(len(report['Previews']), 4)

    def test_repeated_automatic_completion_does_not_move_to_next_month(self):
        row = {'Order Number': '1', 'Task Status': 'Available', 'Task Name': 'CRSP2',
               'Arrival Time': '09/30/2026 10:00 AM', 'SLA Expiration*': '6h'}
        previews = [{'id': i+1, 'name': f'preview{i+1}', 'created': date,
                     'columns': list(row), 'rows': [row]} for i, date in enumerate(
                         ['2026-09-30T10:00:00Z', '2026-10-01T10:00:00Z'])]
        store = Mock()
        store.list.return_value = previews
        store.get.side_effect = lambda identity: previews[identity-1]
        with patch('order_reporting.reporting_date', side_effect=lambda p: p['created'][:10]):
            october, september = monthly_orders(store)
        self.assertEqual(september['SLA On Time'], 1)
        self.assertEqual(october['SLA On Time'], 0)
