import unittest
from unittest.mock import patch

from pathlib import Path
from report_workspace import imported_snapshot, report_frames, publish_reports
from import_excel_changes import editable_frames, read_editable_tabs
from test_pdf_report_workspace import ReportBook
from test_report_date_details import ReportDateDetailsTests as Fixtures


class ReportSourceVisibilityTests(unittest.TestCase):
    def setUp(self):
        patcher = patch('import_excel_changes.sync_imported_tabs', return_value=False)
        self.refresh = patcher.start()
        self.addCleanup(patcher.stop)
        Fixtures.setUp(self)
    snapshot = Fixtures.snapshot

    def test_sheet_summaries_are_empty_but_imported_app_reports_remain(self):
        settings = self.workspace.read()
        snapshot = imported_snapshot(settings['imported'])
        snapshot['latest_preview'] = {'columns': ['Order Number'], 'rows': [{'Order Number': 'LATEST'}]}
        frames, _ = report_frames(snapshot, settings, sheet_publication=True)
        self.assertEqual(len(frames['Monthly Orders']), 1)
        self.assertEqual(len(frames['Daily Status Report']), 1)
        self.assertEqual(frames['All Products'], [['Order Number'], ['LATEST']])
        self.assertTrue(snapshot['reports']['daily'])
        self.assertTrue(snapshot['reports']['monthly'])

    def test_compare_uses_imports_and_separate_queue_in_both_modes(self):
        self.workspace.store.restore(1, ['Order Number', 'Task Status'],
                                     [{'Order Number': 'D', 'Task Status': 'Available'}])
        for mode in ('tracker', 'excel'):
            self.workspace.save(mode=mode)
            response = self.client.get('/api/sla-compare')
            self.assertEqual(response.status_code, 200, response.json)
            self.assertEqual(response.json['source_files'], 'Imported Excel reports')
            self.assertEqual(response.json['selected_preview_id'], 1)
            self.assertTrue(response.json['has_production'])
            self.assertEqual(self.refresh.call_args.args[2]['mode'], 'excel')

    def test_compare_uses_saved_imports_when_sheets_refresh_fails(self):
        self.refresh.side_effect = RuntimeError('offline')
        response = self.client.get('/api/sla-compare')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json['has_production'])
        self.assertIn('offline', response.json['source_warning'])

    def test_publication_clears_old_results_and_replaces_all_products(self):
        settings = self.workspace.read()
        snapshot = imported_snapshot(settings['imported'])
        snapshot['latest_preview'] = {'columns': ['Order Number', 'Status'],
                                     'rows': [{'Order Number': 'LATEST', 'Status': 'Available'}]}
        book = ReportBook()
        for title in ('Monthly Orders', 'Daily Status Report', 'All Products'):
            book.add(title, [{'Order Number': 'OLD', 'Status': 'Completed and Delivered'}])
        publish_reports(book, snapshot, settings, Path(self.folder.name) / 'backups')
        for title in ('Monthly Orders', 'Daily Status Report'):
            values = book.worksheet(title).get_all_values()
            self.assertFalse(any(any(cell for cell in row) for row in values[1:]), (title, values))
        self.assertEqual(book.worksheet('All Products').get_all_values()[1][0], 'LATEST')

    def test_latest_queue_is_not_an_import_edit_source(self):
        settings = self.workspace.read()
        frames = editable_frames(imported_snapshot(settings['imported']), settings)
        self.assertNotIn('All Products', frames)
        book = ReportBook()
        # An old baseline must not cause queue rows to overwrite imported orders.
        self.assertEqual(read_editable_tabs(book, {'All Products': [['Order Number'], ['OLD']]}), {})

    def test_normalized_countdown_does_not_replace_portal_arrival_reference(self):
        from datetime import datetime
        from sla_status import build_sla_status
        class Clock(datetime):
            @classmethod
            def now(cls):
                return cls(2026, 11, 6)
        snapshot = {'sla_reference_at': '2026-10-22T22:47:00',
                    'sheets': {'Overview': {'rows': [{'Order Number': 'A',
                        'SLA Expiration*': '1d', 'SLA Expiration': '2026-11-06 12:00:00'}]}}}
        with patch('sla_status.datetime', Clock):
            report = build_sla_status(snapshot)
        self.assertEqual(report['as_of'], '2026-10-22')
