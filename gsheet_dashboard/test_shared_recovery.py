from io import BytesIO
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from unittest.mock import Mock, patch

from cloud_backend.publication import digest
from cloud_backend.worker import ShadowWorker
from preview_store import PreviewStore
from shared_recovery import validate, worker_tokens, recover_worker
from shared_backend import CloudError
from workspace_backup import make_backup,restore_backup


class SharedRecoveryTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.source=PreviewStore(self.root/'source'/'previews')
        self.target=PreviewStore(self.root/'target'/'previews')
        self.workspace=str(uuid.uuid4())
        self.worker=ShadowWorker(None,self.source.root.parent/'shared-worker'/self.workspace)
        self.token=self.worker._token(self.workspace)
        self.plan={'format':'tv-tracker-migration-1','id':str(uuid.uuid4()),'workspace':self.workspace,
            'seed_operation':str(uuid.uuid4()),'activation_operation':str(uuid.uuid4()),
            'tables':{'Full':[['Order Number'],['001']]},'rows':[{'Order Number':'001'}],'next_sequence':48}
        self.plan['digest']=digest(self.plan['tables'])
        path=self.source.root.parent/'migration-snapshots'/f"{self.plan['id']}.tvmigration"
        path.parent.mkdir()
        path.write_bytes(json.dumps(self.plan).encode())

    def test_backup_restores_pending_worker_ownership_and_migration_without_credentials(self):
        (self.source.root.parent/'settings.vault').write_bytes(b'fixture-secret')
        raw=make_backup(self.source).getvalue()
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            self.assertNotIn('settings.vault',archive.namelist())
            self.assertIn(f'shared-worker/{self.workspace}/worker-state.sqlite',archive.namelist())
        restore_backup(self.target,raw)
        restored=ShadowWorker(None,self.target.root.parent/'shared-worker'/self.workspace)
        self.assertEqual(restored._token(self.workspace),self.token)
        plan=self.target.root.parent/'migration-snapshots'/f"{self.plan['id']}.tvmigration"
        self.assertEqual(json.loads(plan.read_bytes()),self.plan)

    def test_existing_different_worker_token_blocks_restore_before_replacing_workspace(self):
        current=ShadowWorker(None,self.target.root.parent/'shared-worker'/self.workspace)
        token=current._token(self.workspace)
        before=(self.target.root/'previews.sqlite').read_bytes()
        with self.assertRaisesRegex(ValueError,'Existing shared recovery state differs'):
            restore_backup(self.target,make_backup(self.source).getvalue())
        self.assertEqual(current._token(self.workspace),token)
        self.assertEqual((self.target.root/'previews.sqlite').read_bytes(),before)

    def test_snapshot_destination_integrity_and_unsupported_database_objects_are_rejected(self):
        name=f"migration-snapshots/{self.plan['id']}.tvmigration"
        broken={**self.plan,'digest':'invalid'}
        with self.assertRaisesRegex(ValueError,'integrity'):
            validate(name,json.dumps(broken).encode())
        with self.assertRaisesRegex(ValueError,'different workspace'):
            validate(f'shared-worker/{uuid.uuid4()}/worker-state.sqlite',(self.worker.root/'worker-state.sqlite').read_bytes())
        path=self.worker.root/'worker-state.sqlite'
        with closing(sqlite3.connect(path)) as db,db:
            db.execute('CREATE VIEW unexpected AS SELECT token FROM job_tokens')
        with self.assertRaisesRegex(ValueError,'schema'):
            worker_tokens(path.read_bytes())

    def test_replacement_worker_requires_bound_backup_and_original_pending_token(self):
        worker_id=str(uuid.uuid4())
        self.plan.update(state='active',worker=worker_id,spreadsheet='synthetic-workbook')
        path=self.source.root.parent/'migration-snapshots'/f"{self.plan['id']}.tvmigration"
        path.write_bytes(json.dumps(self.plan).encode())
        rpc=Mock()
        rpc.call.return_value={'mode':'active','worker':worker_id,'spreadsheet':'synthetic-workbook','job':{'kind':'publish'}}
        config={'url':'https://qontoybecrqpbjzoajqf.supabase.co','publishableKey':'fixture'}
        with patch('cloud_backend.transport.OfficeWorkerRpc') as office:
            office.return_value.call.return_value={'busy':True}
            with self.assertRaisesRegex(CloudError,'does not own'):
                recover_worker(rpc,config,'fixture',self.source.root.parent,self.workspace)
            office.return_value.call.return_value={'job':{'token':self.token,'workspace_id':self.workspace}}
            self.assertEqual(recover_worker(rpc,config,'fixture',self.source.root.parent,self.workspace)['worker'],worker_id)
            office.return_value.call.assert_called_with('tv_claim_job',{'p_workspace':self.workspace,'p_token':self.token})
        rpc.call.return_value['worker']=str(uuid.uuid4())
        with self.assertRaisesRegex(CloudError,'migration backup'):
            recover_worker(rpc,config,'fixture',self.source.root.parent,self.workspace)
