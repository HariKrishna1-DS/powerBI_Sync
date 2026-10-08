"""Resume saved captures after authentication recovers without retrying conflicts."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

from preview_store import PreviewStore
from server import create_app


class ConnectionSyncRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / 'previews'
        self.store = PreviewStore(self.root)
        self.store.restore(1, ['Order Number', 'Product', 'Task Name', 'Task Status'],
                           [{'Order Number': 'FIXTURE-1', 'Product': 'Full Search',
                             'Task Name': 'Search', 'Task Status': 'Available'}])
        self.syncer = Mock(return_value=['Tracker'])
        self.app = create_app(self.root, syncer=self.syncer)
        self.resume = self.app.extensions['resume_connection_sync']

    def test_working_connection_resumes_oldest_authentication_failure(self):
        self.store.mark_failed(1, 'Google Sheets authentication failed: Invalid JWT Signature.')
        self.assert_resumes_saved_capture()

    def test_working_connection_resumes_missing_key_failure(self):
        self.store.mark_failed(1, 'Set GOOGLE_SERVICE_ACCOUNT_JSON to a valid service account JSON file or JSON object.')
        self.assert_resumes_saved_capture()

    def assert_resumes_saved_capture(self):
        with patch('server.target_worksheet', return_value=(Mock(), None)) as connection:
            self.assertTrue(self.resume())
        deadline = time.monotonic() + 5
        while self.app.test_client().get('/api/health').json['running'] and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertEqual(self.store.pending_count(), 0)
        self.assertEqual(self.store.failed_syncs(), [])
        self.syncer.assert_called_once()
        connection.assert_called_once()

    def test_rejected_key_does_not_write_and_checks_are_throttled(self):
        self.store.mark_failed(1, 'Google Sheets authentication failed: Invalid JWT Signature.')
        with patch('server.target_worksheet', side_effect=RuntimeError('Invalid JWT Signature')) as connection:
            self.assertFalse(self.resume())
            self.assertFalse(self.resume())
        connection.assert_called_once()
        self.syncer.assert_not_called()
        self.assertEqual(self.store.pending_count(), 1)

    def test_validation_conflict_stays_blocked_without_network_or_write(self):
        self.store.mark_failed(1, 'Duplicate Order Number needs review.')
        with patch('server.target_worksheet') as connection:
            self.assertFalse(self.resume())
        connection.assert_not_called()
        self.syncer.assert_not_called()
        self.assertEqual(self.store.pending_count(), 1)

    def test_earlier_unresolved_conflict_blocks_later_authentication_failure(self):
        self.store.mark_failed(1, 'Duplicate Order Number needs review.')
        self.store.restore(2, ['Order Number'], [{'Order Number': 'FIXTURE-2'}])
        self.store.mark_failed(2, 'Google Sheets authentication failed: Invalid JWT Signature.')
        with patch('server.target_worksheet') as connection:
            self.assertFalse(self.resume())
        connection.assert_not_called()
        self.syncer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
