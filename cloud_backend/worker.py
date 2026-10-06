"""Crash-safe capture processor, initially restricted to shadow workspaces.

The injected RPC transport must be a server-only credential boundary. This
module intentionally has no desktop credentials or direct Google Sheets writes.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import uuid

from cloud_backend.processor import process_capture
from shared_backend import CloudError


class ShadowWorker:
    def __init__(self, rpc, state_directory):
        self.rpc = rpc
        self.root = Path(state_directory)
        self.root.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS job_tokens(workspace TEXT PRIMARY KEY, token TEXT NOT NULL)')
        with closing(sqlite3.connect(self.root / 'worker-lock.sqlite')) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS mutex(id INTEGER PRIMARY KEY)')

    def connect(self):
        db = sqlite3.connect(self.root / 'worker-state.sqlite', timeout=5)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def _token(self, workspace):
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR IGNORE INTO job_tokens VALUES(?,?)', (workspace, str(uuid.uuid4())))
            return db.execute('SELECT token FROM job_tokens WHERE workspace=?', (workspace,)).fetchone()[0]

    def _clear(self, workspace, token):
        with closing(self.connect()) as db, db:
            db.execute('DELETE FROM job_tokens WHERE workspace=? AND token=?', (workspace, token))

    def step(self, workspace):
        uuid.UUID(workspace)
        # A local process lock covers network/processing but token persistence is
        # a separate committed database. A crash releases the lock, not the token.
        with closing(sqlite3.connect(self.root / 'worker-lock.sqlite', timeout=0)) as lock, lock:
            try:
                lock.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                if 'locked' not in str(exc).lower():
                    raise
                return {'state': 'busy'}
            token = self._token(workspace)
            claim = self.rpc.call('tv_claim_job', {'p_workspace': workspace, 'p_token': token})
            if claim is None or (isinstance(claim, dict) and claim.get('busy') is True):
                self._clear(workspace, token)
                return {'state': 'idle' if claim is None else 'busy'}
            if not isinstance(claim, dict):
                raise CloudError('The worker claim response could not be verified.', 'retry')
            if claim.get('completed') is True:
                receipt = self._receipt(claim.get('result'))
                self._clear(workspace, token)
                return receipt
            job = claim.get('job', {})
            if job.get('token') != token or job.get('workspace_id') != workspace:
                raise CloudError('The worker claim belongs to another job.')
            if claim.get('mode') != 'shadow' or job.get('kind') != 'capture':
                raise CloudError('This preparation worker only processes shadow captures. Active publishing needs the verified publisher.')
            rows, report, review = process_capture(claim)
            receipt = self._receipt(self.rpc.call('tv_commit_capture', {'p_workspace': workspace,
                'p_token': token, 'p_rows': rows, 'p_report': report, 'p_review': review}))
            self._clear(workspace, token)
            return receipt

    @staticmethod
    def _receipt(value):
        if not isinstance(value, dict) or value.get('state') not in ('processed', 'review') or type(value.get('revision')) is not int or value['revision'] < 0:
            raise CloudError('Worker completion could not be verified. The same job will be reconciled on retry.', 'retry')
        return value
