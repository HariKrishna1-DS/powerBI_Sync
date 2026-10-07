"""Persist report source selection and publish the PDF's public reporting tabs.

Imported workbooks are a separate report dataset. They never become queue captures
and therefore cannot infer completion of missing tracker orders.
"""
from collections import Counter
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import csv
import gzip
import hashlib
import json
import re
import secrets
import threading

DAILY_COLUMNS = ['Date', 'Received', 'Completed', 'Clarification', 'Cancelled',
                 'Vendor Pending', 'In-House Pending', 'SLA OnTime', 'Missing']
CAPACITY_COLUMNS = DAILY_COLUMNS[:7] + ['Capacity', 'Ext capacity']


class ReportWorkspace:
    def __init__(self, store):
        self.store = store
        if not hasattr(self, "lock"):
            self.lock = threading.RLock()
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS report_workspace (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')

    def read(self):
        with self.store.connect() as db:
            row = db.execute('SELECT payload FROM report_workspace WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {'mode': 'tracker', 'enabled': True,
            'selected_date': '', 'capacity': 700, 'extended_capacity': 750}

    def save(self, **changes):
        with self.lock:
            value = dict(self.read(), **changes)
            if {'mode', 'imported', 'selected_date', 'capacity', 'extended_capacity'} & changes.keys():
                value['data_revision'] = secrets.token_hex(12)
            with self.store.connect() as db:
                db.execute('INSERT OR REPLACE INTO report_workspace VALUES (1,?)', (json.dumps(value),))
            return value

    def public(self):
        value = self.read()
        public = {k: v for k, v in value.items() if k != 'imported'}
        public['imports'] = [{'name': s['name'], 'rows': len(s['rows']),
                              'worksheets': len(s['files']), 'legacy': s.get('legacy', False)}
                             for s in import_sources(value.get('imported'))]
        return public


def import_sources(imported):
    """Older releases without provenance remain one removable batch."""
    if not imported:
        return []
    if 'sources' in imported:
        return imported['sources']
    # Old releases did not store file provenance. Keep ambiguous batches intact.
    return [{'name': 'Previous imported batch', 'legacy': True, 'rows': imported['rows'],
             'columns': imported['columns'], 'files': imported.get('files', []),
             'reviews': imported.get('reviews', [])}]


def combine_sources(sources):
    from tracker_sync import key
    saved, columns, files, reviews = {}, [], [], []
    for source in sources:
        columns = list(dict.fromkeys(columns + source['columns']))
        reviews.extend(source.get('reviews', []))
        if sum(f['rows'] for f in source['files']) == len(source['rows']):
            offset = 0
            for metadata in source['files']:
                duplicates = 0
                for row in source['rows'][offset:offset + metadata['rows']]:
                    duplicates += key(row) in saved
                    saved[key(row)] = row
                files.append(dict(metadata, duplicates=duplicates))
                offset += metadata['rows']
        else:
            files.extend(source['files'])
            for row in source['rows']:
                saved[key(row)] = row
    if len(saved) > 100000:
        raise ValueError('The combined report exceeds 100,000 orders.')
    return {'rows': list(saved.values()), 'columns': columns, 'files': files,
            'reviews': reviews, 'sources': sources,
            'created': datetime.now(timezone.utc).isoformat()}


def read_report_files(uploads):
    """Read all order worksheets, preserving text IDs and positional headers."""
    from openpyxl import load_workbook
    from tracker_sync import canonical_headers, text, key, STATUS_NAMES
    from production_timing import sla_result
    if not 1 <= len(uploads) <= 30:
        raise ValueError('Choose between 1 and 30 Excel or CSV files.')
    saved, columns, counts, reviews, sources = {}, [], [], [], []
    total = 0
    for name, content in uploads:
        name = Path(name.replace('\\', '/')).name
        suffix = Path(name).suffix.lower()
        book = None
        if suffix == '.xlsx':
            try:
                with ZipFile(BytesIO(content)) as archive:
                    if sum(item.file_size for item in archive.infolist()) > 100 * 1024 * 1024:
                        raise ValueError(f'{name}: expanded workbook exceeds 100 MB.')
                book = load_workbook(BytesIO(content), read_only=True, data_only=True)
                tabs = [(sheet.title, sheet.iter_rows()) for sheet in book.worksheets
                        if sheet.max_column <= 200 and sheet.max_row <= 100001]
                if len(tabs) != len(book.worksheets):
                    raise ValueError(f'{name}: a sheet exceeds 100,000 rows or 200 columns.')
            except ValueError:
                raise
            except Exception as exc:
                raise ValueError(f'{name}: cannot read this XLSX workbook.') from exc
        elif suffix == '.csv':
            try:
                tabs = [(name, iter(csv.reader(content.decode('utf-8-sig').splitlines())))]
            except UnicodeError as exc:
                raise ValueError(f'{name}: CSV must use UTF-8 encoding.') from exc
        else:
            raise ValueError(f'{name}: choose XLSX or CSV files.')
        found = False
        file_rows, file_columns, file_counts, file_reviews = [], [], [], []
        try:
            for title, iterator in tabs:
                headers = None
                for index, cells in enumerate(iterator):
                    raw = [cell.value if hasattr(cell, 'value') else cell for cell in cells]
                    while raw and raw[-1] is None:
                        raw.pop()
                    candidate = canonical_headers(raw)
                    if 'Order Number' in candidate:
                        headers = candidate
                        break
                    if index >= 19:
                        break
                if not headers:
                    continue  # Summary/chart worksheets are not order datasets.
                if not any(c in headers for c in ('Status', 'Task Status')):
                    raise ValueError(f'{name} / {title}: include a Status or Task Status column.')
                found = True
                columns = list(dict.fromkeys(columns + [c for c in headers if c]))
                file_columns = list(dict.fromkeys(file_columns + [c for c in headers if c]))
                count = {'file': name, 'sheet': title, 'rows': 0, 'duplicates': 0}
                for cells in iterator:
                    values = []
                    for cell in cells:
                        value = cell.value if hasattr(cell, 'value') else cell
                        # Excel often stores order IDs as numbers with a 000000 format.
                        fmt = getattr(cell, 'number_format', '')
                        if isinstance(value, int) and re.fullmatch('0+', fmt or ''):
                            value = str(value).zfill(len(fmt))
                        values.append(text(value))
                    row = {h: v for h, v in zip(headers, values) if h}
                    if not key(row):
                        continue
                    total += 1
                    if total > 100000:
                        raise ValueError('The combined import exceeds 100,000 orders.')
                    for target, aliases in {'In-Time': ('Arrival Time', 'RequestArrivalTime', 'In Time'),
                                             'Date': ('Arrival Date',), 'SLA Expiration': ('SLA Expiration*',)}.items():
                        if not row.get(target):
                            row[target] = next((row[a] for a in aliases if row.get(a)), '')
                    if not row.get('Product'):
                        hint = (name + ' ' + title).casefold().replace('_', ' ')
                        if 'full' in hint or title == 'TV Orders':
                            row['Product'] = 'Full Search'
                        elif any(term in hint for term in ('remaining', 'co update', 'c-o', 'current owner')):
                            row['Product'] = 'Remaining Products'
                        else:
                            raise ValueError(f'{name} / {title}: order {row["Order Number"]} needs a Product.')
                    status = ' '.join((row.get('Status') or row.get('Task Status', '')).casefold().split())
                    row['Status'] = STATUS_NAMES.get(status, {'canceled': 'Cancelled', 'completed': 'Completed and Delivered'}.get(status, row.get('Status') or row.get('Task Status', '')))
                    result, reason = sla_result(row)
                    if row.get('Free Site') not in ('On Time', 'Missing'):
                        row['Free Site'] = result
                    if reason:
                        reviews.append({'Order Number': row['Order Number'], 'Reason': reason})
                        file_reviews.append({'Order Number': row['Order Number'], 'Reason': reason})
                    if key(row) in saved:
                        count['duplicates'] += 1
                    saved[key(row)] = row  # Last file / worksheet wins, explicitly reported.
                    file_rows.append(row)
                    count['rows'] += 1
                counts.append(count)
                file_counts.append(count)
            if not found:
                raise ValueError(f'{name}: no worksheet has an Order Number header in its first 20 rows.')
            sources.append({'name': name, 'rows': file_rows, 'columns': file_columns,
                            'files': file_counts, 'reviews': file_reviews})
        finally:
            if book:
                book.close()
    if not saved:
        raise ValueError('No order rows were found. The existing report was kept.')
    return {'rows': list(saved.values()), 'columns': columns, 'files': counts, 'reviews': reviews, 'sources': sources,
            'created': datetime.now(timezone.utc).isoformat()}


def imported_snapshot(imported):
    from tracker_sync import FULL, REMAINING, HEADERS, sheet_reports, key
    from monthly_production import arrival_sort
    rows = arrival_sort(imported['rows'])
    columns = list(dict.fromkeys(HEADERS + imported['columns']))
    members, owners = {True: set(), False: set()}, {}
    for source in import_sources(imported):
        if sum(metadata['rows'] for metadata in source['files']) != len(source['rows']):
            continue  # Legacy batches cannot be safely split by worksheet offsets.
        offset = 0
        for metadata in source['files']:
            hint = re.sub(r'[^a-z0-9]+', ' ', (source['name'] + ' ' + metadata['sheet']).casefold())
            group = (True if 'full search' in hint or metadata['sheet'].casefold() == 'tv orders'
                     else False if any(term in hint for term in ('remaining', 'c o', 'co update', 'current owner'))
                     else None)
            for row in source['rows'][offset:offset + metadata['rows']]:
                identity = key(row)
                full = group if group is not None else ' '.join(row.get('Product', '').casefold().split()) in ('full title', 'full search')
                members[full].add(identity)
                owners[identity] = full
            offset += metadata['rows']
    for row in rows:
        identity = key(row)
        if identity not in owners:
            full = ' '.join(row.get('Product', '').casefold().split()) in ('full title', 'full search')
            members[full].add(identity)
            owners[identity] = full
    # Keep each uploaded report's membership, including its other products and
    # carried orders. Overall totals count shared Order Numbers only once.
    full = arrival_sort([r for r in rows if key(r) in members[True]])
    remaining = arrival_sort([r for r in rows if key(r) in members[False]])
    sheets = {name: {'columns': columns, 'rows': data} for name, data in (
        ('Full Title', full), ('Remaining Products', remaining), ('Overview', rows), ('All Products', rows))}
    reports = sheet_reports({FULL: [r for r in rows if owners[key(r)]],
                             REMAINING: [r for r in rows if not owners[key(r)]]})
    statuses = sorted({str(r.get('Status') or r.get('Task Status') or '(Blank)').strip() for r in rows}, key=str.casefold)
    for periods in reports.values():
        for period in periods:
            counts = Counter(str(r.get('Status') or r.get('Task Status') or '(Blank)').strip() for r in period['rows'])
            period['status_counts'] = {status: counts[status] for status in statuses}
            period.update({'Status: ' + status: counts[status] for status in statuses})
    return {'sheets': sheets, 'reports': reports, 'statuses': statuses,
            'source': 'Imported Excel', 'mode': 'excel', 'offline': False, 'updated_at': imported['created'],
            'revision': hashlib.sha256(json.dumps(imported, sort_keys=True).encode()).hexdigest()}


def capacity_report(reports, settings):
    status_columns = sorted({'Status: ' + status for period in reports['daily']
                             for status in period.get('status_counts', {})}, key=str.casefold)
    daily_capacity = settings.get('capacity', 700)
    extended = settings.get('extended_capacity', 750)
    days = [dict(row, Capacity=daily_capacity, **{'Ext capacity': extended}) for row in reports['daily'] if row['Date'] != 'Undated']
    selected = settings.get('selected_date', '')
    month = selected[:7] if re.fullmatch(r'\d{4}-\d{2}-\d{2}', selected) else next((r['Date'][:7] for r in days), datetime.now().strftime('%Y-%m'))
    monthly = []
    for row in sorted(reports['monthly'], key=lambda r: r['Month']):
        if row['Month'] == 'Undated':
            continue
        count = sum(day['Date'].startswith(row['Month']) for day in days)
        monthly.append(dict(row, Date=row['Month'], Capacity=count * daily_capacity, **{'Ext capacity': count * extended}))
    return {'columns': CAPACITY_COLUMNS + status_columns, 'monthly': monthly,
            'daily': sorted([r for r in days if settings.get('mode') == 'excel' or r['Date'].startswith(month)], key=lambda r: r['Date']),
            'month': month, 'scope_label': 'All imported dates' if settings.get('mode') == 'excel' else month,
            'capacity': daily_capacity, 'extended_capacity': extended}


def report_frames(snapshot, settings):
    from tracker_sync import matrix
    from monthly_views import view_name
    reports = snapshot['reports']
    selected = settings.get('selected_date')
    day = next((r for r in reports['daily'] if r['Date'] == selected), None)
    day = day or next((r for r in reports['daily'] if r['Date'] != 'Undated'), None) or next(iter(reports['daily']), None)
    month = day['Date'][:7] if day and day['Date'] != 'Undated' else datetime.now().strftime('%Y-%m')
    detail_columns = snapshot['sheets']['Full Title']['columns']
    all_rows = snapshot['sheets']['Overview']['rows']
    frames = {'All Products': matrix(all_rows, snapshot['sheets']['Overview']['columns'])}
    for full, label in ((True, 'Full Title'), (False, 'Remaining Products')):
        if snapshot.get('mode') == 'excel':
            rows = snapshot['sheets'][label]['rows']
        else:
            month_report = next((r for r in reports['monthly'] if r['Month'] == month), {})
            rows = [r for r in month_report.get('rows', []) if (' '.join(str(r.get('Product', '')).casefold().split()) in ('full title', 'full search')) == full]
        frames[view_name(full, month)] = matrix([dict(row, No=index) for index, row in enumerate(rows, 1)], detail_columns)
    status_columns = ['Status: ' + status for status in snapshot.get('statuses', [])]
    frames['Monthly Orders'] = matrix(reports['monthly'], ['Month'] + DAILY_COLUMNS[1:] + status_columns)
    daily_status_columns = DAILY_COLUMNS[:7] + ['SLA On Time', 'SLA Missing']
    daily_status = [dict(row, **{'SLA On Time': row.get('SLA OnTime', 0),
                                'SLA Missing': row.get('Missing', 0)})
                    for row in sorted(reports['daily'], key=lambda row: row['Date'])]
    daily_total = {'Date': 'Total', **{column: sum(row.get(column, 0) for row in daily_status)
                                      for column in daily_status_columns[1:]}}
    frames['Daily Status Report'] = matrix(daily_status + [daily_total], daily_status_columns)
    counts = Counter(str(r.get('Status', '')).strip() or '(Blank)' for r in all_rows)
    frames['Status Report'] = [['Status', 'Orders', 'Share']] + [[s, n, n / len(all_rows)] for s, n in counts.items()]
    capacity = capacity_report(reports, dict(settings, selected_date=day['Date'] if day else ''))
    monthly = capacity['monthly']
    year = month[:4]
    total = {'Date': f'{year} YTD Total', **{c: sum(r.get(c, 0) for r in monthly if str(r['Date']).startswith(year)) for c in capacity['columns'][1:]}}
    daily_total = {'Date': 'Total', **{c: sum(r.get(c, 0) for r in capacity['daily']) for c in capacity['columns'][1:]}}
    frames['Capacity Report'] = (matrix(monthly + [total], capacity['columns'])
                                 + matrix(capacity['daily'] + [daily_total], capacity['columns']))
    return frames, capacity


def publish_reports(book, snapshot, settings, backup_root, daily_only=False):
    """Back up replaced reports, publish atomically, and keep seven report tabs visible.

    Internal tracker/history tabs are hidden because sync and recovery need them.
    The retired Daily Orders output is backed up locally before removal.
    """
    from datatrace_sync import sheet_cell, sheet_color
    from tracker_formatting import format_requests
    from monthly_views import view_identity
    frames, capacity = report_frames(snapshot, settings)
    if daily_only:
        frames = {'Daily Status Report': frames['Daily Status Report']}
    metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats,charts)'})['sheets']
    by_title = {s['properties']['title']: s for s in metadata}
    ids = {s['properties']['sheetId'] for s in metadata}
    requests, originals = [], {}
    retired = by_title.get('Daily Orders')
    retired_id = retired['properties']['sheetId'] if retired else None
    if retired:
        originals['Daily Orders'] = book.worksheet('Daily Orders').get_all_values(value_render_option='FORMULA')
        requests.append({'deleteSheet': {'sheetId': retired_id}})
    for title, values in frames.items():
        existing = by_title.get(title)
        if not existing and view_identity(title):
            existing = next((s for name, s in by_title.items() if view_identity(name) == view_identity(title)), None)
        if existing:
            props = existing['properties']
            number = props['sheetId']
            originals[props['title']] = book.worksheet(props['title']).get_all_values(value_render_option='FORMULA')
            if props['title'] != title:
                requests.append({'updateSheetProperties': {'properties': {'sheetId': number, 'title': title}, 'fields': 'title'}})
        else:
            number = secrets.randbelow(2**30)
            while number in ids:
                number = secrets.randbelow(2**30)
            ids.add(number)
            props = {}
            requests.append({'addSheet': {'properties': {'sheetId': number, 'title': title}}})
        cols = max((len(r) for r in values), default=1)
        old_grid = props.get('gridProperties', {})
        requests.append({'updateSheetProperties': {'properties': {'sheetId': number, 'hidden': False,
            'gridProperties': {'rowCount': max(len(values) + 25, old_grid.get('rowCount', 0)),
                               'columnCount': max(cols, old_grid.get('columnCount', 0)), 'frozenRowCount': 1}},
            'fields': 'hidden,gridProperties'}})
        requests.append({'updateCells': {'range': {'sheetId': number},
            'rows': [{'values': [sheet_cell(value) for value in row]} for row in values], 'fields': 'userEnteredValue'}})
        requests.extend(format_requests(number, values, (existing or {}).get('conditionalFormats', []),
                                        replace_rules=title == 'Status Report'))
        # Old report fills can extend far beyond the current data. Clear those
        # blank rows as well; status rules are bounded to populated rows.
        requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': len(values),
            'endColumnIndex': cols}, 'cell': {'userEnteredFormat': {
                'backgroundColor': sheet_color('#ffffff'),
                'textFormat': {'foregroundColor': sheet_color('#111827')}}},
            'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.foregroundColor'}})
        if title == 'Status Report' and len(values) > 1:
            requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': 1,
                'endRowIndex': len(values), 'startColumnIndex': 2, 'endColumnIndex': 3},
                'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0.00%'}}},
                'fields': 'userEnteredFormat.numberFormat'}})
        if title == 'Daily Status Report':
            if len(values) > 2:
                requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': 1,
                    'endRowIndex': len(values)-1, 'endColumnIndex': cols},
                    'cell': {'userEnteredFormat': {'backgroundColor': sheet_color('#ffffff'),
                        'textFormat': {'bold': False, 'foregroundColor': sheet_color('#111827')}}},
                    'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold,userEnteredFormat.textFormat.foregroundColor'}})
            for row_index, row in enumerate(values[1:-1], 1):
                if str(row[0]) == settings.get('selected_date'):
                    requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': row_index,
                        'endRowIndex': row_index+1, 'endColumnIndex': cols},
                        'cell': {'userEnteredFormat': {'backgroundColor': sheet_color('#cfe2f3'),
                            'textFormat': {'bold': True, 'foregroundColor': sheet_color('#111827')}}},
                        'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold,userEnteredFormat.textFormat.foregroundColor'}})
            for row_index, color in ((0, '#f6b26b'), (len(values)-1, '#ffe599')):
                requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': row_index,
                    'endRowIndex': row_index+1, 'endColumnIndex': cols},
                    'cell': {'userEnteredFormat': {'backgroundColor': sheet_color(color), 'textFormat': {'bold': True}}},
                    'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold'}})
        if title == 'Capacity Report':
            last_month_row = len(capacity['monthly']) + 1
            daily_start = last_month_row + 1
            daily_end = daily_start + len(capacity['daily']) + 1
            def source(column):
                return {'sourceRange': {'sources': [
                    {'sheetId': number, 'startRowIndex': daily_start, 'endRowIndex': max(daily_start + 2, daily_end),
                     'startColumnIndex': column, 'endColumnIndex': column + 1}]}}
            spec = {'title': 'Overall — ' + capacity['scope_label'], 'basicChart': {'chartType': 'COMBO', 'legendPosition': 'BOTTOM_LEGEND', 'headerCount': 1,
                'axis': [{'position': 'BOTTOM_AXIS', 'title': 'Date'}, {'position': 'LEFT_AXIS', 'title': 'Orders'}],
                'domains': [{'domain': source(0)}], 'series': [
                    {'series': source(c), 'type': kind, 'targetAxis': 'LEFT_AXIS'} for c, kind in ((1, 'COLUMN'), (2, 'COLUMN'), (7, 'LINE'), (8, 'LINE'))]}}
            chart = next((c for c in (existing or {}).get('charts', []) if c.get('spec', {}).get('title', '').startswith('Overall')), None)
            if chart:
                requests.append({'updateChartSpec': {'chartId': chart['chartId'], 'spec': spec}})
                requests.append({'updateEmbeddedObjectPosition': {'objectId': chart['chartId'], 'newPosition': {'overlayPosition': {'anchorCell': {'sheetId': number, 'rowIndex': len(values)+2, 'columnIndex': 0}, 'widthPixels': 900, 'heightPixels': 350}}, 'fields': 'anchorCell,widthPixels,heightPixels'}})
            else:
                requests.append({'addChart': {'chart': {'spec': spec, 'position': {'overlayPosition': {'anchorCell': {'sheetId': number, 'rowIndex': len(values)+2, 'columnIndex': 0}, 'widthPixels': 900, 'heightPixels': 350}}}}})
            for start, end, color, bold in ((0, 1, '#f6b26b', True), (daily_start, daily_start+1, '#f6b26b', True), (1, last_month_row, '#d9ead3', False), (last_month_row, last_month_row+1, '#a4c2f4', True), (len(values)-1, len(values), '#ffe599', True)):
                if end > start:
                    requests.append({'repeatCell': {'range': {'sheetId': number, 'startRowIndex': start, 'endRowIndex': end, 'endColumnIndex': cols},
                        'cell': {'userEnteredFormat': {'backgroundColor': sheet_color(color), 'textFormat': {'bold': bold}}},
                        'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.bold'}})
    if not daily_only:
        shown_ids = {req['updateSheetProperties']['properties']['sheetId'] for req in requests if req.get('updateSheetProperties', {}).get('properties', {}).get('hidden') is False}
        for item in metadata:
            props = item['properties']
            if props['sheetId'] != retired_id and props['sheetId'] not in shown_ids and not props.get('hidden'):
                requests.append({'updateSheetProperties': {'properties': {'sheetId': props['sheetId'], 'hidden': True}, 'fields': 'hidden'}})
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / f'reports-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.json.gz'
    with gzip.open(backup, 'wt', encoding='utf-8') as stream:
        json.dump({'metadata': metadata, 'values': originals}, stream)
    book.batch_update({'requests': requests})
    # A failed/lost reply leaves the source saved and retryable. Each retry rereads
    # metadata, so no chart, tab or appended data can be duplicated.
    for title, wanted in frames.items():
        actual = book.worksheet(title).get_all_values(value_render_option='UNFORMATTED_VALUE')
        def normalized(matrix):
            result = []
            for row in matrix:
                row = [str(float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v) for v in row]
                while row and not row[-1]:
                    row.pop()
                result.append(row)
            while result and not result[-1]:
                result.pop()
            return result
        if normalized(actual) != normalized(wanted):
            raise RuntimeError(f'{title} could not be verified. Retry publishing the saved report.')
    highlighted = settings.get('selected_date', '')
    highlighted = highlighted if any(str(row[0]) == highlighted for row in frames['Daily Status Report'][1:-1]) else ''
    return {'tabs': list(frames), 'backup': str(backup), 'highlighted_date': highlighted}


