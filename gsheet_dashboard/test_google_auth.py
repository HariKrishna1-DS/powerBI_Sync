"""Google authentication failures are actionable without exposing credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from google.auth.exceptions import RefreshError

import datatrace_sync as sync
from server import create_app


class GoogleAuthTests(unittest.TestCase):
    def fail_auth(self, description):
        failure = RefreshError('secret raw response', {
            'error': 'invalid_grant', 'error_description': description,
        })
        client = Mock()
        client.open_by_key.side_effect = failure
        with patch.dict(sync.os.environ, {'GOOGLE_SERVICE_ACCOUNT_JSON': json.dumps({
            'client_email': 'test@example.iam.gserviceaccount.com',
            'private_key': 'secret private key',
        })}), patch('google.oauth2.service_account.Credentials.from_service_account_info'), \
                patch('gspread.authorize', return_value=client):
            with self.assertRaises(RuntimeError) as caught:
                sync.target_worksheet()
        return str(caught.exception)

    def test_invalid_signature_points_to_key_replacement(self):
        message = self.fail_auth('Invalid JWT Signature.')
        self.assertIn('Invalid JWT Signature', message)
        self.assertIn('GOOGLE_SERVICE_ACCOUNT_JSON', message)
        self.assertNotIn('secret', message)
        self.assertNotIn('worksheet gid', message)

    def test_clock_skew_points_to_server_time(self):
        message = self.fail_auth('Invalid JWT: Token must be a short-lived token and in a reasonable timeframe.')
        self.assertIn('server clock', message)

    def test_unknown_error_does_not_expose_raw_response(self):
        message = self.fail_auth('secret response content')
        self.assertIn('key are active', message)
        self.assertNotIn('secret', message)

    def test_live_sheet_endpoint_returns_json_error(self):
        with tempfile.TemporaryDirectory() as root:
            client = create_app(Path(root) / 'previews').test_client()
            with patch('server.target_worksheet', side_effect=RuntimeError('Replace the service-account JSON.')):
                response = client.get('/api/live-sheets')
            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json, {'error': 'Replace the service-account JSON.'})


if __name__ == '__main__':
    unittest.main()
