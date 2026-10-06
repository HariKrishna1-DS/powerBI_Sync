"""DataTrace extraction, local exports and authenticated Google Sheets sync."""
import datetime as dt
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import time

import pandas as pd
from openpyxl.worksheet.table import Table, TableStyleInfo
from sync_config import BASE_DIR, ASSET_DIR, SPREADSHEET_ID, WORKSHEET_GID, TARGET_GSHEET_URL

# Product list used only by dashboard filters; sync includes every product.
REMAINING_PRODUCTS = json.loads(Path(__file__).with_name('remaining_products.json').read_text(encoding='utf-8'))


ALL_PRODUCT_FIELDS = [
    ('Order Number', 'Order Number'), ('External Product Order Number', None),
    ('Originator Product Order Number', 'OPON'), ('Borrower', 'Borrower'),
    ('Online/Ground', 'Online/ Ground'), ('Product', 'Product'), ('Last User', 'Last User'),
    ('Skill Grade', 'Skill Grade'), ('State', 'St'), ('County', 'County'),
    ('Municipality', 'Municipality'), ('Parcel ID', 'Parcel ID'), ('Task Name', 'Task Name'),
    ('Task Status', 'Task Status'), ('Comment', 'Comment'), ('ETA', 'ETA'),
    ('ETA Comments', 'ETA Comments'), ('Time Since Arrival (hours)', 'Queue Age Hours'),
    ('Task Time In Queue (hours)', 'Task Time in Queue'),
    ('WorkflowSuspended', '__workflow_suspended__'), ('TaskSuspended', '__task_suspended__'),
    ('IsAutomated', None), ('IsBlocked', None), ('SLA Expiration', 'SLA Expiration*'),
    ('Completed Time (hours)', 'Completed Time'), ('Vendor', 'Vendor'), ('Originator', 'Orig'),
    ('ClientCode', 'Client'), ('RequestArrivalTime', 'Arrival Time'),
    ('WorkflowSuspendReason', None), ('UserContextId', None), ('WorkflowSuspendTypeId', None),
    ('WorkflowTaskSuspendTypeId', None), ('SuspendUntil', None), ('Out Time', 'Out Time'),
]
SLICED_PRODUCT_FIELDS = [
    ('No', '__number__'), ('Date', 'Arrival Date'), ('Order Number', 'Order Number'),
    ('TraceQ Id', 'TraceQ Id'), ('State', 'St'), ('County', 'County'), ('Client', 'Client'),
    ('Online/Ground', 'Online/ Ground'), ('Product', 'Product'), ('Status', 'Task Status'),
    ('ETA', 'ETA'), ('Comments', 'Comment'), ('Assignee', 'Last User'), ('Searcher', 'Searcher'),
    ('Clarification Requested', 'Clarification Requested'), ('Shift', 'Shift'),
    ('Process date', 'Completed Time'), ('Review/QC', 'Review/QC'), ('Expense', 'Expense'),
    ('In-Time', 'Arrival Time'), ('Out Time', 'Out Time'), ('SLA Expiration', 'SLA Expiration*'),
    ('Free Site', 'Free Site'), ('review', 'review'),
]
FULL_TITLE_FIELDS = list(SLICED_PRODUCT_FIELDS)
REMAINING_PRODUCT_FIELDS = list(SLICED_PRODUCT_FIELDS)
REPORT_SHEETS = [('All Products', ALL_PRODUCT_FIELDS), ('Full Title', FULL_TITLE_FIELDS),
                 ('Remaining Products', REMAINING_PRODUCT_FIELDS)]
STATUS_COLORS = json.loads((ASSET_DIR / 'status_colors.json').read_text(encoding='utf-8'))


