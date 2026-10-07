"""Persist operation identity before a shared write; ambiguous replies reuse it."""
import hashlib
import json
import uuid

from shared_backend import CloudError

ALLOWED = {'tv_save_report_import','tv_change_reporting','tv_correct_sla','tv_apply_monthly'}


class SharedRequests:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS cloud_requests (
                workspace TEXT NOT NULL, digest TEXT NOT NULL, operation TEXT NOT NULL UNIQUE,
                rpc TEXT NOT NULL, body TEXT NOT NULL, receipt TEXT,
                PRIMARY KEY(workspace,digest))''')

    @staticmethod
    def validate_database(db):
        for workspace, fingerprint, operation, name, raw, receipt in db.execute('SELECT * FROM cloud_requests'):
            try:
                uuid.UUID(workspace); uuid.UUID(operation)
                body = json.loads(raw)
                if name not in ALLOWED or not isinstance(body,dict) or body.get('p_workspace')!=workspace or 'p_operation' in body:
                    raise ValueError('Invalid request')
                if hashlib.sha256((name+'|'+raw).encode()).hexdigest()!=fingerprint:
                    raise ValueError('Invalid request hash')
                if receipt is not None and not isinstance(json.loads(receipt),dict):
                    raise ValueError('Invalid receipt')
            except (ValueError,TypeError,KeyError) as error:
                raise ValueError('Backup contains invalid shared requests. The current workspace was retained.') from error

    def perform(self, rpc, name, body):
        if name not in ALLOWED or 'p_operation' in body:
            raise ValueError('Invalid shared request')
        workspace = str(uuid.UUID(body['p_workspace']))
        raw = json.dumps(body, sort_keys=True, separators=(',',':'), ensure_ascii=False, allow_nan=False)
        fingerprint = hashlib.sha256((name+'|'+raw).encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('INSERT OR IGNORE INTO cloud_requests VALUES(?,?,?,?,?,NULL)',
                (workspace,fingerprint,str(uuid.uuid4()),name,raw))
            operation, previous = db.execute('SELECT operation,receipt FROM cloud_requests WHERE workspace=? AND digest=?',
                (workspace,fingerprint)).fetchone()
        if previous is not None:
            return json.loads(previous)
        receipt = rpc.call(name, dict(body,p_operation=operation))
        if not isinstance(receipt,dict):
            raise CloudError('The shared save could not be verified. Retry retains the same operation.', 'retry')
        with self.store.connect() as db:
            db.execute('UPDATE cloud_requests SET receipt=? WHERE workspace=? AND digest=?',
                (json.dumps(receipt,allow_nan=False),workspace,fingerprint))
        return receipt

    def pending_sla(self, workspace, selections, status):
        def normalized(items):
            return sorted((item['order_key'],item['completion_date'],item['expected_status']) for item in items)
        with self.store.connect() as db:
            records = db.execute("SELECT body FROM cloud_requests WHERE workspace=? AND rpc='tv_correct_sla' AND receipt IS NULL",(workspace,)).fetchall()
        matches = [json.loads(raw) for (raw,) in records if json.loads(raw).get('p_status')==status
            and normalized(json.loads(raw)['p_orders'])==normalized(selections)]
        if len(matches)>1:
            raise CloudError('Multiple unresolved SLA saves require review before retrying.', 'conflict')
        return matches[0] if matches else None
