from datetime import datetime
import unittest
from preview_completion import reconcile_completions
from tracker_sync import FULL, REMAINING
from monthly_views import refresh_monthly_views
from test_monthly_production import AtomicBook


def capture(number, ids, hour, **extra):
    return [dict({'Preview': f'preview{number}', 'Preview Timestamp': f'2026-10-05T{hour:02}:00:00.123456',
        'Order Number': identity, 'Product': 'Full Title', 'SLA Expiration': '2h'}, **extra) for identity in ids]


def order(identity='A', **extra):
    return dict({'Order Number': identity, 'Product': 'Full Title', 'Status': 'Search In Progress',
        'In-Time': '10/05/2026 08:00 AM', 'Out Time': '', 'SLA Expiration': '10/05/2026 11:00 AM',
        'Searcher': 'Preserved', 'Free Site': ''}, **extra)


class PreviewCompletionTests(unittest.TestCase):
    def repair(self, rows, history):
        return reconcile_completions({FULL: rows}, history)[0][FULL]

    def test_first_missing_timestamp_is_stable_and_sla_uses_out_time(self):
        history=capture(1,['A','B','C'],9)+capture(2,['C'],11)+capture(3,['C'],12)
        rows=[order(),order('B', **{'SLA Expiration':'10/05/2026 10:59:59 AM'})]
        repaired=self.repair(rows,history)
        self.assertEqual([r['Free Site'] for r in repaired], ['On Time','Missing'])
        self.assertEqual(repaired[0]['Out Time'],'10/05/2026 11:00:00 AM')
        self.assertEqual(repaired[0]['Status'],'Completed and Delivered')
        self.assertEqual(repaired[0]['Searcher'],'Preserved')
        self.assertEqual(self.repair(repaired,history),repaired)

    def test_relative_deadline_anchors_to_last_seen_capture(self):
        row=self.repair([order(**{'SLA Expiration':'2h'})],capture(1,['A','B'],9)+capture(2,['B'],12))[0]
        self.assertEqual(row['SLA Expiration'],'10/05/2026 11:00:00 AM')
        self.assertEqual(row['Free Site'],'Missing')

    def test_exceptions_manual_times_and_never_seen_orders_are_preserved(self):
        rows=[order('A',Status='Cancelled'),order('B',Status='Task Suspended'),order('C',**{'Out Time':'10/05/2026 09:30 AM'}),order('D')]
        repaired=self.repair(rows,capture(1,['A','B','C','E'],9)+capture(2,['E'],11))
        self.assertEqual(repaired[0],rows[0]); self.assertEqual(repaired[1],rows[1])
        self.assertEqual(repaired[2]['Out Time'],rows[2]['Out Time'])
        self.assertEqual(repaired[3],rows[3])

    def test_reappearance_reopens_only_inferred_completion_and_next_absence_uses_new_time(self):
        history=capture(1,['A','B'],9)+capture(2,['B'],10)
        closed=self.repair([order()],history)
        history+=capture(3,['A','B'],11)
        reopened=self.repair(closed,history)[0]
        self.assertEqual((reopened['Status'],reopened['Out Time'],reopened['Free Site']),('Search In Progress','',''))
        history+=capture(4,['B'],12)
        self.assertEqual(self.repair(closed,history)[0]['Out Time'],'10/05/2026 12:00:00 PM')
        manual=order(Status='Completed and Delivered',**{'Out Time':'10/05/2026 09:45 AM'})
        self.assertEqual(self.repair([manual],history[:-1])[0]['Out Time'],manual['Out Time'])

    def test_invalid_snapshots_break_continuity(self):
        for invalid in (capture(2,[''],10),capture(2,['B','B'],10),capture(2,['B'],8),capture(2,['B'],10,**{'Preview Timestamp':'unknown'})):
            with self.subTest(invalid=invalid):
                rows=self.repair([order()],capture(1,['A','B'],9)+invalid+capture(3,['B'],11))
                self.assertEqual(rows[0]['Out Time'],'')
        duplicate=self.repair([order(),order()],capture(1,['A','B'],9)+capture(2,['B'],11))
        self.assertTrue(all(not r['Out Time'] for r in duplicate))

    def test_capture_offsets_use_ist_and_impossible_arrival_does_not_complete(self):
        history=capture(1,['A','B'],9,**{'Preview Timestamp':'2026-10-05T03:30:00Z'})+capture(2,['B'],10,**{'Preview Timestamp':'2026-10-05T04:30:00Z'})
        self.assertEqual(self.repair([order()],history)[0]['Out Time'],'10/05/2026 10:00:00 AM')
        self.assertEqual(self.repair([order(**{'In-Time':'10/05/2026 11:00 AM'})],history)[0]['Out Time'],'')

    def test_sync_merge_reappearance_clears_inferred_time_after_status_mapping(self):
        from tracker_sync import merge_trackers
        history=capture(1,['A','B'],9)+capture(2,['B'],10)
        closed=self.repair([order()],history)
        current=capture(3,['A','B'],11,**{'Task Name':'Search','Task Status':'Available'})
        merged,_=merge_trackers({FULL:closed},current,capture(2,['B'],10),datetime(2026,10,5,11),history+current)
        row=next(r for r in merged[FULL] if r['Order Number']=='A')
        self.assertEqual((row['Status'],row['Out Time'],row['Free Site']),('Search In Progress','',''))

    def test_repeat_sync_repairs_history_with_backups_and_preserves_raw_rows(self):
        book=AtomicBook()
        book.add(FULL,[order()])
        book.add(REMAINING,[])
        history=capture(1,['A','B'],9)+capture(2,['B'],11)
        raw=book.add('Sheet1',history,headers=list(history[0]))
        original=raw.get_all_values()
        refresh_monthly_views(book)
        from monthly_production import decode
        fixed=decode(book.worksheet(FULL).get_all_values())[0]
        self.assertEqual((fixed['Status'],fixed['Free Site']),('Completed and Delivered','On Time'))
        self.assertEqual(book.worksheet('Sheet1').get_all_values(),original)
        count=len(book.batches)
        refresh_monthly_views(book)
        self.assertEqual(len(book.batches),count)

    def test_existing_view_extra_columns_removed_atomically_and_tracker_attributes_retained(self):
        book=AtomicBook()
        full=book.add(FULL,[order(Typer='Manual')])
        book.add(REMAINING,[order('B',Product='Update')])
        book.add('Full_search_OCT_2026',[order(Borrower='Raw extra')])
        book.add('Remaining_OCT_2026',[order('B',Vendor='Raw extra')])
        refresh_monthly_views(book)
        for name in ('Full_Search_OCT_2026','Remaining_Search_OCT_2026'):
            values=book.worksheet(name).get_all_values()
            self.assertEqual([v for v in values[0] if v],full.values[0])
        batches=len(book.batches)
        refresh_monthly_views(book)
        self.assertEqual(len(book.batches),batches)
        self.assertTrue(any(s.title.startswith('__DataTrace_Backup_') for s in book.worksheets()))


if __name__=='__main__': unittest.main()
