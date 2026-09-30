"""DataTrace extraction, local exports and authenticated Google Sheets sync."""
import datetime as dt
import json
import os
import re
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
    text = str(value if pd.notna(value) else '').strip()
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        pass
    for pattern in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
                    '%m/%d/%Y %H:%M:%S', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return dt.datetime.strptime(text, pattern)
        except ValueError:
            pass
    return None


def sla_result(row):
    out_text = str(row.get('Out Time', '') or '').strip()
    if not out_text:
        return ''
    out = parse_report_datetime(out_text)
    if out is None:
        return 'Missed'
    sla = str(row.get('SLA Expiration*', row.get('SLA Expiration', '')) or '').strip()
    if re.fullmatch(r'-?(?:(?:\d+)d\s*)?(?:(?:\d+)h\s*)?(?:(?:\d+)m\s*)?', sla) and sla:
        return 'Missed' if sla.startswith('-') else 'On Time'
    if re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?', sla, re.I):
        return 'On Time'
    expiration = sla_expiration(row)
    if expiration is None:
        return 'Missed'
    return 'On Time' if out < expiration else 'Missed'


def sla_expiration(row):
    sla = str(row.get('SLA Expiration*', row.get('SLA Expiration', '')) or '').strip()
    expiration = parse_report_datetime(sla)
    if expiration is None:
        arrival = parse_report_datetime(row.get('Arrival Time', row.get('In-Time', '')))
        anchor = arrival or parse_report_datetime(row.get('Out Time', ''))
        if anchor is None:
            return None
        for pattern in ('%Y/%m/%d %I:%M %p', '%Y/%m/%d'):
            try:
                expiration = dt.datetime.strptime(f'{anchor.year}/{sla}', pattern)
                if arrival and expiration.date() < arrival.date():
                    expiration = expiration.replace(year=expiration.year + 1)
                break
            except ValueError:
                pass
    return expiration


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
                value = str(row.get('Task Status', '')).strip().casefold() == 'workflow suspended'
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
                        value = parsed.strftime('%m/%d/%Y')
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
        dated = result['Out Time'].map(completion_date).notna()
        result.loc[completed & ~dated, 'Out Time'] = today
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


def build_synced_workbook_stream(df, preview_name='Preview', selected_products=None, sync_time=None):
    from io import BytesIO
    if selected_products is None:
        selected_products = df.attrs.get('selected_products')
    if selected_products is None:
        try:
            stored = json.loads(Path(__file__).with_name('remaining_products.json').read_text(encoding='utf-8'))
            if isinstance(stored, list) and stored:
                selected_products = stored
        except Exception:
            pass

    original = df.attrs.get('original_capture')
    raw = pd.DataFrame(original['rows'], columns=original['columns']).fillna('') if original else df.copy()
    raw_status = apply_status_rules(raw, [])
    sync_time_str = sync_time or df.attrs.get('sync_time') or dt.datetime.now().astimezone().strftime('%Y-%m-%d %I:%M:%S %p')
    preview_name_str = preview_name or df.attrs.get('preview_name') or 'Preview'

    frames = report_frames(df, selected_products=selected_products)
    all_products_frame = report_frame(raw, ALL_PRODUCT_FIELDS)
    full_title_frame = frames[1]
    remaining_frame = frames[2]
    status_frame = status_report_frame(df, preview_name=preview_name_str, sync_time=sync_time_str)

    sheets_data = [
        ('Sheet1', raw_status, 'Sheet1_Data'),
        ('All Products', all_products_frame, 'All_Products_Data'),
        ('Full Title', full_title_frame, 'Full_Title_Data'),
        ('Remaining Products', remaining_frame, 'Remaining_Products_Data'),
        ('Status Report', status_frame, 'Status_Report_Data'),
    ]

    stream = BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        for sheet_title, sheet_df, table_name in sheets_data:
            sheet_df.to_excel(writer, sheet_name=sheet_title, index=False)
            ws = writer.sheets[sheet_title]
            for row in ws:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = 's'
            if not sheet_df.empty:
                table = Table(displayName=table_name, ref=ws.dimensions)
                table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
                ws.add_table(table)
            ws.freeze_panes = 'A2'
    stream.seek(0)
    return stream


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
    if sheet.col_count > len(df.columns):
        requests.append({'deleteDimension': {
            'range': {
                'sheetId': sheet.id,
                'dimension': 'COLUMNS',
                'startIndex': len(df.columns),
                'endIndex': sheet.col_count
            }
        }})
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


def retain_completed_orders(df, existing_values, valid_completed_ids=None):
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
    if valid_completed_ids is not None:
        completed = [row for row in completed if str(row.get('Order Number', '')).strip() in valid_completed_ids]
    result = df.copy()
    incoming = result['Order Number'].astype(str).str.strip()
    dates = {str(row['Order Number']).strip(): completion_date(row.get('Out Time')) for row in completed}
    status = next((column for column in ('Task Status','Status') if column in result.columns), None)
    if status:
        prior_dates = incoming.map(dates)
        mask = result[status].astype(str).str.strip().str.casefold().eq('completed and delivered') & prior_dates.notna()
        if mask.any():
            result.loc[mask, 'Out Time'] = prior_dates[mask]
    # Current queue statuses take precedence over historical sheet completion.
    missing = [row for row in completed if str(row['Order Number']).strip() not in set(incoming)]
    if missing:
        result = pd.concat([result, pd.DataFrame(missing).reindex(columns=df.columns).fillna('')], ignore_index=True)
    return result


