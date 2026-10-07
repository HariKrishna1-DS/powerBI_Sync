import uuid
from test_database import BackendDatabaseTests, rpc, sql, quote, OWNER, VIEWER, OTHER


import unittest


class ReportingDatabaseTests(unittest.TestCase):
    setUp = BackendDatabaseTests.setUp
    submit = BackendDatabaseTests.submit
    def test_business_conflicts_do_not_trigger_transaction_retries(self):
        definitions=sql("select pg_catalog.pg_get_functiondef(p.oid) from pg_catalog.pg_proc p "
            "join pg_catalog.pg_namespace n on n.oid=p.pronamespace "
            "where n.nspname='public' and p.proname like 'tv_%';")
        self.assertNotIn("errcode='40001'",definitions)
        self.assertIn("errcode='PT409'",definitions)
        before=rpc('tv_snapshot',[self.workspace])
        self.assertIn('Snapshot revision changed',rpc('tv_snapshot',[self.workspace,99],fails=True))
        self.assertEqual(before,rpc('tv_snapshot',[self.workspace]))
    # Reuse setup, not the inherited order tests a second time.
    def test_shared_source_target_and_import_keep_capture_orders_separate(self):
        dataset={'columns':['Order Number','Product','Status','Date'],
            'rows':[{'Order Number':'0007','Product':'Update','Status':'Available','Date':'10/01/2026'}],
            'files':[{'name':'orders.xlsx','accepted':1}]}
        identity,operation=str(uuid.uuid4()),str(uuid.uuid4())
        args=[self.workspace,operation,identity,dataset]
        self.assertEqual(rpc('tv_save_report_import',args),rpc('tv_save_report_import',args))
        # Another computer/user operation can reference the same immutable import.
        repeated=rpc('tv_save_report_import',[self.workspace,str(uuid.uuid4()),identity,dataset])
        self.assertEqual(repeated,{'id':identity,'count':1})
        changed=dict(dataset,rows=[dict(dataset['rows'][0],Status='Cancelled')])
        self.assertIn('different content',rpc('tv_save_report_import',
            [self.workspace,str(uuid.uuid4()),identity,changed],fails=True))
        self.assertEqual(rpc('tv_snapshot',[self.workspace])['orders'],[])
        self.assertEqual(rpc('tv_reporting_state',[self.workspace])['preferences']['source'],'tracker')
        selected=rpc('tv_change_reporting',[self.workspace,str(uuid.uuid4()),0,'source',{'source':'import','import_id':identity}])
        self.assertEqual(selected,{'state':'pending','revision':1})
        state=rpc('tv_reporting_state',[self.workspace,1])
        self.assertEqual(state['dataset'],dataset)
        rpc('tv_change_reporting',[self.workspace,str(uuid.uuid4()),1,'capacity',{'date':'2026-10-01','capacity':10,'extended':12}])
        state=rpc('tv_reporting_state',[self.workspace,2])
        self.assertEqual(state['targets']['2026-10-01'],{'capacity':10,'extended':12})
        self.assertEqual(rpc('tv_snapshot',[self.workspace])['orders'],[])

    def test_reporting_role_conflicts_and_retry_receipts(self):
        args=[self.workspace,str(uuid.uuid4()),0,'capacity',{'date':'default','capacity':15,'extended':20}]
        receipt=rpc('tv_change_reporting',args)
        self.assertEqual(receipt,rpc('tv_change_reporting',args))
        self.assertIn('permission denied',rpc('tv_reporting_state',[self.workspace],role='anon',user=None,fails=True))
        self.assertIn('access denied',rpc('tv_reporting_state',[self.workspace],user=OTHER,fails=True))
        self.assertIn('access denied',rpc('tv_change_reporting',args,user=VIEWER,fails=True))
        self.assertEqual(rpc('tv_reporting_state',[self.workspace],user=VIEWER)['preferences']['default_capacity'],15)
        args[1]=str(uuid.uuid4())
        self.assertIn('refresh',rpc('tv_change_reporting',args,fails=True))
        self.assertIn('revision changed',rpc('tv_reporting_state',[self.workspace,0],fails=True))
        self.submit()
        rpc('tv_claim_job',[self.workspace,str(uuid.uuid4())],role='service_role',user=None)
        args[1],args[2]=str(uuid.uuid4()),1
        self.assertIn('worker is processing',rpc('tv_change_reporting',args,fails=True))

    def test_invalid_targets_imports_and_cross_workspace_selection_roll_back(self):
        for patch in ({'date':'default','capacity':1.5,'extended':3},{'date':'2026-02-30','capacity':1,'extended':3},
            {'date':'default','capacity':True,'extended':3},{'date':'default','capacity':20,'extended':3},
            {'date':'default','capacity':-1,'extended':3}):
            self.assertTrue(rpc('tv_change_reporting',[self.workspace,str(uuid.uuid4()),0,'capacity',patch],fails=True))
        self.assertEqual(rpc('tv_reporting_state',[self.workspace])['revision'],0)
        self.assertTrue(rpc('tv_change_reporting',[self.workspace,str(uuid.uuid4()),0,'source',{'source':'import','import_id':str(uuid.uuid4())}],fails=True))
        self.assertTrue(rpc('tv_save_report_import',[self.workspace,str(uuid.uuid4()),str(uuid.uuid4()),{'rows':[],'columns':[],'files':[]}],fails=True))
        self.assertIn('permission denied',sql('select * from tv_tracker.report_settings;',role='authenticated',user=OWNER,fails=True))

    def test_publish_claim_freezes_selected_report_and_targets(self):
        rpc('tv_change_reporting',[self.workspace,str(uuid.uuid4()),0,'capacity',{'date':'default','capacity':10,'extended':None}])
        sql(f"update tv_tracker.workspaces set mode='active' where id={quote(self.workspace)};")
        token=str(uuid.uuid4())
        claim=rpc('tv_claim_job',[self.workspace,token],role='service_role',user=None)
        self.assertEqual(claim['report_context']['preferences']['default_capacity'],10)
        self.assertIsNone(claim['report_context']['preferences']['default_extended'])
        self.assertEqual(claim,rpc('tv_claim_job',[self.workspace,token],role='service_role',user=None))

    def test_sla_bulk_is_atomic_versioned_and_retry_safe(self):
        row={'Order Number':'001','Status':'Completed and Delivered','Out Time':'10/01/2026 10:00 AM',
            'SLA Expiration':'10/01/2026 11:00 AM','Free Site':'On Time'}
        rpc('tv_seed_workspace',[self.workspace,str(uuid.uuid4()),[row],1])
        selection=[{'order_key':'001','version':1,'completion_date':'2026-10-01','expected_status':'On Time'}]
        operation=str(uuid.uuid4())
        args=[self.workspace,operation,1,selection,'Missing']
        result=rpc('tv_correct_sla',args)
        self.assertEqual(result,{'state':'pending','revision':2,'updated_count':1})
        self.assertEqual(result,rpc('tv_correct_sla',args))
        data=rpc('tv_snapshot',[self.workspace])['orders'][0]['data']
        self.assertEqual(data['Free Site'],'Missing')
        self.assertEqual(data['SLA Override Out Time'],row['Out Time'])
        self.assertIn('access denied',rpc('tv_correct_sla',args,user=VIEWER,fails=True))
        args[1]=str(uuid.uuid4());args[2]=2
        self.assertIn('selected order changed',rpc('tv_correct_sla',args,fails=True))

    def test_one_inferred_sla_selection_rolls_back_entire_bulk(self):
        common={'Status':'Completed and Delivered','Out Time':'10/01/2026 10:00 AM',
            'SLA Expiration':'10/01/2026 11:00 AM','Free Site':'On Time'}
        rpc('tv_seed_workspace',[self.workspace,str(uuid.uuid4()),[dict(common,**{'Order Number':'001'}),
            dict(common,**{'Order Number':'002','Completion Evidence':'Inferred from queue absence'})],1])
        selection=[{'order_key':key,'version':1,'completion_date':'2026-10-01','expected_status':'On Time'} for key in ('001','002')]
        self.assertIn('lacks recorded SLA timing',rpc('tv_correct_sla',[self.workspace,str(uuid.uuid4()),1,selection,'Missing'],fails=True))
        saved=rpc('tv_snapshot',[self.workspace])
        self.assertEqual(saved['revision'],1)
        self.assertTrue(all(item['data']['Free Site']=='On Time' for item in saved['orders']))

    def test_monthly_rollover_and_import_are_versioned_atomic_and_retry_safe(self):
        row={'Order Number':'001','Status':'Available','Comments':'Keep','Reporting Month':'2026-10'}
        rpc('tv_seed_workspace',[self.workspace,str(uuid.uuid4()),[row],1])
        changes=[{'order_key':'001','version':1,'data':dict(row,**{'Reporting Month':'2026-11','Carried From':'Oct_2026'})}]
        args=[self.workspace,str(uuid.uuid4()),str(uuid.uuid4()),1,'rollover','2026-10',changes,['2026-10','2026-11']]
        receipt=rpc('tv_apply_monthly',args)
        self.assertEqual(receipt,rpc('tv_apply_monthly',args))
        self.assertEqual(receipt,{'state':'pending','revision':2,'updated_count':1})
        self.assertEqual(rpc('tv_reporting_state',[self.workspace])['periods'],['2026-10','2026-11'])
        self.assertIn('access denied',rpc('tv_apply_monthly',args,user=VIEWER,fails=True))
        args[1]=str(uuid.uuid4())
        self.assertIn('changed',rpc('tv_apply_monthly',args,fails=True))
        args[3]=2;args[6][0]['version']=2;args[6][0]['data']['Comments']='Overwrite'
        self.assertIn('only change month ownership',rpc('tv_apply_monthly',args,fails=True))
        self.assertEqual(rpc('tv_snapshot',[self.workspace])['orders'][0]['data']['Comments'],'Keep')

    def test_monthly_new_order_import_and_archive_guard(self):
        row={'Order Number':'002','Status':'Available','Reporting Month':'2026-11'}
        args=[self.workspace,str(uuid.uuid4()),str(uuid.uuid4()),0,'import','2026-11',
            [{'order_key':'002','version':None,'data':row}],['2026-11']]
        self.assertEqual(rpc('tv_apply_monthly',args)['updated_count'],1)
        args[1]=str(uuid.uuid4());args[3]=1;args[6][0]['version']=1
        args[6][0]['data']['Reporting Month']='2026-09'
        self.assertIn('Invalid canonical monthly row',rpc('tv_apply_monthly',args,fails=True))
        self.assertEqual(rpc('tv_snapshot',[self.workspace])['revision'],1)


del BackendDatabaseTests  # Only discover this module's reporting tests.
