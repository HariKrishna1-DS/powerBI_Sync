"""Workbook-wide publishing jobs for cooperating Tv Tracker installations.

The fixed job sheet is claimed atomically and held across reads and writes.
Legacy clients are fenced out on migration. Google sharing permissions remain
the boundary for people or external scripts that do not use this protocol.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import threading
import uuid
import time
from contextlib import contextmanager
from functools import wraps

CONTROL_ID = 1894260701
CONTROL_TITLE = '__TvTracker_Writer'
_device_lock = threading.Lock()
# Keep these below the old writer ID: prior releases allocated report-tab IDs
# sequentially above that ID, including 1894260702 and 1894260703.
SHARED_ID = 1297002001
JOB_ID = 1297002002
SHARED_TITLE = '__TvTracker_Shared'
JOB_TITLE = '__TvTracker_Job'
_active = threading.local()
_local_locks = {}
_locks_guard = threading.Lock()


def shared_job(book, label='Publishing', wait=0, progress=None):
    guard = getattr(book, 'writer_guard', None)
    if isinstance(guard, SharedWriterGuard):
        return guard.session(label, wait=wait, progress=progress)
    from contextlib import nullcontext
    return nullcontext()


def coordinated(label):
    """Hold a workbook job across its reads, calculations, receipt and writes."""
    def decorate(function):
        @wraps(function)
        def run(book, *args, **kwargs):
            with shared_job(book, label):
                return function(book, *args, **kwargs)
        return run
    return decorate


class SharedWriterGuard:
    def __init__(self, book, identity, key=None):
        self.book, self.identity = book, identity
        self.key = key or getattr(book, 'id', None) or str(id(book))
        with _locks_guard:
            self.lock = _local_locks.setdefault(self.key, threading.RLock())

    def read(self, number):
        from gspread.exceptions import WorksheetNotFound, APIError
        # Fixed, bounded ranges avoid fetching all workbook metadata on every
        # poll. Four PCs share the same service-account request quota.
        if callable(getattr(self.book, 'values_get', None)):
            title, end = {CONTROL_ID: (CONTROL_TITLE, 'C2'), SHARED_ID: (SHARED_TITLE, 'C2'), JOB_ID: (JOB_TITLE, 'E2')}[number]
            try:
                return self.book.values_get(f"'{title}'!A1:{end}").get('values', [])
            except APIError as exc:
                if exc.code == 400 and str(exc.error.get('message', '')).startswith('Unable to parse range:'):
                    return None
                raise
        try:
            return self.book.get_worksheet_by_id(number).get_all_values()
        except WorksheetNotFound:
            return None

    @staticmethod
    def cells(number, rows):
        return {'updateCells': {'start': {'sheetId': number, 'rowIndex': 0, 'columnIndex': 0},
            'rows': [{'values': [{'userEnteredValue': {'stringValue': str(value)}} for value in row]} for row in rows],
            'fields': 'userEnteredValue'}}

    def enable(self):
        existing = self.read(SHARED_ID)
        if existing is not None:
            if len(existing) < 2 or existing[0][:2] != ['Protocol', 'Enabled'] or existing[1][:1] != ['tv-tracker-shared-v2']:
                raise ValueError('Shared publishing control is invalid; no production changes were sent.')
            return
        old = self.read(CONTROL_ID)
        if old is not None and (len(old) < 2 or old[0][:2] != ['Protocol', 'Writer'] or old[1][:1] != ['tv-tracker-v1']):
            raise ValueError('The workbook writer control is invalid. Review it before enabling shared publishing.')
        stamp = datetime.now(timezone.utc).isoformat()
        requests = [{'addSheet': {'properties': {'sheetId': SHARED_ID, 'title': SHARED_TITLE, 'hidden': True,
            'gridProperties': {'rowCount': 2, 'columnCount': 2}}}},
            self.cells(SHARED_ID, [['Protocol', 'Enabled'], ['tv-tracker-shared-v2', stamp]])]
        if old is None:
            requests.append({'addSheet': {'properties': {'sheetId': CONTROL_ID, 'title': CONTROL_TITLE, 'hidden': True,
                'gridProperties': {'rowCount': 2, 'columnCount': 3}}}})
        # Older clients cannot continue writing around the shared-job protocol.
        requests.append(self.cells(CONTROL_ID, [['Protocol', 'Writer', 'Claimed'], ['tv-tracker-v1', 'tv-tracker-shared-v2', stamp]]))
        try:
            self.book.batch_update({'requests': requests})
        except Exception:
            existing = self.read(SHARED_ID)
            if not existing or len(existing) < 2 or existing[1][:1] != ['tv-tracker-shared-v2']:
                raise

    def job(self):
        value = self.read(JOB_ID)
        if value is None:
            return None
        if len(value) < 2 or value[0][:5] != ['Protocol', 'Token', 'Computer', 'Job', 'Started'] or value[1][:1] != ['tv-tracker-job-v2'] or len(value[1]) < 5:
            raise ValueError('Shared publishing job control is invalid; no writes were sent.')
        return dict(zip(('protocol', 'token', 'computer', 'label', 'started'), value[1][:5]))

    def ensure(self):
        session = getattr(_active, 'jobs', {}).get(self.key)
        job = self.job()
        if not session or not job or job['token'] != session:
            raise ValueError('The shared publishing job is no longer owned by this operation. Saved data was retained; retry after reviewing the workbook.')

    def reserve_preview(self, minimum):
        """Reserve a number even if this job later fails before uploading its capture."""
        self.ensure()
        values = self.read(SHARED_ID)
        raw = values[1][2] if len(values[1]) > 2 else ''
        if raw and (not raw.isdigit() or int(raw) < 1):
            raise ValueError('Shared preview numbering is invalid. No capture was created.')
        number = max(int(raw or 1), minimum)
        requests = [{'updateSheetProperties': {'properties': {'sheetId': SHARED_ID, 'gridProperties': {'columnCount': 3}}, 'fields': 'gridProperties.columnCount'}},
            self.cells(SHARED_ID, [values[0][:2] + ['Next preview'], values[1][:2] + [str(number + 1)]])]
        try:
            self.book.batch_update({'requests': requests})
        except Exception:
            # A lost reply may already have consumed this number. Never reuse it
            # unless the exact counter update can be verified while we own the job.
            self.ensure()
            updated = self.read(SHARED_ID)
            if len(updated[1]) < 3 or updated[1][2] != str(number + 1):
                raise
        return number

    @contextmanager
    def session(self, label, wait=0, progress=None):
        with self.lock:
            jobs = getattr(_active, 'jobs', {})
            if self.key in jobs:
                # Guarded mutations revalidate ownership themselves. Re-entering
                # a local context must not add another remote read per mutation.
                yield
                return
            self.enable()
            token = uuid.uuid4().hex
            deadline = time.monotonic() + wait
            delay = 2
            while True:
                held = self.job()
                if held is None:
                    rows = [['Protocol', 'Token', 'Computer', 'Job', 'Started'], ['tv-tracker-job-v2', token,
                        os.environ.get('COMPUTERNAME', 'This computer'), label, datetime.now(timezone.utc).isoformat()]]
                    try:
                        self.book.batch_update({'requests': [{'addSheet': {'properties': {'sheetId': JOB_ID,
                            'title': JOB_TITLE, 'hidden': True, 'gridProperties': {'rowCount': 2, 'columnCount': 5}}}}, self.cells(JOB_ID, rows)]})
                    except Exception:
                        held = self.job()
                        if held is None:
                            raise
                    else:
                        held = self.job()
                if held and held['token'] == token:
                    break
                if held is None:
                    raise ValueError('Shared publishing ownership could not be confirmed.')
                message = f"{held['computer']} is running {held['label']}. Waiting for shared publishing; saved data is retained."
                if progress:
                    progress(message)
                if time.monotonic() >= deadline:
                    raise ValueError(message + ' Retry when that job finishes. If it was interrupted, close that app and recover its publishing slot in Storage and recovery.')
                time.sleep(min(delay, max(0, deadline - time.monotonic())))
                delay = min(20, delay * 2)
            _active.jobs = jobs
            jobs[self.key] = token
            try:
                from sheets_transport import clear_book_metadata
                clear_book_metadata(self.book)
                self.ensure()
                yield
            finally:
                try:
                    held = self.job()
                    if held and held['token'] == token:
                        self.book.batch_update({'requests': [{'deleteSheet': {'sheetId': JOB_ID}}]})
                finally:
                    jobs.pop(self.key, None)


def device_identity(root):
    file = Path(root) / 'writer-device.id'
    with _device_lock:
        file.parent.mkdir(parents=True, exist_ok=True)
        if not file.exists():
            try:
                with file.open('x', encoding='ascii') as output:
                    output.write(uuid.uuid4().hex)
            except FileExistsError:
                pass
        seed = file.read_text(encoding='ascii').strip()
        if len(seed) != 32:
            raise ValueError('Writer identity is damaged. Restore this computer\'s workspace identity before syncing.')
    # Copying a workspace backup to another Windows account must not clone ownership.
    return hashlib.sha256(f'{seed}|{os.environ.get("COMPUTERNAME", "local")}|{os.environ.get("USERNAME", "user")}'.encode()).hexdigest()


class WriterGuard:
    def __init__(self, book, identity):
        self.book, self.identity = book, identity
        self.lock = threading.Lock()

    def owner(self):
        from gspread.exceptions import WorksheetNotFound
        try:
            values = self.book.get_worksheet_by_id(CONTROL_ID).get_all_values()
        except WorksheetNotFound:
            return None
        if len(values) < 2 or len(values[1]) < 2 or values[0][:2] != ['Protocol', 'Writer'] or values[1][0] != 'tv-tracker-v1':
            raise ValueError('The workbook writer control is invalid. Review it before syncing; no production changes were sent.')
        return values[1][1]

    def ensure(self):
        with self.lock:
            # Ownership can change while an application is open (for example,
            # during recovery). Revalidate before every guarded mutation. A
            # cached success must never authorize writes after a transfer.
            owner = self.owner()
            if owner is None:
                stamp = datetime.now(timezone.utc).isoformat()
                requests = [
                    {'addSheet': {'properties': {'sheetId': CONTROL_ID, 'title': CONTROL_TITLE, 'hidden': True, 'gridProperties': {'rowCount': 2, 'columnCount': 3}}}},
                    {'updateCells': {'start': {'sheetId': CONTROL_ID, 'rowIndex': 0, 'columnIndex': 0},
                                     'rows': [{'values': [{'userEnteredValue': {'stringValue': v}} for v in row]} for row in
                                              (['Protocol', 'Writer', 'Claimed'], ['tv-tracker-v1', self.identity, stamp])], 'fields': 'userEnteredValue'}}]
                try:
                    self.book.batch_update({'requests': requests})
                except Exception:
                    # A competing claim or a lost reply can both be resolved by rereading.
                    owner = self.owner()
                    if owner is None:
                        raise
                owner = self.owner()
            if owner != self.identity:
                raise ValueError('This workbook has another designated Tv Tracker writer. Use this computer for reports only; run capture/sync on the designated computer.')


class GuardedWorksheet:
    WRITES = {'update', 'update_acell', 'update_cell', 'update_cells', 'batch_update', 'clear', 'batch_clear',
              'append_row', 'append_rows', 'insert_row', 'insert_rows', 'delete_rows', 'delete_columns',
              'resize', 'add_rows', 'add_cols', 'update_title', 'format', 'batch_format', 'freeze',
              'set_basic_filter', 'clear_basic_filter', 'hide', 'show', 'hide_rows', 'hide_columns',
              'add_protected_range', 'delete_protected_range', 'sort', 'cut_range', 'copy_range'}
    def __init__(self, sheet, guard):
        self._sheet, self._guard = sheet, guard

    def __getattr__(self, name):
        value = getattr(self._sheet, name)
        if name not in self.WRITES:
            return value
        def write(*args, **kwargs):
            if isinstance(self._guard, SharedWriterGuard):
                with self._guard.session('Worksheet update'):
                    self._guard.ensure()
                    return value(*args, **kwargs)
            self._guard.ensure()
            return value(*args, **kwargs)
        return write


class GuardedBook:
    WRITES = {'batch_update', 'values_update', 'values_append', 'values_batch_update', 'values_clear',
              'values_batch_clear', 'del_worksheet', 'reorder_worksheets', 'duplicate_sheet'}
    def __init__(self, book, identity, shared=False, key=None):
        self._book = book
        self.writer_guard = SharedWriterGuard(book, identity, key) if shared else WriterGuard(book, identity)

    def worksheets(self):
        return [GuardedWorksheet(sheet, self.writer_guard) for sheet in self._book.worksheets()]

    def worksheet(self, title):
        return GuardedWorksheet(self._book.worksheet(title), self.writer_guard)

    def get_worksheet_by_id(self, identity):
        return GuardedWorksheet(self._book.get_worksheet_by_id(identity), self.writer_guard)

    def add_worksheet(self, *args, **kwargs):
        if isinstance(self.writer_guard, SharedWriterGuard):
            with self.writer_guard.session('Create worksheet'):
                self.writer_guard.ensure()
                return GuardedWorksheet(self._book.add_worksheet(*args, **kwargs), self.writer_guard)
        self.writer_guard.ensure()
        return GuardedWorksheet(self._book.add_worksheet(*args, **kwargs), self.writer_guard)

    def values_batch_get(self, *args, **kwargs):
        return self._book.values_batch_get(*args, **kwargs)

    def __getattr__(self, name):
        value = getattr(self._book, name)
        if name not in self.WRITES:
            return value
        def write(*args, **kwargs):
            if isinstance(self.writer_guard, SharedWriterGuard):
                with self.writer_guard.session('Google Sheets update'):
                    self.writer_guard.ensure()
                    return value(*args, **kwargs)
            self.writer_guard.ensure()
            return value(*args, **kwargs)
        return write
