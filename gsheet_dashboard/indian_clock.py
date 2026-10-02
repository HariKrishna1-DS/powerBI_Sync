"""Network time advanced by a monotonic clock, independent of PC wall time."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import threading
import time
import uuid

import requests

IST = timezone(timedelta(hours=5, minutes=30), 'IST')


class IndianClock:
    def __init__(self, session=None, monotonic=time.monotonic):
        self.session = session or requests.Session()
        self.monotonic = monotonic
        self.lock = threading.Lock()
        self.epoch = self.anchor = None
        self.last_attempt = float('-inf')
        self.refreshing = False
        self.source = None
        self.error = None

    def synchronize(self):
        """Acquire fresh HTTPS response time; retain a valid anchor on failure."""
        try:
            started = self.monotonic()
            response = self.session.head(
                'https://www.google.com/generate_204',
                params={'clock': uuid.uuid4().hex},
                headers={'Cache-Control': 'no-cache, no-store'}, timeout=5)
            response.raise_for_status()
            received = self.monotonic()
            remote = parsedate_to_datetime(response.headers['Date'])
            if remote.tzinfo is None:
                raise ValueError('Network time did not include its timezone')
            # HTTP Date has one-second precision. Account for transit without
            # ever consulting datetime.now() or time.time().
            with self.lock:
                self.epoch = remote.timestamp() + 0.5 + (received - started) / 2
                self.anchor = received
                self.source = 'Google HTTPS time'
                self.error = None
            return True
        except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
            with self.lock:
                self.error = f'Network time unavailable: {type(exc).__name__}'
            return False
        finally:
            with self.lock:
                self.last_attempt = self.monotonic()
                self.refreshing = False

    def refresh(self):
        with self.lock:
            interval = 30 if self.error or self.epoch is None else 300
            if self.refreshing or self.monotonic() - self.last_attempt < interval:
                return
            self.refreshing = True
            self.last_attempt = self.monotonic()
        threading.Thread(target=self.synchronize, daemon=True).start()

    def snapshot(self):
        self.refresh()
        with self.lock:
            elapsed = self.monotonic() - self.anchor if self.anchor is not None else None
            return {'epoch_ms': (self.epoch + elapsed) * 1000 if elapsed is not None else None,
                    'timezone': 'Asia/Kolkata', 'source': self.source,
                    'synchronized': self.epoch is not None, 'refresh_error': self.error}

    def now(self):
        snapshot = self.snapshot()
        return datetime.fromtimestamp(snapshot['epoch_ms'] / 1000, IST) if snapshot['synchronized'] else None
