from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from cloud_backend.publication import projection
from preview_store import PreviewStore
from report_workspace import read_workbooks
from shared_backend import CloudError
from shared_requests import SharedRequests
from shared_runtime import SharedRuntime
from test_report_workspace import workbook,order
from tracker_sync import FULL
from workspace_backup import make_backup,restore_backup


class SharedReportingTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.store=PreviewStore(Path(folder.name)/'previews')
        self.config={'id':str(uuid.uuid4()),'role':'editor','queue_scope':'queue',
            'url':'https://qontoybecrqpbjzoajqf.supabase.co','publishableKey':'sb_publishable_fixture'}
        self.runtime=SharedRuntime(self.store,self.config)
        self.context={'preferences':{'source':'tracker','import_id':None,'default_capacity':10,'default_extended':12},
            'targets':{},'imports':[],'dataset':None,'revision':1,'published_revision':0}

    def test_lost_write_reply_and_backup_restore_reuse_operation_identity(self):
        body={'p_workspace':self.config['id'],'p_revision':1,'p_action':'publish','p_change':{}}
        rpc=Mock(); rpc.call.side_effect=CloudError('Lost reply','retry')
        with self.assertRaises(CloudError):self.runtime.requests.perform(rpc,'tv_change_reporting',body)
        operation=rpc.call.call_args.args[1]['p_operation']
        archive=make_backup(self.store).getvalue()
        restore_backup(self.store,archive)
        rpc.call.side_effect=None; rpc.call.return_value={'revision':2,'state':'pending'}
        requests=SharedRequests(self.store)
        self.assertEqual(requests.perform(rpc,'tv_change_reporting',body),rpc.call.return_value)
        self.assertEqual(rpc.call.call_args.args[1]['p_operation'],operation)
        requests.perform(rpc,'tv_change_reporting',body)
        self.assertEqual(rpc.call.call_count,2)

    def test_selected_import_does_not_replace_canonical_tracker_or_targets(self):
        dataset=read_workbooks([('report.xlsx',workbook([order('0007')]))])
        context=deepcopy(self.context)
        context['preferences'].update(source='import',import_id=str(uuid.uuid4()))
        context['dataset']=dataset
        context['targets']={'2026-10-01':{'capacity':30,'extended':35}}
        tables,value=projection([{'order_key':'0001','data':order('0001',Comments='Keep')}],'2026-10-07T00:00:00Z',context)
        self.assertEqual(value['sheets']['All Products']['rows'][0]['Order Number'],'0007')
        self.assertEqual(tables[FULL][1][tables[FULL][0].index('Order Number')],'0001')
        self.assertEqual(value['capacity']['daily'][0]['Capacity'],30)
        self.assertEqual(value['source_mode'],'import')

    def test_context_revision_change_restarts_entire_snapshot(self):
        self.runtime.rpc=Mock()
        self.runtime.rpc.snapshot.side_effect=[{'revision':1,'orders':[]},{'revision':2,'orders':[]}]
        self.runtime.rpc.call.side_effect=[CloudError('Changed','conflict'),dict(self.context,revision=2)]
        value=self.runtime.snapshot(force=True)
        self.assertEqual(value['shared_revision'],2)
        self.assertEqual(self.runtime.rpc.snapshot.call_count,2)
        self.assertEqual(value['report_preferences']['publish_status'],'pending')

    def test_viewer_stale_revision_and_malformed_receipts_cannot_claim_success(self):
        viewer=SharedRuntime(self.store,dict(self.config,role='viewer'))
        with self.assertRaises(ValueError):viewer.report_change('publish',{},1)
        with self.assertRaises(ValueError):self.runtime.report_change('publish',{},None)
        self.runtime.rpc=Mock(); self.runtime.rpc.call.return_value={'revision':999,'state':'pending'}
        with self.assertRaises(CloudError):self.runtime.report_change('publish',{},1)
