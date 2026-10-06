"""Live central-publisher rehearsal restricted to the approved synthetic workbook."""
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'gsheet_dashboard'))


def run():
    import gspread
    from google.oauth2.service_account import Credentials
    from cloud_backend.publication import SheetsPublisher, PROTOCOL, RECEIPT, projection, digest
    from sheets_writer import SHARED_TITLE, SharedWriterGuard
    from sheet_reads import read_values
    identity = '1H9V7xogbxzPqzsMecuMa1qGIIwLKkRetkZ2EUBdKKwI'
    account = json.loads((ROOT / 'gsheet_dashboard/service_account.json').read_text())
    client = gspread.authorize(Credentials.from_service_account_info(account,
        scopes=['https://www.googleapis.com/auth/spreadsheets']))
    client.set_timeout(45)
    book = client.open_by_key(identity)
    if not book.title.startswith('Tv Tracker acceptance QA'):
        raise ValueError('Expected the explicitly approved synthetic workbook.')
    existing = {sheet.title: sheet for sheet in book.worksheets()}
    workspace = str(uuid.uuid4())
    if RECEIPT in existing:
        saved = json.loads(existing[RECEIPT].get_all_values()[1][0])
        workspace = saved['workspace']
    publisher = SheetsPublisher(book, workspace, identity)
    row = {'Order Number':'TV-QA-CLOUD-001','Product':'Full Title','Status':'Completed and Delivered',
        'In-Time':'10/01/2026 09:00 AM','Out Time':'10/01/2026 10:00 AM','SLA Expiration':'10/01/2026 10:00 AM'}
    tables, _ = projection([{'order_key':'tv-qa-cloud-001','data':row}], '2026-10-06T12:00:00Z')
    titles = sorted(set(tables) & set(existing))
    baseline = dict(zip(titles, read_values(book, [existing[t] for t in titles], render='UNFORMATTED_VALUE')))
    # Refuse to use this rehearsal if any recognized order table has real orders.
    for matrix in baseline.values():
        if matrix and 'Order Number' in matrix[0]:
            index = matrix[0].index('Order Number')
            if any(len(r)>index and r[index] and not str(r[index]).startswith('TV-QA-') for r in matrix[1:]):
                raise ValueError('Non-synthetic order encountered; no publication attempted.')
    publisher.bind(titles, digest(baseline))
    receipt = publisher._receipt()
    published = publisher.publish(receipt['revision']+1, tables)
    assert publisher.publish(published['revision'], tables) == published
    # Older 2.7.x writers must fail before reserving a slot or changing data.
    try:
        SharedWriterGuard(book, 'legacy-rehearsal').enable()
    except ValueError:
        fenced = True
    else:
        raise AssertionError('Legacy writer was not fenced')
    controls = book.worksheet(SHARED_TITLE).get_all_values()
    assert controls[1][0] == PROTOCOL
    result = {'workbook':identity,'workspace':workspace,'revision':published['revision'],
        'verified_publication':True,'repeat_idempotent':True,'legacy_writers_blocked':fenced,'production_modified':False}
    (ROOT / '.desktop-build/cloud-publisher-acceptance.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print('Publisher rehearsal failed: '+type(error).__name__, file=sys.stderr)
        sys.exit(1)
