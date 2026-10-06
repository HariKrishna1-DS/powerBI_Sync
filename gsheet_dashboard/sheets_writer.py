"""Designated-writer protocol for upgraded Tv Tracker installations.

The fixed control sheet is claimed in one atomic create-and-fill request. This
coordinates cooperating app clients; Google sharing permissions remain the
security boundary for people and older clients that do not use this protocol.
"""
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import threading
import uuid

CONTROL_ID = 1894260701
CONTROL_TITLE = '__TvTracker_Writer'
_device_lock = threading.Lock()


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
            self._guard.ensure()
            return value(*args, **kwargs)
        return write


class GuardedBook:
    WRITES = {'batch_update', 'values_update', 'values_append', 'values_batch_update', 'values_clear',
              'values_batch_clear', 'del_worksheet', 'reorder_worksheets', 'duplicate_sheet'}
    def __init__(self, book, identity):
        self._book, self.writer_guard = book, WriterGuard(book, identity)

    def worksheets(self):
        return [GuardedWorksheet(sheet, self.writer_guard) for sheet in self._book.worksheets()]

    def worksheet(self, title):
        return GuardedWorksheet(self._book.worksheet(title), self.writer_guard)

    def get_worksheet_by_id(self, identity):
        return GuardedWorksheet(self._book.get_worksheet_by_id(identity), self.writer_guard)

    def add_worksheet(self, *args, **kwargs):
        self.writer_guard.ensure()
        return GuardedWorksheet(self._book.add_worksheet(*args, **kwargs), self.writer_guard)

    def values_batch_get(self, *args, **kwargs):
        return self._book.values_batch_get(*args, **kwargs)

    def __getattr__(self, name):
        value = getattr(self._book, name)
        if name not in self.WRITES:
            return value
        def write(*args, **kwargs):
            self.writer_guard.ensure()
            return value(*args, **kwargs)
        return write
