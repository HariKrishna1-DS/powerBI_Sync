import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from google.auth.credentials import AnonymousCredentials
from gspread.exceptions import APIError
from gspread.http_client import HTTPClient
import pandas as pd
from requests import Response

from preview_store import PreviewStore
from production_cache import ProductionCache
from sheets_transport import QuotaHTTPClient, RequestBudget, SheetsQuotaError, request_context, retry_seconds


def response(code=200, body=None, retry=None):
    result = Response()
    result.status_code = code
    result._content = json.dumps(body or {'error': {'code': code, 'message': 'test failure'}}).encode()
    if retry is not None:
        result.headers['Retry-After'] = str(retry)
    return result


class Clock:
    def __init__(self):
        self.value = 0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class SheetsQuotaTests(unittest.TestCase):
    def client(self):
        client = QuotaHTTPClient(AnonymousCredentials())
        clock = Clock()
        client.budget = RequestBudget(now=clock.now, sleep=clock.sleep)
        return client, clock

    def test_four_clients_stay_under_default_shared_read_quota(self):
        sent = []
        for _ in range(4):
            clock = Clock()
            budget = RequestBudget(now=clock.now, sleep=clock.sleep)
            for _ in range(30):
                budget.acquire('read')
                sent.append(clock.now())
        for start in sorted(set(sent)):
            self.assertLessEqual(sum(start <= stamp < start + 60 for stamp in sent), 48)

    def test_rotated_keys_and_new_connections_share_one_account_budget(self):
        first = QuotaHTTPClient(AnonymousCredentials())
        second = QuotaHTTPClient(AnonymousCredentials())
        self.assertIs(first.budget, second.budget)

    def test_quota_retry_obeys_retry_after_and_preserves_successful_response(self):
        client, clock = self.client()
        success = response(body={'values': [['Order']]})
        with patch.object(HTTPClient, 'request', side_effect=[APIError(response(429, retry=90)), success]) as send:
            self.assertIs(client.request('get', 'https://sheets.googleapis.com/v4/spreadsheets/test/values/A1'), success)
        self.assertEqual(send.call_count, 2)
        self.assertGreaterEqual(clock.now(), 90)

    def test_quota_retries_are_bounded_and_error_is_actionable(self):
        client, clock = self.client()
        with patch.object(HTTPClient, 'request', side_effect=APIError(response(429))) as send:
            with self.assertRaises(SheetsQuotaError) as error:
                client.request('post', 'https://sheets.googleapis.com/v4/spreadsheets/test:batchUpdate', json={})
        self.assertEqual(send.call_count, 3)
        self.assertGreaterEqual(clock.now(), 195)
        self.assertNotIn('credentials', str(error.exception))
        self.assertGreater(error.exception.retry_after, 60)

    def test_unknown_write_outcome_and_permissions_are_not_replayed(self):
        for code in (403, 503):
            client, _ = self.client()
            with patch.object(HTTPClient, 'request', side_effect=APIError(response(code))) as send:
                with self.assertRaises(APIError):
                    client.request('post', 'https://sheets.googleapis.com/v4/spreadsheets/test:batchUpdate', json={})
            self.assertEqual(send.call_count, 1)

    def test_metadata_reused_but_values_and_ownership_always_fresh(self):
        client, _ = self.client()
        root = 'https://sheets.googleapis.com/v4/spreadsheets/test'
        with patch.object(HTTPClient, 'request', return_value=response(body={'sheets': []})) as send:
            client.request('get', root)
            client.request('get', root)
            self.assertEqual(send.call_count, 1)
            for _ in range(2):
                client.request('get', root + '/values/ownership')
            self.assertEqual(send.call_count, 3)
            client.request('post', root + ':batchUpdate', json={})
            client.request('get', root)
            self.assertEqual(send.call_count, 5)

    def test_wait_can_be_interrupted_for_shutdown(self):
        stop = threading.Event()
        stop.set()
        with request_context(stop=stop), self.assertRaisesRegex(RuntimeError, 'interrupted'):
            RequestBudget().acquire('read')

    def test_retry_after_http_date_and_invalid_header(self):
        with patch('sheets_transport.time.time', return_value=0):
            self.assertGreaterEqual(retry_seconds(response(429, retry='Thu, 01 Jan 1970 00:02:00 GMT')), 120)
        self.assertGreaterEqual(retry_seconds(response(429, retry='invalid')), 65)

    def test_existing_271_quota_failures_resume_without_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreviewStore(Path(directory) / 'previews')
            preview = store.save(pd.DataFrame([{'Order Number': 'A'}]))
            store.mark_failed(preview['id'], "APIError: [429]: Quota exceeded for quota metric 'Read requests'")
            reopened = PreviewStore(store.root)
            self.assertEqual(reopened.pending_syncs(), [preview['id']])
            self.assertTrue(reopened.failed_syncs()[0]['automatic_retry'])
            self.assertEqual(reopened.get(preview['id'])['rows'], [{'Order Number': 'A'}])

    def test_deferred_retry_persists_and_blocks_newer_captures(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreviewStore(Path(directory) / 'previews')
            first = store.save(pd.DataFrame([{'Order Number': 'A'}]))
            second = store.save(pd.DataFrame([{'Order Number': 'B'}]))
            with patch('time.time', return_value=100):
                store.defer_sync(first['id'], 'Google Sheets busy', 90)
                store.defer_sync(first['id'], 'same attempt', 90)
                self.assertEqual(PreviewStore(store.root).pending_syncs(), [])
                with store.connect() as db:
                    self.assertEqual(db.execute('SELECT attempts FROM sync_retry').fetchone()[0], 1)
            with patch('time.time', return_value=191):
                self.assertEqual(store.pending_syncs(), [first['id'], second['id']])
            store.mark_synced(first['id'])
            self.assertEqual(store.failed_syncs(), [])

    def test_recovery_cap_requires_manual_retry_without_losing_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PreviewStore(Path(directory) / 'previews')
            preview = store.save(pd.DataFrame([{'Order Number': 'A'}]))
            for attempt in range(6):
                with patch('time.time', return_value=100 + attempt * 1000):
                    store.defer_sync(preview['id'], 'Google Sheets busy', 65)
            self.assertFalse(store.failed_syncs()[0]['automatic_retry'])
            self.assertEqual(store.pending_syncs(), [])
            self.assertEqual(store.get(preview['id'])['rows'], [{'Order Number': 'A'}])
            store.reset_retry(preview['id'])
            with patch('time.time', return_value=10000):
                store.defer_sync(preview['id'], 'Google Sheets busy', 65)
            self.assertTrue(store.failed_syncs()[0]['automatic_retry'])

    def test_background_refresh_does_not_block_cached_reads_or_duplicate_work(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProductionCache(Path(directory) / 'cache.json', 'fixture')
            first = cache.get(lambda: {'sheets': {'Overview': {'rows': [{'Order Number': 'A'}]}}})
            started, release = threading.Event(), threading.Event()
            def load():
                started.set()
                release.wait(3)
                return {'sheets': {'Overview': {'rows': [{'Order Number': 'B'}]}}}
            loader = Mock(side_effect=load)
            before = time.monotonic()
            waiting = cache.get(loader, force=True, background=True)
            self.assertLess(time.monotonic() - before, .5)
            self.assertTrue(started.wait(1))
            self.assertTrue(waiting['refreshing'])
            self.assertEqual(waiting['updated_at'], first['updated_at'])
            for _ in range(4):
                cache.get(loader, force=True, background=True)
            self.assertEqual(loader.call_count, 1)
            release.set()
            fresh = cache.get(loader)
            self.assertEqual(fresh['sheets']['Overview']['rows'][0]['Order Number'], 'B')

    def test_force_cannot_bypass_quota_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProductionCache(Path(directory) / 'cache.json', 'fixture')
            first = cache.get(lambda: {'sheets': {}})
            loader = Mock(side_effect=SheetsQuotaError(90))
            for _ in range(5):
                result = cache.get(loader, force=True)
            self.assertEqual(loader.call_count, 1)
            self.assertTrue(result['offline'])
            self.assertEqual(result['updated_at'], first['updated_at'])
            self.assertGreater(result['retry_after'], 0)
