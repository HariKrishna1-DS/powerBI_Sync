"""Product coverage, completion evidence and report-format regression cases."""
from datetime import datetime
import unittest
from unittest.mock import patch

from monthly_production import BASES, decode, tab_name
from monthly_views import monthly_view_values, refresh_monthly_views
from production_timing import sla_result
from tracker_sync import FULL, REMAINING, merge_trackers, sheet_reports
from tracker_formatting import MARKER, rules_for, ensure_tracker_formatting
from test_monthly_production import AtomicBook, order


class ReportRefinementTests(unittest.TestCase):
    def completed(self, **extra):
        return {'Status': 'Completed and Delivered', 'In-Time': '10/5/2026 09:00 AM',
                'Out Time': '10/5/2026 10:00 AM', 'SLA Expiration': '10/5/2026 10:00 AM', **extra}

    def test_only_completed_orders_receive_sla_and_equality_is_on_time(self):
        self.assertEqual(sla_result(self.completed())[0], 'On Time')
        self.assertEqual(sla_result(self.completed(**{'Out Time':'10/5/2026 10:00:01 AM'}))[0], 'Missing')
        for status in ('Cancelled', 'Task Suspended', 'Awaiting for Clarification', 'In Progress', 'Search In Progress', ''):
            with self.subTest(status=status):
                self.assertEqual(sla_result(self.completed(Status=status)), ('', None))

    def test_incomplete_or_impossible_timestamps_are_not_classified(self):
        date_serial=str((datetime(2026,10,6)-datetime(1899,12,30)).days)+'.0'
        for out, due in (('', '10/5/2026 10:00 AM'), ('10/5/2026', '10/5/2026 10:00 AM'),
                         ('1h 20m', '10/5/2026 10:00 AM'), ('10/5/2026 10:00 AM', 'PAUSED'),
                         (date_serial, '10/7/2026 10:00 AM'), ('10/5/2026 10:00 AM',date_serial),
                         ('10/5/2026 10:00 AM', '10/5/2026'), ('10/5/2026 08:59 AM', '10/5/2026 10:00 AM')):
            with self.subTest(out=out, due=due):
                self.assertEqual(sla_result(self.completed(**{'Out Time':out, 'SLA Expiration':due}))[0], '')
        self.assertEqual(sla_result(self.completed(**{'In-Time':'10/4/2026 10:00 PM','Out Time':'10/5/2026 00:00','SLA Expiration':'10/5/2026 00:00'}))[0],'On Time')

    def test_negative_countdown_compares_actual_completion_and_local_times(self):
        row = self.completed(**{'SLA Expiration':'-1h'})
        self.assertEqual(sla_result(row, datetime(2026,10,5,12))[0], 'On Time')
        self.assertEqual(sla_result(row)[0], '')
        row = self.completed(**{'Out Time':'2026-10-05T10:00:00-07:00', 'SLA Expiration':'2026-10-05T10:00:00-07:00'})
        self.assertEqual(sla_result(row)[0], 'On Time')

    def test_completion_hours_never_replace_an_out_time_in_either_tracker(self):
        for base in (FULL, REMAINING):
            with self.subTest(base=base):
                existing = self.completed(**{'Order Number':'A', 'Product':'Full Title' if base==FULL else 'Update'})
                raw = {'Order Number':'A', 'Completed Time (hours)':'46279.5', 'Completed Time':'10/5/2026 11:00 AM'}
                result, _ = merge_trackers({base:[existing]}, [raw], [], datetime(2026,10,5,12))
                self.assertEqual(result[base][0]['Out Time'], existing['Out Time'])
                existing['Out Time']=''
                raw.pop('Completed Time')
                result, _ = merge_trackers({base:[existing]}, [raw], [], datetime(2026,10,5,12))
                self.assertEqual(result[base][0]['Out Time'], '')
                self.assertEqual(result[base][0]['Free Site'], '')

    def test_reports_exclude_stale_sla_labels_on_ineligible_orders(self):
        rows = [dict(self.completed(), **{'Order Number':'A', 'Free Site':'On Time'}),
                dict(self.completed(Status='Cancelled'), **{'Order Number':'B', 'Free Site':'On Time'}),
                dict(self.completed(**{'SLA Expiration':'PAUSED'}), **{'Order Number':'C', 'Free Site':'Missing'})]
        report = sheet_reports({FULL:rows})['monthly'][0]
        self.assertEqual((report['Month Orders'],report['SLA On Time'],report['SLA Missed']), (3,1,0))

    def test_remaining_view_includes_every_non_full_product_with_exact_production_schema(self):
        rows = [order('B', Product='Update'), order('A', Product='  Full   Search  '),
                order('C', Product='Unlisted product'), order('D', Product='Current Owner')]
        views = monthly_view_values({tab_name(BASES[0],'2026-10'):rows}, [{'Order Number':'C','Vendor':'Retained vendor'}])
        self.assertEqual([r['Order Number'] for r in decode(views['Full_search_OCT_2026'])], ['A'])
        remaining = decode(views['Remaining_OCT_2026'])
        self.assertEqual([r['Order Number'] for r in remaining], ['B','C','D'])
        self.assertEqual([r['No'] for r in remaining], [1,2,3])
        self.assertNotIn('Vendor', remaining[1])
        self.assertEqual(views['Remaining_OCT_2026'][0], views['Full_search_OCT_2026'][0])

    def test_repeat_view_refresh_does_not_create_duplicate_tabs_or_change_trackers(self):
        book = AtomicBook()
        for base in BASES:
            book.add(tab_name(base,'2026-10'), [order(base[-6:], Product='Full Title' if base==BASES[0] else 'Update')])
        before = {sheet.title:sheet.get_all_values() for sheet in book.worksheets()}
        refresh_monthly_views(book)
        batch_count = len(book.batches)
        refresh_monthly_views(book)
        self.assertEqual(len(book.batches),batch_count)
        self.assertEqual(len([s for s in book.worksheets() if s.title=='Remaining_OCT_2026']),1)
        for title, values in before.items():
            self.assertEqual(book.worksheet(title).get_all_values(), values)
        ensure_tracker_formatting(book)
        self.assertEqual(ensure_tracker_formatting(book),0)
        self.assertTrue(all(MARKER in str(rule) for rule in book.worksheet('Remaining_OCT_2026').conditional_formats))


if __name__ == '__main__':
    unittest.main()
