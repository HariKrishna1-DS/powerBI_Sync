import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid
from server import create_app


class SharedRoutesTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'DATATRACE_DESKTOP': '1', 'DATATRACE_DESKTOP_TOKEN': 'fixture-engine-token'}):
            self.app = create_app(root=Path(folder.name) / 'previews', start_scheduler=False)
        self.client = self.app.test_client()
        self.workspace = str(uuid.uuid4())
        self.body = {'workspace': self.workspace, 'action': 'inspect', 'config': {
            'url': 'https://qontoybecrqpbjzoajqf.supabase.co', 'publishableKey': 'sb_publishable_fixtureonly'}}
        self.headers = {'X-DataTrace-Token': 'fixture-engine-token', 'X-TV-Cloud-Access': 'fixture-cloud-token'}
        self.rpc = Mock()
        self.member = {'id': self.workspace, 'mode': 'shadow', 'role': 'owner', 'queue_scope': 'queue'}
        self.rpc.call.return_value = [self.member]
        self.rpc.snapshot.return_value = {'revision': 2, 'published_revision': 0, 'orders': [], 'mode': 'shadow'}
        self.mock_rpc = patch('shared_routes.SupabaseRpc', return_value=self.rpc)
        self.mock_rpc.start()
        self.addCleanup(self.mock_rpc.stop)

    def post(self, **fields):
        return self.client.post('/api/desktop/shared/action', json=dict(self.body, **fields), headers=self.headers)

    def test_local_auth_and_cloud_auth_are_both_required(self):
        self.assertEqual(self.client.post('/api/desktop/shared/action', json=self.body).status_code, 401)
        self.assertEqual(self.client.post('/api/desktop/shared/action', json=self.body,
            headers={'X-DataTrace-Token': 'fixture-engine-token'}).status_code, 401)
        self.rpc.call.assert_not_called()

    def test_workspace_access_and_mode_are_verified_on_server(self):
        self.rpc.call.return_value = []
        self.assertEqual(self.post().status_code, 403)
        self.rpc.call.return_value = [dict(self.member, mode='active')]
        self.assertEqual(self.post(action='worker').status_code, 409)
        self.rpc.snapshot.assert_not_called()

    def test_inspection_returns_only_summary_and_releases_gate(self):
        self.assertEqual(self.post().json['revision'], 2)
        self.assertEqual(self.post().status_code, 200)
        self.assertNotIn('fixture-cloud-token', self.post().get_data(as_text=True))

    def test_viewer_cannot_run_worker_or_submit_and_owner_can_process(self):
        self.rpc.call.return_value = [dict(self.member, role='viewer')]
        self.assertEqual(self.post(action='worker').status_code, 403)
        self.assertEqual(self.post(action='submit', preview_id=1).status_code, 403)
        self.rpc.call.return_value = [self.member]
        with patch('shared_routes.ShadowWorker') as worker, patch('shared_routes.OwnerWorkerRpc'):
            worker.return_value.step.return_value = {'state': 'processed', 'revision': 2}
            self.assertEqual(self.post(action='worker').json['worker']['state'], 'processed')
            worker.return_value.step.assert_called_once_with(self.workspace)
