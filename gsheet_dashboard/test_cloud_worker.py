from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from cloud_backend.worker import ShadowWorker, OfficeWorker
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


class OfficeWorkerTests(unittest.TestCase):
    def test_google_failures_retain_job_token_and_never_acknowledge(self):
        from gspread.exceptions import APIError
        from requests import Response, ConnectionError
        from google.auth.exceptions import RefreshError
        for status,kind in ((429,'retry'),(503,'retry'),(403,'review')):
            response=Response();response.status_code=status
            response._content=b'{"error":{"code":403,"message":"Sensitive upstream detail"}}'
            errors=[APIError(response)]
            if status==429:
                errors.extend((ConnectionError('Private connection details'),RefreshError('Private credential details')))
            for error in errors:
                with self.subTest(status=status,error=type(error).__name__),tempfile.TemporaryDirectory() as folder:
                    workspace=str(uuid.uuid4());rpc=Mock();tokens=[]
                    def claim_job(name,body):
                        self.assertEqual(name,'tv_claim_job');tokens.append(body['p_token'])
                        return {'mode':'active','spreadsheet':'qa','orders':[],
                            'job':{'workspace_id':workspace,'token':body['p_token'],'kind':'publish',
                                'revision':1,'started_at':'2026-10-07T12:00:00Z'}}
                    rpc.call.side_effect=claim_job
                    worker=OfficeWorker(rpc,folder,Mock(side_effect=error))
                    for _ in range(2):
                        with self.assertRaises(CloudError) as caught:worker.step(workspace)
                        expected='review' if isinstance(error,RefreshError) else 'retry' if isinstance(error,ConnectionError) else kind
                        self.assertEqual(caught.exception.kind,expected)
                        self.assertNotIn('Private',str(caught.exception));self.assertNotIn('Sensitive',str(caught.exception))
                    self.assertEqual(tokens[0],tokens[1]);self.assertEqual(rpc.call.call_count,2)

    def test_publication_is_verified_before_ack_and_lost_ack_reuses_job(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            workspace = str(uuid.uuid4())
            rpc = Mock()
            received = []
            claim_body = {'mode':'active','spreadsheet':'synthetic-workbook','orders':[],
                'job':{'workspace_id':workspace,'kind':'publish','revision':1,'started_at':'2026-10-06T12:00:00Z'}}
            def call(name, body):
                received.append(name)
                if name == 'tv_claim_job':
                    return dict(claim_body, job=dict(claim_body['job'], token=body['p_token']))
                raise CloudError('Acknowledgment response lost', 'retry')
            rpc.call.side_effect = call
            worker = OfficeWorker(rpc, folder, lambda _: object())
            with patch('cloud_backend.publication.SheetsPublisher') as publisher:
                publisher.return_value.publish.side_effect = CloudError('Cannot verify Sheets', 'retry')
                with self.assertRaises(CloudError):
                    worker.step(workspace)
                self.assertEqual(received, ['tv_claim_job'])
                publisher.return_value.publish.side_effect = None
                with self.assertRaises(CloudError):
                    worker.step(workspace)
                self.assertEqual(received[-1], 'tv_ack_publication')
                publisher.reset_mock()
                rpc.call.side_effect = None
                rpc.call.return_value = {'completed':True,'result':{'state':'published','revision':1}}
                recovered = OfficeWorker(rpc, folder, lambda _: object())
                self.assertEqual(recovered.step(workspace), {'state':'published','revision':1})
                publisher.assert_not_called()
