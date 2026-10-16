import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import create_app
from test_production_sync import Book, Sheet
from sync_config import TRACKER_TITLES
from production_rules import TRACKER_COLUMNS


class LiveSheetUpdatesTests(unittest.TestCase):
    def test_sheet_edits_refresh_reports_without_local_previews(self):
        with tempfile.TemporaryDirectory() as folder:
            row = {'Order Number': 'A', 'Date': '09/30/2026', 'Product': 'Full Title', 'Status': 'Completed and Delivered',
                   'Out Time': '09/30/2026 12:00 PM', 'SLA Expiration': '09/30/2026 11:00 AM', 'Free Site': 'Missing'}
            book = Book([[row], []])
            for title in ('All Products', 'Status Report', 'Changes', 'Needs review'):
                book.sheets.append(Sheet(title, len(book.sheets), [['Preview'], ['preview1']]))
            client = create_app(Path(folder) / 'previews').test_client()
            with patch('server.target_worksheet', return_value=(book, book.sheets[0])):
                self.assertEqual(client.get('/api/monthly-orders').json['rows'][0]['SLA Missed'], 1)
                book.worksheet(TRACKER_TITLES[0]).values[1][TRACKER_COLUMNS.index('Free Site')] = 'On Time'
                self.assertEqual(client.get('/api/monthly-orders').json['rows'][0]['SLA On Time'], 1)
                live = client.get('/api/live-sheets')
                self.assertEqual(live.status_code, 200)
                self.assertEqual(live.json['sheets']['Overview']['rows'][0]['Free Site'], 'On Time')
                self.assertEqual(client.get('/api/daily-orders').json['rows'][0]['Today Orders'], 1)

    def test_reports_do_not_fall_back_to_previews_when_sheets_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            client = create_app(Path(folder) / 'previews').test_client()
            with patch('server.target_worksheet', side_effect=RuntimeError('Offline')):
                self.assertEqual(client.get('/api/monthly-orders').status_code, 502)
                self.assertEqual(client.get('/api/daily-orders').status_code, 502)
