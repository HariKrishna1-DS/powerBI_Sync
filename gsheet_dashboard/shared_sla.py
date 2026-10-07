"""Strict eligibility and optimistic versions for canonical SLA corrections."""
import re

from production_timing import sla_result
from report_metrics import completion_inferred
from tracker_sync import sheet_reports,FULL,REMAINING
from shared_backend import CloudError


def correct_shared_sla(runtime,body,bulk=False):
    runtime.authorize_capture()
    if not isinstance(body,dict):
        raise ValueError('Choose an SLA correction.')
    status = 'Missing' if body.get('status')=='Missed' else body.get('status')
    if status not in ('On Time','Missing'):
        raise ValueError('Choose On Time or Missing.')
    selected = body.get('orders') if bulk else [body]
    if not isinstance(selected,list) or not 1<=len(selected)<=10000:
        raise ValueError('Select between 1 and 10,000 SLA orders.')
    identities=[]
    for item in selected:
        if not isinstance(item,dict) or not isinstance(item.get('order_number'),str):
            raise ValueError('Each SLA selection needs an order number.')
        expected = 'Missing' if item.get('expected_status')=='Missed' else item.get('expected_status')
        identities.append({'order_key':item['order_number'].strip().lower(),
            'completion_date':item.get('completion_date'),'expected_status':expected})
    pending = runtime.requests.pending_sla(runtime.selection['id'],identities,status)
    if pending:
        receipt = runtime.requests.perform(runtime.rpc,'tv_correct_sla',pending)
        if receipt.get('revision')!=pending['p_revision']+1 or receipt.get('updated_count')!=len(selected) or receipt.get('state')!='pending':
            raise CloudError('The previous SLA save could not be verified. Saved selections were retained.', 'retry')
        runtime.cache.invalidate(); runtime.reporting=None
        value=runtime.snapshot(force=True)
        return {'saved':True,'updated_count':len(selected),'rows':value['reports']['monthly'],
            'message':'The interrupted SLA save was recovered. Google Sheets publication may still be pending.'}
    saved = runtime.rpc.snapshot(runtime.selection['id'])
    context = runtime.report_state(saved['revision'])
    if context['preferences']['source']=='import':
        raise ValueError('Correct the source workbook and re-import it. Imported reports do not change tracker SLA values.')
    by_key = {item['order_key']:item for item in saved['orders']}
    orders,seen = [],set()
    for item in selected:
        if not isinstance(item,dict) or not isinstance(item.get('order_number'),str):
            raise ValueError('Each SLA selection needs an order number.')
        key = item['order_number'].strip().lower()
        day = item.get('completion_date','')
        expected = 'Missing' if item.get('expected_status')=='Missed' else item.get('expected_status')
        record = by_key.get(key)
        if not record or key in seen or expected not in ('On Time','Missing') or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(day)):
            raise ValueError('Refresh and select each eligible SLA order once.')
        row = record['data']
        from monthly_production import local_datetime
        finished = local_datetime(row.get('Out Time'))
        if (completion_inferred(row) or not sla_result(row)[0] or not finished or finished.strftime('%Y-%m-%d')!=day
                or row.get('Free Site')!=expected):
            raise CloudError('An SLA selection changed or lacks verified timing. Refresh before saving.', 'conflict')
        orders.append({'order_key':key,'version':record['version'],'completion_date':day,'expected_status':expected})
        seen.add(key)
    receipt = runtime.requests.perform(runtime.rpc,'tv_correct_sla', {'p_workspace':runtime.selection['id'],
        'p_revision':saved['revision'],'p_orders':orders,'p_status':status})
    if receipt.get('revision')!=saved['revision']+1 or receipt.get('updated_count')!=len(orders) or receipt.get('state')!='pending':
        raise CloudError('The SLA save could not be verified. Retry retains the same operation.', 'retry')
    runtime.cache.invalidate(); runtime.reporting=None
    for key in seen:
        by_key[key]['data']['Free Site'] = status
    from production_rules import full_title
    rows = [item['data'] for item in saved['orders']]
    reports = sheet_reports({FULL:[row for row in rows if full_title(row)],REMAINING:[row for row in rows if not full_title(row)]})
    return {'saved':True,'updated_count':len(orders),'rows':reports['monthly'],
        'message':f'{len(orders)} SLA corrections saved in the shared workspace. Google Sheets publication is pending.'}
