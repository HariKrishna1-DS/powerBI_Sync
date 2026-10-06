"""Bounded, explicitly dated copies of Google Sheets data for offline reading."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import threading
import time


class ProductionCache:
    def __init__(self, path, identity, ttl=120):
        self.path, self.identity, self.ttl = Path(path), identity, ttl
        self.lock = threading.Lock()
        self.ready = threading.Condition(self.lock)
        self.loading = False
        self.invalidations = 0
        self.checked = float('-inf')
        self.value = None
        self.error = None
        self.warning = None
        self.revision = None
        self.generation = 0
        self.retry_at = 0
        self.reload()

    def reload(self):
        with self.lock:
            self._reload()

    def _reload(self):
        self.value = None
        self.error = None
        self.warning = None
        self.revision = None
        self.checked = float('-inf')
        try:
            saved = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(saved, dict):
                return
            def normalized(identity):
                aliases = {f'{name}_-_September_2026': name for name in (
                    'TV_Search_Production_Report_Full_Search', 'TV_Search_Production_Report_C-O_and_Update')}
                return '|'.join(aliases.get(part, part) for part in str(identity).split('|'))
            if normalized(saved.get('identity')) == normalized(self.identity) and isinstance(saved.get('sheets'), dict):
                self.value = saved
                self.revision = self._revision(saved)
        except (OSError, ValueError):
            pass

    def invalidate(self):
        with self.lock:
            self.checked = float('-inf')
            self.invalidations += 1

    @staticmethod
    def _revision(value):
        content = {key: item for key, item in value.items() if key not in ('updated_at', 'identity', 'revision')}
        return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def _refresh(self, loader, invalidations):
        try:
            value = dict(loader(), identity=self.identity, updated_at=datetime.now(timezone.utc).isoformat())
            revision = self._revision(value)
            warning = None
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.path.with_suffix('.tmp')
                temporary.write_text(json.dumps(value), encoding='utf-8')
                temporary.replace(self.path)
            except OSError:
                warning = 'Production is current, but its offline copy could not be saved. Check free disk space.'
            with self.lock:
                self.value, self.error = value, None
                self.revision, self.warning = revision, warning
                self.retry_at = 0
        except Exception as exc:
            from sheets_transport import SheetsQuotaError
            with self.lock:
                self.error = str(exc)
                if isinstance(exc, SheetsQuotaError):
                    self.retry_at = time.monotonic() + exc.retry_after
        finally:
            with self.ready:
                self.checked = time.monotonic() if invalidations == self.invalidations else float('-inf')
                self.generation += 1
                self.loading = False
                self.ready.notify_all()

    def get(self, loader, force=False, known_revision=None, background=False):
        start = False
        with self.ready:
            if self.loading and not background:
                self.ready.wait_for(lambda: not self.loading)
                force = False  # Share the refresh already running when we arrived.
            due = force or time.monotonic() - self.checked >= self.ttl
            if due and not self.loading and time.monotonic() >= self.retry_at:
                self.loading = True
                start = True
                invalidations = self.invalidations
        if start:
            if background:
                threading.Thread(target=self._refresh, args=(loader, invalidations), daemon=True).start()
            else:
                self._refresh(loader, invalidations)
        with self.lock:
            if self.value is None:
                if self.loading:
                    return dict(sheets={}, reports={'daily': [], 'monthly': []}, refreshing=True,
                                source='Loading Google Sheets', offline=True, updated_at=None)
                if self.retry_at > time.monotonic():
                    from sheets_transport import SheetsQuotaError
                    raise SheetsQuotaError(self.retry_at - time.monotonic())
                raise RuntimeError(self.error or 'Connect Google Sheets to load production data.')
            unchanged = bool(known_revision and known_revision == self.revision)
            result = ({key: value for key, value in self.value.items() if key not in ('sheets', 'reports')}
                      if unchanged else deepcopy(self.value))
            result.pop('identity', None)
            result.update(offline=bool(self.error), sync_error=self.error, cache_warning=self.warning,
                          refreshing=self.loading,
                          retry_after=max(0, int(self.retry_at - time.monotonic())),
                          revision=self.revision, source='Saved Google Sheets copy' if self.error else 'Google Sheets')
            if unchanged:
                result['unchanged'] = True
            return result
