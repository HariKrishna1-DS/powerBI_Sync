"""Credential scanning covers actual/JSON keys without leaking matched text."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('release_secret_scan', Path(__file__).resolve().parents[1] / 'desktop' / 'secret_scan.py')
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class ReleaseSecretTests(unittest.TestCase):
    def test_private_keys_and_tokens_are_blocked_without_echoing_them(self):
        key = b'-----BEGIN PRIVATE KEY-----\n' + b'A' * 256 + b'\n-----END PRIVATE KEY-----'
        for data in (key, key.replace(b'\n', b'\\n'), b'ghp_' + b'Z' * 36):
            with self.assertRaisesRegex(ValueError, 'Secret value withheld') as error:
                scanner.check_bytes('example.txt', data)
            self.assertNotIn('A' * 32, str(error.exception))
            self.assertNotIn('Z' * 32, str(error.exception))

    def test_placeholders_and_redaction_fixtures_remain_usable(self):
        scanner.check_bytes('fixture.txt', b'-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----')
        scanner.check_bytes('example.env', b'GITHUB_TOKEN=your-token-here')
