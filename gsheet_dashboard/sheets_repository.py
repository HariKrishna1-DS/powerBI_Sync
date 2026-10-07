"""Atomic, append-only production sync and recoverable preview history in Sheets."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
import time

import pandas as pd

from production_rules import TRACKER_COLUMNS, merge_trackers, order_key
from sync_config import BASE_DIR, TRACKER_TITLES

INDEX_TITLE = '__DataTrace_Previews'
INDEX_COLUMNS = ['Preview ID', 'Preview', 'Created', 'Source', 'Columns', 'Fingerprint', 'Pass Report']
ARCHIVE_COLUMNS = ['Preview', 'Captured At']
CHANGE_COLUMNS = ['Preview', 'Timestamp', 'Type', 'Order Number', 'Old Status', 'New Status', 'Reason']
SYNC_LOCK = threading.RLock()


def records(values):
    return [dict(zip(values[0], row)) for row in values[1:]] if values else []


def fingerprint(preview):
    raw = {'created': preview['created'], 'columns': preview['columns'], 'rows': [
        {c: '' if row.get(c) is None else str(row.get(c, '')) for c in preview['columns']}
        for row in preview['rows']]}
    return hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def writer_lock():
    # One lock shared by threads and backend/CLI processes on the same host.
    with SYNC_LOCK:
        path = BASE_DIR / 'previews' / '.sheets-sync.lock'
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('a+b') as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b'0')
                handle.flush()
            if __import__('os').name == 'nt':
                import msvcrt
                while True:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(.1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)


class Batch:
    """Plan all mutations before sending one Sheets transaction."""
    def __init__(self, book):
        self.book = book
        self.requests = []
        self.sheets = {sheet.title: sheet for sheet in book.worksheets()}
        self.values = {}
        self.ids = {sheet.id for sheet in self.sheets.values()}
        self.next_id = max(self.ids, default=0) + 1

    def read(self, title):
        if title not in self.values:
            self.values[title] = self.sheets[title].get_all_values() if title in self.sheets else []
        return self.values[title]

    def sheet(self, title, aliases=()):
        if title not in self.sheets:
            from sheet_titles import existing_title
            old = existing_title(self.sheets, title, aliases)
            if old:
                sheet = self.sheets[old]
                self.values[title] = self.values[old] if old in self.values else sheet.get_all_values()
                self.sheets[title] = sheet
                if old in aliases and old.casefold() != title.casefold():
                    # Explicit tracker migrations retain the existing rename
                    # contract. Monthly projection aliases only reuse the ID.
                    self.sheets.pop(old)
                    self.requests.append({'updateSheetProperties': {
                        'properties': {'sheetId': sheet.id, 'title': title}, 'fields': 'title'}})
            else:
                from types import SimpleNamespace
                sheet = SimpleNamespace(id=self.next_id, title=title, row_count=1, col_count=1)
                self.next_id += 1
                self.sheets[title] = sheet
                self.values[title] = []
                self.requests.append({'addSheet': {'properties': {'sheetId': sheet.id, 'title': title,
                                                                'gridProperties': {'rowCount': 1, 'columnCount': 1}}}})
        return self.sheets[title]

    def capacity(self, sheet, rows, columns):
        if rows > sheet.row_count or columns > sheet.col_count:
            self.requests.append({'updateSheetProperties': {
                'properties': {'sheetId': sheet.id, 'gridProperties': {
                    'rowCount': max(sheet.row_count, rows), 'columnCount': max(sheet.col_count, columns)}},
                'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})

    def cells(self, sheet, start_row, start_col, rows):
        from datatrace_sync import sheet_cell
        self.requests.append({'updateCells': {'start': {'sheetId': sheet.id, 'rowIndex': start_row, 'columnIndex': start_col},
                                             'rows': [{'values': [sheet_cell(v) for v in row]} for row in rows],
                                             'fields': 'userEnteredValue'}})

    def replace_view(self, title, frame):
        from datatrace_sync import status_row_format_request
        sheet = self.sheet(title)
        values = [list(frame.columns)] + frame.fillna('').values.tolist()
        old = self.read(title)
        self.capacity(sheet, max(len(values), len(old)), len(frame.columns))
        self.cells(sheet, 0, 0, values + [[''] * max(len(frame.columns), len(old[0]) if old else 0)
                                       for _ in range(max(0, len(old) - len(values)))])
        if old and len(old[0]) > len(frame.columns):
            self.requests.append({'repeatCell': {'range': {'sheetId': sheet.id, 'endRowIndex': max(len(old), len(values)),
                'startColumnIndex': len(frame.columns), 'endColumnIndex': len(old[0])},
                'cell': {}, 'fields': 'userEnteredValue'}})
        color = status_row_format_request(frame, sheet.id)
        if color:
            # Restrict formatting to populated rows; never clear an entire sheet.
            color['updateCells']['range']['endRowIndex'] = len(values)
            self.requests.append(color)
        self.requests.append({'setBasicFilter': {'filter': {'range': {'sheetId': sheet.id,
                              'endRowIndex': len(values), 'endColumnIndex': len(frame.columns)}}}})
        self.free_site_colors(sheet, frame)

    def free_site_colors(self, sheet, frame):
        from datatrace_sync import sheet_color
        if 'Free Site' not in frame.columns or frame.empty:
            return
        column = list(frame.columns).index('Free Site')
        self.requests.append({'updateCells': {'start': {'sheetId': sheet.id, 'rowIndex': 1, 'columnIndex': column},
            'rows': [{'values': [{'userEnteredFormat': {'backgroundColor': sheet_color(
                '#00b050' if value == 'On Time' else '#ff0000' if value in ('Missing', 'Missed') else '#ffffff')}}]}
                     for value in frame['Free Site']], 'fields': 'userEnteredFormat.backgroundColor'}})

    def tracker(self, title, rows, processed_orders=()):
        from datatrace_sync import sheet_color, status_color
        sheet = self.sheets[title]
        old = self.read(title)
        headers = list(old[0]) if old else list(TRACKER_COLUMNS)
        if len(headers) != len(set(headers)) or any(not c for c in headers):
            raise ValueError(f'{title} has duplicate or blank headers. Fix them before syncing.')
        if old and ('Order Number' not in headers or 'Status' not in headers):
            raise ValueError(f'{title} must have Order Number and Status headers.')
        missing = [c for c in TRACKER_COLUMNS if c not in headers]
        headers += missing
        self.capacity(sheet, len(rows) + 1, len(headers))
        if not old:
            self.cells(sheet, 0, 0, [headers])
        elif missing:
            self.cells(sheet, 0, len(old[0]), [missing])
        previous = records(old)
        for offset, row in enumerate(rows):
            before = previous[offset] if offset < len(previous) else None
            if before is None:
                self.cells(sheet, offset + 1, 0, [[row.get(c, '') for c in headers]])
            else:
                # Only these fields belong to automation. Manual cells and formulas
                # are never written back from get_all_values' rendered values.
                for name in ('Status', 'ETA', 'Comments', 'Assignee', 'Out Time', 'SLA Expiration', 'Free Site'):
                    if str(row.get(name, '')) != str(before.get(name, '')):
                        self.cells(sheet, offset + 1, headers.index(name), [[row.get(name, '')]])
            if before is None or order_key(row.get('Order Number')) in processed_orders:
                self.requests.append({'repeatCell': {'range': {'sheetId': sheet.id, 'startRowIndex': offset + 1,
                    'endRowIndex': offset + 2, 'endColumnIndex': len(headers)},
                    'cell': {'userEnteredFormat': {'backgroundColor': sheet_color(status_color(row.get('Status')))}},
                    'fields': 'userEnteredFormat.backgroundColor'}})
                free = row.get('Free Site')
                self.requests.append({'repeatCell': {'range': {'sheetId': sheet.id, 'startRowIndex': offset + 1,
                    'endRowIndex': offset + 2, 'startColumnIndex': headers.index('Free Site'), 'endColumnIndex': headers.index('Free Site') + 1},
                    'cell': {'userEnteredFormat': {'backgroundColor': sheet_color('#00b050' if free == 'On Time' else '#ff0000' if free == 'Missing' else '#ffffff')}},
                    'fields': 'userEnteredFormat.backgroundColor'}})
        self.requests.append({'setBasicFilter': {'filter': {'range': {'sheetId': sheet.id,
                              'endRowIndex': len(rows) + 1, 'endColumnIndex': len(headers)}}}})

    def append(self, title, columns, rows):
        sheet = self.sheet(title)
        old = self.read(title)
        headers = list(old[0]) if old else []
        extra = [c for c in columns if c not in headers]
        headers += extra
        start = len(old) if old else 1
        self.capacity(sheet, start + len(rows), len(headers))
        if not old:
            self.cells(sheet, 0, 0, [headers])
        elif extra:
            self.cells(sheet, 0, len(old[0]), [extra])
        if rows:
            self.cells(sheet, start, 0, [[row.get(c, '') for c in headers] for row in rows])


def tracker_values(book):
    by_title = {sheet.title: sheet for sheet in book.worksheets()}
    result = []
    for title, legacy in zip(TRACKER_TITLES, ('Full Title', 'Remaining Products')):
        sheet = by_title.get(title) or by_title.get(legacy)
        result.append(sheet.get_all_values() if sheet else [])
    return result


def read_tracker_rows(book):
    rows = []
    by_title = {sheet.title: sheet for sheet in book.worksheets()}
    for title, legacy in zip(TRACKER_TITLES, ('Full Title', 'Remaining Products')):
        sheet = by_title.get(title) or by_title.get(legacy)
        values = sheet.get_all_values() if sheet else []
        rows.extend(dict(row, _sheet=sheet.title, _sheet_row=index) for index, row in enumerate(records(values), start=2))
    return rows


def read_preview_history(book):
    by_title = {sheet.title: sheet for sheet in book.worksheets()}
    if INDEX_TITLE not in by_title or 'Sheet1' not in by_title:
        return []
    index = records(by_title[INDEX_TITLE].get_all_values())
    raw = records(by_title['Sheet1'].get_all_values())
    grouped = {}
    for row in raw:
        grouped.setdefault(row.get('Preview'), []).append(row)
    history = []
    for row in index:
        columns = json.loads(row['Columns'])
        history.append({'id': int(row['Preview ID']), 'name': row['Preview'], 'created': row['Created'], 'source': row['Source'],
                        'columns': columns, 'rows': [{c: record.get(c, '') for c in columns} for record in grouped.get(row['Preview'], [])]})
    return history


def sync_production(df, on_progress=None):
    from datatrace_sync import target_worksheet, report_frame, ALL_PRODUCT_FIELDS, status_report_frame, write_sheet_batch
    from order_reporting import daily_orders, monthly_orders
    preview = df.attrs.get('original_capture') or {
        'id': df.attrs.get('preview_id', 0), 'name': df.attrs.get('preview_name', 'Preview'),
        'created': datetime.now(timezone.utc).isoformat(), 'source': 'Manual',
        'columns': list(df.columns), 'rows': df.fillna('').to_dict('records')}
    if {'Preview', 'Captured At'} & set(preview['columns']):
        raise ValueError('Preview and Captured At are reserved archive headers.')
    with writer_lock():
        if on_progress:
            on_progress('Reading Google Sheets production trackers')
        book, _ = target_worksheet()
        batch = Batch(book)
        index = records(batch.read(INDEX_TITLE))
        digest = fingerprint(preview)
        receipt = next((row for row in index if row['Preview'] == preview['name']), None)
        if receipt:
            if receipt['Fingerprint'] != digest:
                raise ValueError('This preview name already belongs to a different saved snapshot. Recover history before capturing again.')
            report = json.loads(receipt['Pass Report'])
            report = dict(report, added=0, updated=0, unchanged=report['scanned'] - len(report['unprocessed']), updates=[], already_synced=True)
            df.attrs['pass_report'] = report
            return list(TRACKER_TITLES) + ['Full Title', 'Remaining Products', 'Status Report']
        if index and preview['id'] <= max(int(row['Preview ID']) for row in index):
            raise ValueError('An older preview cannot overwrite newer production data. Compare or export it instead.')
        for title, aliases in zip(TRACKER_TITLES, (('TV Orders', 'Full Title'), ('Remaining Products',))):
            # Only rename a legacy tab that is actually a production tracker.
            candidates = tuple(name for name in aliases if name in batch.sheets and 'Status' in (batch.read(name)[0] if batch.read(name) else []))
            if title not in batch.sheets and title == TRACKER_TITLES[1] and 'Sheet1' in batch.sheets:
                headers = batch.read('Sheet1')[0] if batch.read('Sheet1') else []
                if 'Status' in headers and 'No' in headers and 'Task Status' not in headers:
                    candidates = ('Sheet1',) + candidates
            batch.sheet(title, candidates)
        previous = df.attrs.get('previous_capture')
        if index:
            last = max(index, key=lambda row: int(row['Preview ID']))
            raw_rows = [row for row in records(batch.read('Sheet1')) if row.get('Preview') == last['Preview']]
            columns = json.loads(last['Columns'])
            previous = {'rows': [{c: row.get(c, '') for c in columns} for row in raw_rows]}
        merged, report = merge_trackers(preview, previous, [records(batch.read(title)) for title in TRACKER_TITLES])
        report['sync_timestamp'] = datetime.now(timezone.utc).isoformat()
        # Validate tracker headers before making any external mutation.
        for title, rows in zip(TRACKER_TITLES, merged):
            batch.tracker(title, rows, {order_key(number) for number in report['processed_orders']})
        all_rows = [row for rows in merged for row in rows if order_key(row.get('Order Number'))]
        combined = pd.DataFrame(all_rows, columns=TRACKER_COLUMNS).fillna('')
        combined.attrs['preview_name'] = preview['name']
        combined.attrs['sync_time'] = report['sync_timestamp']
        for title, rows in zip(('Full Title', 'Remaining Products'), merged):
            batch.replace_view(title, pd.DataFrame(rows, columns=TRACKER_COLUMNS).fillna(''))
        batch.replace_view('Overview', combined)
        batch.replace_view('Status Report', status_report_frame(combined))
        daily = daily_orders(sheet_rows=all_rows)
        monthly = monthly_orders(sheet_rows=all_rows)
        for title, reports, columns in (
                ('Daily Orders', daily, ['Date', 'Today Orders', 'Completed Orders', 'Awaiting for Clarification']),
                ('Monthly report', monthly, ['Month', 'Month Orders', 'Completed Orders', 'Awaiting for Clarification', 'SLA On Time', 'SLA Missed'])):
            batch.replace_view(title, pd.DataFrame(reports).reindex(columns=columns).fillna(''))
        if sum(r['Today Orders'] for r in daily) != len(all_rows) or sum(r['Month Orders'] for r in monthly) != len(all_rows):
            raise RuntimeError('Report totals do not match the trackers; no changes were sent.')
        archive = [dict({c: '' if row.get(c) is None else str(row.get(c, '')) for c in preview['columns']},
                        Preview=preview['name'], **{'Captured At': preview['created']}) for row in preview['rows']]
        batch.append('Sheet1', ARCHIVE_COLUMNS + preview['columns'], archive)
        raw_frame = report_frame(pd.DataFrame(preview['rows'], columns=preview['columns']), ALL_PRODUCT_FIELDS)
        batch.append('All Products', ARCHIVE_COLUMNS + list(raw_frame.columns),
                     [dict(row, Preview=preview['name'], **{'Captured At': preview['created']}) for row in raw_frame.to_dict('records')])
        logs = [dict(Preview=preview['name'], Timestamp=preview['created'], Type='Summary', Reason=json.dumps(report))]
        logs += [dict(Preview=preview['name'], Timestamp=preview['created'], Type='Updated', **{
            'Order Number': r['order'], 'Old Status': r['old_status'], 'New Status': r['new_status']}) for r in report['updates']]
        logs += [dict(Preview=preview['name'], Timestamp=preview['created'], Type='Not in latest preview', **{'Order Number': number}) for number in report['not_in_latest']]
        for kind in ('ambiguous', 'unprocessed'):
            logs += [dict(Preview=preview['name'], Timestamp=preview['created'], Type=kind, **{'Order Number': r['order'], 'Reason': r['reason']}) for r in report[kind]]
        batch.append('Changes', CHANGE_COLUMNS, logs)
        batch.append('Needs review', CHANGE_COLUMNS, [row for row in logs if row['Type'] in ('ambiguous', 'unprocessed')])
        if len(json.dumps(report)) > 45000:
            raise ValueError('The pass report exceeds a Google Sheets cell limit. Split the input into smaller previews.')
        batch.append(INDEX_TITLE, INDEX_COLUMNS, [{'Preview ID': preview['id'], 'Preview': preview['name'],
            'Created': preview['created'], 'Source': preview.get('source', 'DataTrace'), 'Columns': json.dumps(preview['columns']),
            'Fingerprint': digest, 'Pass Report': json.dumps(report)}])
        if on_progress:
            on_progress('Committing trackers, history and reports to Google Sheets')
        # Exact ranges, explicit sheet IDs and a fingerprint receipt make retries
        # safe after a timed-out request that may already have committed.
        write_sheet_batch(book, batch.sheets[INDEX_TITLE], batch.requests, on_progress, verify_commit=lambda: _committed(book, preview['name'], digest))
        if not _committed(book, preview['name'], digest):
            raise RuntimeError('Google Sheets sync receipt could not be verified. Preview retained for retry.')
        actual = read_tracker_rows(book)
        expected = {order_key(r['Order Number']): r for r in all_rows}
        if {order_key(r.get('Order Number')) for r in actual if order_key(r.get('Order Number'))} != set(expected):
            raise RuntimeError('Tracker order verification failed. Check Changes before retrying.')
        for row in actual:
            key = order_key(row.get('Order Number'))
            if key and any(str(row.get(c, '')) != str(expected[key].get(c, '')) for c in ('Status', 'Out Time', 'Free Site')):
                raise RuntimeError('Tracker status or SLA verification failed. Check Changes before retrying.')
        df.attrs['pass_report'] = report
        return list(TRACKER_TITLES) + ['Sheet1', 'All Products', 'Full Title', 'Remaining Products', 'Overview',
                                     'Daily Orders', 'Monthly report', 'Status Report', 'Changes', 'Needs review']


def _committed(book, name, digest):
    try:
        rows = records(book.worksheet(INDEX_TITLE).get_all_values())
        return any(row.get('Preview') == name and row.get('Fingerprint') == digest for row in rows)
    except Exception:
        return False
