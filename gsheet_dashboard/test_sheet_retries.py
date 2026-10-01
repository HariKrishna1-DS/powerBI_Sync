import json
import unittest
from unittest.mock import Mock, patch

import pandas as pd
from requests import Response
from requests.exceptions import ReadTimeout
from gspread.exceptions import APIError

import datatrace_sync as sync


def api_error(code):
    response = Response()
    response.status_code = code
    response._content = json.dumps({'error': {'code': code, 'message': 'Test response',
                                             'status': 'PERMISSION_DENIED'}}).encode()
    return APIError(response)


class SheetRetryTests(unittest.TestCase):
    def fixture(self):
        frame = pd.DataFrame([{'Task Status': 'Available', 'Order Number': '001'}])
        sheet = Mock(id=0, row_count=1, col_count=4, title='Full Title')
        sheet.get_all_values.return_value = [list(frame.columns)] + frame.values.tolist()
        return frame, Mock(), sheet

    def test_timeout_replays_same_idempotent_dimensions_and_verifies(self):
        frame, book, sheet = self.fixture()
        book.batch_update.side_effect = [ReadTimeout('Test'), None]
        progress = Mock()
        with patch('datatrace_sync.time.sleep') as sleep:
            self.assertEqual(sync.sync_dataframe(frame, (book, sheet), validate=False, on_progress=progress), 'Full Title')
        self.assertEqual(book.batch_update.call_count, 2)
        self.assertEqual(book.batch_update.call_args_list[0], book.batch_update.call_args_list[1])
        requests = book.batch_update.call_args.args[0]['requests']
        self.assertIn('updateSheetProperties', requests[0])
        self.assertFalse(any('appendDimension' in request or 'deleteDimension' in request for request in requests))
        sleep.assert_called_once_with(1)
        self.assertTrue(any('retrying Full Title' in call.args[0] for call in progress.call_args_list))
        self.assertEqual(progress.call_args.args[0], 'Verifying Full Title')

    def test_repeated_timeout_reports_timeout_without_permission_advice(self):
        frame, book, sheet = self.fixture()
        book.batch_update.side_effect = ReadTimeout('Test')
        with patch('datatrace_sync.time.sleep'), self.assertRaisesRegex(RuntimeError, 'timed out.*Full Title') as caught:
            sync.sync_dataframe(frame, (book, sheet), validate=False)
        self.assertEqual(book.batch_update.call_count, 2)
        self.assertNotIn('Editor', str(caught.exception))
        self.assertIn('may have completed', str(caught.exception))

    def test_permission_error_is_not_retried(self):
        frame, book, sheet = self.fixture()
        book.batch_update.side_effect = api_error(403)
        with patch('datatrace_sync.time.sleep') as sleep, self.assertRaisesRegex(RuntimeError, 'denied.*Full Title'):
            sync.sync_dataframe(frame, (book, sheet), validate=False)
        book.batch_update.assert_called_once()
        sleep.assert_not_called()

    def test_quota_error_retries_once(self):
        frame, book, sheet = self.fixture()
        book.batch_update.side_effect = [api_error(429), None]
        with patch('datatrace_sync.time.sleep'):
            sync.sync_dataframe(frame, (book, sheet), validate=False)
        self.assertEqual(book.batch_update.call_count, 2)

    def test_update_range_clears_trailing_old_rows_and_is_bounded(self):
        frame, book, sheet = self.fixture()
        sheet.row_count = 1000
        previous = [list(frame.columns), ['Available', '001'], ['Available', '002']]
        sync.sync_dataframe(frame, (book, sheet), validate=False, existing_values=previous)
        update = book.batch_update.call_args.args[0]['requests'][-1]['updateCells']
        self.assertEqual(update['range']['endRowIndex'], 3)
        self.assertEqual(len(update['rows']), 2)


if __name__ == '__main__':
    unittest.main()
