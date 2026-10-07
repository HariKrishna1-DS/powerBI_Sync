"""Append-only production trackers with local preview receipts and raw Sheet history.

Archived queue disappearance uses the first missing preview as completion evidence.
Typing tasks and completion-looking task names alone are not completion evidence.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3

import pandas as pd
from sync_config import BASE_DIR, ASSET_DIR, FULL_TRACKER_TITLE, REMAINING_TRACKER_TITLE

BASE = BASE_DIR
IST = timezone(timedelta(hours=5, minutes=30))
FULL = FULL_TRACKER_TITLE
OLD_FULL = 'TV_Search_Production_Report_Full_Search_-_September_2026'
REMAINING = REMAINING_TRACKER_TITLE
OLD_REMAINING = 'TV_Search_Production_Report_C-O_and_Update_-_September_2026'
TRACKERS = (FULL, REMAINING)
HEADERS = ['No', 'Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
           'Online/Ground', 'Product', 'Status', 'ETA', 'Comments', 'Assignee',
           'Searcher', 'Clarification Requested', 'Shift', 'Process date', 'Review/QC',
           'Expense', 'In-Time', 'Out Time', 'SLA Expiration', 'Free Site', 'review']
ALIASES = {'received date': 'Date', 'arrival date': 'Date', 'order number': 'Order Number',
           'traceq id': 'TraceQ Id', 'online/gorund': 'Online/Ground',
           'online/ ground': 'Online/Ground', 'processed date': 'Process date',
           'free site': 'Free Site'}
SOURCE = {'Date': ('Date', 'Arrival Date', 'Arrival Time', 'RequestArrivalTime'),
          'State': ('State', 'St'), 'Online/Ground': ('Online/Ground', 'Online/ Ground'),
          'Comments': ('Comments', 'Comment', 'ETA Comments'), 'Assignee': ('Assignee', 'Last User'),
          'In-Time': ('In-Time', 'Arrival Time', 'RequestArrivalTime'),
          'SLA Expiration': ('SLA Expiration', 'SLA Expiration*')}
EMPTY_COLUMNS = ('Comments', 'Assignee', 'iAssignee')
UPDATABLE = ('Status', 'ETA', 'Out Time', 'SLA Expiration')
STATUS_NAMES = {s.casefold(): s for s in ('Awaiting for Clarification', 'Available',
    'Search In Progress', 'In Progress', 'Typing in Progress', 'Task Suspended', 'Completed and Delivered',
    'Cancelled', 'QC in Progress', 'Ready to Send', 'Assign to ABS', 'Waiting for Effective Date')}


def text(value):
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ''
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime('%m/%d/%Y %I:%M:%S %p')
    return str(value).strip()


def archive_value_matches(expected, actual):
    """Compare the value written to Sheets, allowing its numeric round trip.

    Only numeric source cells use numeric equality: text identifiers such as
    '001' must not silently become '1'. Read unformatted values so a sheet's
    display format or locale cannot disguise a changed number.
    """
    if text(expected).casefold() in ('true', 'false'):
        return text(expected).casefold() == text(actual).casefold()
    if isinstance(expected, (int, float)) and not isinstance(actual, bool):
        try:
            left, right = Decimal(str(expected)), Decimal(str(actual))
            return left.is_finite() and right.is_finite() and left == right
        except InvalidOperation:
            return False
    return text(expected) == text(actual)


def key(row):
    return text(row.get('Order Number')).casefold()


def value(row, column):
    return next((row[name] for name in SOURCE.get(column, (column,)) if name in row), '')


def canonical_headers(headers):
    seen, result = Counter(), []
    canonical = {name.casefold(): name for name in HEADERS if name != 'review'}
    for header in headers:
        name = text(header)
        name = ALIASES.get(name.casefold(), canonical.get(name.casefold(), name))
        # Preserve both SLA columns and the manual Typer column in the master file.
        if name == 'SLA' and not seen['SLA']:
            name = 'ETA'
        seen[name] += 1
        result.append(name if seen[name] == 1 else f'{name} ({seen[name]})')
    return result


def records(values):
    if not values:
        return []
    return [dict(zip(values[0], list(row) + [''] * (len(values[0]) - len(row)))) for row in values[1:]]


def matrix(rows, headers):
    return [headers] + [[row.get(c, '') for c in headers] for row in rows]


def load_defaults():
    result = {}
    for title, filename, tab in ((FULL, 'full_search.xlsx', 'TV Orders'),
                                  (REMAINING, 'co_update.xlsx', 'Sheet1')):
        path = ASSET_DIR / 'default_trackers' / filename
        if not path.exists():
            raise RuntimeError(f'Default tracker is missing: {path.name}')
        frame = pd.read_excel(path, sheet_name=tab, header=None, dtype=object).fillna('')
        headers = canonical_headers(frame.iloc[0].tolist())
        rows = [dict(zip(headers, [text(v) for v in row])) for row in frame.iloc[1:].values.tolist()]
        result[title] = [r for r in rows if key(r)]
    return result


def suspended(row):
    return (any(text(row.get(c)).casefold() in ('true', '1', 'yes')
                for c in ('WorkflowSuspended', 'Workflow Suspended', 'Is Suspended'))
            or text(row.get('Task Status')).casefold() == 'workflow suspended')


def mapped_status(row, existing='', new=False):
    from production_timing import completed, precise_timestamp
    if completed(row) and (precise_timestamp(row.get('Out Time')) or precise_timestamp(row.get('Completed Time'))):
        return 'Completed and Delivered'
    if text(row.get('Status')).casefold() in ('cancelled', 'canceled'):
        return 'Cancelled'
    if text(existing).casefold() in ('cancelled', 'task suspended', 'workflow suspended'):
        return existing
    if suspended(row):
        return 'Awaiting for Clarification'
    if new or (text(row.get('Task Name')).casefold() == 'search'
               and text(row.get('Task Status')).casefold() == 'available'):
        return 'Search In Progress'
    return existing


def driving(row):
    return (text(row.get('Task Name')).casefold(), text(row.get('Task Status')).casefold(),
            suspended(row), text(row.get('Status')).casefold(), text(row.get('Completed Time')), text(row.get('Out Time')))


def timestamp(value):
    from monthly_production import local_datetime
    return local_datetime(value)


def deadline(raw, anchor):
    raw = text(raw)
    parsed = timestamp(raw)
    if parsed:
        return parsed
    if anchor is None:
        return None  # Relative deadlines need the capture time, never the current wall clock.
    for fmt in ('%m/%d %I:%M %p', '%m/%d %I:%M:%S %p', '%m/%d %H:%M'):
        try:
            return datetime.strptime(raw, fmt).replace(year=anchor.year)
        except ValueError:
            pass
    match = re.fullmatch(r'(-)?(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?', raw, re.I)
    if match and any(match.group(i) for i in (2, 3, 4)):
        delta = timedelta(days=int(match[2] or 0), hours=int(match[3] or 0), minutes=int(match[4] or 0))
        return anchor + (-delta if match[1] else delta)
    return None


def free_site(row, anchor):
    from production_timing import sla_result
    return sla_result(row, anchor)


def merge_trackers(trackers, incoming, previous, anchor, completion_history=None):
    """Pure merge: preserve position/manual values, append new identities, report ambiguity."""
    result = {title: [dict(r) for r in trackers.get(title, [])] for title in TRACKERS}
    locations, duplicates = {}, set()
    for title, rows in result.items():
        for index, row in enumerate(rows):
            identity = key(row)
            if identity in locations:
                duplicates.add(identity)
            elif identity:
                locations[identity] = (title, index)
    old = {key(r): r for r in previous if key(r)}
    counts = Counter(key(r) for r in incoming if key(r))
    report = {'scanned': len(incoming), 'added': 0, 'updated': 0, 'unchanged': 0,
              'not_in_latest': [r.get('Order Number') for k, r in old.items() if k not in counts],
              'changes': [], 'ambiguous': []}
    for raw in incoming:
        from production_timing import precise_timestamp
        identity = key(raw)
        if not identity or counts[identity] > 1 or identity in duplicates:
            report['ambiguous'].append({'Order Number': raw.get('Order Number', ''),
                                        'Reason': 'Missing or duplicate Order Number'})
            continue
        product = text(raw.get('Product'))
        route = FULL if product.casefold() in ('full title', 'full search') else REMAINING
        new = identity not in locations
        if new and not product:
            report['ambiguous'].append({'Order Number': raw.get('Order Number'), 'Reason': 'Missing Product'})
            continue
        if new:
            row = {c: '' for c in HEADERS}
            for c in ('Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
                      'Online/Ground', 'Product', 'ETA', 'In-Time', 'Out Time', 'SLA Expiration'):
                row[c] = text(value(raw, c))
            date = timestamp(row['Date'])
            if date:
                row['Date'] = date.strftime('%m/%d/%Y')
            serials = [int(text(r.get('No'))) for r in result[route] if text(r.get('No')).isdigit()]
            row['No'] = max(serials, default=0) + 1
            row['Status'] = mapped_status(raw, new=True)
            result[route].append(row)
            locations[identity] = route, len(result[route]) - 1
            before = None
        else:
            title, index = locations[identity]
            row = result[title][index]
            before = dict(row)
            if product and route != title:
                report['ambiguous'].append({'Order Number': row['Order Number'], 'Reason': 'Product route conflicts with tracker; row retained'})
            if identity not in old or driving(old[identity]) != driving(raw):
                row['Status'] = mapped_status(raw, row.get('Status', ''))
            for c in UPDATABLE:
                if c in ('Status', 'Out Time'):
                    continue
                if any(a in raw for a in SOURCE.get(c, (c,))):
                    row[c] = text(value(raw, c))
            if timestamp(raw.get('Out Time')):
                row['Out Time'] = text(raw['Out Time'])
            # Only take a real completion timestamp for an explicitly completed tracker.
            completed_time = raw.get('Completed Time', '')
            if text(row.get('Status')).casefold() == 'completed and delivered' and precise_timestamp(completed_time) and not text(row.get('Out Time')):
                row['Out Time'] = text(completed_time)
        if text(row.get('Status')).casefold() == 'completed and delivered' and not text(row.get('Out Time')) and precise_timestamp(raw.get('Completed Time')):
            row['Out Time'] = text(raw['Completed Time'])
        if text(row.get('Out Time')) and not precise_timestamp(row.get('Out Time')):
            report['ambiguous'].append({'Order Number': row['Order Number'], 'Reason': 'Out Time lacks a valid completion date and time; retained for review'})
        for column in EMPTY_COLUMNS:
            if column in row:
                row[column] = ''
        row['Status'] = STATUS_NAMES.get(text(row.get('Status')).casefold(), row.get('Status', ''))
        raw_sla = row.get('SLA Expiration', '')
        due = deadline(raw_sla, anchor)
        if due:
            row['SLA Expiration'] = due.strftime('%m/%d/%Y %I:%M:%S %p')
        elif text(raw_sla):
            report['ambiguous'].append({'Order Number': row['Order Number'], 'Reason': f'Ambiguous SLA: {raw_sla}'})
        row['Free Site'], reason = free_site(row, anchor)
        if reason:
            report['ambiguous'].append({'Order Number': row['Order Number'], 'Reason': reason})
        action = 'added' if new else 'updated' if row != before else 'unchanged'
        report[action] += 1
        if action != 'unchanged':
            report['changes'].append({'Order Number': row['Order Number'], 'Action': action,
                'Old Status': before.get('Status', '') if before else '', 'New Status': row['Status']})
    if completion_history is not None:
        from preview_completion import reconcile_completions
        result, completion_changes = reconcile_completions(result, completion_history)
        report['changes'].extend(completion_changes)
        report['updated'] += len(completion_changes)
    # These computed/empty columns also apply to orders absent from this preview.
    for rows in result.values():
        for row in rows:
            for column in EMPTY_COLUMNS:
                if column in row:
                    row[column] = ''
            row['Status'] = STATUS_NAMES.get(text(row.get('Status')).casefold(), row.get('Status', ''))
            if key(row) in counts and counts[key(row)] == 1 and key(row) not in duplicates:
                continue
            row['Free Site'], reason = free_site(row, anchor)
            if reason and not any(r['Order Number'] == row.get('Order Number') and r['Reason'] == reason for r in report['ambiguous']):
                report['ambiguous'].append({'Order Number': row.get('Order Number', ''), 'Reason': reason})
    report['unprocessed'] = sum(1 for r in incoming if not key(r) or counts[key(r)] > 1 or key(r) in duplicates
                              or (not text(r.get('Product')) and key(r) not in locations))
    return result, report


@contextmanager
def sync_lock(root=None):
    root = Path(root or BASE / 'previews')
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'sync-lock.sqlite', timeout=600)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS mutex (id INTEGER PRIMARY KEY)')
        db.commit()
        db.execute('BEGIN IMMEDIATE')
        yield
    finally:
        db.rollback()
        db.close()


def read_trackers(book):
    from monthly_production import decode, tab_identity
    return {sheet.title if tab_identity(sheet.title) else title: decode(values) for title, sheet, values in tracker_sources(book)}


def tracker_sources(book):
    """Read existing legacy names without renaming a Sheet on a read request."""
    from monthly_production import production_sources
    from sheet_reads import read_values
    available = book.worksheets()
    monthly = production_sources(book, available)
    if monthly:
        return monthly
    sheets = {sheet.title: sheet for sheet in available}
    result = []
    for title, old, short in ((FULL, OLD_FULL, 'Full Title'), (REMAINING, OLD_REMAINING, 'Remaining Products')):
        default = old.removesuffix('_-_September_2026')
        aliases = (title, old, short) if title == default else (title,)
        source = next((sheets[name] for name in aliases if name in sheets), None)
        if source is None:
            raise ValueError(f'Tracker tab "{title}" is missing. Import or capture a queue to initialize it, or check Connections.')
        result.append((title, source))
    return [(title, sheet, values) for (title, sheet), values in zip(result, read_values(book, [sheet for _, sheet in result]))]


def read_tracker_rows(book):
    from monthly_production import decode, tab_identity
    return [dict(row, _sheet=sheet.title, _tracker=title, _sheet_row=index,
                 _month=(tab_identity(sheet.title) or ('', ''))[1])
            for title, sheet, values in tracker_sources(book)
            for index, row in enumerate(decode(values), 2)]


def read_preview_history(book):
    """Recover v2 raw history, retaining the v2.0 ledger's exact column metadata."""
    from sheets_repository import read_preview_history as read_legacy
    legacy = read_legacy(book)
    saved = {row['id']: row for row in legacy}
    sheets = {sheet.title: sheet for sheet in book.worksheets()}
    values = sheets['Sheet1'].get_all_values() if 'Sheet1' in sheets else []
    if not values or 'Preview' not in values[0]:
        return list(saved.values())
    columns = [name for name in values[0] if name not in ('Preview', 'Preview Timestamp', 'Captured At')]
    grouped = {}
    for row in records(values):
        match = re.fullmatch(r'preview([1-9]\d*)', text(row.get('Preview')))
        if match:
            grouped.setdefault(int(match[1]), []).append(row)
    for number, rows in grouped.items():
        if number in saved:
            continue
        raw_date = rows[0].get('Preview Timestamp') or rows[0].get('Captured At')
        created = datetime.fromisoformat(raw_date) if raw_date else datetime.now(IST)
        if created.tzinfo is None:
            created = created.replace(tzinfo=IST)
        saved[number] = {'id': number, 'name': f'preview{number}', 'created': created.isoformat(),
                         'source': 'Google Sheets recovery', 'columns': columns,
                         'rows': [{c: row.get(c, '') for c in columns} for row in rows if any(text(row.get(c)) for c in columns)]}
    return [saved[number] for number in sorted(saved)]