def target_worksheet():
    import gspread
    from google.auth.exceptions import RefreshError
    from google.oauth2.service_account import Credentials
    value = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'service_account.json').strip()
    if os.environ.get('DATATRACE_DESKTOP') == '1' and (not value or not SPREADSHEET_ID):
        raise RuntimeError('Open Connections & settings to add your Google Sheet and service-account key.')
    try:
        if value.startswith('{'):
            info = json.loads(value)
        else:
            path = Path(value)
            if not path.is_absolute():
                path = BASE_DIR / path
            info = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError('Set GOOGLE_SERVICE_ACCOUNT_JSON to a valid service account JSON file or JSON object.') from exc
    email = info.get('client_email', 'the client_email in your service account JSON')
    try:
        credentials = Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/spreadsheets'])
        client = gspread.authorize(credentials)
        client.set_timeout((10, 90))
        book = client.open_by_key(SPREADSHEET_ID)
        if os.environ.get('DATATRACE_DESKTOP') == '1':
            from sheets_writer import GuardedBook, device_identity
            book = GuardedBook(book, device_identity(BASE_DIR))
        return book, book.get_worksheet_by_id(WORKSHEET_GID)
    except RefreshError as exc:
        details = next((arg for arg in exc.args if isinstance(arg, dict)), {})
        description = str(details.get('error_description', '')).casefold()
        if 'invalid jwt signature' in description:
            message = (
                'Google Sheets authentication failed: Invalid JWT Signature. '
                f'Replace the service-account JSON with a new active key for {email}, '
                'update GOOGLE_SERVICE_ACCOUNT_JSON, then restart or redeploy the backend.'
            )
        elif 'reasonable timeframe' in description or 'short-lived token' in description:
            message = ('Google Sheets authentication failed: the server clock is outside the accepted range. '
                       'Synchronize the server date and time, then retry.')
        else:
            message = (f'Google Sheets authentication failed for {email}. '
                       'Check that the service account and its key are active, update '
                       'GOOGLE_SERVICE_ACCOUNT_JSON, then restart or redeploy the backend.')
        raise RuntimeError(message) from exc
    except Exception as exc:
        raise RuntimeError(
            f'Google Sheets access failed ({type(exc).__name__}). Enable the Google Sheets API, '
            f'check credentials and worksheet gid={WORKSHEET_GID}, and share '
            f'{TARGET_GSHEET_URL} with {email} as Editor.') from exc


def validate_queue(df):
    if df.empty:
        raise ValueError('No queue records extracted. Existing exports and Google Sheet were retained.')
    if not {'Arrival Time', 'Task Status'}.issubset(df.columns):
        raise ValueError('Extracted data is not a recognized DataTrace queue table.')
    if df.columns.duplicated().any():
        raise ValueError('Queue column names must be unique.')


def powerbi_table(df, timestamp):
    result = df.copy()
    # Portal dates have no timezone. Do not invent a year for partial SLA dates.
    arrival = pd.to_datetime(result['Arrival Time'], format='%m/%d/%Y %I:%M %p', errors='coerce')
    result['Arrival Date'] = arrival.dt.strftime('%Y-%m-%d').fillna('')
    duration = result.get('Time Since Arrival', pd.Series('', index=df.index)).str.extract(
        r'^(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?$')
    hours = duration.apply(pd.to_numeric, errors='coerce')
    result['Queue Age Hours'] = (hours[0].fillna(0) * 24 + hours[1].fillna(0)
                                 + hours[2].fillna(0) / 60).where(hours.notna().any(axis=1)).round(2)
    status = result['Task Status'].str.lower()
    result['Is Available'] = status.eq('available')
    from tracker_sync import suspended
    result['WorkflowSuspended'] = [suspended(row) or str(row.get('Task Status', '')).strip().casefold() == 'workflow suspended'
                                    for row in result.to_dict('records')]
    result['Is Suspended'] = result['WorkflowSuspended']
    sla = result.get('SLA Expiration*', result.get('SLA Expiration', pd.Series('', index=df.index)))
    result['SLA Status'] = sla.map(lambda v: 'Overdue' if str(v).startswith('-') else 'Unknown')
    result['Sync Timestamp'] = timestamp
    return result