def register_report_routes(app, workspace, gate, load_snapshot, get_book, invalidate):
    from flask import request, jsonify, send_file
    from tracker_sync import sync_lock

    requested = threading.Event()
    full_requested = threading.Event()
    worker_lock = threading.Lock()
    worker = None
    stopped = app.extensions.get('stop_scheduler', threading.Event())

    def publish(daily_only=False):
        revision = workspace.read().get('data_revision')
        try:
            with sync_lock(workspace.store.root):
                settings = workspace.read()
                revision = settings.get('data_revision')
                with workspace.lock:
                    if workspace.read().get('data_revision') == revision:
                        workspace.save(publication_state='working', sync_error=None)
                snapshot = (imported_snapshot(settings['imported'])
                            if settings['mode'] == 'excel' and settings.get('imported')
                            else load_snapshot(force=True, tracker_only=True))
                if snapshot.get('offline'):
                    raise RuntimeError('Reconnect Google Sheets before publishing tracker reports.')
                book, _ = get_book()
                if workspace.read().get('data_revision') != revision:
                    requested.set()
                    return {'synced': False, 'queued': True}
                result = publish_reports(book, snapshot, settings, workspace.store.root.parent / 'backups' / 'reports', daily_only)
            with workspace.lock:
                if workspace.read().get('data_revision') != revision:
                    requested.set()
                    return dict(result, synced=False, queued=True)
                workspace.save(sync_error=None, publication_state='synced', highlighted_date=result['highlighted_date'],
                               synced_at=datetime.now(timezone.utc).isoformat())
            return dict(result, synced=True)
        except Exception as exc:
            app.logger.exception('Report publication failed; saved source retained')
            with workspace.lock:
                if workspace.read().get('data_revision') == revision:
                    workspace.save(sync_error=str(exc), publication_state='error')
                else:
                    requested.set()
                    return {'synced': False, 'queued': True}
            return {'synced': False, 'sync_error': str(exc)}

    def publication_worker():
        while not stopped.is_set():
            if not requested.wait(1):
                continue
            if not gate.acquire(timeout=1):
                continue
            try:
                with workspace.lock:
                    requested.clear()
                    full = full_requested.is_set()
                    full_requested.clear()
                publish(daily_only=not full)
            finally:
                gate.release()

    def queue_publication(daily_only=False):
        nonlocal worker
        with workspace.lock:
            workspace.save(publication_state='pending', sync_error=None, enabled=True)
            if not daily_only:
                full_requested.set()
            requested.set()
        with worker_lock:
            if worker is None or not worker.is_alive():
                worker = threading.Thread(target=publication_worker, daemon=True, name='report-publication')
                worker.start()
        return {'synced': False, 'queued': True}

    app.extensions['queue_report_publication'] = queue_publication

    @app.get('/api/report-workspace')
    def get_report_workspace():
        return jsonify(workspace.public())

    @app.post('/api/report-source')
    def choose_report_source():
        mode = (request.get_json(silent=True) or {}).get('mode')
        if mode not in ('tracker', 'excel'):
            raise ValueError('Choose Tracker report or Import Excel report.')
        with workspace.lock:
            if mode == 'excel' and not workspace.read().get('imported'):
                raise ValueError('Import Excel files before selecting the Excel report.')
            workspace.save(mode=mode, enabled=True, selected_date='')
        invalidate()
        return jsonify(**workspace.public(), publication=queue_publication())

    @app.post('/api/report-import')
    def import_reports():
        files = request.files.getlist('files')
        # Parse before any mutation. Local report edits do not wait for cloud sync.
        uploaded = read_report_files([(file.filename, file.read()) for file in files if file.filename])
        with workspace.lock:
            sources = [] if request.form.get('replace_all') == 'true' else import_sources(workspace.read().get('imported'))
            uploaded_names = {s['name'].casefold() for s in uploaded['sources']}
            sources = [s for s in sources if not (s.get('legacy') and
                       {f['file'].casefold() for f in s['files']}.issubset(uploaded_names))]
            replaced = []
            for source in uploaded['sources']:
                name = source['name'].casefold()
                replaced.extend(s['name'] for s in sources if s['name'].casefold() == name)
                sources = [s for s in sources if s['name'].casefold() != name]
                sources.append(source)
            imported = combine_sources(sources)
            workspace.save(imported=imported, files=imported['files'], row_count=len(imported['rows']),
                           imported_at=imported['created'], mode='excel', enabled=True, selected_date='')
        invalidate()
        publication = queue_publication()
        return jsonify(**workspace.public(), reviews=imported['reviews'], replaced_files=replaced, publication=publication), 201

    @app.post('/api/report-remove')
    def remove_imported_file():
        body = request.get_json(silent=True) or {}
        with workspace.lock:
            sources = import_sources(workspace.read().get('imported'))
            name = body.get('file')
            if body.get('all') is True:
                sources = []
            elif isinstance(name, str) and any(s['name'] == name for s in sources):
                sources = [s for s in sources if s['name'] != name]
            else:
                raise ValueError('Choose an imported file to remove.')
            imported = combine_sources(sources)
            # An empty Excel report stays empty until the user selects Tracker.
            workspace.save(imported=imported, files=imported['files'], row_count=len(imported['rows']),
                           imported_at=imported['created'], selected_date='')
        invalidate()
        return jsonify(**workspace.public(), publication=queue_publication())

    @app.post('/api/report-publish')
    def publish_current_reports():
        return jsonify(**queue_publication())

    @app.post('/api/report-date')
    def choose_report_date():
        date = (request.get_json(silent=True) or {}).get('date', '')
        if not isinstance(date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}|Undated', date):
            raise ValueError('Choose a report date.')
        if not any(row['Date'] == date for row in load_snapshot()['reports']['daily']):
            raise ValueError('That date is no longer in the selected report source.')
        workspace.save(selected_date=date, enabled=True)
        return jsonify(date=date, **queue_publication(daily_only=True))

    @app.get('/api/capacity-report')
    def get_capacity_report():
        snapshot = load_snapshot()
        return jsonify(**capacity_report(snapshot['reports'], workspace.read()),
                       source=snapshot.get('source'), offline=snapshot.get('offline', False))

    @app.post('/api/report-capacity')
    def save_capacity():
        body = request.get_json(silent=True) or {}
        for field in ('capacity', 'extended_capacity'):
            value = body.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1000000:
                raise ValueError('Capacity must be a whole number from 0 to 1,000,000.')
        workspace.save(capacity=body['capacity'], extended_capacity=body['extended_capacity'], enabled=True)
        return jsonify(**workspace.public(), publication=queue_publication())

    if workspace.read().get('publication_state') in ('pending', 'working'):
        queue_publication()

    @app.get('/api/export/report')
    def export_report():
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.chart import BarChart, LineChart, Reference
        from openpyxl.chart.series import SeriesLabel
        snapshot = load_snapshot()
        settings = workspace.read()
        month = request.args.get('month')
        if month:
            if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
                raise ValueError('Choose a month in YYYY-MM format.')
            selected = next((r for r in snapshot['reports']['daily'] if r['Date'].startswith(month)), None)
            if not selected:
                raise ValueError('No orders are available for that month.')
            settings = dict(settings, selected_date=selected['Date'])
        frames, capacity = report_frames(snapshot, settings)
        book = Workbook()
        book.remove(book.active)
        for title, values in frames.items():
            sheet = book.create_sheet(title[:31])
            for row in values:
                sheet.append(row)
            for cells in sheet:
                for cell in cells:
                    if isinstance(cell.value, str):
                        cell.data_type = 's'
            for cell in sheet[1]:
                cell.font = Font(bold=True)
                cell.fill = PatternFill('solid', fgColor='F6B26B')
            sheet.freeze_panes = 'A2'
        sheet = book['Capacity Report']
        start = len(capacity['monthly']) + 4
        end = start + len(capacity['daily']) - 1
        if end >= start:
            chart, lines = BarChart(), LineChart()
            chart.title = 'Overall — ' + capacity['scope_label']
            for column, target in ((2, chart), (3, chart), (8, lines), (9, lines)):
                target.add_data(Reference(sheet, min_col=column, min_row=start, max_row=end))
                target.series[-1].title = SeriesLabel(v=CAPACITY_COLUMNS[column-1])
            chart.set_categories(Reference(sheet, min_col=1, min_row=start, max_row=end))
            chart += lines
            sheet.add_chart(chart, f'A{len(frames["Capacity Report"])+3}')
        stream = BytesIO()
        book.save(stream)
        stream.seek(0)
        return send_file(stream, as_attachment=True, download_name='Production_data.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return publish