def read_pass_report(book=None, store=None):
    from preview_store import PreviewStore
    store = store or PreviewStore(BASE / 'previews')
    result = store.latest_sync_report()
    if result:
        return result
    # Transition support until the old audit tabs have been backed up and removed.
    if book is not None and any(sheet.title == 'Preview History' for sheet in book.worksheets()):
        receipts = records(book.worksheet('Preview History').get_all_values())
        if receipts:
            latest = receipts[-1]
            changes = [r for r in records(book.worksheet('Changes').get_all_values())
                       if r.get('Preview') == latest['Preview']] if any(s.title == 'Changes' for s in book.worksheets()) else []
            result = json.loads(latest.get('Report') or latest.get('Pass Report') or '{}')
            result['changes'] = changes
            result['not_in_latest'] = [r['Order Number'] for r in changes
                                       if r.get('Action') == 'Not in latest preview']
            return result
    return {}


def import_default_details(book):
    """One-time import of master manual fields missing from legacy queue reports."""
    from datatrace_sync import sheet_cell, write_sheet_batch
    sheets = {s.title: s for s in book.worksheets()}
    title = 'Default import details'
    audit = sheets.get(title)
    if audit and audit.get_all_values():
        return
    audit = audit or book.add_worksheet(title=title, rows=2, cols=4)
    defaults, requests, changes = load_defaults(), [], []
    for name in TRACKERS:
        target = sheets[name]
        values = target.get_all_values()
        formulas = target.get_all_values(value_render_option='FORMULA')
        headers = values[0]
        baseline = {}
        for row in defaults[name]:
            baseline.setdefault(key(row), row)
        for index, row in enumerate(records(values), 1):
            source = baseline.get(key(row), {})
            for column in headers:
                if column in UPDATABLE or column in ('No', 'Free Site', *EMPTY_COLUMNS):
                    continue
                val = text(source.get(column))
                j = headers.index(column)
                raw = formulas[index][j] if index < len(formulas) and j < len(formulas[index]) else ''
                if val and not text(row.get(column)) and not text(raw).startswith('='):
                    requests.append({'updateCells': {'start': {'sheetId': target.id, 'rowIndex': index,
                        'columnIndex': headers.index(column)}, 'rows': [{'values': [sheet_cell(val)]}], 'fields': 'userEnteredValue'}})
                    changes.append([name, row['Order Number'], column, val])
    values = [['Tracker', 'Order Number', 'Column', 'Imported value']] + changes
    requests.append({'updateSheetProperties': {'properties': {'sheetId': audit.id,
        'gridProperties': {'rowCount': max(len(values), 2), 'columnCount': 4}}, 'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})
    requests.append({'updateCells': {'start': {'sheetId': audit.id, 'rowIndex': 0, 'columnIndex': 0},
        'rows': [{'values': [sheet_cell(v) for v in row]} for row in values], 'fields': 'userEnteredValue'}})
    write_sheet_batch(book, audit, requests)


def sheet_reports(trackers, audit=None):
    """All totals originate in tracker rows returned by Google Sheets."""
    from sla_comments import sla_entry, sla_status
    from monthly_production import arrival_sort, tab_identity, local_datetime
    from production_timing import sla_eligible
    rows = [dict(row, _sheet=row.get('_sheet', title), _tracker=(tab_identity(title) or (title, ''))[0],
                 _month=row.get('_month') or (tab_identity(title) or ('', ''))[1])
            for title, items in trackers.items() for row in items if key(row)]
    if len({(r['_month'], key(r)) for r in rows}) != len(rows):
        raise ValueError('Duplicate Order Number in Google Sheets trackers. Resolve duplicates before reporting.')
    groups = {'daily': {}, 'monthly': {}}
    completed_months = {}
    for row in rows:
        date = local_datetime(row.get('In-Time')) or timestamp(row.get('Date'))
        day = date.strftime('%Y-%m-%d') if date else 'Undated'
        for kind, bucket in (('daily', day), ('monthly', row['_month'] or (day[:7] if date else 'Undated'))):
            groups[kind].setdefault(bucket, []).append(row)
        completed_at = timestamp(row.get('Out Time'))
        if completed_at and sla_eligible(row) and sla_status(row.get('Free Site')):
            month = row['_month'] or completed_at.strftime('%Y-%m')
            completed_months.setdefault(month, []).append(row)
            groups['monthly'].setdefault(month, [])
    reports = {}
    missing = {text(x).casefold() for x in (audit or {}).get('not_in_latest', [])}
    added = {key(r) for r in (audit or {}).get('changes', []) if r.get('Action') == 'added'}
    updated = {key(r) for r in (audit or {}).get('changes', []) if r.get('Action') == 'updated'}
    for kind, buckets in groups.items():
        reports[kind] = []
        for period, items in sorted(buckets.items(), reverse=True):
            items = arrival_sort(items)
            status = [text(r.get('Status') or r.get('Task Status')).casefold() for r in items]
            completed = [r['Order Number'] for r in items if text(r.get('Status')).casefold() == 'completed and delivered']
            absent = [r['Order Number'] for r in items if key(r) in missing]
            new_ids = [r['Order Number'] for r in items if key(r) in added]
            unchanged = [r['Order Number'] for r in items if key(r) not in added | updated | missing]
            sla_items = completed_months.get(period, []) if kind == 'monthly' else items
            sla = [sla_entry(r, sla_status(r.get('Free Site'))) for r in sla_items
                   if sla_eligible(r) and sla_status(r.get('Free Site'))]
            reports[kind].append({'Date': period, 'Month': period, 'MonthLabel': period,
                'Previews': [(audit or {}).get('preview_name', '')], 'Days': [],
                'Today Orders': len(items), 'Month Orders': len(items), 'Completed Orders': len(completed),
                'Received': len(items), 'Completed': len(completed),
                'Clarification': sum(s == 'awaiting for clarification' for s in status),
                'Cancelled': sum(s == 'cancelled' for s in status),
                'Vendor Pending': sum(s == 'assign to abs' for s in status),
                'In-House Pending': sum(s not in ('completed and delivered', 'cancelled',
                    'awaiting for clarification', 'assign to abs') for s in status),
                'Not in latest preview': len(absent), 'Newly Orders': len(new_ids), 'Unchanged': len(unchanged),
                'Awaiting for Clarification': sum(text(r.get('Status')).casefold() == 'awaiting for clarification' for r in items),
                'SLA On Time': sum(r['Free Site'] == 'On Time' for r in sla),
                'SLA Missed': sum(r['Free Site'] == 'Missing' for r in sla), 'sla_rows': sla,
                'SLA OnTime': sum(r['Free Site'] == 'On Time' for r in sla),
                'Missing': sum(r['Free Site'] == 'Missing' for r in sla),
                'rows': items, 'columns': list(dict.fromkeys(HEADERS + [c for r in items for c in r if not c.startswith('_')])), 'missing_ids': absent, 'completed_ids': completed,
                'new_ids': new_ids, 'unchanged_ids': unchanged})
    return reports


def sync_trackers(frame=None, on_progress=None, book=None):
    """One atomic Sheets batch includes tracker edits, raw history and reports.

    Sheet1's Preview column is the cloud commit witness after a lost reply.
    """
    from datatrace_sync import target_worksheet, sheet_cell, sheet_color, status_color, write_sheet_batch
    from tracker_formatting import ensure_tracker_formatting
    from monthly_views import monthly_view_values, refresh_monthly_views
    from preview_store import PreviewStore
    if frame is not None:
        capture = frame.attrs.get('original_capture') or {'columns': list(frame.columns)}
        if {'Preview', 'Preview Timestamp', 'Captured At'} & set(capture['columns']):
            raise ValueError('Preview, Preview Timestamp, and Captured At are reserved archive headers.')
        if 'Order Number' not in capture['columns']:
            raise ValueError('The capture must include an Order Number column.')
    store_root = frame.attrs.get('store_root') if frame is not None else None
    with sync_lock(store_root):
        store = PreviewStore(store_root or BASE / 'previews')
        from report_workspace import ReportWorkspace
        publish_tracker_reports = ReportWorkspace(store).read()['mode'] != 'excel'
        if book is None:
            book, _ = target_worksheet()
        from monthly_production import tab_identity
        if any(tab_identity(s.title) for s in book.worksheets()):
            from monthly_sync import sync_monthly
            return sync_monthly(book, frame, store, on_progress)
        worksheets = {s.title: s for s in book.worksheets()}
        if FULL == OLD_FULL.removesuffix('_-_September_2026') and FULL not in worksheets and OLD_FULL in worksheets:
            worksheets[OLD_FULL].update_title(FULL)
            worksheets[FULL] = worksheets.pop(OLD_FULL)
        if REMAINING == OLD_REMAINING.removesuffix('_-_September_2026') and REMAINING not in worksheets and OLD_REMAINING in worksheets:
            worksheets[OLD_REMAINING].update_title(REMAINING)
            worksheets[REMAINING] = worksheets.pop(OLD_REMAINING)
        def sheet(title):
            from monthly_views import view_identity
            if title not in worksheets and view_identity(title):
                alias = next((name for name in list(worksheets) if view_identity(name) == view_identity(title)), None)
                if alias:
                    worksheets[title] = worksheets.pop(alias)
                    worksheets[title].update_title(title)
            if title not in worksheets:
                worksheets[title] = book.add_worksheet(title=title, rows=1, cols=1)
            return worksheets[title]
        history_sheet = sheet('Sheet1')
        history_values = history_sheet.get_all_values(value_render_option='UNFORMATTED_VALUE')
        history = records(history_values)
        committed = {}
        for row in history:
            if re.fullmatch(r'preview[1-9]\d*', text(row.get('Preview'))):
                committed.setdefault(row['Preview'], []).append(row)
        preview = frame.attrs.get('preview_name', 'Preview') if frame is not None else 'Default trackers'
        original = frame.attrs.get('original_capture') if frame is not None else None
        incoming = original['rows'] if original else frame.fillna('').to_dict('records') if frame is not None else []
        digest = hashlib.sha256(json.dumps(incoming, sort_keys=True, default=str).encode()).hexdigest()
        preview_id = frame.attrs.get('preview_id') if frame is not None else 0
        receipt = store.get_sync_report(preview_id, include_staged=True)
        if frame is None and receipt and receipt['committed']:
            if publish_tracker_reports:
                refresh_monthly_views(book)
            ensure_tracker_formatting(book)
            import_default_details(book)
            return list(TRACKERS)
        if frame is not None and preview in committed:
            columns = original['columns'] if original else list(frame.columns)
            raw_committed = committed[preview]
            if not incoming and len(raw_committed) == 1 and not any(text(raw_committed[0].get(c)) for c in columns):
                raw_committed = []  # The archive marker represents a valid empty capture.
            if len(incoming) != len(raw_committed) or any(
                    not archive_value_matches(wanted.get(c, ''), actual.get(c, ''))
                    for wanted, actual in zip(incoming, raw_committed) for c in columns):
                raise ValueError('This preview name already identifies a different saved snapshot.')
            if receipt and receipt['sha256'] != digest:
                raise ValueError('This preview has a different saved snapshot hash.')
            if receipt and not receipt['committed']:
                verify_tracker_cells(book, receipt['report'].get('_expected_tracker_cells', {}))
                store.commit_sync_report(preview_id, digest)
            if publish_tracker_reports:
                refresh_monthly_views(book)
            ensure_tracker_formatting(book)
            frame.attrs['pass_report'] = {k: v for k, v in receipt['report'].items() if not k.startswith('_')} if receipt else {}
            return list(TRACKERS) + ['All Products', 'Sheet1']
        if frame is not None and frame.attrs.get('preview_id'):
            last = max((int(name[7:]) for name in committed), default=0)
            if frame.attrs['preview_id'] < last:
                raise ValueError('An unsynced older preview cannot overwrite a newer tracker state. Review it in history.')
        defaults = load_defaults()
        current, additions, requests, saved_values, conflicts = {}, {}, [], {}, []
        for title in TRACKERS:
            # Migrate actual legacy tracker tabs by name, never by tab position.
            legacy = 'Full Title' if title == FULL else 'Remaining Products'
            default_title = OLD_FULL.removesuffix('_-_September_2026') if title == FULL else OLD_REMAINING.removesuffix('_-_September_2026')
            if title == default_title and title not in worksheets and legacy in worksheets:
                worksheets[legacy].update_title(title)
                worksheets[title] = worksheets.pop(legacy)
            target = sheet(title)
            prior = target.get_all_values()
            if not any(any(text(cell) for cell in row) for row in prior):
                prior = []  # A newly created one-cell sheet can read back as [[]].
            if prior and ('Order Number' not in prior[0] or len(set(prior[0])) != len(prior[0])):
                raise ValueError(f'Tracker {title} needs unique headers and an Order Number column before syncing.')
            saved_values[title] = prior
        global_locations = {key(r): title for title in TRACKERS for r in records(saved_values[title]) if key(r)}
        for title in TRACKERS:
            prior = saved_values[title]
            existing = records(prior)
            ids = {key(r) for r in existing if key(r)}
            source_ids = set()
            extra = []
            serial = max((int(text(r.get('No'))) for r in existing if text(r.get('No')).isdigit()), default=0)
            for r in defaults[title]:
                if key(r) in source_ids or (key(r) in global_locations and global_locations[key(r)] != title):
                    conflicts.append(dict(r, **{'Source tracker': title, 'Reason': 'Duplicate Order Number in default workbook; retained for review'}))
                source_ids.add(key(r))
                if key(r) not in global_locations:
                    serial += 1
                    seeded = dict(r, No=serial)
                    seeded['Status'] = STATUS_NAMES.get(text(seeded.get('Status')).casefold(), seeded.get('Status', ''))
                    extra.append(seeded)
                    ids.add(key(r))
                    global_locations[key(r)] = title
            # When a tracker already exists, its order and values remain authoritative.
            current[title] = existing + extra
            additions[title] = extra
        created = frame.attrs.get('preview_created') if frame is not None else None
        anchor = datetime.fromisoformat(created).astimezone(IST).replace(tzinfo=None) if created else datetime.now(IST).replace(tzinfo=None)
        previous = []
        if committed:
            last_name = max(committed, key=lambda name: int(name[7:]))
            try:
                previous = store.get(int(last_name[7:]))['rows']
            except KeyError:
                previous = committed[last_name]
        completion_history = None
        if frame is not None and created:
            completion_history = history + [dict(r, Preview=preview, **{'Preview Timestamp': anchor.isoformat()}) for r in incoming]
            if not incoming:
                completion_history.append({'Preview': preview, 'Preview Timestamp': anchor.isoformat()})
        merged, report = merge_trackers(current, incoming, previous, anchor, completion_history)
        from monthly_production import arrival_sort
        merged = {title: arrival_sort(rows, report['ambiguous']) for title, rows in merged.items()}
        new_seed_ids = {key(r) for rows in additions.values() for r in rows}
        for rows in merged.values():
            for row in rows:
                if key(row) in new_seed_ids and key(row) not in {key(r) for r in incoming}:
                    row['Free Site'], reason = free_site(row, anchor)
                    if reason:
                        report['ambiguous'].append({'Order Number': row['Order Number'], 'Reason': reason})
        report.update(preview_name=preview, timestamp=anchor.isoformat(),
                      seeded=sum(len(v) for v in additions.values()),
                      default_conflicts_count=len(conflicts), default_conflicts=conflicts)

        def write(title, values, tracker=False, append=False):
            target = sheet(title)
            prior = saved_values.get(title)
            if prior is None:
                prior = target.get_all_values()
            headers = values[0]
            rows = values[1:]
            if append and prior:
                headers = list(dict.fromkeys(prior[0] + headers))
                rows = [[r.get(c, '') for c in headers] for r in records(prior) + records(values)]
                values = [headers] + rows
            row_count = max(target.row_count, len(values), 2)
            col_count = max(target.col_count, len(headers), 1)
            requests.append({'updateSheetProperties': {'properties': {'sheetId': target.id,
                'gridProperties': {'rowCount': row_count, 'columnCount': col_count, 'frozenRowCount': 1}},
                'fields': 'gridProperties.rowCount,gridProperties.columnCount,gridProperties.frozenRowCount'}})
            if tracker and prior:
                if prior[0] != headers:
                    # Existing columns retain their positions, new columns append.
                    requests.append({'updateCells': {'start': {'sheetId': target.id, 'rowIndex': 0, 'columnIndex': 0},
                        'rows': [{'values': [sheet_cell(c) for c in headers]}], 'fields': 'userEnteredValue'}})
                for i, row in enumerate(rows, 1):
                    old = prior[i] if i < len(prior) else []
                    if i >= len(prior):
                        if i == len(prior):
                            requests.append({'updateCells': {'start': {'sheetId': target.id, 'rowIndex': i, 'columnIndex': 0},
                                'rows': [{'values': [sheet_cell(v) for v in r]} for r in rows[i - 1:]], 'fields': 'userEnteredValue'}})
                    else:
                        for j, val in enumerate(row):
                            old_val = old[j] if j < len(old) else ''
                            if text(val) != text(old_val):
                                requests.append({'updateCells': {'start': {'sheetId': target.id, 'rowIndex': i, 'columnIndex': j},
                                    'rows': [{'values': [sheet_cell(val)]}], 'fields': 'userEnteredValue'}})
            elif append and prior and prior[0] == headers:
                requests.append({'updateCells': {'start': {'sheetId': target.id, 'rowIndex': len(prior), 'columnIndex': 0},
                    'rows': [{'values': [sheet_cell(v) for v in r]} for r in values[len(prior):]], 'fields': 'userEnteredValue'}})
            else:
                requests.append({'updateCells': {'range': {'sheetId': target.id, 'startRowIndex': 0,
                    'endRowIndex': max(len(values), len(prior)), 'startColumnIndex': 0, 'endColumnIndex': max(len(headers), max((len(r) for r in prior), default=0))},
                    'rows': [{'values': [sheet_cell(v) for v in row]} for row in values], 'fields': 'userEnteredValue'}})
        for title in TRACKERS:
            prior_headers = saved_values[title][0] if saved_values[title] else HEADERS
            headers = list(dict.fromkeys(prior_headers + HEADERS + [c for r in merged[title] for c in r]))
            write(title, matrix(merged[title], headers), tracker=True)
        full_headers = list(dict.fromkeys((saved_values[FULL][0] if saved_values[FULL] else HEADERS) + HEADERS + [c for r in merged[FULL] for c in r]))
        for title, values in (monthly_view_values(merged, headers=full_headers).items() if publish_tracker_reports else []):
            from monthly_views import keep_view_headers
            if title in worksheets:
                prior_view = worksheets[title].get_all_values()
                values = keep_view_headers(values, prior_view)
                if prior_view:
                    import secrets
                    used_ids = {s.id for s in worksheets.values()}
                    backup_id = secrets.randbelow(2**30)
                    while backup_id in used_ids:
                        backup_id = secrets.randbelow(2**30)
                    backup_title = f'__DataTrace_Backup_{title}_{preview}'[:99]
                    if backup_title not in worksheets:
                        requests.append({'duplicateSheet': {'sourceSheetId': worksheets[title].id, 'newSheetId': backup_id, 'newSheetName': backup_title}})
                        requests.append({'updateSheetProperties': {'properties': {'sheetId': backup_id, 'hidden': True}, 'fields': 'hidden'}})
            write(title, values)
        if frame is not None:
            raw_headers = list(original['columns']) if original else list(frame.columns)
            raw_history = [dict(r, Preview=preview, **{'Preview Timestamp': anchor.isoformat()}) for r in incoming]
            if not raw_history:
                raw_history = [{'Preview': preview, 'Preview Timestamp': anchor.isoformat()}]
            history_headers = list(dict.fromkeys(['Preview', 'Preview Timestamp'] + raw_headers))
            for title in (('All Products', 'Sheet1') if publish_tracker_reports else ('Sheet1',)):
                write(title, matrix(raw_history, history_headers), append=True)
        # These cached sheets are refreshed from tracker results on each sync. API reports
        # also reread live tracker values, including subsequent human edits.
        all_rows = [r for title in TRACKERS for r in merged[title] if key(r)]
        statuses = Counter(text(r.get('Status')) or '(Blank)' for r in all_rows)
        if publish_tracker_reports:
            write('Status Report', [['Status', 'Orders', 'Share', 'Preview', 'Sync Date & Time']] +
                  [[s, n, n / len(all_rows) if all_rows else 0, preview, anchor.isoformat()] for s, n in statuses.items()])
            summaries = sheet_reports(merged, report)
            from monthly_views import capacity_report_values
            for title, kind, period in (('Monthly Orders', 'monthly', 'Month'),):
                columns = [period, 'Received' if kind == 'daily' else 'Month Orders', 'Completed Orders',
                           'Awaiting for Clarification', 'Cancelled', 'Vendor Pending',
                           'In-House Pending', 'Not in latest preview', 'SLA OnTime', 'Missing']
                write(title, matrix(summaries[kind], columns))
            write('Capacity Report', capacity_report_values(summaries['monthly'], summaries['daily']))
        report['ambiguous_count'] = len(report['ambiguous'])
        report['not_in_latest_count'] = len(report['not_in_latest'])
        report['_expected_tracker_cells'] = {title: [
            {c: text(row.get(c)) for c in ('Order Number', 'Status', 'ETA', 'Out Time', 'SLA Expiration', 'Free Site', *EMPTY_COLUMNS) if c in row}
            for row in merged[title]] for title in TRACKERS}
        store.stage_sync_report(preview_id, digest, report)
        if on_progress:
            on_progress(f'Updating trackers and saving {preview} history')
        write_sheet_batch(book, history_sheet, requests, on_progress)
        ensure_tracker_formatting(book)
        actual = read_trackers(book)
        expected_ids = {key(r) for r in all_rows}
        actual_ids = {key(r) for rs in actual.values() for r in rs if key(r)}
        if expected_ids != actual_ids or sum(len(rs) for rs in actual.values()) != sum(len(rs) for rs in merged.values()):
            raise RuntimeError('Tracker readback totals do not match the sync. Preview retained; retry safely.')
        verify_tracker_cells(book, report['_expected_tracker_cells'], actual)
        store.commit_sync_report(preview_id, digest)
        if frame is not None:
            frame.attrs['pass_report'] = {k: v for k, v in report.items() if not k.startswith('_')}
        else:
            import_default_details(book)
        return list(TRACKERS) + ['All Products', 'Sheet1', 'Status Report', 'Monthly Orders', 'Capacity Report']


def verify_tracker_cells(book, expected, actual=None):
    if not expected:
        return
    actual = actual if actual is not None else read_trackers(book)
    for title, rows in expected.items():
        received = actual.get(title, [])
        if len(rows) != len(received) or any(
                any(text(remote.get(column)) != text(value) for column, value in wanted.items())
                for wanted, remote in zip(rows, received)):
            raise RuntimeError(f'Tracker readback values differ in {title}. Preview retained for review and retry.')
