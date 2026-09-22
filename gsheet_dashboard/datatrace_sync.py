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


def sheet_cell(value):
    if pd.isna(value):
        return {}
    if isinstance(value, bool):
        key = 'boolValue'
    elif isinstance(value, (int, float)):
        key = 'numberValue'
    else:
        key, value = 'stringValue', str(value)
    return {'userEnteredValue': {key: value}}


def sync_dataframe(df, target=None):
    validate_queue(df)
    book, sheet = target or target_worksheet()
    values = [list(df.columns)] + df.astype(object).values.tolist()
    requests = []
    for dimension, required, existing in [('ROWS', len(values), sheet.row_count),
                                           ('COLUMNS', len(df.columns), sheet.col_count)]:
        if required > existing:
            requests.append({'appendDimension': {'sheetId': sheet.id, 'dimension': dimension,
                                                 'length': required - existing}})
    # Full-sheet range clears trailing values in the same atomic request.
    requests.append({'updateCells': {'range': {'sheetId': sheet.id},
                     'rows': [{'values': [sheet_cell(v) for v in row]} for row in values],
                     'fields': 'userEnteredValue'}})
    try:
        book.batch_update({'requests': requests})
    except Exception as exc:
        email = getattr(book.client.auth, 'service_account_email', 'the service account client_email')
        raise RuntimeError(f'Google Sheets write failed. Share the target with {email} as Editor. Check '
                           'worksheet protection, API quota and connectivity. Local exports are retained.') from exc
    received = sheet.get_all_values()
    if (len(received) != len(values) or not received or received[0] != list(df.columns)
            or any(len(row) != len(df.columns) for row in received)):
        raise RuntimeError('Google Sheets write returned, but row/column verification failed. Check the worksheet before retrying.')
    return sheet.title


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
    status = {'started_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'scrape': 'pending',
              'google_sheet': 'pending', 'rows': 0, 'error': None}
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
        progress('Syncing Google Sheets')
        status['worksheet'] = sync_dataframe(df)
        status.update(google_sheet='success', last_success_at=dt.datetime.now(dt.timezone.utc).isoformat())
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
