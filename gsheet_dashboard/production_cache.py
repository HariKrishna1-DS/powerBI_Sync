"""Bounded, explicitly dated copies of Google Sheets data for offline reading."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time


class ProductionCache:
    def __init__(self, path, identity, ttl=30):
        self.path, self.identity, self.ttl = Path(path), identity, ttl
        self.lock = threading.Lock()
        self.checked = float('-inf')
        self.value = None
        self.error = None
        self.reload()

    def reload(self):
        self.value = None
        self.error = None
        self.checked = float('-inf')
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if saved.get('identity') == self.identity and isinstance(saved.get('sheets'), dict):
                self.value = saved
        except (OSError, ValueError):
            pass

    def invalidate(self):
        with self.lock:
            self.checked = float('-inf')

    def get(self, loader, force=False):
        with self.lock:
            if force or time.monotonic() - self.checked >= self.ttl:
                try:
                    value = dict(loader(), identity=self.identity, updated_at=datetime.now(timezone.utc).isoformat())
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = self.path.with_suffix('.tmp')
                    temporary.write_text(json.dumps(value), encoding='utf-8')
                    temporary.replace(self.path)
                    self.value, self.error = value, None
                except Exception as exc:
                    self.error = str(exc)
                finally:
                    self.checked = time.monotonic()
            if self.value is None:
                raise RuntimeError(self.error or 'Connect Google Sheets to load production data.')
            result = deepcopy(self.value)
            result.pop('identity', None)
            result.update(offline=bool(self.error), sync_error=self.error, source='Saved Google Sheets copy' if self.error else 'Google Sheets')
            return result