def _product_match_mask(series, selected_set):
    if not selected_set:
        return pd.Series(True, index=series.index)
    direct_mask = series.isin(selected_set)
    unmatched_indices = series[~direct_mask].index
    if len(unmatched_indices) == 0:
        return direct_mask
    mask = direct_mask.copy()
    cleaned_selected = [s.rstrip('.').strip() for s in selected_set if s.rstrip('.').strip()]
    for idx, val in series[unmatched_indices].items():
        v_clean = val.rstrip('.').strip()
        if not v_clean:
            continue
        for s, s_clean in zip(selected_set, cleaned_selected):
            if s == val or (v_clean and (s.startswith(v_clean) or val.startswith(s_clean))):
                mask[idx] = True
                break
    return mask


def parse_report_datetime(value):
    text = re.sub(r'\s+', ' ', str(value if pd.notna(value) else '')).strip()
    if not text:
        return None
    # Excel/Google Sheets date serials can be returned as displayed numbers
    # when an imported date column has General formatting.
    if re.fullmatch(r'\d{5}(?:\.\d+)?', text):
        serial = float(text)
        if 20000 <= serial < 100000:
            return dt.datetime(1899, 12, 30) + dt.timedelta(days=serial)
    try:
        parsed = dt.datetime.fromisoformat(text.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=None)
    except ValueError:
        pass
    for pattern in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
                    '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return dt.datetime.strptime(text.upper(), pattern)
        except ValueError:
            pass
    return None


def sla_result(row):
    from tracker_sync import free_site
    anchor = capture_anchor(row.get('Sync Timestamp', ''))
    data = dict(row)
    data['SLA Expiration'] = row.get('SLA Expiration*', row.get('SLA Expiration', ''))
    return free_site(data, anchor)[0]


def sla_expiration(row):
    from tracker_sync import deadline
    anchor = capture_anchor(row.get('Sync Timestamp', ''))
    return deadline(row.get('SLA Expiration*', row.get('SLA Expiration', '')), anchor)


def capture_anchor(value):
    """Capture instants use IST; imported order timestamps remain wall clocks."""
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return parse_report_datetime(value)


def report_frame(df, fields, product=None, selected_products=None):
    if product == '__remaining__':
        if 'Product' in df.columns:
            products = df['Product'].fillna('').astype(str).str.split().str.join(' ').str.casefold()
            not_full = ~products.isin({'full title', 'full search'})
            if selected_products is not None and len(selected_products) > 0:
                selected_set = {str(p).strip().casefold() for p in selected_products}
                match_mask = _product_match_mask(products, selected_set)
                source = df[match_mask & not_full]
            else:
                source = df[not_full]
        else:
            source = df
    elif product == 'full title':
        if 'Product' in df.columns:
            products = df['Product'].fillna('').astype(str).str.split().str.join(' ').str.casefold()
            source = df[products.isin({'full title', 'full search'})]
        else:
            source = df.iloc[:0]
    elif product is not None:
        if 'Product' in df.columns:
            source = df[df['Product'].fillna('').astype(str).str.strip().str.casefold().eq(product)]
        else:
            source = df.iloc[:0]
    else:
        source = df
    matrix = []
    for number, (_, row) in enumerate(source.iterrows(), start=1):
        values = []
        for target, source_column in fields:
            if source_column == '__number__':
                value = number
            elif source_column == '__workflow_suspended__':
                from production_rules import suspended
                value = suspended(row)
            elif source_column == '__task_suspended__':
                value = str(row.get('Task Status', '')).strip().casefold() == 'task suspended'
            else:
                value = ''
                if source_column and source_column in row and pd.notna(row[source_column]):
                    value = row[source_column]
                elif target and target in row and pd.notna(row[target]):
                    value = row[target]
                elif source_column:
                    aliases = {
                        'Arrival Date': ['Date'],
                        'St': ['State'],
                        'Online/ Ground': ['Online/Ground', 'Online/Gorund'],
                        'Comment': ['Comments', 'ETA Comments'],
                        'Last User': ['Assignee'],
                        'Completed Time': ['Process date', 'Processed Date'],
                        'Arrival Time': ['In-Time'],
                        'SLA Expiration*': ['SLA Expiration'],
                        'Task Status': ['Status'],
                    }
                    for alt in aliases.get(source_column, []):
                        if alt in row and pd.notna(row[alt]):
                            value = row[alt]
                            break
            if fields == SLICED_PRODUCT_FIELDS:
                if target == 'Free Site':
                    value = sla_result(row)
                elif target == 'SLA Expiration':
                    parsed = sla_expiration(row)
                    if parsed:
                        value = parsed.strftime('%m/%d/%Y %I:%M %p')
                elif target in ('Date', 'In-Time', 'Out Time', 'Process date'):
                    parsed = parse_report_datetime(value)
                    if parsed:
                        value = parsed.strftime('%m/%d/%Y') if target == 'Date' else parsed.strftime('%m/%d/%Y %I:%M:%S %p')
            values.append(value)
        matrix.append(values)
    return pd.DataFrame(matrix, columns=[target for target, _ in fields])


