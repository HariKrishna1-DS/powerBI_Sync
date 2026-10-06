import threading
import os
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from gspread.exceptions import WorksheetNotFound
from test_monthly_production import AtomicBook
from sheets_writer import GuardedBook, WriterGuard, SharedWriterGuard, JOB_ID, shared_job


class SharedBook(AtomicBook):
    def __init__(self):
        super().__init__()
        self.mutex = threading.Lock()

    def get_worksheet_by_id(self, number):
        with self.mutex:
            found = next((s for s in self.sheets if s.id == number), None)
            if found is None:
                raise WorksheetNotFound(str(number))
            return found

    def batch_update(self, body):
        with self.mutex:
            return super().batch_update(body)


class SharedPublishingTests(unittest.TestCase):
    def setUp(self):
        self.book = SharedBook()

    def client(self, number):
        return GuardedBook(self.book, f'pc-{number}', shared=True, key=f'simulated-pc-{number}-{id(self)}')

    def test_all_four_computers_can_publish_sequentially_and_legacy_is_blocked(self):
        WriterGuard(self.book, 'old-pc').ensure()
        for number in range(4):
            client = self.client(number)
            with shared_job(client, 'Reports'):
                client.batch_update({'requests': []})
                self.assertIsNotNone(client.writer_guard.job())
            self.assertIsNone(client.writer_guard.job())
        with self.assertRaisesRegex(ValueError, 'another designated'):
            WriterGuard(self.book, 'old-pc').ensure()

    def test_four_simultaneous_computers_have_exactly_one_active_writer(self):
        self.client(0).writer_guard.enable()
        started = threading.Barrier(4)
        release = threading.Event()
        results = []
        def run(number):
            client = self.client(number)
            started.wait(timeout=3)
            try:
                with shared_job(client):
                    results.append(True)
                    release.wait(timeout=2)
            except ValueError:
                results.append(False)
                if len(results) >= 4:
                    release.set()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(run, range(4)))
        self.assertEqual(sorted(results), [False, False, False, True])

    def test_lost_claim_reply_is_verified_and_job_released_after_failure(self):
        client = self.client(1)
        client.writer_guard.enable()
        self.book.lose_reply = True
        with self.assertRaisesRegex(RuntimeError, 'test failure'):
            with shared_job(client):
                client.batch_update({'requests': []})
                raise RuntimeError('test failure')
        self.assertIsNone(client.writer_guard.job())

    def test_recreated_connections_nest_in_the_same_job(self):
        a = self.client(1)
        b = self.client(1)
        with shared_job(a):
            token = a.writer_guard.job()['token']
            with shared_job(b):
                b.batch_update({'requests': []})
            self.assertEqual(a.writer_guard.job()['token'], token)

    def test_failed_unuploaded_captures_do_not_reuse_shared_numbers(self):
        numbers = []
        for number in range(4):
            client = self.client(number)
            with shared_job(client, 'Capture'):
                numbers.append(client.writer_guard.reserve_preview(40))
        self.assertEqual(numbers, [40, 41, 42, 43])
        with shared_job(self.client(0)):
            self.assertEqual(self.client(0).writer_guard.reserve_preview(90), 90)

    def test_old_report_tab_ids_are_preserved_during_shared_migration(self):
        first = self.book.add('All Products', [])
        first.id = 1894260702
        second = self.book.add('Daily Orders', [])
        second.id = 1894260703
        with shared_job(self.client(1)):
            self.client(1).writer_guard.reserve_preview(1)
        self.assertEqual(self.book.worksheet('All Products').id, 1894260702)
        self.assertEqual(self.book.worksheet('Daily Orders').id, 1894260703)

    def test_waiting_computers_finish_sequentially_after_the_slot_is_released(self):
        self.client(0).writer_guard.enable()
        active, maximum = 0, 0
        mutex = threading.Lock()
        def publish(number):
            nonlocal active, maximum
            with shared_job(self.client(number), wait=10):
                with mutex:
                    active += 1
                    maximum = max(maximum, active)
                self.client(number).batch_update({'requests': []})
                with mutex:
                    active -= 1
            return number
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(sorted(pool.map(publish, range(4))), [0, 1, 2, 3])
        self.assertEqual(maximum, 1)

    def test_lost_ownership_and_unreadable_control_never_authorize_writes(self):
        client = self.client(1)
        with shared_job(client):
            sheet = self.book.get_worksheet_by_id(JOB_ID)
            sheet.values[1][1] = 'different-job'
            before = len(self.book.batches)
            with self.assertRaisesRegex(ValueError, 'no longer owned'):
                client.batch_update({'requests': []})
            self.assertEqual(len(self.book.batches), before)
        self.assertEqual(client.writer_guard.job()['token'], 'different-job')
        with self.assertRaisesRegex(ValueError, 'Waiting'):
            with shared_job(self.client(2)):
                self.fail('Never enter another computer\'s job')
        with patch.object(self.book, 'get_worksheet_by_id', side_effect=ConnectionError('offline')):
            with self.assertRaises(ConnectionError):
                SharedWriterGuard(self.book, 'another').enable()

    def test_four_server_captures_reserve_numbers_even_after_unpublished_failure(self):
        import pandas as pd
        from copy import deepcopy
        from preview_store import PreviewStore
        from server import create_app
        history, allocated = [], []
        environment = {'DATATRACE_DESKTOP': '1', 'DATATRACE_DESKTOP_TOKEN': 'synthetic', 'GOOGLE_SERVICE_ACCOUNT_JSON': 'synthetic'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, environment):
            for pc in range(4):
                directory = Path(folder) / str(pc)
                store = PreviewStore(directory / 'previews')
                guarded = self.client(pc)
                def runner(on_progress):
                    saved = store.save(pd.DataFrame([{'Order Number': f'QA-{pc}', 'Product': 'Full Title', 'Task Status': 'Available'}]))
                    allocated.append(saved['id'])
                    return {'preview_id': saved['id']}
                def sync(frame, **kwargs):
                    if pc == 0:
                        raise ValueError('Synthetic failure before upload')
                    history.append(store.get(frame.attrs['preview_id']))
                    return []
                with patch('server.BASE_DIR', directory), patch('server.sync_workbook', side_effect=sync), patch('server.target_worksheet', return_value=(guarded, None)), patch('server.read_preview_history', side_effect=lambda book: deepcopy(history)):
                    app = create_app(runner=runner, time_source=Mock(snapshot=lambda: {}, now=lambda: None))
                    app.extensions['publish_reports'] = lambda: {}
                    client = app.test_client()
                    headers = {'X-DataTrace-Token': 'synthetic'}
                    actual_batch = self.book.batch_update
                    def fail_release(body):
                        if any('deleteSheet' in item for item in body['requests']):
                            raise ConnectionError('Synthetic loss during slot release')
                        return actual_batch(body)
                    if pc == 3:
                        self.book.batch_update = fail_release
                    self.assertEqual(client.post('/api/extract', headers=headers).status_code, 202)
                    limit = time.monotonic() + 5
                    while time.monotonic() < limit:
                        state = client.get('/api/state', headers=headers).json
                        if not state['job']['running']:
                            break
                        time.sleep(.01)
                    self.assertFalse(state['job']['running'])
                    if pc == 0:
                        self.assertIn('before upload', state['job']['result']['error'])
                        self.assertEqual(store.pending_count(), 1)
                    else:
                        self.assertEqual(state['job']['result']['google_sheet'], 'success', state['job'])
                    self.book.batch_update = actual_batch
                    if pc == 3:
                        self.assertIn('slot release could not be confirmed', state['job']['result']['error'])
                        self.assertIsNotNone(guarded.writer_guard.job())
                        actual_batch({'requests': [{'deleteSheet': {'sheetId': JOB_ID}}]})
                    self.assertIsNone(guarded.writer_guard.job())
        self.assertEqual(allocated, [1, 2, 3, 4])
