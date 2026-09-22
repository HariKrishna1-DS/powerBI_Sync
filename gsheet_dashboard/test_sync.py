import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
from openpyxl import load_workbook

import datatrace_sync as sync


class SyncTests(unittest.TestCase):
    def frame(self):
        return pd.DataFrame([{'Arrival Time': '09/22/2026 01:00 PM',
                              'Task Status': 'Available', 'Parcel ID': '00123',
                              'Comment': '=1+1', 'Time Since Arrival': '2d 3h 30m',
                              'SLA Expiration*': '-1h 0m'}])

    def test_powerbi_and_literal_exports(self):
        df = sync.powerbi_table(self.frame(), '2026-09-22T12:00:00+00:00')
        self.assertEqual(df.loc[0, 'Queue Age Hours'], 51.5)
        self.assertEqual(df.loc[0, 'Arrival Date'], '2026-09-22')
        self.assertEqual(df.loc[0, 'SLA Status'], 'Overdue')
        self.assertTrue(df.loc[0, 'Is Available'])
        with tempfile.TemporaryDirectory() as folder:
            excel, csv = sync.export_to_excel_and_csv(df, Path(folder) / 'queue')
            read = pd.read_csv(csv, dtype=str, keep_default_na=False)
            self.assertEqual(read.loc[0, 'Parcel ID'], '00123')
            ws = load_workbook(excel).active
            self.assertIn('DataTraceQueue', ws.tables)
            self.assertEqual(ws['D2'].value, '=1+1')
            self.assertEqual(ws['D2'].data_type, 's')

    def test_atomic_replace_gid_zero_and_literals(self):
        df = self.frame()
        book, sheet = Mock(), Mock(id=0, row_count=1, col_count=1, title='Actual tab')
        sheet.get_all_values.return_value = [list(df.columns)] + df.values.tolist()
        self.assertEqual(sync.sync_dataframe(df, (book, sheet)), 'Actual tab')
        requests = book.batch_update.call_args.args[0]['requests']
        self.assertEqual(len(requests), 3)
        update = requests[-1]['updateCells']
        self.assertEqual(update['range'], {'sheetId': 0})
        self.assertEqual(update['fields'], 'userEnteredValue')
        self.assertEqual(update['rows'][1]['values'][2]['userEnteredValue'], {'stringValue': '00123'})
        self.assertEqual(update['rows'][1]['values'][3]['userEnteredValue'], {'stringValue': '=1+1'})

    def test_empty_data_never_writes(self):
        book = Mock()
        with self.assertRaises(ValueError):
            sync.sync_dataframe(self.frame().iloc[:0], (book, Mock()))
        book.batch_update.assert_not_called()

    def test_failed_scrape_never_uploads_old_files(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(sync, 'BASE_DIR', Path(folder)), \
                patch.dict(sync.os.environ, {'DATATRACE_USERNAME': 'test', 'DATATRACE_PASSWORD': 'test'}), \
                patch.object(sync.subprocess, 'run', return_value=Mock(returncode=1)), \
                patch.object(sync, 'sync_dataframe') as upload, \
                patch.object(sync, 'export_to_excel_and_csv') as export:
            result = sync.run_sync()
            self.assertEqual(result['scrape'], 'failed')
            upload.assert_not_called()
            export.assert_not_called()

    def test_sheet_failure_retains_export_and_last_success(self):
        def scrape(*args, **kwargs):
            Path(kwargs['env']['DATATRACE_OUTPUT_JSON']).write_text(
                self.frame().to_json(orient='records'), encoding='utf-8')
            return Mock(returncode=0)
        with tempfile.TemporaryDirectory() as folder, patch.object(sync, 'BASE_DIR', Path(folder)), \
                patch.dict(sync.os.environ, {'DATATRACE_USERNAME': 'test', 'DATATRACE_PASSWORD': 'test'}), \
                patch.object(sync.subprocess, 'run', side_effect=scrape), \
                patch.object(sync, 'sync_dataframe', side_effect=RuntimeError('Share as Editor')):
            (Path(folder) / 'sync_status.json').write_text(json.dumps({'last_success_at': 'previous'}))
            result = sync.run_sync()
            self.assertEqual(result['scrape'], 'success')
            self.assertEqual(result['google_sheet'], 'failed')
            self.assertEqual(result['last_success_at'], 'previous')
            self.assertTrue((Path(folder) / 'queue_data_sheet2.xlsx').exists())

    def test_verification_failure_is_not_success(self):
        book, sheet = Mock(), Mock(id=0, row_count=100, col_count=30)
        sheet.get_all_values.return_value = []
        with self.assertRaisesRegex(RuntimeError, 'verification failed'):
            sync.sync_dataframe(self.frame(), (book, sheet))


if __name__ == '__main__':
    unittest.main()