def report_frames(df, selected_products=None):
    return [report_frame(df, ALL_PRODUCT_FIELDS),
            report_frame(df, FULL_TITLE_FIELDS, 'full title'),
            report_frame(df, REMAINING_PRODUCT_FIELDS, '__remaining__', selected_products=selected_products)]


def status_color(status):
    key = str(status or '').strip().casefold()
    if key in STATUS_COLORS:
        return STATUS_COLORS[key]
    hue = 0
    for character in key:
        hue = (hue * 31 + ord(character)) % 360
    import colorsys
    red, green, blue = colorsys.hls_to_rgb(hue / 360, 0.78, 0.58)
    return '#%02x%02x%02x' % (round(red * 255), round(green * 255), round(blue * 255))


def completion_date(value):
    parsed = parse_report_datetime(value)
    if parsed:
        return parsed.date().isoformat()
    text = str(value or '').strip()
    for pattern in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return dt.datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            continue
    return None


def apply_status_rules(df, rules, reporting_date=None):
    if not isinstance(rules, list):
        raise ValueError('Status rules must be a list.')
    mapping = {}
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError('Invalid status rule.')
        source, target = rule.get('source'), rule.get('target')
        if not isinstance(source, str) or not isinstance(target, str) or not source.strip() or not target.strip():
            raise ValueError('Choose both statuses for each rule.')
        key = source.strip().casefold()
        if key in mapping:
            raise ValueError('Each Status_1 can have only one replacement.')
        mapping[key] = target.strip()
    result = df.copy()
    columns = [column for column in ('Task Status', 'Status') if column in result.columns]
    if mapping and not columns:
        raise ValueError('This preview has no status column.')
    for column in columns:
        result[column] = result[column].map(lambda value: mapping.get(str(value).strip().casefold(), value))
        from production_rules import mapped_status
        for index, row in result.iterrows():
            result.at[index, column] = mapped_status(row, row[column])
    if 'Is Available' in result.columns and columns:
        result['Is Available'] = result[columns[0]].astype(str).str.strip().str.casefold().eq('available')
    return result


def status_report_frame(df, preview_name=None, sync_time=None):
    column = 'Task Status' if 'Task Status' in df.columns else 'Status' if 'Status' in df.columns else None
    preview_name = preview_name or df.attrs.get('preview_name')
    sync_time = sync_time or df.attrs.get('sync_time')
    include_metadata = bool(preview_name or sync_time)

    if not column:
        cols = ['Status', 'Orders', 'Share']
        if include_metadata:
            cols += ['Preview', 'Sync Date & Time']
        return pd.DataFrame(columns=cols)

    counts = df[column].fillna('').astype(str).map(lambda value: value.strip() or '(Blank)').value_counts()
    total = len(df) or 1
    if include_metadata:
        rows = [{'Status': status, 'Orders': int(count), 'Share': f'{(count / total) * 100:.1f}%',
                 'Preview': str(preview_name or ''), 'Sync Date & Time': str(sync_time or '')}
                for status, count in counts.items()]
        cols = ['Status', 'Orders', 'Share', 'Preview', 'Sync Date & Time']
    else:
        rows = [{'Status': status, 'Orders': int(count), 'Share': f'{(count / total) * 100:.1f}%'}
                for status, count in counts.items()]
        cols = ['Status', 'Orders', 'Share']
    return pd.DataFrame(rows, columns=cols)


