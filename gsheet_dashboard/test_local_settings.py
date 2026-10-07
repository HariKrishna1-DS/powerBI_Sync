import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import local_settings
import server
import sync_config


@unittest.skipUnless(os.name == 'nt', 'Windows encrypted connection storage')
class LocalSettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        environment = patch.dict(os.environ, {'DATATRACE_DESKTOP': '0', 'GOOGLE_SERVICE_ACCOUNT_JSON': '',
                                              'DATATRACE_PASSWORD': '', 'RENDER': ''})
        environment.start()
        self.addCleanup(environment.stop)
        base = patch.object(server, 'BASE_DIR', self.root)
        base.start()
        self.addCleanup(base.stop)
        self.app = server.create_app(self.root / 'previews')
        self.client = self.app.test_client()
        self.settings = self.client.get('/api/local/settings').json
        self.headers = {'X-Settings-Token': self.settings['csrfToken']}

    def key(self):
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return json.dumps({'type': 'service_account', 'project_id': 'fixture',
                           'client_email': 'test@fixture.iam.gserviceaccount.com',
                           'private_key': private.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
                           'token_uri': 'https://oauth2.googleapis.com/token'})

    def test_save_masks_secrets_and_survives_restart_with_blank_password(self):
        raw = self.key()
        payload = dict(self.settings, spreadsheetId='https://docs.google.com/spreadsheets/d/' + 'a' * 30 + '/edit#gid=2',
                       password='private-fixture-password', serviceAccount=raw)
        result = self.client.post('/api/local/settings', json=payload, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(result.json['spreadsheetId'], 'a' * 30)
        self.assertTrue(result.json['passwordSet'])
        self.assertNotIn('password', result.json)
        self.assertNotIn('serviceAccount', result.json)
        vault = (self.root / 'settings.vault.browser').read_bytes()
        self.assertNotIn(b'private-fixture-password', vault)
        self.assertNotIn(b'PRIVATE KEY', vault)
        result = self.client.post('/api/local/settings', json=dict(result.json, password=''), headers=self.headers)
        self.assertEqual(result.status_code, 200)
        os.environ['DATATRACE_PASSWORD'] = ''
        local_settings.load_environment(self.root)
        self.assertEqual(os.environ['DATATRACE_PASSWORD'], 'private-fixture-password')
        self.assertEqual(json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON']), json.loads(raw))
        import datatrace_sync
        self.assertEqual(datatrace_sync.SPREADSHEET_ID, 'a' * 30)

    def test_settings_reject_remote_cross_origin_and_missing_token(self):
        self.assertEqual(self.client.get('/api/local/settings', base_url='http://evil.example').status_code, 403)
        self.assertEqual(self.client.get('/api/local/settings', environ_base={'REMOTE_ADDR': '192.168.1.2'}).status_code, 403)
        self.assertEqual(self.client.get('/api/local/settings', headers={'Origin': 'http://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/api/local/settings', json=self.settings).status_code, 403)
        self.assertEqual(self.client.post('/api/local/check-connection', json={}, headers={'X-Settings-Token': 'wrong'}).status_code, 403)

    def test_validation_does_not_replace_saved_settings(self):
        for changes in ({'spreadsheetId': 'bad'}, {'queueUrl': 'https://example.com'},
                        {'remainingTrackerTitle': self.settings['fullTrackerTitle']}, {'serviceAccount': '{}'}):
            response = self.client.post('/api/local/settings', json=dict(self.settings, **changes), headers=self.headers)
            self.assertEqual(response.status_code, 422, response.json)
        self.assertFalse((self.root / 'settings.vault.browser').exists())
        info = json.loads(self.key())
        info['token_uri'] = 'https://example.com/token'
        with self.assertRaises(ValueError):
            local_settings.service_account(json.dumps(info))

    def test_connection_check_is_read_only_and_reports_failure(self):
        from unittest.mock import Mock
        book = Mock(title='Production')
        book.worksheets.return_value = [Mock(title=title) for title in sync_config.TRACKER_TITLES]
        with patch.object(server, 'target_worksheet', return_value=(book, None)):
            response = self.client.post('/api/local/check-connection', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['missingTrackers'], [])
        self.assertEqual([call[0] for call in book.mock_calls], ['worksheets'])
        with patch.object(server, 'target_worksheet', side_effect=RuntimeError('Invalid JWT Signature')):
            response = self.client.post('/api/local/check-connection', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertIn('Invalid JWT Signature', response.json['error'])


if __name__ == '__main__':
    unittest.main()
