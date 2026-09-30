import unittest
from datetime import datetime
from io import BytesIO
from pathlib import Path
import tempfile
import pandas as pd
from openpyxl import load_workbook

from datatrace_sync import status_report_frame, build_synced_workbook_stream
from order_reporting import monthly_orders
from preview_store import PreviewStore
from server import create_app


class NewFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.store = PreviewStore(self.root / 'previews')

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_status_report_frame_with_metadata(self):
        df = pd.DataFrame([
            {'Task Status': 'Search In Progress'},
            {'Task Status': 'Available'},
            {'Task Status': 'Available'},
        ])
        # Test backwards compatibility
        df_no_meta = status_report_frame(df)
        self.assertEqual(list(df_no_meta.columns), ['Status', 'Orders', 'Share'])

        # Test with preview name and sync time
        sync_time = '2026-09-30 10:00:00 AM'
        df_meta = status_report_frame(df, preview_name='preview1', sync_time=sync_time)
        self.assertEqual(list(df_meta.columns), ['Status', 'Orders', 'Share', 'Preview', 'Sync Date & Time'])
        self.assertEqual(df_meta['Preview'].tolist(), ['preview1', 'preview1'])
        self.assertEqual(df_meta['Sync Date & Time'].tolist(), [sync_time, sync_time])

    def test_multi_sheet_excel_download(self):
        raw = pd.DataFrame([
            {'Order Number': '101', 'Task Name': 'Search', 'Task Status': 'Available', 'Product': 'Full Title', 'Arrival Time': '09/30/2026 09:00 AM'},
            {'Order Number': '102', 'Task Name': 'Other', 'Task Status': 'Available', 'Product': 'Current Owner', 'Arrival Time': '09/30/2026 09:00 AM'},
        ])
        preview = self.store.save(raw)
        client = create_app(self.store.root).test_client()

        res = client.get(f"/api/previews/{preview['id']}/download/xlsx")
        self.assertEqual(res.status_code, 200)

        wb = load_workbook(BytesIO(res.data))
        expected_sheets = ['Sheet1', 'All Products', 'Full Title', 'Remaining Products', 'Status Report']
        self.assertEqual(wb.sheetnames, expected_sheets)

        # Check Status Report sheet contains Preview and Sync Date & Time
        status_ws = wb['Status Report']
        headers = [cell.value for cell in status_ws[1]]
        self.assertIn('Preview', headers)
        self.assertIn('Sync Date & Time', headers)
        preview_col_idx = headers.index('Preview') + 1
        self.assertEqual(status_ws.cell(row=2, column=preview_col_idx).value, preview['name'])

    def test_sync_schedule_multiple_times(self):
        client = create_app(self.store.root).test_client()

        # Update with multiple times
        res = client.post('/api/sync-schedule', json={
            'enabled': True,
            'times': ['10:00', '09:00', '14:30']
        })
        self.assertEqual(res.status_code, 200)
        data = res.json
        self.assertTrue(data['enabled'])
        # Should be sorted and deduplicated
        self.assertEqual(data['times'], ['09:00', '10:00', '14:30'])
        self.assertEqual(data['time'], '09:00')

        # Verify state endpoint returns updated schedule
        state_res = client.get('/api/state')
        self.assertEqual(state_res.json['schedule']['times'], ['09:00', '10:00', '14:30'])

    def test_monthly_orders_and_endpoint(self):
        # Create previews across September 2026
        df_sep1 = pd.DataFrame([
            {'Order Number': '1', 'Task Status': 'Available', 'Arrival Time': '09/01/2026 10:00 AM'},
            {'Order Number': '2', 'Task Status': 'Available', 'Arrival Time': '09/01/2026 10:00 AM'},
        ])
        df_sep2 = pd.DataFrame([
            {'Order Number': '1', 'Task Status': 'Available', 'Arrival Time': '09/01/2026 10:00 AM'},
            {'Order Number': '3', 'Task Status': 'Available', 'Arrival Time': '09/15/2026 10:00 AM'},
            # Order 2 is missing in latest snapshot -> Completed
        ])
        self.store.save(df_sep1)
        self.store.save(df_sep2)

        reports = monthly_orders(self.store)
        self.assertEqual(len(reports), 1)
        sep_report = reports[0]
        self.assertEqual(sep_report['Month'], '2026-09')
        self.assertEqual(sep_report['MonthLabel'], 'September 2026')
        self.assertEqual(sep_report['Month Orders'], 3)
        self.assertEqual(sep_report['Missing (Completed Orders)'], 1)
        self.assertEqual(sep_report['missing_ids'], ['2'])

        client = create_app(self.store.root).test_client()
        api_res = client.get('/api/monthly-orders')
        self.assertEqual(api_res.status_code, 200)
        self.assertEqual(len(api_res.json['rows']), 1)
        self.assertEqual(api_res.json['rows'][0]['Month'], '2026-09')


if __name__ == '__main__':
    unittest.main()
