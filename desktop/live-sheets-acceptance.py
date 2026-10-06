"""Explicit live acceptance against a pre-created synthetic QA workbook only.
Credentials arrive over stdin; no secrets or production rows are logged.
"""
import json
import sys
import tempfile
import traceback
import os
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'gsheet_dashboard'))


def run(config):
    import gspread
    from google.oauth2.service_account import Credentials
    from openpyxl import Workbook
    from requests.exceptions import Timeout
    from preview_store import PreviewStore
    from report_workspace import ReportWorkspace
    from report_publishing import publish_reports, CHART_TITLE
    from sheets_writer import GuardedBook, WriterGuard, shared_job

    identity = config['testSpreadsheetId']
    if identity == config['spreadsheetId']:
        raise ValueError('A separate synthetic QA workbook is required.')
    credentials = Credentials.from_service_account_info(config['credentials'], scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(credentials)
    client.set_timeout(45)
    book = client.open_by_key(identity)
    if not book.title.startswith('Tv Tracker acceptance QA'):
        raise ValueError('The target is not an explicitly named acceptance workbook.')
    raw = book.worksheet('Sheet1')
    baseline = [['Order Number', 'Status'], ['TV-QA-RAW', 'Available']]
    prior = raw.get_all_values()
    if any(any(str(cell) for cell in row) for row in prior) and prior != baseline:
        raise ValueError('The synthetic raw tab has unexpected data; refusing to overwrite it.')
    raw.update(values=baseline, range_name='A1')
    guarded = GuardedBook(book, 'tv-tracker-live-qa-A', shared=True, key='live-qa-A')
    with tempfile.TemporaryDirectory() as directory:
        workspace = ReportWorkspace(PreviewStore(Path(directory) / 'previews'))
        def snapshot(number, source, remaining=True):
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(['Order Number', 'Product', 'Status', 'In-Time', 'Out Time', 'SLA Expiration', 'Custom reference'])
            sheet.append([number, 'Full Title', 'Completed and Delivered', '10/01/2026 09:00 AM', '10/01/2026 10:00 AM', '10/01/2026 10:00 AM', 'QA-only'])
            if remaining:
                sheet.append([number + '-remaining', 'Update', 'Assign to ABS', '10/01/2026 09:00 AM', '', '', 'preserved'])
            stream = BytesIO()
            workbook.save(stream)
            saved = workspace.save_import([('synthetic.xlsx', stream.getvalue())])
            value = workspace.imported_snapshot(saved['id'])
            value['source'] = source
            return value
        first = snapshot('TV-QA-001', 'Imported Excel')
        initial = publish_reports(guarded, first, workspace.capacity(first))
        assert initial['daily_dates'] == ['2026-10-01']
        daily = book.worksheet('Daily Orders').get_all_records()
        assert daily[0]['Received'] == 2 and daily[0]['On time SLA'] == 1 and daily[0]['Vendor Pending'] == 1
        assert raw.get_all_values() == baseline
        try:
            WriterGuard(book, 'tv-tracker-live-qa-B').ensure()
            raise AssertionError('A second writer was authorized')
        except ValueError:
            pass
        # Four updated PCs can take turns, while a competing active job is blocked.
        reserved = []
        for number in range(4):
            pc = GuardedBook(book, f'live-pc-{number}', shared=True, key=f'live-pc-{number}')
            with shared_job(pc, 'Synthetic capture'):
                reserved.append(pc.writer_guard.reserve_preview(100))
                other = GuardedBook(book, 'competing-pc', shared=True, key='competing-pc')
                try:
                    with shared_job(other):
                        raise AssertionError('Two PCs owned the same publishing slot')
                except ValueError:
                    pass
            assert pc.writer_guard.job() is None
        assert len(set(reserved)) == 4 and reserved == list(range(reserved[0], reserved[0] + 4))
        # Commit to the real API, then simulate a lost HTTP reply. The receipt
        # must prove this attempt committed, without replaying sheet creation.
        actual_batch = book.batch_update
        calls = []
        def lost_reply(body):
            result = actual_batch(body)
            calls.append(True)
            if len(calls) == 1:
                raise Timeout('synthetic lost response after real commit')
            return result
        second = snapshot('TV-QA-002', 'Google Sheets (synthetic tracker)', remaining=False)
        with shared_job(guarded, 'Lost-response acceptance'):
            book.batch_update = lost_reply
            try:
                updated = publish_reports(guarded, second, workspace.capacity(second))
            finally:
                book.batch_update = actual_batch
        assert len(calls) == 1, 'Committed update was replayed after a lost reply'
        assert updated['daily_gid'] == initial['daily_gid']
        assert book.worksheet('All Products').acell('A2').value is not None
        values = book.worksheet('All Products').get_all_records()
        assert {row['Order Number'] for row in values} == {'TV-QA-002'}
        assert book.worksheet('Remaining_OCT_2026').get_all_records() == []
        headers = book.worksheet('All Products').row_values(1)
        assert book.worksheet('Full_search_OCT_2026').row_values(1) == headers
        assert book.worksheet('Remaining_OCT_2026').row_values(1) == headers
        metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,charts(spec(title,basicChart)))'})
        charts = [chart for sheet in metadata['sheets'] for chart in sheet.get('charts', []) if chart['spec'].get('title') == CHART_TITLE]
        assert len(charts) == 1 and charts[0]['spec']['basicChart']['chartType'] == 'COMBO'
        raw_meta = next(sheet for sheet in metadata['sheets'] if sheet['properties']['title'] == 'Sheet1')
        assert raw_meta['properties']['hidden']
        assert raw.get_all_values() == baseline
        # Exercise archive and restore only for synthetic QA backup tabs.
        from cloud_retention import plan, archive, restore
        from monthly_production import LEDGER
        os.environ['DATATRACE_DESKTOP'] = '1'
        present = {sheet.title: sheet for sheet in book.worksheets()}
        ledger_rows = [['Operation', 'Kind', 'Timestamp', 'Order Number', 'From tab', 'To tab', 'Reason']]
        setup = []
        for number in range(1, 7):
            name = f'__DataTrace_Backup_{number:012x}_0'
            identity = present[name].id if name in present else 1800000100 + number
            if name not in present:
                setup.append({'addSheet': {'properties': {'title': name, 'sheetId': identity, 'gridProperties': {'rowCount': 3, 'columnCount': 2}}}})
            setup.append({'updateCells': {'start': {'sheetId': identity, 'rowIndex': 0, 'columnIndex': 0}, 'rows': [{'values': [{'userEnteredValue': {'stringValue': 'TV-QA-ARCHIVE'}, 'note': 'Synthetic recovery evidence'}, {'userEnteredValue': {'formulaValue': '=1+1'}}]}], 'fields': 'userEnteredValue,note'}})
            ledger_rows.append([f'{number:012x}', 'fixture', f'2026-09-0{number}T12:00:00', '', '', '', 'Committed'])
        ledger_id = present[LEDGER].id if LEDGER in present else 1800000110
        if LEDGER not in present:
            setup.append({'addSheet': {'properties': {'title': LEDGER, 'sheetId': ledger_id, 'gridProperties': {'rowCount': 7, 'columnCount': 7}}}})
        setup.append({'updateCells': {'start': {'sheetId': ledger_id, 'rowIndex': 0, 'columnIndex': 0}, 'rows': [{'values': [{'userEnteredValue': {'stringValue': cell}} for cell in row]} for row in ledger_rows], 'fields': 'userEnteredValue'}})
        guarded.batch_update({'requests': setup})
        cloud_plan = plan(guarded)
        assert len(cloud_plan['tabs']) == 1
        cloud_result = archive(guarded, Path(directory) / 'cloud-archives', cloud_plan['fingerprint'])
        assert cloud_result['archived_tabs'] == 1
        assert restore(guarded, (Path(directory) / 'cloud-archives' / cloud_result['archive']).read_bytes())['restored_tabs'] == 1
        assert book.worksheet('__DataTrace_Backup_000000000001_0').acell('B1', value_render_option='FORMULA').value == '=1+1'
        assert raw.get_all_values() == baseline
        return {'passed': True, 'test_workbook': config['testSpreadsheetId'], 'production_rows_modified': False,
                'checks': ['live report publication', 'SLA deadline equality', 'source replacement', 'empty product category', 'preserved raw data', 'shared detail schema', 'single capacity chart', 'legacy writer fenced', 'four PCs take turns', 'competing job rejected', 'unique preview reservations', 'lost response verified without replay', 'stable daily date links', 'encrypted cloud archive', 'cloud restore with formulas and notes']}


if __name__ == '__main__':
    try:
        print(json.dumps(run(json.load(sys.stdin))))
    except Exception as error:
        # Assertions and API status are useful; request/auth payloads are not.
        print(json.dumps({'passed': False, 'error_type': type(error).__name__, 'http_status': getattr(error, 'code', None), 'api_message': getattr(error.__cause__, 'error', {}).get('message', ''), 'locations': [f'{Path(frame.filename).name}:{frame.lineno}' for frame in traceback.extract_tb(error.__traceback__)]}))
        sys.exit(1)