def export_to_excel_and_csv(df, output_prefix=None):
    prefix = Path(output_prefix) if output_prefix else BASE_DIR / 'queue_data_sheet2'
    csv_path, excel_path = prefix.with_suffix('.csv'), prefix.with_suffix('.xlsx')
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='DataTraceQueue', index=False)
        ws = writer.sheets['DataTraceQueue']
        for row in ws:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
        table = Table(displayName='DataTraceQueue', ref=ws.dimensions)
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        ws.add_table(table)
        ws.freeze_panes = 'A2'
    return str(excel_path), str(csv_path)


def sheet_color(hex_color):
    value = str(hex_color or '').lstrip('#')
    if len(value) != 6:
        return None
    try:
        red, green, blue = [int(value[index:index + 2], 16) / 255 for index in (0, 2, 4)]
    except ValueError:
        return None
    return {'red': red, 'green': green, 'blue': blue}


def sheet_cell(value, background=None):
    if pd.isna(value):
        cell = {}
    elif isinstance(value, bool):
        cell = {'userEnteredValue': {'boolValue': value}}
    elif isinstance(value, (int, float)):
        cell = {'userEnteredValue': {'numberValue': value}}
    else:
        cell = {'userEnteredValue': {'stringValue': str(value)}}
    color = sheet_color(background)
    if color:
        cell['userEnteredFormat'] = {'backgroundColor': color}
    return cell


def status_row_format_request(df, sheet_id):
    from tracker_formatting import foreground
    column = next((name for name in ('Task Status', 'Status') if name in df.columns), None)
    if column is None or df.empty:
        return None
    return {'updateCells': {
        'range': {'sheetId': sheet_id, 'startRowIndex': 1,
                  'startColumnIndex': 0, 'endColumnIndex': len(df.columns)},
        'rows': [{'values': [{'userEnteredFormat': {'backgroundColor': sheet_color(status_color(value)),
                                                  'textFormat': {'foregroundColor': sheet_color(foreground(status_color(value)))}}}
                            for _ in df.columns]} for value in df[column].fillna('')],
        'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.foregroundColor'}}


def write_sheet_batch(book, sheet, requests, on_progress=None, verify_commit=None):
    """Retry transient failures; verify receipts before replaying sheet creation."""
    from requests.exceptions import Timeout, ConnectionError
    from gspread.exceptions import APIError
    for attempt in range(3):
        try:
            book.batch_update({'requests': requests})
            return
        except (Timeout, ConnectionError) as exc:
            reason = 'timed out' if isinstance(exc, Timeout) else 'lost the network connection'
            if verify_commit and verify_commit():
                return
            if attempt == 2:
                raise RuntimeError(f'Google Sheets {reason} while updating {sheet.title} after three attempts. '
                                   'The write may have completed; check the tab before retrying. Saved previews are retained.') from exc
        except APIError as exc:
            code = exc.code
            if code not in (429, 500, 502, 503, 504):
                if code == 403:
                    message = f'Google Sheets denied the write to {sheet.title}. Check Editor access and worksheet protection.'
                else:
                    message = f'Google Sheets rejected the update to {sheet.title} (HTTP {code}). Check the worksheet structure and protection.'
                raise RuntimeError(message) from exc
            if verify_commit and verify_commit():
                return
            if attempt == 2:
                raise RuntimeError(f'Google Sheets could not update {sheet.title} (HTTP {code}) after three attempts. '
                                   'Wait briefly and retry; saved previews are retained.') from exc
        if on_progress:
            on_progress(f'Google Sheets is slow: retrying {sheet.title} (attempt {attempt + 2} of 3)')
        time.sleep(2 ** attempt)


