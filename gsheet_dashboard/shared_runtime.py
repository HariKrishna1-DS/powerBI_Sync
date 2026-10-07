"""Selected shared-workspace runtime. Tokens are memory-only and supplied by Electron."""
from datetime import datetime, timezone
import json
import os
import threading
import time
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
        self.worker_error = None
        self.worker_retry_at = 0
        self.worker_attempts = 0
        self.reporting = None
        self.open_book = open_book
        if not self.enabled:
            return
        uuid.UUID(config['id'])
        if config['role'] not in ('owner','editor','viewer') or not config.get('queue_scope'):
            raise ValueError('The selected shared workspace is invalid.')
        self.rpc = SupabaseRpc(config['url'], config['publishableKey'], lambda: self.access)
        self.outbox = CloudOutbox(store)
        from shared_requests import SharedRequests
        self.requests = SharedRequests(store)
        self.cache = ProductionCache(store.root.parent / 'shared-cache.json', config['url']+'|'+config['id']+'|'+config.get('userId',''))

    @property
    def can_capture(self):
        return not self.enabled or self.selection.get('role') in ('owner','editor')

    def authorize_capture(self):
        if not self.can_capture:
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
            worker_completed = False
            try:
                status = self.rpc.call('tv_workspace_status', {'p_workspace':workspace})
                if status['mode']!='active' or status['queue_scope']!=self.selection['queue_scope']:
                    raise CloudError('Workspace configuration changed. Reconnect before processing.', 'conflict')
                self.outbox.drain_one(workspace, self.rpc)
                if self.selection.get('officeWorker'):
                    worker_id = self.selection['worker']
                    if status.get('worker')!=worker_id or not self.open_book:
                        raise CloudError('This PC is not the configured office publisher.', 'conflict')
                    if time.monotonic() >= self.worker_retry_at:
                        rpc = OfficeWorkerRpc(self.selection['url'], self.selection['publishableKey'], lambda:self.access, worker_id)
                        try:
                            self.worker_result = OfficeWorker(rpc, self.store.root.parent / 'shared-worker' / workspace, self.open_book).step(workspace)
                            worker_completed = self.worker_result.get('state') in ('published','processed')
                            self.worker_error, self.worker_retry_at, self.worker_attempts = None, 0, 0
                        except CloudError as error:
                            self.worker_error = str(error)
                            delay = max(error.retry_after, min(900, 30 * 2 ** min(self.worker_attempts,5)))
                            self.worker_attempts += 1
                            self.worker_retry_at = time.monotonic() + delay
                            self.worker_result = {'state':'pending' if error.kind=='retry' else error.kind,
                                'error':str(error),'retry_after':delay}
                unresolved = set(self.store.unsynced_ids())
                accepted = [row for row in self.outbox.status(workspace) if row['state']=='accepted' and row['preview_id'] in unresolved]
                for row in accepted[:20]:
                    receipt = self.rpc.call('tv_operation', {'p_workspace':workspace,'p_operation':row['operation']})
                    if receipt.get('published') is True and receipt.get('processing_state')=='processed':
                        self.store.mark_synced(row['preview_id'], {'shared_workspace':workspace,
                            'revision':receipt['processed_revision'],'sequence':row['receipt']['sequence']})
                self.error = self.worker_error
                if worker_completed:
                    self.cache.invalidate()
                return self.status()
            except CloudError as error:
                self.error = str(error)
                return self.status()

    def snapshot(self, **kwargs):
        def load():
            for _ in range(3):
                try:
                    saved = self.rpc.snapshot(self.selection['id'])
                    context = self.report_state(saved['revision'])
                    _, result = projection(saved['orders'], datetime.now(timezone.utc).isoformat(), context)
                    result.update(offline=False,shared_revision=saved['revision'],published_revision=context['published_revision'])
                    result['report_preferences'] = self.report_preferences(context)
                    return result
                except CloudError as error:
                    if error.kind!='conflict':
                        raise
            raise CloudError('Reports changed during refresh. The last verified copy was retained.', 'retry')
        return self.cache.get(load, **kwargs)

    def report_state(self, revision=None):
        result = self.rpc.call('tv_reporting_state', {'p_workspace':self.selection['id'],'p_revision':revision})
        if (not isinstance(result,dict) or not isinstance(result.get('preferences'),dict)
                or result['preferences'].get('source') not in ('tracker','import')
                or type(result.get('revision')) is not int or type(result.get('published_revision')) is not int
                or not isinstance(result.get('targets'),dict) or not isinstance(result.get('imports'),list)):
            raise CloudError('Shared report settings could not be verified.', 'retry')
        self.reporting = result
        return result

    def cached_preferences(self):
        if self.reporting:
            return self.report_preferences(self.reporting)
        with self.cache.lock:
            if self.cache.value and isinstance(self.cache.value.get('report_preferences'),dict):
                return dict(self.cache.value['report_preferences'])
        return {'source':'tracker','import_id':None,'revision':None,'shared':True,
            'default_capacity':None,'default_extended':None,'publish_status':'offline',
            'publish_error':'Connect to the shared workspace to load report settings.'}

    def report_preferences(self, context):
        return dict(context['preferences'], revision=context['revision'], shared=True,
            can_edit=self.selection.get('role') in ('owner','editor'),
            publish_status='published' if context['revision']<=context['published_revision'] else 'pending',
            publish_error='', published_revision=context['published_revision'])

    def report_change(self, action, change, revision):
        self.authorize_capture()
        if type(revision) is not int or revision<0:
            raise ValueError('Refresh shared report settings before saving.')
        receipt = self.requests.perform(self.rpc,'tv_change_reporting', {
            'p_workspace':self.selection['id'],'p_revision':revision,'p_action':action,'p_change':change})
        if type(receipt.get('revision')) is not int or receipt['revision']!=revision+1 or receipt.get('state')!='pending':
            raise CloudError('The shared report change could not be verified. Retry the same save.', 'retry')
        self.cache.invalidate()
        self.reporting = None
        return receipt

    def status(self):
        return {'enabled':self.enabled,'workspace':self.selection.get('id'),'can_capture':self.can_capture,
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
    try:
        account = json.loads(os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON', '{}'))
    except ValueError as error:
        raise CloudError('Import a valid Google service-account JSON on the office worker.') from error
    if not isinstance(account,dict):
        raise CloudError('Import a valid Google service-account JSON on the office worker.')
    if account.get('token_uri') != 'https://oauth2.googleapis.com/token':
        raise CloudError('Import the office worker’s valid Google service-account JSON in Settings.')
    try:
        credentials = Credentials.from_service_account_info(account, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    except (ValueError, KeyError) as error:
        raise CloudError('Import a valid Google service-account JSON on the office worker.') from error
    client = gspread.authorize(credentials, http_client=QuotaHTTPClient)
    client.set_timeout((10,90))
    return client.open_by_key(identity)
