"""Authenticated migration/publication, restricted to the approved QA workbook.

The old synthetic fixture is backed up with Windows encryption before reset.
Stable identities allow an interrupted rehearsal to resume without re-seeding.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

from cloud_backend.migration import Migration
from cloud_backend.transport import OfficeWorkerRpc
from cloud_backend.worker import OfficeWorker
from shared_backend import SupabaseRpc

QA_BOOK = '1H9V7xogbxzPqzsMecuMa1qGIIwLKkRetkZ2EUBdKKwI'


def save_json(path, value):
    from workspace_backup import write_verified_backup
    write_verified_backup(path, json.dumps(value, sort_keys=True).encode())


def run(settings):
    import gspread
    from google.oauth2.service_account import Credentials
    from sheets_transport import QuotaHTTPClient
    from sheets_repository import Batch
    from tracker_sync import FULL, REMAINING
    from backup_protection import MAGIC, protect, unprotect
    from cloud_backend.publication import SheetsPublisher, RECEIPT, digest
    from sheet_reads import read_values
    from workspace_backup import write_verified_backup
    root = Path(__file__).resolve().parents[1]
    account = json.loads((root / 'gsheet_dashboard/service_account.json').read_text())
    client = gspread.authorize(Credentials.from_service_account_info(account,
        scopes=['https://www.googleapis.com/auth/spreadsheets']), http_client=QuotaHTTPClient)
    client.set_timeout((10,90))
    book = client.open_by_key(QA_BOOK)
    if not book.title.startswith('Tv Tracker acceptance QA'):
        raise ValueError('Expected the explicitly approved synthetic workbook.')
    config, token = settings['config'], settings['accessToken']
    rpc = SupabaseRpc(config['url'], config['publishableKey'], lambda: token)
    os.environ['DATATRACE_DESKTOP'] = '1'
    target = root / '.desktop-build/shared-publication-target.json'
    if target.exists():
        saved = json.loads(target.read_text())
        if saved['workbook'] != QA_BOOK:
            raise ValueError('The saved rehearsal destination differs from the approved workbook.')
    else:
        sheets = book.worksheets()
        matrices = dict(zip([s.title for s in sheets], read_values(book, sheets)))
        # All order-bearing tabs, including retained history, must be synthetic.
        for values in matrices.values():
            if values and 'Order Number' in values[0]:
                column = values[0].index('Order Number')
                if any(len(row)>column and row[column] and not str(row[column]).startswith('TV-QA-') for row in values[1:]):
                    raise ValueError('Non-synthetic data encountered; no test reset attempted.')
        old_receipt = json.loads(matrices[RECEIPT][1][0])
        workspace = old_receipt['workspace']
        uuid.UUID(workspace)
        existing = rpc.call('tv_list_workspaces', {})
        if any(row['id'] == workspace for row in existing):
            raise ValueError('This QA identity already exists; use its saved rehearsal state.')
        backup = protect(json.dumps(matrices, sort_keys=True).encode())
        if not backup.startswith(MAGIC) or json.loads(unprotect(backup)) != matrices:
            raise ValueError('The QA fixture backup could not be protected and verified.')
        backup_path = root / '.desktop-build/shared-publication-qa' / workspace / 'original-workbook.tvbackup'
        write_verified_backup(backup_path, backup)
        saved = {'workspace':workspace,'workbook':QA_BOOK,'worker':str(uuid.uuid4()),
            'scope':'synthetic-publication-'+workspace,'base':(datetime.now(timezone.utc)-timedelta(minutes=2)).isoformat(),
            'operations':[str(uuid.uuid4()) for _ in range(4)],'initialized':False,'backup':str(backup_path)}
        save_json(target, saved)
    workspace, worker_id, scope = saved['workspace'], saved['worker'], saved['scope']
    state_root = root / '.desktop-build/shared-publication-qa' / workspace
    migration = Migration(rpc,book,state_root/'migration',scope)
    if not any(row['id']==workspace for row in rpc.call('tv_list_workspaces', {})):
        rpc.call('tv_create_workspace', {'p_workspace':workspace,'p_name':'Tv Tracker publication QA','p_queue_scope':scope})
    status = rpc.call('tv_workspace_status', {'p_workspace':workspace})
    if status['queue_scope'] != scope:
        raise ValueError('The saved QA queue differs from the workspace.')
    if not saved['initialized']:
        if status['mode']!='shadow' or status['revision']!=0 or status['pending_captures'] or status['job']:
            raise ValueError('Only an empty QA validation workspace can initialize the fixture.')
        batch = Batch(book)
        headers = ['Order Number','Product','Status','Comments','Preview']
        row = ['TV-QA-CLOUD-001','Full Title','Available','Preserve manual comment','preview47']
        for title, values in ((FULL,[headers,row]),(REMAINING,[headers])):
            sheet = batch.sheet(title)
            batch.capacity(sheet,len(values)+1,len(headers))
            batch.requests.append({'repeatCell':{'range':{'sheetId':sheet.id},'cell':{},'fields':'userEnteredValue'}})
            batch.cells(sheet,0,0,values)
        if 'Personal notes' not in batch.sheets:
            batch.cells(batch.sheet('Personal notes'),0,0,[['Keep synthetic note']])
        book.batch_update({'requests':batch.requests})
        tables, _, _, _ = migration._read()
        # Test fixture only: restart the previously completed synthetic receipt.
        publisher = SheetsPublisher(book,workspace,QA_BOOK)
        publisher._fence()
        receipt = {'workspace':workspace,'spreadsheet':QA_BOOK,'revision':0,'digest':digest(tables),'tabs':sorted(tables)}
        book.worksheet(RECEIPT).update([['Receipt'],[json.dumps(receipt,sort_keys=True)]],range_name='A1:A2')
        assert publisher._receipt()==receipt
        saved['initialized']=True
        save_json(target,saved)
    plan = migration.latest(workspace)
    if plan is None:
        plan = migration.preview(workspace)
    assert plan['next_sequence']==48 and sum(r['orders'] for r in plan['counts'])==1
    assert migration._path(plan['id']).read_bytes().startswith(MAGIC)
    if status['mode']!='active':
        activated = migration.activate(workspace,plan['id'],worker_id,True,True)
        assert activated['state']=='active'
    unknown = read_values(book,[book.worksheet('Personal notes')])[0]
    worker_rpc = OfficeWorkerRpc(config['url'],config['publishableKey'],lambda:token,worker_id)
    worker = OfficeWorker(worker_rpc,state_root/'worker',lambda identity:client.open_by_key(identity))
    if status['mode']!='active':
        assert worker.step(workspace)['state']=='published'
    base = datetime.fromisoformat(saved['base'])
    operations = saved['operations']
    def submit(index):
        incoming = {'Order Number':'TV-QA-CLOUD-001','Product':'Full Title','Status':'Search In Progress',
            'In-Time':'10/01/2026 09:00 AM'}
        body = {'p_workspace':workspace,'p_operation':operations[index],
            'p_captured_at':(base+timedelta(seconds=index)).isoformat(),
            'p_payload':{'columns':list(incoming),'rows':[incoming],'queue_scope':scope,
                'metadata':{'kind':'portal','complete':True,'expected_rows':1,'actual_rows':1}}}
        own = SupabaseRpc(config['url'],config['publishableKey'],lambda:token)
        receipt = own.call('tv_submit_capture',body)
        assert own.call('tv_submit_capture',body)==receipt
        if not saved.get('submitted'):
            assert own.call('tv_operation',{'p_workspace':workspace,'p_operation':operations[index]})['published'] is False
        return receipt
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(submit,range(4)))
    assert sorted(r['sequence'] for r in receipts)==[48,49,50,51]
    saved['submitted']=True
    save_json(target,saved)
    results=[]
    for _ in range(20):
        # Recreate every step to exercise persisted job-state recovery.
        step = OfficeWorker(worker_rpc,state_root/'worker',lambda identity:client.open_by_key(identity)).step(workspace)
        results.append(step)
        if step['state']=='idle':
            break
    assert results[-1]['state']=='idle'
    current=rpc.snapshot(workspace)
    assert current['revision']==current['published_revision']
    assert current['orders'][0]['data']['Comments']=='Preserve manual comment'
    assert book.worksheet('Personal notes').get_all_values()==unknown
    for operation in operations:
        receipt=rpc.call('tv_operation',{'p_workspace':workspace,'p_operation':operation})
        assert receipt['processing_state'] in ('processed','review')
        if receipt['processing_state']=='processed':
            assert receipt['published'] is True
    result={'workspace':workspace,'workbook':book.id,'migration_verified':True,'snapshot_windows_encrypted':True,
        'sequence_preserved':True,'four_concurrent_logical_clients':True,'duplicate_retries_idempotent':True,
        'worker_restart_verified':True,'manual_fields_preserved':True,'unknown_tabs_preserved':True,
        'original_qa_fixture_encrypted_backup':True,
        'publication_revision':current['published_revision'],'production_modified':False}
    (root/'.desktop-build/shared-publication-acceptance.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))


if __name__=='__main__':
    try:
        run(json.load(sys.stdin))
    except Exception as error:
        print('Shared publication acceptance failed: '+type(error).__name__,file=sys.stderr)
        sys.exit(1)
