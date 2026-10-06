import json
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
        runtime.update_token('fixture-private-access')
        with self.assertRaises(ValueError):
            runtime.submit(self.preview)
        self.assertNotIn('fixture-private-access', json.dumps(runtime.status()))
        self.assertNotIn(b'fixture-private-access', (self.root/'previews.sqlite').read_bytes())

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
