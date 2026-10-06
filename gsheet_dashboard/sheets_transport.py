"""Shared per-account request budgets and bounded Sheets quota recovery.

Four installations each reserve at most 12 reads/writes per rolling minute.
This leaves headroom under Google's default 60/user/minute quota. This is a
client budget, not a distributed lock; publishing ownership remains mandatory.
"""
from collections import deque
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
import json
import random
import threading
import time

from gspread.exceptions import APIError
from gspread.http_client import HTTPClient


class SheetsQuotaError(RuntimeError):
    def __init__(self, retry_after=65):
        self.retry_after = max(1, int(retry_after))
        super().__init__('Google Sheets is temporarily limiting requests. Your saved data is safe. '
                         f'Sync will retry automatically after about {self.retry_after} seconds. '
                         'Your connection settings do not need changing.')


_context = threading.local()
_budgets = {}
_budgets_lock = threading.Lock()


@contextmanager
def request_context(progress=None, stop=None):
    previous = getattr(_context, 'value', (None, None))
    _context.value = (progress, stop)
    try:
        yield
    finally:
        _context.value = previous


class RequestBudget:
    def __init__(self, limit=12, window=61, now=time.monotonic, sleep=time.sleep):
        self.limit, self.window, self.now, self.sleep = limit, window, now, sleep
        self.lock = threading.Lock()
        self.events = {'read': deque(), 'write': deque()}
        self.cooldown = 0

    def pause(self, seconds):
        with self.lock:
            self.cooldown = max(self.cooldown, self.now() + seconds)

    def acquire(self, kind):
        while True:
            progress, stop = getattr(_context, 'value', (None, None))
            if stop is not None and stop.is_set():
                raise RuntimeError('Sync interrupted; saved data was retained.')
            with self.lock:
                now = self.now()
                queue = self.events[kind]
                while queue and queue[0] <= now - self.window:
                    queue.popleft()
                delay = max(0, self.cooldown - now,
                            queue[0] + self.window - now if len(queue) >= self.limit else 0)
                if delay <= 0:
                    queue.append(now)
                    return
            if progress:
                progress(f'Waiting for Google Sheets request capacity (about {int(delay) + 1}s). Saved data is retained.')
            if stop is not None:
                stop.wait(min(delay, 5))
            else:
                self.sleep(min(delay, 5))


def retry_seconds(response, attempt=0):
    value = response.headers.get('Retry-After', '')
    try:
        requested = float(value)
    except (TypeError, ValueError):
        try:
            requested = parsedate_to_datetime(value).timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            requested = 0
    return max(requested, min(130, 65 * (2 ** attempt))) + random.uniform(0, 3)


class QuotaHTTPClient(HTTPClient):
    def __init__(self, auth, session=None):
        super().__init__(auth, session=session)
        # Keys rotating must not create a fresh quota bucket for the same account.
        identity = (getattr(auth, 'service_account_email', None), getattr(auth, 'quota_project_id', None))
        with _budgets_lock:
            self.budget = _budgets.setdefault(identity, RequestBudget())
        self.metadata = {}

    def clear_metadata(self):
        self.metadata.clear()

    def request(self, method, endpoint, **kwargs):
        read = method.lower() == 'get'
        # Only metadata is cached briefly. Values, lock tokens and receipts must
        # always be fetched from Google, including before every guarded write.
        is_metadata = read and '/spreadsheets/' in endpoint and '/' not in endpoint.split('/spreadsheets/', 1)[1] and ':' not in endpoint.rsplit('/', 1)[-1]
        key = (endpoint, json.dumps(kwargs.get('params'), sort_keys=True))
        cached = self.metadata.get(key) if is_metadata else None
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        if not read:
            self.clear_metadata()
        for attempt in range(3):
            self.budget.acquire('read' if read else 'write')
            try:
                result = super().request(method, endpoint, **kwargs)
                if is_metadata:
                    self.metadata[key] = (time.monotonic(), result)
                return result
            except APIError as exc:
                # A quota rejection did not apply the request. Other write
                # errors/timeouts can have committed and belong to receipt logic.
                if exc.code != 429:
                    raise
                delay = retry_seconds(exc.response, attempt)
                self.budget.pause(delay)
                if attempt == 2:
                    raise SheetsQuotaError(delay) from exc


def clear_book_metadata(book):
    client = getattr(book, 'client', None)
    if isinstance(client, QuotaHTTPClient):
        client.clear_metadata()
