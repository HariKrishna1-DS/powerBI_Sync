"""DataTrace extraction, local exports and authenticated Google Sheets sync."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile

import pandas as pd
from openpyxl.worksheet.table import Table, TableStyleInfo
from sync_config import BASE_DIR, SPREADSHEET_ID, WORKSHEET_GID, TARGET_GSHEET_URL

# Product list from the September 2026 C-O and Update production report, Sheet1 column I.
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
FULL_TITLE_FIELDS = [
    ('No', '__number__'), ('Received Date', 'Arrival Date'), ('Order number', 'Order Number'),
    ('TraceQ id', None), ('State', 'St'), ('County', 'County'), ('Client', 'Client'),
    ('Online/Gorund', 'Online/ Ground'), ('Product', 'Product'), ('Status', 'Task Status'),
    ('SLA', 'ETA'), ('Comments', 'Comment'), ('Assignee', 'Last User'), ('Searcher', None),
    ('Clarification Requested', None), ('Shift', None), ('Processed Date', 'Completed Time'),
    ('Typer', None), ('Review/QC', None), ('Expense', None), ('In-Time', 'Arrival Time'),
    ('Out Time', 'Out Time'), ('SLA Expiration', 'SLA Expiration*'), ('SLA', 'SLA Status'),
    ('Free Site', None),
]
REMAINING_PRODUCT_FIELDS = [
    ('No', '__number__'), ('Date', 'Arrival Date'), ('Order Number', 'Order Number'),
    ('TraceQ Id', None), ('State', 'St'), ('County', 'County'), ('Client', 'Client'),
    ('Online/Ground', 'Online/ Ground'), ('Product', 'Product'), ('Status', 'Task Status'),
    ('ETA', 'ETA'), ('Comments', 'Comment'), ('Assignee', 'Last User'), ('Searcher', None),
    ('Clarification Requested', None), ('Shift', None), ('Process date', 'Completed Time'),
    ('Review/QC', None), ('Expense', None), ('In-Time', 'Arrival Time'), ('Out Time', 'Out Time'),
    ('SLA Expiration', 'SLA Expiration*'), ('Free Site', None), ('review', None),
]
REPORT_SHEETS = [('All Products', ALL_PRODUCT_FIELDS), ('Full Title', FULL_TITLE_FIELDS),
                 ('Remaining Products', REMAINING_PRODUCT_FIELDS)]
STATUS_COLORS = {
    'available': '#d9ead3',
    'in progress': '#00b050',
    'qc in progress': '#f4b183',
    'ready to send': '#ffff00',
    'search in progress': '#ffffff',
    'typing in progress': '#00b050',
    'typing is progress': '#00b050',
    'waiting for effective date': '#ffffff',
    'assign to abs': '#a6a6a6',
    'need to assign abs': '#a6a6a6',
    'awaiting for clarification': '#a66ad3',
    'cancelled': '#f4cccc',
    'completed and delivered': '#fff2cc',
    'task suspended': '#c9daf8',
    'workflow suspended': '#c9daf8',
}


def target_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials
    value = os.getenv('GOOGLE_SERVICE_ACCOUNT_JSON', 'service_account.json').strip()
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
        client.set_timeout(30)
        book = client.open_by_key(SPREADSHEET_ID)
        return book, book.get_worksheet_by_id(WORKSHEET_GID)
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
    result['Is Suspended'] = status.str.contains('suspended', na=False)
    sla = result.get('SLA Expiration*', result.get('SLA Expiration', pd.Series('', index=df.index)))
    result['SLA Status'] = sla.map(lambda v: 'Overdue' if str(v).startswith('-') else 'Unknown')
    result['Sync Timestamp'] = timestamp
    return result


def report_frame(df, fields, product=None):
    source = df if product is None else df[df['Product'].fillna('').astype(str).str.strip().str.casefold().eq(product)]
    if product == '__remaining__':
        products = df['Product'].fillna('').astype(str).str.split().str.join(' ').str.casefold()
        source = df[products.isin({value.casefold() for value in REMAINING_PRODUCTS})]
    matrix = []
    for number, (_, row) in enumerate(source.iterrows(), start=1):
        values = []
        for _, source_column in fields:
            if source_column == '__number__':
                value = number
            elif source_column == '__workflow_suspended__':
                value = str(row.get('Task Status', '')).strip().casefold() == 'workflow suspended'
            elif source_column == '__task_suspended__':
                value = str(row.get('Task Status', '')).strip().casefold() == 'task suspended'
            else:
                value = row.get(source_column, '') if source_column else ''
            values.append(value)
        matrix.append(values)
    return pd.DataFrame(matrix, columns=[target for target, _ in fields])


def report_frames(df):
    return [report_frame(df, ALL_PRODUCT_FIELDS),
            report_frame(df, FULL_TITLE_FIELDS, 'full title'),
            report_frame(df, REMAINING_PRODUCT_FIELDS, '__remaining__')]


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
        if 'Task Name' in result.columns:
            tasks = result['Task Name'].astype(str).str.strip().str.casefold().str.replace(' ', '', regex=False)
            available = result[column].astype(str).str.strip().str.casefold().eq('available')
            result.loc[available & tasks.eq('search'), column] = 'Search In Progress'
            result.loc[available & tasks.eq('typingmodule'), column] = 'Typing is Progress'
            result.loc[tasks.isin(['crsp2', 'searchfix', 'n/a']), column] = 'Completed and Delivered'
    if columns:
        if 'Out Time' not in result.columns:
            result['Out Time'] = ''
        completed = result[columns[0]].astype(str).str.strip().str.casefold().eq('completed and delivered')
        today = reporting_date or df.attrs.get('reporting_date') or dt.date.today().isoformat()
        # A missing-order date assigned by the comparison survives the sync pass.
        keep_today = result['Out Time'].astype(str).eq(today)
        result.loc[completed & ~keep_today, 'Out Time'] = 'Completed'
    if 'Is Available' in result.columns and columns:
        result['Is Available'] = result[columns[0]].astype(str).str.strip().str.casefold().eq('available')
    return result


def status_report_frame(df):
    column = 'Task Status' if 'Task Status' in df.columns else 'Status' if 'Status' in df.columns else None
    if not column:
        return pd.DataFrame(columns=['Status', 'Orders', 'Share'])
    counts = df[column].fillna('').astype(str).map(lambda value: value.strip() or '(Blank)').value_counts()
    total = len(df) or 1
    rows = [{'Status': status, 'Orders': int(count), 'Share': f'{(count / total) * 100:.1f}%'}
            for status, count in counts.items()]
    return pd.DataFrame(rows, columns=['Status', 'Orders', 'Share'])


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
    column = next((name for name in ('Task Status', 'Status') if name in df.columns), None)
    if column is None:
        return None
    return {'updateCells': {
        'range': {'sheetId': sheet_id, 'startRowIndex': 1,
                  'startColumnIndex': 0, 'endColumnIndex': len(df.columns)},
        'rows': [{'values': [{'userEnteredFormat': {'backgroundColor': sheet_color(status_color(value))}}
                            for _ in df.columns]} for value in df[column].fillna('')],
        'fields': 'userEnteredFormat.backgroundColor'}}


def sync_dataframe(df, target=None, validate=True, row_backgrounds=None, color_status=False):
    if validate:
        validate_queue(df)
    book, sheet = target or target_worksheet()
    values = [list(df.columns)] + df.astype(object).values.tolist()
    include_format = row_backgrounds is not None
    row_backgrounds = row_backgrounds or [None] * len(values)
    requests = []
    for dimension, required, existing in [('ROWS', len(values), sheet.row_count),
                                           ('COLUMNS', len(df.columns), sheet.col_count)]:
        if required > existing:
            requests.append({'appendDimension': {'sheetId': sheet.id, 'dimension': dimension,
                                                 'length': required - existing}})
    # Full-sheet range clears trailing values in the same atomic request.
    requests.append({'updateCells': {'range': {'sheetId': sheet.id},
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
    try:
        book.batch_update({'requests': requests})
    except Exception as exc:
        email = getattr(book.client.auth, 'service_account_email', 'the service account client_email')
        raise RuntimeError(f'Google Sheets write failed. Share the target with {email} as Editor. Check '
                           'worksheet protection, API quota and connectivity. Local exports are retained.') from exc
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


def retain_completed_orders(df, existing_values):
    if not existing_values or 'Order Number' not in df.columns:
        return df
    headers = existing_values[0]
    status_column = next((name for name in ('Task Status', 'Status') if name in headers), None)
    if 'Order Number' not in headers or not status_column:
        return df
    records = [dict(zip(headers, row)) for row in existing_values[1:]]
    completed = [row for row in records
                 if str(row.get(status_column, '')).strip().casefold() == 'completed and delivered'
                 and str(row.get('Order Number', '')).strip()]
    result = df.copy()
    incoming = result['Order Number'].astype(str).str.strip()
    # Current queue statuses take precedence over historical sheet completion.
    missing = [row for row in completed if str(row['Order Number']).strip() not in set(incoming)]
    if missing:
        result = pd.concat([result, pd.DataFrame(missing).reindex(columns=df.columns).fillna('')], ignore_index=True)
    return result


def sync_workbook(df):
    book, primary = target_worksheet()
    original = df.attrs.get('original_capture')
    raw = pd.DataFrame(original['rows'], columns=original['columns']).fillna('') if original else df.copy()
    report_date = df.attrs.get('reporting_date')
    capture_date = df.attrs.get('capture_date')
    worksheets = book.worksheets()
    df = retain_completed_orders(df, primary.get_all_values())
    if original:
        # Raw tabs no longer store automated completion history. Keep it in the reports.
        for title, fields in REPORT_SHEETS[1:]:
            sheet = next((sheet for sheet in worksheets if sheet.title == title), None)
            values = sheet.get_all_values() if sheet else []
            if not values:
                continue
            mapping = [(index, source) for index, name in enumerate(values[0])
                       for target, source in fields if name == target and source and not source.startswith('__')]
            records = [{source: row[index] if index < len(row) else '' for index, source in mapping}
                       for row in values[1:]]
            if records:
                history = pd.DataFrame(records).fillna('')
                df = retain_completed_orders(df, [list(history.columns)] + history.values.tolist())
    if report_date and capture_date and 'Out Time' in df.columns:
        df.loc[df['Out Time'].astype(str).eq(capture_date), 'Out Time'] = report_date
    df = apply_status_rules(df, [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}], reporting_date=report_date)
    synced = [sync_dataframe(raw, (book, primary), color_status=True)]
    frames = report_frames(df)
    frames[0] = report_frame(raw, ALL_PRODUCT_FIELDS)
    for index, ((title, _), frame) in enumerate(zip(REPORT_SHEETS, frames), start=1):
        if len(worksheets) <= index:
            worksheets.append(book.add_worksheet(title=title, rows=1, cols=1))
        sheet = worksheets[index]
        if sheet.title != title:
            sheet.update_title(title)
        synced.append(sync_dataframe(frame, (book, sheet), validate=False, color_status=True))
    status_frame = status_report_frame(df)
    index = len(REPORT_SHEETS) + 1
    if len(worksheets) <= index:
        worksheets.append(book.add_worksheet(title='Status Report', rows=1, cols=1))
    sheet = worksheets[index]
    if sheet.title != 'Status Report':
        sheet.update_title('Status Report')
    backgrounds = [None] + [status_color(value) for value in status_frame['Status'].tolist()]
    synced.append(sync_dataframe(status_frame, (book, sheet), validate=False, row_backgrounds=backgrounds))
    return synced


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


def run_sync(on_progress=None):
    from dotenv import load_dotenv
    from preview_store import PreviewStore
    load_dotenv(BASE_DIR / '.env', override=True)
    status = {'action': 'extract', 'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scrape': 'pending', 'google_sheet': 'not_synced', 'rows': 0, 'error': None}
    def progress(stage):
        status['stage'] = stage
        if on_progress:
            on_progress(dict(status))
    try:
        progress('Connecting to DataTrace')
        if not os.getenv('DATATRACE_USERNAME') or not os.getenv('DATATRACE_PASSWORD'):
            raise RuntimeError('Set DATATRACE_USERNAME and DATATRACE_PASSWORD in gsheet_dashboard/.env or the environment.')
        # Per-run output prevents old exports from being uploaded after a failed scrape.
        with tempfile.TemporaryDirectory(prefix='datatrace-') as folder:
            output = Path(folder) / 'queue.json'
            env = dict(os.environ, DATATRACE_OUTPUT_JSON=str(output))
            process = subprocess.run(['node', str(BASE_DIR / 'scrape_datatrace.js')],
                                     cwd=BASE_DIR, env=env, capture_output=True, text=True, timeout=300)
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
        validate_queue(df)
        status.update(scrape='success', rows=len(df))
        df = powerbi_table(df, status['started_at'])
        progress('Saving preview')
        preview = PreviewStore(BASE_DIR / 'previews').save(df)
        status['preview_id'] = preview['id']
        status['preview_name'] = preview['name']
        export_to_excel_and_csv(df)
        status['local_export'] = 'success'
        status['last_success_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
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
