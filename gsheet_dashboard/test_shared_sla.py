from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from cloud_backend.processor import process_capture
from preview_store import PreviewStore
from shared_backend import CloudError
from shared_runtime import SharedRuntime
from shared_sla import correct_shared_sla


class SharedSlaTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.store=PreviewStore(Path(folder.name)/'previews')
        self.config={'id':str(uuid.uuid4()),'role':'editor','queue_scope':'queue',
            'url':'https://qontoybecrqpbjzoajqf.supabase.co','publishableKey':'sb_publishable_fixture'}
        self.runtime=SharedRuntime(self.store,self.config); self.runtime.rpc=Mock()
        self.row={'Order Number':'001','Product':'Full Title','Status':'Completed and Delivered','Date':'10/01/2026',
            'In-Time':'10/01/2026 09:00 AM','Out Time':'10/01/2026 10:00 AM',
            'SLA Expiration':'10/01/2026 11:00 AM','Free Site':'On Time','Completion Evidence':'Recorded completion timestamp'}
        self.context={'preferences':{'source':'tracker'},'revision':1,'published_revision':1,'targets':{},'imports':[]}
        self.snapshot={'revision':1,'orders':[{'order_key':'001','version':1,'data':deepcopy(self.row)}]}
        self.runtime.rpc.snapshot.return_value=self.snapshot
        self.body={'order_number':'001','completion_date':'2026-10-01','expected_status':'On Time','status':'Missing'}
        self.runtime.rpc.call.side_effect=lambda name,body: self.context if name=='tv_reporting_state' else {'state':'pending','revision':2,'updated_count':1}

    def test_shared_sla_is_pending_and_does_not_contact_google(self):
        value=correct_shared_sla(self.runtime,self.body)
        self.assertTrue(value['saved']); self.assertIn('pending',value['message'])
        body=self.runtime.rpc.call.call_args.args[1]
        self.assertEqual(body['p_orders'][0]['version'],1)
        self.assertEqual(body['p_status'],'Missing')

    def test_uncertain_stale_duplicate_and_imported_orders_are_rejected(self):
        for patch in ({'Completion Evidence':'Inferred from queue absence'},{'Out Time':'10/01/2026'},
            {'Status':'Cancelled'},{'Free Site':'Missing'}):
            self.snapshot['orders'][0]['data']=dict(self.row,**patch)
            with self.assertRaises(CloudError):correct_shared_sla(self.runtime,self.body)
        self.snapshot['orders'][0]['data']=deepcopy(self.row)
        with self.assertRaises(ValueError):correct_shared_sla(self.runtime,{'orders':[self.body,self.body],'status':'Missing'},True)
        self.context['preferences']['source']='import'
        with self.assertRaises(ValueError):correct_shared_sla(self.runtime,self.body)

    def test_response_loss_retries_old_version_even_after_cloud_row_changed(self):
        def call(name,body):
            if name=='tv_reporting_state':return self.context
            self.saved=deepcopy(body)
            raise CloudError('Lost response','retry')
        self.runtime.rpc.call.side_effect=call
        with self.assertRaises(CloudError):correct_shared_sla(self.runtime,self.body)
        self.snapshot['orders'][0]['data']['Free Site']='Missing'
        self.snapshot['revision']=2
        self.runtime.rpc.call.side_effect=None
        self.runtime.rpc.call.return_value={'state':'pending','revision':2,'updated_count':1}
        self.runtime.snapshot=Mock(return_value={'reports':{'monthly':[]}})
        value=correct_shared_sla(self.runtime,self.body)
        self.assertTrue(value['saved'])
        self.assertEqual(self.runtime.rpc.call.call_args.args[1],self.saved)

    def test_correction_survives_capture_only_while_recorded_timing_matches(self):
        row=dict(self.row,**{'SLA Override Status':'Missing','SLA Override Out Time':self.row['Out Time'],
            'SLA Override Deadline':self.row['SLA Expiration'],'SLA Override Completion':'2026-10-01','Free Site':'Missing'})
        payload={'rows':[{'Order Number':'002','Product':'Update','Task Status':'Available'}],
            'columns':['Order Number'],'metadata':{'kind':'portal','complete':True,'expected_rows':1,'actual_rows':1}}
        claim={'capture':{'payload':payload,'captured_at':'2026-10-07T09:00:00Z'},'previous':None,
            'orders':[{'order_key':'001','data':row}]}
        rows,_,_=process_capture(claim)
        # Unchanged completed orders need no canonical write; override stays in source.
        self.assertFalse(any(item['Order Number']=='001' and item['Free Site']=='On Time' for item in rows))
        claim['orders'][0]['data']['SLA Override Deadline']='Old deadline'
        rows,_,_=process_capture(claim)
        updated=next(item for item in rows if item['Order Number']=='001')
        self.assertEqual(updated['Free Site'],'On Time')
        self.assertEqual(updated['SLA Override Status'],'')
