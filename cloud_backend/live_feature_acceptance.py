"""New shared workflows, using only the explicitly approved synthetic workbook."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import traceback
import uuid

from cloud_backend.live_publication_acceptance import QA_BOOK, save_json
from cloud_backend.transport import OfficeWorkerRpc
from cloud_backend.worker import OfficeWorker
from shared_backend import CloudError, SupabaseRpc


def run(settings):
    import gspread
    from google.oauth2.service_account import Credentials
    from sheets_transport import QuotaHTTPClient
    from tracker_sync import FULL
    root=Path(__file__).resolve().parents[1]
    target=json.loads((root/'.desktop-build/shared-publication-target.json').read_text())
    if target['workbook']!=QA_BOOK or not target.get('submitted'):
        raise ValueError('Complete the approved publication rehearsal first.')
    account=json.loads((root/'gsheet_dashboard/service_account.json').read_text())
    client=gspread.authorize(Credentials.from_service_account_info(account,
        scopes=['https://www.googleapis.com/auth/spreadsheets']),http_client=QuotaHTTPClient)
    client.set_timeout((10,90))
    book=client.open_by_key(QA_BOOK)
    if not book.title.startswith('Tv Tracker acceptance QA'):
        raise ValueError('Unexpected QA workbook.')
    config,token=settings['config'],settings['accessToken']
    workspace=target['workspace']
    rpc=SupabaseRpc(config['url'],config['publishableKey'],lambda:token)
    status=rpc.call('tv_workspace_status',{'p_workspace':workspace})
    if status['spreadsheet']!=QA_BOOK or status['worker']!=target['worker'] or status['queue_scope']!=target['scope']:
        raise ValueError('Unexpected QA workspace binding.')
    path=root/'.desktop-build/shared-feature-target.json'
    saved=json.loads(path.read_text()) if path.exists() else {'workspace':workspace,'steps':{}}
    if saved['workspace']!=workspace:
        raise ValueError('Unexpected saved feature rehearsal.')
    if 'personal_notes' not in saved:
        saved['personal_notes']=book.worksheet('Personal notes').get_all_values()
        save_json(path,saved)
    os.environ['DATATRACE_DESKTOP']='1'
    state_root=root/'.desktop-build/shared-publication-qa'/workspace
    worker_rpc=OfficeWorkerRpc(config['url'],config['publishableKey'],lambda:token,target['worker'])

    def step(name,method,body):
        if name not in saved['steps']:
            saved['steps'][name]={'method':method,'body':dict(body(),p_operation=str(uuid.uuid4()))}
            save_json(path,saved)
        record=saved['steps'][name]
        result=rpc.call(record['method'],record['body'])
        assert result==rpc.call(record['method'],record['body'])
        if 'result' in record:
            assert record['result']==result
        record['result']=result
        save_json(path,saved)
        print('Verified shared step: '+name,flush=True)
        return result

    def version():
        return rpc.snapshot(workspace)['revision']

    row={'Order Number':'TV-QA-FEATURE-002','Product':'Full Title','Status':'Completed and Delivered',
        'In-Time':'10/07/2026 09:00 AM','Out Time':'10/07/2026 10:00 AM',
        'SLA Expiration':'10/07/2026 10:00 AM','Free Site':'On Time',
        'Comments':'Preserve feature comment','Reporting Month':'2026-10'}
    step('monthly-import','tv_apply_monthly',lambda:{'p_workspace':workspace,'p_plan':str(uuid.uuid4()),
        'p_revision':version(),'p_kind':'import','p_month':'2026-10',
        'p_rows':[{'order_key':row['Order Number'].lower(),'version':None,'data':row}], 'p_periods':['2026-10']})
    step('empty-period','tv_apply_monthly',lambda:{'p_workspace':workspace,'p_plan':str(uuid.uuid4()),
        'p_revision':version(),'p_kind':'setup','p_month':'2026-12','p_rows':[],'p_periods':['2026-12']})
    def rollover():
        snapshot=rpc.snapshot(workspace)
        order=next(item for item in snapshot['orders'] if item['order_key']=='tv-qa-cloud-001')
        data=dict(order['data'],**{'Reporting Month':'2026-11','Carried From':'Oct_2026'})
        data.pop('No',None)
        return {'p_workspace':workspace,'p_plan':str(uuid.uuid4()),'p_revision':snapshot['revision'],
            'p_kind':'rollover','p_month':'2026-10','p_rows':[dict(order,data=data)],'p_periods':['2026-10','2026-11']}
    step('rollover','tv_apply_monthly',rollover)
    def correction():
        snapshot=rpc.snapshot(workspace)
        order=next(item for item in snapshot['orders'] if item['order_key']==row['Order Number'].lower())
        return {'p_workspace':workspace,'p_revision':snapshot['revision'],'p_status':'Missing',
            'p_orders':[{'order_key':order['order_key'],'version':order['version'],
                'completion_date':'2026-10-07','expected_status':'On Time'}]}
    step('sla-correction','tv_correct_sla',correction)
    stale=dict(saved['steps']['sla-correction']['body'],p_operation=str(uuid.uuid4()),p_revision=version())
    try:
        rpc.call('tv_correct_sla',stale)
        raise AssertionError('A stale selection was accepted.')
    except CloudError as error:
        if error.kind!='conflict':
            print('Stale-selection response: '+error.kind+'; '+str(error),file=sys.stderr)
        assert error.kind=='conflict'
    dataset={'columns':['Order Number','Product','Status','Date'],
        'rows':[{'Order Number':'TV-QA-IMPORT-007','Product':'Update','Status':'Available','Date':'10/07/2026'}],
        'files':[{'name':'synthetic-report.xlsx','accepted':1}]}
    imported=step('report-import','tv_save_report_import',lambda:{'p_workspace':workspace,'p_import':str(uuid.uuid4()),'p_dataset':dataset})
    repeated=step('other-pc-import','tv_save_report_import',lambda:{'p_workspace':workspace,'p_import':imported['id'],'p_dataset':dataset})
    assert repeated==imported
    step('source-import','tv_change_reporting',lambda:{'p_workspace':workspace,'p_revision':version(),
        'p_action':'source','p_change':{'source':'import','import_id':imported['id']}})
    if 'concurrency' not in saved:
        revision=version()
        saved['concurrency']=[{'p_workspace':workspace,'p_revision':revision,'p_operation':str(uuid.uuid4()),
            'p_action':'capacity','p_change':{'date':'default','capacity':10+i,'extended':20+i}} for i in range(4)]
        save_json(path,saved)
    def change(body):
        own=SupabaseRpc(config['url'],config['publishableKey'],lambda:token)
        try:
            return own.call('tv_change_reporting',body)
        except CloudError as error:
            assert error.kind=='conflict'
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes=list(pool.map(change,saved['concurrency']))
    assert sum(result is not None for result in outcomes)==1
    def drain():
        for _ in range(10):
            result=OfficeWorker(worker_rpc,state_root/'worker',lambda identity:client.open_by_key(identity)).step(workspace)
            if result['state']=='idle':
                return
        raise AssertionError('Worker did not finish the test publication.')
    drain()
    state=rpc.call('tv_reporting_state',{'p_workspace':workspace})
    if 'restored-source' not in saved['steps']:
        assert state['preferences']['source']=='import'
        assert book.worksheet('All Products').get_all_values()[1][0]=='TV-QA-IMPORT-007'
        canonical=book.worksheet(FULL).get_all_values()
        assert len(canonical)==3
    step('restored-source','tv_change_reporting',lambda:{'p_workspace':workspace,'p_revision':version(),
        'p_action':'source','p_change':{'source':'tracker'}})
    drain()
    step('batched-publication','tv_change_reporting',lambda:{'p_workspace':workspace,'p_revision':version(),
        'p_action':'capacity','p_change':{'date':'default','capacity':14,'extended':24}})
    drain()
    snapshot=rpc.snapshot(workspace)
    assert snapshot['revision']==snapshot['published_revision']
    orders={item['order_key']:item['data'] for item in snapshot['orders']}
    assert len(orders)==2 and orders['tv-qa-cloud-001']['Comments']=='Preserve manual comment'
    assert orders['tv-qa-cloud-001']['Reporting Month']=='2026-11'
    assert orders['tv-qa-feature-002']['Free Site']=='Missing'
    assert orders['tv-qa-feature-002']['SLA Override Status']=='Missing'
    assert len(book.worksheet(FULL+'_Dec_2026').get_all_values())==1
    assert book.worksheet('Personal notes').get_all_values()==saved['personal_notes']
    result={'workspace':workspace,'workbook':QA_BOOK,'shared_import_retry':True,'source_isolation':True,
        'capacity_conflicts':True,'monthly_import_setup_rollover':True,'sla_version_conflict':True,
        'manual_fields_preserved':True,'publication_revision':snapshot['published_revision'],
        'production_modified':False,'physical_pcs_tested':1}
    save_json(root/'.desktop-build/shared-feature-acceptance.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    try:
        run(json.load(sys.stdin))
    except Exception as error:
        frame=traceback.extract_tb(error.__traceback__)[-1]
        print(f'Shared feature acceptance failed: {type(error).__name__} at {Path(frame.filename).name}:{frame.lineno}',file=sys.stderr)
        sys.exit(1)
