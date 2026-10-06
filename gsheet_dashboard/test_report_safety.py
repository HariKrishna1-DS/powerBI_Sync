"""Failure, concurrency and restart contracts for production reports."""
from io import BytesIO
import logging
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from flask import Flask, jsonify
from gspread.exceptions import WorksheetNotFound
from preview_store import PreviewStore
from report_routes import register_report_routes
from report_workspace import ReportWorkspace
from sheets_writer import WriterGuard, CONTROL_ID
from test_report_workspace import workbook, order
from test_monthly_production import AtomicBook


class WriterBook(AtomicBook):
    def get_worksheet_by_id(self, identity):
        for sheet in self.sheets:
            if sheet.id == identity:
                return sheet
        raise WorksheetNotFound(str(identity))


class ReportSafetyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = PreviewStore(Path(folder.name) / 'previews')
        self.gate = threading.Lock()
        self.book = WriterBook()
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_error_handler(ValueError, lambda error: (jsonify(error=str(error)), 422))
        def tracker(**kwargs):
            return {'source': 'Google Sheets', 'offline': True, 'reports': {'daily': [], 'monthly': []}}
        register_report_routes(self.app, self.store, self.gate, threading.Event(), tracker,
                               lambda: (self.book, None), 'test-only')
        self.workspace = self.app.extensions['report_workspace']
        self.client = self.app.test_client()

    def wait_publish(self):
        self.assertTrue(self.gate.acquire(timeout=5), 'Publisher did not release operation gate')
        self.gate.release()

    def test_source_switch_failed_publish_keeps_local_import_and_retry_succeeds(self):
        response = self.client.post('/api/reporting/import', data={'files': (BytesIO(workbook([order('A')])), 'a.xlsx')})
        self.assertEqual(response.status_code, 200)
        identity = response.json['id']
        self.book.fail_before = True
        response = self.client.post('/api/reporting/source', json={'source': 'import', 'import_id': identity})
        self.assertEqual(response.status_code, 202)
        self.wait_publish()
        self.assertEqual(self.workspace.preferences()['publish_status'], 'failed')
        self.assertEqual(self.workspace.preferences()['source'], 'import')
        self.assertEqual(self.store.list(), [])
        self.assertEqual(self.client.get('/api/reporting/day-link?date=2026-10-01').status_code, 422)
        self.book.fail_before = False
        self.client.post('/api/reporting/publish')
        self.wait_publish()
        self.assertEqual(self.workspace.preferences()['publish_status'], 'published')
        self.assertIn('&range=A2:I2', self.client.get('/api/reporting/day-link?date=2026-10-01').json['url'])

    def test_invalid_requests_and_busy_operation_leave_source_unchanged(self):
        for value in ([], {'source': 'bad'}, {'source': 'import', 'import_id': 'missing'}):
            self.assertEqual(self.client.post('/api/reporting/source', json=value).status_code, 422)
        self.gate.acquire()
        try:
            self.assertEqual(self.client.post('/api/reporting/source', json={'source': 'tracker'}).status_code, 409)
        finally:
            self.gate.release()
        self.assertEqual(self.workspace.preferences()['revision'], 0)

    def test_offline_tracker_never_overwrites_sheets_and_restart_exposes_retry(self):
        self.client.post('/api/reporting/publish')
        self.wait_publish()
        self.assertEqual(self.book.batches, [])
        self.assertEqual(self.workspace.preferences()['publish_status'], 'failed')
        self.workspace.update(publish_status='publishing')
        restarted = ReportWorkspace(self.store)
        self.assertEqual(restarted.preferences()['publish_status'], 'failed')
        self.assertIn('interrupted', restarted.preferences()['publish_error'])

    def test_writer_claim_lost_reply_and_other_computer_is_read_only(self):
        self.book.lose_reply = True
        WriterGuard(self.book, 'computer-A').ensure()
        before = len(self.book.batches)
        with self.assertRaisesRegex(ValueError, 'another designated'):
            WriterGuard(self.book, 'computer-B').ensure()
        self.assertEqual(len(self.book.batches), before)
        self.assertEqual(self.book.get_worksheet_by_id(CONTROL_ID).get_all_values()[1][1], 'computer-A')

    def test_failed_or_malformed_writer_control_never_authorizes(self):
        self.book.fail_before = True
        with self.assertRaises(ValueError):
            WriterGuard(self.book, 'A').ensure()
        self.book.fail_before = False
        sheet = self.book.add('__TvTracker_Writer', [])
        sheet.id = CONTROL_ID
        sheet.values = [['Protocol', 'Writer'], []]
        with self.assertRaisesRegex(ValueError, 'invalid'):
            WriterGuard(self.book, 'A').ensure()

    def test_existing_connection_stops_when_writer_changes_or_check_fails(self):
        from sheets_writer import GuardedBook
        connection = GuardedBook(self.book, 'A')
        connection.writer_guard.ensure()
        sheet = self.book.get_worksheet_by_id(CONTROL_ID)
        sheet.values[1][1] = 'B'
        before = len(self.book.batches)
        with self.assertRaisesRegex(ValueError, 'another designated'):
            connection.batch_update({'requests': []})
        self.assertEqual(len(self.book.batches), before)
        sheet.values[1][1] = 'A'
        with patch.object(self.book, 'get_worksheet_by_id', side_effect=ConnectionError('offline')):
            with self.assertRaises(ConnectionError):
                connection.batch_update({'requests': []})
        self.assertEqual(len(self.book.batches), before)
        connection.batch_update({'requests': []})
        self.assertEqual(len(self.book.batches), before + 1)

    def test_simultaneous_computers_cannot_both_claim_writer(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier, commit_lock = threading.Barrier(2), threading.Lock()
        book = self.book
        original = book.batch_update
        def atomic(body):
            with commit_lock:
                return original(body)
        book.batch_update = atomic
        class RacingGuard(WriterGuard):
            first = True
            def owner(self):
                result = super().owner()
                if self.first:
                    self.first = False
                    barrier.wait(timeout=3)
                return result
        def claim(identity):
            try:
                RacingGuard(book, identity).ensure()
                return True
            except ValueError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(claim, ['A', 'B'])), [False, True])

    def test_redacts_secrets_even_when_only_private_key_is_logged(self):
        from redaction import RedactingFormatter
        secret = '-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----\n'
        with patch.dict(os.environ, {'DATATRACE_PASSWORD': 'pass-secret', 'GOOGLE_SERVICE_ACCOUNT_JSON': '{}'}):
            record = logging.LogRecord('test', logging.ERROR, '', 1, '%s %s', ('pass-secret', secret), None)
            output = RedactingFormatter().format(record)
            self.assertNotIn('pass-secret', output)
            self.assertNotIn('SECRET', output)

    def test_retention_preserves_unsynced_and_active_data_and_archive_restores(self):
        from workspace_retention import archive_history
        from workspace_backup import restore_backup
        with self.store.connect() as db:
            for number in range(1, 6):
                db.execute('INSERT INTO previews VALUES(?,?,?,?,?)', (number, '2026-10-01T10:00:00Z', 'fixture', '["Order Number"]', '[{"Order Number":"A"}]'))
                if number != 1:
                    db.execute('INSERT INTO sync_jobs VALUES(?,?)', (number, 'synced'))
        ids = [self.workspace.save_import([(f'{i}.xlsx', workbook([order(str(i))]))])['id'] for i in range(3)]
        self.workspace.update(publish_status='published', published={'daily_gid': 1, 'daily_dates': ['2026-10-01']})
        result = archive_history(self.store, active_import=ids[0], keep_captures=2, keep_imports=1)
        self.assertEqual(result['archived_captures'], 2)
        self.assertEqual(result['archived_imports'], 1)
        self.assertEqual([p['id'] for p in self.store.list()], [5, 4, 1])
        raw = (self.store.root.parent / 'backups' / result['backup']).read_bytes()
        restore_backup(self.store, raw)
        self.assertEqual(len(self.store.list()), 5)
        self.assertEqual(len(self.workspace.imports()), 3)
        self.assertEqual(self.workspace.preferences()['publish_status'], 'pending')
        self.assertIsNone(self.workspace.preferences()['published'])

    def test_archive_failure_does_not_remove_any_history(self):
        from workspace_retention import archive_history
        with self.store.connect() as db:
            for number in range(1, 4):
                db.execute('INSERT INTO previews VALUES(?,?,?,?,?)', (number, '2026-10-01T10:00:00Z', 'fixture', '[]', '[]'))
                db.execute('INSERT INTO sync_jobs VALUES(?,?)', (number, 'synced'))
        with patch('workspace_retention.make_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                archive_history(self.store, keep_captures=2)
        self.assertEqual(len(self.store.list()), 3)
        with patch('workspace_backup.os.fsync', side_effect=OSError('disk full during flush')):
            with self.assertRaises(OSError):
                archive_history(self.store, keep_captures=2)
        self.assertEqual(len(self.store.list()), 3)
        self.assertEqual(list((self.store.root.parent / 'backups').iterdir()), [])

    def test_backup_flush_failure_preserves_previous_backup(self):
        from workspace_backup import write_verified_backup
        target = self.store.root.parent / 'backup.zip'
        target.write_bytes(b'previous archive')
        with patch('workspace_backup.os.fsync', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                write_verified_backup(target, b'new archive')
        self.assertEqual(target.read_bytes(), b'previous archive')
        self.assertEqual(list(target.parent.glob('backup.zip.*.tmp')), [])

    def test_backup_readback_failure_preserves_previous_backup(self):
        from workspace_backup import write_verified_backup
        target = self.store.root.parent / 'backup.zip'
        target.write_bytes(b'previous archive')
        with patch('workspace_backup.Path.read_bytes', return_value=b'truncated'):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                write_verified_backup(target, b'new archive')
        self.assertEqual(target.read_bytes(), b'previous archive')
        self.assertEqual(list(target.parent.glob('backup.zip.*.tmp')), [])
        write_verified_backup(target, b'new archive')
        self.assertEqual(target.read_bytes(), b'new archive')


if __name__ == '__main__':
    unittest.main()
