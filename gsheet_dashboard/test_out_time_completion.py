from copy import deepcopy
from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from import_excel_changes import editable_frames, reconcile
from monthly_production import decode
from monthly_views import refresh_monthly_views
from preview_completion import reconcile_completions
from preview_store import PreviewStore, compare
from production_timing import completion_from_out_time
from report_workspace import ReportWorkspace, imported_snapshot, read_report_files
from test_pdf_report_workspace import excel, row, ReportBook
from tracker_sync import FULL, REMAINING, merge_trackers


def capture(number, ids, created):
    rows = [row(identity, **{'Task Status': 'Available'}) for identity in ids]
    return {'id': number, 'name': f'preview{number}', 'created': created,
            'columns': list(rows[0]) if rows else ['Order Number'], 'rows': rows}


class OutTimeCompletionTests(unittest.TestCase):
    def test_valid_out_time_controls_status_without_changing_timestamp_or_source(self):
        for status in ('QC in Progress', 'Assign to ABS', 'Awaiting for Clarification', 'Cancelled', 'Task Suspended'):
            original = row('A', status, **{'Task Status': status, 'Out Time': '10/05/2026 10:00:00 AM'})
            saved = deepcopy(original)
            completed = completion_from_out_time(original)
            self.assertEqual(completed['Status'], 'Completed and Delivered')
            self.assertEqual(completed['Task Status'], 'Completed and Delivered')
            self.assertEqual(completed['Out Time'], original['Out Time'])
            self.assertEqual(original, saved)
        for invalid in ('', 'PAUSED', '2h 30m', 'not a date'):
            original = row('A', **{'Out Time': invalid})
            self.assertEqual(completion_from_out_time(original), original)

    def test_missing_comparison_uses_first_absence_in_ist_and_excludes_future_previews(self):
        first = capture(1, ['A', 'B'], '2026-10-05T03:30:00Z')
        missing = capture(2, ['B'], '2026-10-05T04:30:00Z')
        latest = capture(3, ['B'], '2026-10-05T06:30:00Z')
        future = capture(4, ['A', 'B'], '2026-10-05T07:30:00Z')
        history = [first, missing, latest, future]
        saved = deepcopy(history)
        result = compare(first, latest, keys=['Order Number'], history=history)
        absent = next(record for record in result['unmatched_rows'] if record['Order Number'] == 'A')
        self.assertEqual(absent['Comparison Status'], 'Missing')
        self.assertEqual(absent['Status'], 'Completed and Delivered')
        self.assertEqual(absent['Out Time'], '10/05/2026 10:00:00 AM')
        self.assertIn('Status', result['record_columns'])
        self.assertIn('Out Time', result['record_columns'])
        self.assertEqual(history, saved)

    def test_missing_comparison_keeps_existing_manual_out_time(self):
        first = capture(1, ['A', 'B'], '2026-10-05T03:30:00Z')
        first['rows'][0]['Out Time'] = '10/05/2026 09:30 AM'
        first['columns'].append('Out Time')
        latest = capture(2, ['B'], '2026-10-05T04:30:00Z')
        result = compare(first, latest, keys=['Order Number'])
        self.assertEqual(result['unmatched_rows'][0]['Out Time'], '10/05/2026 09:30 AM')
        self.assertEqual(result['unmatched_rows'][0]['Status'], 'Completed and Delivered')

    def test_sync_updates_present_and_absent_tracker_status_from_recorded_out_time(self):
        existing = row('A', 'Awaiting for Clarification', **{'Out Time': '10/05/2026 10:00 AM'})
        merged, report = merge_trackers({FULL: [existing], REMAINING: []}, [], [], datetime(2026, 10, 5, 12))
        self.assertEqual(merged[FULL][0]['Status'], 'Completed and Delivered')
        self.assertEqual(report['updated'], 1)
        incoming = row('B', 'Assign to ABS', **{'Out Time': '10/05/2026 11:00 AM'})
        merged, _ = merge_trackers({FULL: [], REMAINING: []}, [incoming], [], datetime(2026, 10, 5, 12))
        self.assertEqual(merged[FULL][0]['Status'], 'Completed and Delivered')

    def test_sheet_repair_writes_status_and_preserves_out_time_and_raw_capture(self):
        book = ReportBook()
        original = row('A', 'QC in Progress', **{'Out Time': '10/05/2026 10:00 AM'})
        tracker = book.add(FULL, [original])
        book.add(REMAINING, [])
        raw = book.add('Sheet1', [{'Order Number': 'A', 'Preview': 'preview1', 'Status': 'Available'}])
        raw_values = deepcopy(raw.values)
        self.assertTrue(refresh_monthly_views(book, return_changed=True))
        repaired = decode(book.worksheet(FULL).get_all_values())[0]
        self.assertEqual(repaired['Status'], 'Completed and Delivered')
        self.assertEqual(repaired['Out Time'], original['Out Time'])
        self.assertEqual(book.worksheet('Sheet1').values, raw_values)
        self.assertFalse(refresh_monthly_views(book, return_changed=True))

    def test_read_refresh_does_not_rebuild_reports_without_completion_changes(self):
        book=ReportBook()
        book.add(FULL,[row('A')])
        book.add(REMAINING,[])
        self.assertFalse(refresh_monthly_views(book,return_changed=True,only_completions=True))
        self.assertEqual(book.batches,[])

    def test_import_and_remote_out_time_edit_update_local_and_published_status(self):
        imported = read_report_files([('full.xlsx', excel([row('A'), row('B', **{'Out Time': '10/05/2026 10:00 AM'})]))])
        self.assertEqual(imported['rows'][1]['Status'], 'Completed and Delivered')
        snapshot = imported_snapshot(imported)
        baseline = editable_frames(snapshot, {'mode': 'excel'})
        remote = deepcopy(baseline)
        values = remote['All Products']
        values[1][values[0].index('Out Time')] = '10/05/2026 11:00 AM'
        updated, events = reconcile(imported, baseline, remote)
        self.assertEqual(updated['rows'][0]['Status'], 'Completed and Delivered')
        self.assertTrue(any(event['Column'] == 'Status' and event['New Value'] == 'Completed and Delivered' for event in events))
        published = editable_frames(imported_snapshot(updated), {'mode': 'excel'})['All Products']
        self.assertEqual(published[1][published[0].index('Status')], 'Completed and Delivered')

    def test_saved_import_is_repaired_with_backup_and_original_source_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            workspace = ReportWorkspace(store)
            source = row('A', 'Assign to ABS', **{'Out Time': '10/05/2026 10:00 AM'})
            imported = {'rows': [source], 'sources': [], 'columns': list(source), 'files': [], 'created': '2026-10-05'}
            workspace.save(mode='excel', imported=imported)
            restarted = ReportWorkspace(store)
            self.assertEqual(restarted.read()['imported']['rows'][0]['Status'], 'Completed and Delivered')
            self.assertEqual(restarted.read()['publication_state'], 'pending')
            self.assertTrue(list((Path(folder) / 'backups').glob('*')))
            self.assertEqual(source['Status'], 'Assign to ABS')


if __name__ == '__main__':
    unittest.main()