def sync_workbook(df, selected_products=None):
    preview_name = df.attrs.get('preview_name') or (f"preview{df.attrs['preview_id']}" if df.attrs.get('preview_id') else 'Preview')
    book, primary = target_worksheet()
    if selected_products is None:
        selected_products = df.attrs.get('selected_products')
    if selected_products is None:
        try:
            stored = json.loads(Path(__file__).with_name('remaining_products.json').read_text(encoding='utf-8'))
            if isinstance(stored, list) and stored:
                selected_products = stored
        except Exception:
            pass
    original = df.attrs.get('original_capture')
    raw = pd.DataFrame(original['rows'], columns=original['columns']).fillna('') if original else df.copy()
    report_date = df.attrs.get('reporting_date')
    valid_ids = df.attrs.get('valid_completed_ids')
    recovered_dates = df.attrs.get('completion_dates', {})
    existing_dates = {}
    undated_history = set()
    worksheets = book.worksheets()
    primary_values = primary.get_all_values()
    def remember_dates(values):
        if not values:
            return
        for values_row in values[1:]:
            row = dict(zip(values[0], values_row))
            identity = str(row.get('Order Number', '')).strip()
            if valid_ids is not None and identity not in valid_ids:
                continue
            date = completion_date(row.get('Out Time'))
            completed = str(row.get('Task Status', row.get('Status', ''))).strip().casefold() == 'completed and delivered'
            if identity and date and completed:
                existing_dates.setdefault(identity, date)
            elif identity and completed:
                undated_history.add(identity)
    remember_dates(primary_values)
    df = retain_completed_orders(df, primary_values, valid_completed_ids=valid_ids)
    if original:
        # Raw tabs no longer store automated completion history. Keep it in the reports.
        for title, fields in REPORT_SHEETS[1:]:
            sheet = next((sheet for sheet in worksheets if sheet.title == title), None)
            values = sheet.get_all_values() if sheet else []
            if not values:
                continue
            field_map = {target.strip().casefold(): source for target, source in fields if source and not source.startswith('__')}
            field_map['order number'] = 'Order Number'
            field_map['status'] = 'Task Status'
            mapping = [(index, field_map[str(name).strip().casefold()]) for index, name in enumerate(values[0])
                       if str(name).strip().casefold() in field_map]
            records = [{source: row[index] if index < len(row) else '' for index, source in mapping}
                       for row in values[1:]]
            if records:
                history = pd.DataFrame(records).fillna('')
                history_values = [list(history.columns)] + history.values.tolist()
                remember_dates(history_values)
                df = retain_completed_orders(df, history_values, valid_completed_ids=valid_ids)
    df = apply_status_rules(df, [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}], reporting_date=report_date)
    status = next((column for column in ('Task Status','Status') if column in df.columns), None)
    if status and 'Order Number' in df.columns:
        dates = df['Order Number'].astype(str).str.strip().map({**recovered_dates, **existing_dates})
        mask = df[status].astype(str).str.strip().str.casefold().eq('completed and delivered') & dates.notna()
        df.loc[mask, 'Out Time'] = dates[mask]
        unknown = undated_history - set(existing_dates) - set(recovered_dates)
        unknown_mask = df['Order Number'].astype(str).str.strip().isin(unknown) & df[status].astype(str).str.strip().str.casefold().eq('completed and delivered')
        df.loc[unknown_mask, 'Out Time'] = 'Completed'
    synced = [sync_dataframe(raw, (book, primary), color_status=True)]
    frames = report_frames(df, selected_products=selected_products)
    frames[0] = report_frame(raw, ALL_PRODUCT_FIELDS)
    for index, ((title, _), frame) in enumerate(zip(REPORT_SHEETS, frames), start=1):
        if len(worksheets) <= index:
            worksheets.append(book.add_worksheet(title=title, rows=1, cols=1))
        sheet = worksheets[index]
        if sheet.title != title:
            sheet.update_title(title)
        if title in ('Full Title', 'Remaining Products'):
            prior_values = sheet.get_all_values()
            if isinstance(prior_values, list) and prior_values and {'Order Number', 'Out Time', 'Free Site'}.issubset(prior_values[0]):
                prior_rows = {str(row.get('Order Number', '')).strip(): row
                              for row in (dict(zip(prior_values[0], cells)) for cells in prior_values[1:])
                              if str(row.get('Order Number', '')).strip()}
                for row_index, row in frame.iterrows():
                    old = prior_rows.get(str(row['Order Number']).strip())
                    if old and parse_report_datetime(old.get('Out Time')) == parse_report_datetime(row['Out Time']):
                        frame.at[row_index, 'Free Site'] = old.get('Free Site', '')
        sheet.clear()
        synced.append(sync_dataframe(frame, (book, sheet), validate=False, color_status=True))
    now_sync_time = dt.datetime.now().astimezone().strftime('%Y-%m-%d %I:%M:%S %p')
    if not df.attrs.get('sync_time'):
        df.attrs['sync_time'] = now_sync_time
    status_frame = status_report_frame(df, preview_name=preview_name, sync_time=now_sync_time)
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
