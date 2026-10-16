"""Google authentication failures are actionable without exposing credentials."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from google.auth.exceptions import RefreshError, TransportError

import datatrace_sync as sync
from server import create_app


class GoogleAuthTests(unittest.TestCase):
    def fail_auth(self, description, hosted=False):
        failure = RefreshError('secret raw response', {
            'error': 'invalid_grant', 'error_description': description,
        })
        client = Mock()
        client.open_by_key.side_effect = failure
        with patch.dict(sync.os.environ, {'RENDER': '1' if hosted else '', 'GOOGLE_SERVICE_ACCOUNT_JSON': json.dumps({
            'client_email': 'test@example.iam.gserviceaccount.com',
            'private_key_id': 'fixture-key-id',
            'private_key': 'secret private key',
        })}), patch('google.oauth2.service_account.Credentials.from_service_account_info'), \
                patch('gspread.authorize', return_value=client):
            with self.assertRaises(RuntimeError) as caught:
                sync.target_worksheet()
        return str(caught.exception)

    def test_invalid_signature_points_to_key_replacement(self):
        message = self.fail_auth('Invalid JWT Signature.')
        self.assertIn('Invalid JWT Signature', message)
        self.assertIn('Replace key', message)
        self.assertIn('fixture-key-id', message)
        self.assertIn('Save settings', message)
        self.assertNotIn('GOOGLE_SERVICE_ACCOUNT_JSON', message)
        self.assertNotIn('secret', message)
        self.assertNotIn('worksheet gid', message)

    def test_hosted_signature_failure_points_to_environment(self):
        message = self.fail_auth('Invalid JWT Signature.', hosted=True)
        self.assertIn('GOOGLE_SERVICE_ACCOUNT_JSON', message)
        self.assertNotIn('Connections & settings', message)

    def test_transport_failure_reports_network_without_raw_details(self):
        client = Mock()
        client.open_by_key.side_effect = TransportError('secret proxy response')
        with patch.dict(sync.os.environ, {'GOOGLE_SERVICE_ACCOUNT_JSON': '{}'}), \
                patch('google.oauth2.service_account.Credentials.from_service_account_info'), \
                patch('gspread.authorize', return_value=client):
            with self.assertRaises(RuntimeError) as caught:
                sync.target_worksheet()
        self.assertIn('firewall or proxy', str(caught.exception))
        self.assertNotIn('secret', str(caught.exception))

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
