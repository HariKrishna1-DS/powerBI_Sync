"""Bounded, explicitly dated copies of Google Sheets data for offline reading."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
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
        self.warning = None
        self.revision = None
        self.generation = 0
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

    @staticmethod
    def _revision(value):
        content = {key: item for key, item in value.items() if key not in ('updated_at', 'identity', 'revision')}
        return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    def get(self, loader, force=False, known_revision=None):
        generation = self.generation
        with self.lock:
            # Concurrent forced refreshes share the load that completed while they waited.
            if (force and self.generation == generation) or time.monotonic() - self.checked >= self.ttl:
                try:
                    value = dict(loader(), identity=self.identity, updated_at=datetime.now(timezone.utc).isoformat())
                    revision = self._revision(value)
                    self.value, self.error = value, None
                    self.revision, self.warning = revision, None
                    try:
                        self.path.parent.mkdir(parents=True, exist_ok=True)
                        temporary = self.path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(value), encoding='utf-8')
                        temporary.replace(self.path)
                    except OSError:
                        self.warning = 'Production is current, but its offline copy could not be saved. Check free disk space.'
                except Exception as exc:
                    self.error = str(exc)
                finally:
                    self.checked = time.monotonic()
                    self.generation += 1
            if self.value is None:
                raise RuntimeError(self.error or 'Connect Google Sheets to load production data.')
            unchanged = bool(known_revision and known_revision == self.revision)
            result = ({key: value for key, value in self.value.items() if key not in ('sheets', 'reports')}
                      if unchanged else deepcopy(self.value))
            result.pop('identity', None)
            result.update(offline=bool(self.error), sync_error=self.error, cache_warning=self.warning,
                          revision=self.revision, source='Saved Google Sheets copy' if self.error else 'Google Sheets')
            if unchanged:
                result['unchanged'] = True
            return result