def sync_dataframe(df, target=None, validate=True, row_backgrounds=None, color_status=False,
                   existing_values=None, on_progress=None):
    if validate:
        validate_queue(df)
    book, sheet = target or target_worksheet()
    values = [list(df.columns)] + df.astype(object).values.tolist()
    include_format = row_backgrounds is not None
    row_backgrounds = row_backgrounds or [None] * len(values)
    requests = []
    if existing_values is None:
        existing_values = sheet.get_all_values()
    previous_rows = len(existing_values) if isinstance(existing_values, list) else 0
    target_rows = max(sheet.row_count, len(values), previous_rows)
    if target_rows != sheet.row_count or sheet.col_count != len(df.columns):
        # Absolute dimensions make replay safe even if a timed-out request committed.
        requests.append({'updateSheetProperties': {
            'properties': {'sheetId': sheet.id, 'gridProperties': {
                'rowCount': target_rows, 'columnCount': len(df.columns)}},
            'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})
    # Cover new and previously populated rows without touching the entire blank grid.
    requests.append({'updateCells': {'range': {'sheetId': sheet.id, 'startRowIndex': 0,
                     'endRowIndex': max(len(values), previous_rows), 'startColumnIndex': 0,
                     'endColumnIndex': len(df.columns)},
                     'rows': [{'values': [sheet_cell(v, row_backgrounds[index] if index < len(row_backgrounds) else None)
                                          for v in row]} for index, row in enumerate(values)],
                     'fields': 'userEnteredValue,userEnteredFormat.backgroundColor' if include_format else 'userEnteredValue'}})
    if color_status:
        status_format = status_row_format_request(df, sheet.id)
        if status_format:
            requests.append(status_format)
        requests.append({'setBasicFilter': {'filter': {'range': {
            'sheetId': sheet.id, 'startRowIndex': 0, 'endRowIndex': len(values),
            'startColumnIndex': 0, 'endColumnIndex': len(df.columns)}}}})
    if on_progress:
        on_progress(f'Writing {sheet.title} to Google Sheets')
    write_sheet_batch(book, sheet, requests, on_progress)
    if on_progress:
        on_progress(f'Verifying {sheet.title}')
    received = sheet.get_all_values()
    for column in ('Task Status', 'Status', 'Out Time'):
        if column in df.columns:
            offset = list(df.columns).index(column)
            expected_statuses = df[column].fillna('').astype(str).tolist()
            actual_statuses = [row[offset] if len(row) > offset else '' for row in received[1:]]
            if actual_statuses != expected_statuses:
                raise RuntimeError(f'Google Sheets status verification failed on {sheet.title}. Retry the sync.')
    if (len(received) != len(values) or not received or received[0] != list(df.columns)
            or (validate and any(len(row) != len(df.columns) for row in received))):
        raise RuntimeError('Google Sheets write returned, but row/column verification failed. Check the worksheet before retrying.')
    return sheet.title


def sync_workbook(df, selected_products=None, on_progress=None):
    from tracker_sync import sync_trackers
    return sync_trackers(df, on_progress=on_progress)


def read_target(gid=None, title=None):
    book, sheet = target_worksheet()
    if gid is not None and int(gid) != sheet.id:
        sheet = book.get_worksheet_by_id(int(gid))
    elif gid is None and title:
        sheet = book.worksheet(title)
    values = sheet.get_all_values()
    if not values:
        return pd.DataFrame()
    return pd.DataFrame(values[1:], columns=values[0]).fillna('')


def run_sync(on_progress=None, auto_sync=True):
    from dotenv import load_dotenv
    from preview_store import PreviewStore
    if os.environ.get('DATATRACE_DESKTOP') != '1':
        load_dotenv(BASE_DIR / '.env', override=True)
    status = {'action': 'extract', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scrape': 'pending', 'google_sheet': 'not_synced', 'rows': 0, 'error': None}
    def progress(stage):
        status['stage'] = stage
        if on_progress:
            on_progress(dict(status))
    try:
        store = PreviewStore(BASE_DIR / 'previews')
        if auto_sync and not store.list():
            progress('Recovering preview numbering from Google Sheets')
            from tracker_sync import read_preview_history
            book, _ = target_worksheet()
            for saved in read_preview_history(book):
                store.restore(saved['id'], saved['columns'], saved['rows'], saved['source'], created=saved['created'])
                store.mark_synced(saved['id'], {'recovered': True})
        progress('Connecting to DataTrace')
        if not os.getenv('DATATRACE_USERNAME') or not os.getenv('DATATRACE_PASSWORD'):
            raise RuntimeError('Set DATATRACE_USERNAME and DATATRACE_PASSWORD in gsheet_dashboard/.env or the environment.')
        # Per-run output prevents old exports from being uploaded after a failed scrape.
        with tempfile.TemporaryDirectory(prefix='datatrace-') as folder:
            output = Path(folder) / 'queue.json'
            metadata_path = Path(folder) / 'capture-metadata.json'
            env = dict(os.environ, DATATRACE_OUTPUT_JSON=str(output), DATATRACE_OUTPUT_META=str(metadata_path))
            extractor = Path(os.environ.get('DATATRACE_EXTRACTOR_DIR', str(ASSET_DIR)))
            node = os.environ.get('DATATRACE_NODE_EXECUTABLE', 'node')
            env.pop('GOOGLE_SERVICE_ACCOUNT_JSON', None)
            env.pop('DATATRACE_DESKTOP_TOKEN', None)
            if os.environ.get('DATATRACE_DESKTOP') == '1':
                env['ELECTRON_RUN_AS_NODE'] = '1'
            process = subprocess.run([node, str(extractor / 'scrape_datatrace.js')],
                                     cwd=extractor, env=env, capture_output=True, text=True, timeout=300,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if process.returncode:
                details = process.stderr if isinstance(process.stderr, str) else ''
                lines = [line.strip() for line in details.splitlines() if line.strip()]
                reason = next((line for line in lines if '[!] Puppeteer Automation Error:' in line),
                              lines[0] if lines else 'Check portal login/MFA and Node dependencies.')
                for key in ('DATATRACE_USERNAME', 'DATATRACE_PASSWORD'):
                    secret = os.getenv(key)
                    if secret:
                        reason = reason.replace(secret, '[redacted]')
                raise RuntimeError(f'DataTrace extraction failed: {reason[:600]}')
            df = pd.DataFrame(json.loads(output.read_text(encoding='utf-8')))
            metadata = json.loads(metadata_path.read_text(encoding='utf-8')) if metadata_path.exists() else {'kind': 'portal', 'complete': False}
        validate_queue(df)
        status.update(scrape='success', rows=len(df))
        df = powerbi_table(df, status['started_at'])
        progress('Saving preview')
        store = PreviewStore(BASE_DIR / 'previews')
        preview = store.save(df, metadata=metadata)
        status['preview_id'] = preview['id']
        status['preview_name'] = preview['name']
        export_to_excel_and_csv(df)
        status['local_export'] = 'success'
        status['last_success_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        if auto_sync:
            from order_reporting import automatic_sync_frame
            for pending in store.pending():
                frame, _ = automatic_sync_frame(pending, store=store)
                frame.attrs.update(preview_id=pending['id'], preview_name=pending['name'])
                status['worksheets'] = sync_workbook(frame, on_progress=progress)
                status['pass_report'] = frame.attrs.get('pass_report')
                store.mark_synced(pending['id'], status['pass_report'])
            status['action'] = 'sync'
            status['google_sheet'] = 'success'
    except Exception as exc:
        status['error'] = str(exc)
        status['google_sheet' if status['scrape'] == 'success' else 'scrape'] = 'failed'
    previous = load_status()
    status.setdefault('last_success_at', previous.get('last_success_at'))
    progress('Finished' if not status['error'] else 'Finished with errors')
    (BASE_DIR / 'sync_status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return status


def load_status():
    try:
        return json.loads((BASE_DIR / 'sync_status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


if __name__ == '__main__':
    result = run_sync()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result['error'] else 0)
