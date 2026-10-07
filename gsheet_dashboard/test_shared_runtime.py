import json
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import uuid
import pandas as pd

from preview_store import PreviewStore
from shared_backend import CloudError
from shared_runtime import SharedRuntime
from server import create_app


class SharedRuntimeTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)/'previews'
        self.store = PreviewStore(self.root)
        self.config = {'id':str(uuid.uuid4()),'role':'editor','queue_scope':'queue-23656',
            'url':'https://qontoybecrqpbjzoajqf.supabase.co','publishableKey':'sb_publishable_fixtureonly'}
        self.preview = self.store.save(pd.DataFrame([{'Order Number':'001','Task Status':'Available','Product':'Full Title'}]),
            metadata={'kind':'portal','complete':True,'expected_rows':1,'actual_rows':1})

    def test_offline_capture_is_durable_and_acceptance_is_not_publication(self):
        runtime = SharedRuntime(self.store, self.config)
        runtime.rpc = Mock()
        runtime.rpc.call.side_effect = CloudError('Offline', 'retry')
        result = runtime.submit(self.preview)
        self.assertEqual(result['cloud_state'], 'pending')
        self.assertEqual(result['google_sheet'], 'pending')
        self.assertEqual(self.store.pending_count(), 1)
        operation = runtime.outbox.status(self.config['id'])[0]['operation']
        self.assertEqual(runtime.outbox.enqueue(self.config['id'],self.preview,'queue-23656'), operation)

    def test_only_verified_publication_marks_local_capture_synced(self):
        runtime = SharedRuntime(self.store, self.config)
        runtime.rpc = Mock()
        runtime.rpc.call.return_value = {'capture_id':str(uuid.uuid4()),'sequence':45,'state':'accepted'}
        runtime.submit(self.preview)
        self.assertEqual(self.store.pending_count(), 1)
        for published in (False, True):
            runtime.rpc.call.side_effect = lambda name, body: {'mode':'active','queue_scope':'queue-23656'} if name=='tv_workspace_status' else {
                'processing_state':'processed','processed_revision':2,'published':published}
            runtime.tick()
            self.assertEqual(self.store.pending_count(), 0 if published else 1)

    def test_viewer_cannot_capture_and_tokens_are_not_saved(self):
        runtime = SharedRuntime(self.store, dict(self.config,role='viewer'))
        self.assertFalse(runtime.status()['can_capture'])
        runtime.update_token('fixture-private-access')
        with self.assertRaises(ValueError):
            runtime.submit(self.preview)
        self.assertNotIn('fixture-private-access', json.dumps(runtime.status()))
        self.assertNotIn(b'fixture-private-access', (self.root/'previews.sqlite').read_bytes())

    def test_viewer_does_not_execute_an_existing_capture_schedule(self):
        schedule = self.root.parent/'sync_schedule.json'
        saved = json.dumps({'enabled':True,'times':['09:00']})
        schedule.write_text(saved, encoding='utf-8')
        runner = Mock(side_effect=AssertionError('Viewer must not open the capture browser'))
        now = datetime(2026,10,7,10,tzinfo=timezone.utc)
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'local-fixture',
                'DATATRACE_SHARED_WORKSPACE':json.dumps(dict(self.config,role='viewer'))}):
            app = create_app(root=self.root,runner=runner,time_source=Mock(now=lambda:now,snapshot=lambda:{}))
        self.assertFalse(app.extensions['schedule_tick'](now))
        runner.assert_not_called()
        self.assertEqual(schedule.read_text(encoding='utf-8'), saved)

    def test_office_failure_backs_off_while_clients_keep_receipt_checks(self):
        identity=str(uuid.uuid4())
        runtime=SharedRuntime(self.store,dict(self.config,role='owner',officeWorker=True,worker=identity),Mock())
        runtime.rpc=Mock()
        runtime.rpc.call.return_value={'capture_id':str(uuid.uuid4()),'sequence':45,'state':'accepted'}
        runtime.submit(self.preview)
        runtime.rpc.call.side_effect=lambda name,body: {'mode':'active','queue_scope':'queue-23656','worker':identity} if name=='tv_workspace_status' else {
            'processing_state':'processed','processed_revision':2,'published':True}
        with patch('shared_runtime.OfficeWorker') as worker,patch('shared_runtime.time.monotonic',return_value=100):
            worker.return_value.step.side_effect=CloudError('Google busy','retry',60)
            runtime.tick();runtime.tick()
            self.assertEqual(worker.return_value.step.call_count,1)
            self.assertEqual(runtime.worker_retry_at,160)
            self.assertEqual(self.store.pending_count(),0)
            self.assertEqual(runtime.status()['error'],'Google busy')
        with patch('shared_runtime.OfficeWorker') as worker,patch('shared_runtime.time.monotonic',return_value=161):
            worker.return_value.step.return_value={'state':'idle'}
            runtime.tick()
            worker.return_value.step.assert_called_once()
            self.assertIsNone(runtime.status()['error'])

    def test_manual_capture_uses_outbox_without_contacting_google(self):
        def runner(on_progress):
            saved = self.store.save(pd.DataFrame(self.preview['rows']), metadata=self.preview['metadata'])
            return {'preview_id':saved['id']}
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'local-fixture',
                'DATATRACE_SHARED_WORKSPACE':json.dumps(self.config)}):
            app = create_app(root=self.root, runner=runner)
        runtime = app.extensions['shared_runtime']
        runtime.rpc = Mock()
        runtime.rpc.call.side_effect = CloudError('Sign in first', 'auth')
        client = app.test_client()
        headers = {'X-DataTrace-Token':'local-fixture'}
        with patch('server.target_worksheet', side_effect=AssertionError('Must not access Google on client')):
            self.assertEqual(client.post('/api/extract',headers=headers).status_code,202)
            deadline = time.monotonic()+10
            while client.get('/api/health',headers=headers).json['running'] and time.monotonic()<deadline:
                time.sleep(.02)
            result = client.get('/api/state',headers=headers).json
        self.assertFalse(result['job']['running'])
        self.assertEqual(result['job']['result']['cloud_state'],'auth')
        self.assertEqual(len(runtime.outbox.status(self.config['id'])),1)

    def test_shared_cloud_history_never_uses_client_google_credentials(self):
        with patch.dict(os.environ,{'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'local-fixture',
                'DATATRACE_SHARED_WORKSPACE':json.dumps(self.config)}):
            app=create_app(root=self.root)
        client=app.test_client();headers={'X-DataTrace-Token':'local-fixture'}
        with patch('server.target_worksheet',side_effect=AssertionError('No Google access on shared clients')):
            result=client.get('/api/reporting/cloud-history',headers=headers)
            self.assertEqual(result.status_code,200);self.assertTrue(result.json['shared'])
            self.assertEqual(client.post('/api/reporting/cloud-history',headers=headers,json={}).status_code,409)
            self.assertEqual(client.post('/api/reporting/cloud-history/restore',headers=headers,json={}).status_code,409)
