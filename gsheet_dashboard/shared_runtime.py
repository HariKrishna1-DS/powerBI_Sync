"""Selected shared-workspace runtime. Tokens are memory-only and supplied by Electron."""
from datetime import datetime, timezone
import json
import os
import threading
import uuid

from shared_backend import CloudError, CloudOutbox, SupabaseRpc
from production_cache import ProductionCache
from cloud_backend.publication import projection
from cloud_backend.worker import OfficeWorker
from cloud_backend.transport import OfficeWorkerRpc


class SharedRuntime:
    def __init__(self, store, config=None, open_book=None):
        self.store, self.selection = store, config or {}
        self.enabled = bool(config)
        self.lock = threading.RLock()
        self.access = ''
        self.error = None
        self.worker_result = None
        self.open_book = open_book
        if not self.enabled:
            return
        uuid.UUID(config['id'])
        if config['role'] not in ('owner','editor','viewer') or not config.get('queue_scope'):
            raise ValueError('The selected shared workspace is invalid.')
        self.rpc = SupabaseRpc(config['url'], config['publishableKey'], lambda: self.access)
        self.outbox = CloudOutbox(store)
        self.cache = ProductionCache(store.root.parent / 'shared-cache.json', config['url']+'|'+config['id'])

    def authorize_capture(self):
        if self.selection.get('role') not in ('owner','editor'):
            raise ValueError('This shared workspace account has read-only access.')

    def update_token(self, token):
        if not isinstance(token, str) or len(token)>16384:
            raise ValueError('Invalid workspace session.')
        self.access = token
        if token:
            self.outbox.resume_auth(self.selection['id'])

    def submit(self, preview):
        self.authorize_capture()
        workspace = self.selection['id']
        self.outbox.enqueue(workspace, preview, self.selection['queue_scope'])
        self.outbox.drain_one(workspace, self.rpc)
        saved = next(row for row in self.outbox.status(workspace) if row['preview_id']==preview['id'])
        return {'action':'sync','preview_id':preview['id'],'preview_name':preview['name'],
            'cloud_state':saved['state'],'google_sheet':'pending','error':saved['error'],
            'stage':'Accepted by shared workspace' if saved['state']=='accepted' else 'Saved locally; upload pending'}

    def tick(self):
        with self.lock:
            workspace = self.selection['id']
            try:
                status = self.rpc.call('tv_workspace_status', {'p_workspace':workspace})
                if status['mode']!='active' or status['queue_scope']!=self.selection['queue_scope']:
                    raise CloudError('Workspace configuration changed. Reconnect before processing.', 'conflict')
                self.outbox.drain_one(workspace, self.rpc)
                if self.selection.get('officeWorker'):
                    worker_id = self.selection['worker']
                    if status.get('worker')!=worker_id or not self.open_book:
                        raise CloudError('This PC is not the configured office publisher.', 'conflict')
                    rpc = OfficeWorkerRpc(self.selection['url'], self.selection['publishableKey'], lambda:self.access, worker_id)
                    self.worker_result = OfficeWorker(rpc, self.store.root.parent / 'shared-worker' / workspace, self.open_book).step(workspace)
                unresolved = set(self.store.unsynced_ids())
                accepted = [row for row in self.outbox.status(workspace) if row['state']=='accepted' and row['preview_id'] in unresolved]
                for row in accepted[:20]:
                    receipt = self.rpc.call('tv_operation', {'p_workspace':workspace,'p_operation':row['operation']})
                    if receipt.get('published') is True and receipt.get('processing_state')=='processed':
                        self.store.mark_synced(row['preview_id'], {'shared_workspace':workspace,
                            'revision':receipt['processed_revision'],'sequence':row['receipt']['sequence']})
                self.error = None
                if self.worker_result and self.worker_result.get('state') in ('published','processed'):
                    self.cache.invalidate()
                return self.status()
            except CloudError as error:
                self.error = str(error)
                return self.status()

    def snapshot(self, **kwargs):
        def load():
            saved = self.rpc.snapshot(self.selection['id'])
            _, result = projection(saved['orders'], datetime.now(timezone.utc).isoformat())
            result.update(offline=False,shared_revision=saved['revision'],published_revision=saved['published_revision'])
            return result
        return self.cache.get(load, **kwargs)

    def status(self):
        return {'enabled':self.enabled,'workspace':self.selection.get('id'),
            'error':self.error,'worker':self.worker_result,'office_worker':bool(self.selection.get('officeWorker'))}


def environment_selection(value):
    if not value:
        return None
    try:
        result = json.loads(value)
        if not isinstance(result, dict):
            raise ValueError('Expected selection')
        return result
    except (ValueError, TypeError) as error:
        raise ValueError('The shared workspace selection could not be loaded.') from error


def open_worker_book(identity):
    import gspread
    from google.oauth2.service_account import Credentials
    from sheets_transport import QuotaHTTPClient
    account = json.loads(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '{}'))
    if account.get('token_uri') != 'https://oauth2.googleapis.com/token':
        raise ValueError('Import the office worker’s valid Google service-account JSON in Settings.')
    credentials = Credentials.from_service_account_info(account, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    client = gspread.authorize(credentials, http_client=QuotaHTTPClient)
    client.set_timeout((10,90))
    return client.open_by_key(identity)
