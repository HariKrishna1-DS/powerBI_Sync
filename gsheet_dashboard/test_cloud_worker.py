from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from cloud_backend.worker import ShadowWorker
from shared_backend import CloudError
from test_shared_backend import claim, order


class ShadowWorkerTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = str(uuid.uuid4())
        self.rpc = Mock()
        self.worker = ShadowWorker(self.rpc, self.folder.name)

    def capture_claim(self, body):
        return dict(claim([], [order()]), mode='shadow', job={'token': body['p_token'],
            'workspace_id': self.workspace, 'kind': 'capture'})

    def test_lost_commit_reply_recovers_receipt_without_processing_again(self):
        accepted = {'state': 'processed', 'revision': 1}
        sent_token = []

        def first(name, body):
            if name == 'tv_claim_job':
                sent_token.append(body['p_token'])
                return self.capture_claim(body)
            raise CloudError('Reply lost after commit', 'retry')

        self.rpc.call.side_effect = first
        with self.assertRaises(CloudError):
            self.worker.step(self.workspace)
        recovered = ShadowWorker(self.rpc, self.folder.name)
        self.rpc.call.reset_mock()
        self.rpc.call.side_effect = None
        self.rpc.call.return_value = {'completed': True, 'result': accepted}
        self.assertEqual(recovered.step(self.workspace), accepted)
        self.rpc.call.assert_called_once_with('tv_claim_job', {'p_workspace': self.workspace, 'p_token': sent_token[0]})

    def test_worker_local_lock_prevents_parallel_use_of_same_job_token(self):
        db = sqlite3.connect(Path(self.folder.name) / 'worker-lock.sqlite')
        self.addCleanup(db.close)
        db.execute('BEGIN IMMEDIATE')
        self.assertEqual(self.worker.step(self.workspace), {'state': 'busy'})
        self.rpc.call.assert_not_called()
        db.rollback()

    def test_active_publishing_cannot_run_from_preparation_worker(self):
        self.rpc.call.side_effect = lambda _, body: dict(self.capture_claim(body), mode='active')
        with self.assertRaisesRegex(CloudError, 'shadow'):
            self.worker.step(self.workspace)
        self.assertEqual(self.rpc.call.call_count, 1)

    def test_malformed_commit_receipt_keeps_original_job_token(self):
        seen = []

        def reply(name, body):
            if name == 'tv_claim_job':
                seen.append(body['p_token'])
                return self.capture_claim(body)
            return {'state': 'processed', 'revision': 'not-a-number'}

        self.rpc.call.side_effect = reply
        for _ in range(2):
            with self.assertRaises(CloudError):
                self.worker.step(self.workspace)
        self.assertEqual(seen[0], seen[1])
