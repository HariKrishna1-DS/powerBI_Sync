from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid
from werkzeug.datastructures import FileStorage
from openpyxl import Workbook

from cloud_backend.publication import projection
from preview_store import PreviewStore
from shared_backend import CloudError
from shared_monthly import SharedMonthly
from shared_runtime import SharedRuntime
from monthly_production import tab_name, BASES


class SharedMonthlyTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.runtime=SharedRuntime(PreviewStore(Path(folder.name)/'previews'),{
            'id':str(uuid.uuid4()),'role':'editor','queue_scope':'queue',
            'url':'https://qontoybecrqpbjzoajqf.supabase.co','publishableKey':'sb_publishable_fixture'})
        self.runtime.rpc=Mock()
        self.rows=[{'order_key':'001','version':3,'data':{'Order Number':'001','Product':'Full Title',
            'Status':'Available','In-Time':'10/01/2026 10:00 AM','Out Time':'','Comments':'Keep','Reporting Month':'2026-10'}}]
        self.runtime.rpc.snapshot.return_value={'revision':5,'orders':self.rows}
        self.runtime.rpc.call.return_value={'preferences':{'source':'tracker'},'targets':{},'imports':[],
            'revision':5,'published_revision':4}
        self.monthly=SharedMonthly(self.runtime)

    def upload(self,rows):
        book=Workbook();book.active.title='TV Orders'
        book.active.append(['Order Number','Product','Status','In-Time','Out Time'])
        for row in rows:book.active.append(row)
        data=BytesIO();book.save(data);data.seek(0)
        return FileStorage(data,filename='orders.xlsx')

    def test_rollover_retains_manual_data_and_preview_versions(self):
        plan=self.monthly.preview('rollover','2026-10',{})
        self.assertEqual(len(plan['changes']),1)
        row=plan['changes'][0]
        self.assertEqual(row['version'],3)
        self.assertEqual(row['data']['Comments'],'Keep')
        self.assertEqual(row['data']['Reporting Month'],'2026-11')
        self.assertEqual(row['data']['Carried From'],'Oct_2026')
        self.assertEqual(plan['revision'],5)
        self.runtime.rpc.call.return_value={'revision':6,'state':'pending','updated_count':1}
        self.assertEqual(self.monthly.apply(plan)['revision'],6)

    def test_lost_reply_retry_and_changed_source_do_not_replan(self):
        plan=self.monthly.preview('rollover','2026-10',{})
        self.runtime.rpc.call.side_effect=CloudError('Lost reply','retry')
        with self.assertRaises(CloudError):self.monthly.apply(plan)
        operation=self.runtime.rpc.call.call_args.args[1]['p_operation']
        self.runtime.rpc.call.side_effect=None
        self.runtime.rpc.call.return_value={'revision':6,'state':'pending','updated_count':1}
        self.monthly.apply(plan)
        self.assertEqual(self.runtime.rpc.call.call_args.args[1]['p_operation'],operation)
        self.assertEqual(self.runtime.rpc.snapshot.call_count,1)

    def test_import_rejects_duplicate_identity_and_preserves_later_completion(self):
        row=['001','Full Title','Available','10/01/2026 10:00 AM','']
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.monthly.preview('import','2026-10',{'full_search':self.upload([row,row])})
        self.rows[0]['data'].update(Status='Completed and Delivered',**{'Out Time':'10/02/2026 10:00 AM'})
        plan=self.monthly.preview('import','2026-10',{'full_search':self.upload([row])})
        self.assertEqual(plan['changes'][0]['data']['Out Time'],'10/02/2026 10:00 AM')

    def test_viewer_archive_foreign_plan_and_missing_month_are_rejected(self):
        with self.assertRaises(ValueError):self.monthly.preview('setup','2026-09',{})
        plan=self.monthly.preview('setup','2026-10',{})
        other=deepcopy(plan);other['workspace']=str(uuid.uuid4())
        with self.assertRaises(ValueError):self.monthly.apply(other)
        self.runtime.selection['role']='viewer'
        with self.assertRaises(ValueError):self.monthly.preview('setup','2026-10',{})

    def test_projection_uses_reporting_ownership_and_retains_empty_periods(self):
        rows=deepcopy(self.rows);rows[0]['data']['Reporting Month']='2026-11'
        tables,value=projection(rows,'2026-11-01T00:00:00Z',{'periods':['2026-10']})
        self.assertEqual(len(tables[tab_name(BASES[0],'2026-10')]),1)
        self.assertEqual(len(tables[tab_name(BASES[0],'2026-11')]),2)
        self.assertEqual(value['reports']['monthly'][0]['Month'],'2026-11')
