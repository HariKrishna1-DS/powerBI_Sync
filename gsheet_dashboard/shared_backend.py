"""Authenticated Supabase RPC transport and durable, ordered desktop uploads.

No admin key or refresh token belongs in this module. The desktop supplies a
short-lived access token; the central worker uses a separate server client.
"""
from datetime import datetime
import hashlib
import json
import math
import re
import time
import uuid

import requests


class CloudError(RuntimeError):
    def __init__(self, message, kind='review', retry_after=30):
        self.kind, self.retry_after = kind, retry_after
        super().__init__(message)


def verified_capture(payload):
    rows, metadata = payload.get('rows'), payload.get('metadata')
    return (isinstance(rows, list) and bool(rows) and isinstance(metadata, dict)
        and metadata.get('kind') == 'portal' and metadata.get('complete') is True
        and type(metadata.get('expected_rows')) is int and metadata['expected_rows'] == len(rows)
        and type(metadata.get('actual_rows')) is int and metadata['actual_rows'] == len(rows))


class SupabaseRpc:
    def __init__(self, url, publishable_key, access_token, session=None):
        if not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co', url):
            raise ValueError('Use the HTTPS Supabase project URL.')
        if not isinstance(publishable_key, str) or not publishable_key.startswith('sb_publishable_'):
            raise ValueError('Use a Supabase publishable key, never a secret or service-role key.')
        self.url, self.api_key, self.access_token = url, publishable_key, access_token
        self.session = session or requests.Session()

    def call(self, name, body):
        if not re.fullmatch(r'tv_[a-z_]+', name):
            raise ValueError('Invalid backend operation.')
        token = self.access_token()
        if not token:
            raise CloudError('Sign in to the shared workspace to resume uploads.', 'auth')
        try:
            response = self.session.post(self.url + '/rest/v1/rpc/' + name, json=body,
                headers={'apikey': self.api_key, 'Authorization': 'Bearer ' + token}, timeout=(5, 30), allow_redirects=False)
        except requests.RequestException as exc:
            raise CloudError('Shared backend is unreachable. Saved operations will retry.', 'retry') from exc
        if response.status_code == 401:
            raise CloudError('Your session expired. Sign in again; saved operations are retained.', 'auth')
        if response.status_code == 429 or response.status_code >= 500:
            try:
                delay = min(900, max(30, int(response.headers.get('Retry-After', '30'))))
            except ValueError:
                delay = 30
            raise CloudError('Shared backend is busy. Saved operations will retry.', 'retry', delay)
        if response.status_code == 403:
            raise CloudError('You do not have permission for this workspace operation.', 'auth')
        if not 200 <= response.status_code < 300:
            try:
                code = response.json().get('code')
            except (ValueError, AttributeError):
                code = None
            if code == '40001':
                raise CloudError('Shared data changed. Refresh before retrying this operation.', 'conflict')
            raise CloudError('The backend rejected this operation. Review its data or the latest order version.')
        try:
            return response.json()
        except ValueError as exc:
            raise CloudError('The backend response could not be verified. Retry uses the same operation ID.', 'retry') from exc

    def snapshot(self, workspace):
        for _ in range(3):
            try:
                return self._snapshot(workspace)
            except CloudError as exc:
                if exc.kind != 'conflict':
                    raise
        raise CloudError('Shared orders are changing. The last verified report is retained; try refreshing shortly.', 'retry')

    def _snapshot(self, workspace):
        # Each page checks the same revision. Never blend two versions of orders.
        rows, cursor, revision = [], '', None
        while True:
            page = self.call('tv_snapshot', {'p_workspace': workspace, 'p_revision': revision, 'p_after': cursor})
            if not isinstance(page, dict) or not isinstance(page.get('orders'), list) or type(page.get('revision')) is not int:
                raise CloudError('Invalid shared report response.', 'retry')
            if revision is not None and page['revision'] != revision:
                raise CloudError('Shared orders changed during refresh. Refresh again.', 'conflict')
            revision = page['revision']
            if any(not isinstance(row, dict) or not isinstance(row.get('data'), dict)
                   or not isinstance(row.get('order_key'), str) or not row['order_key']
                   or type(row.get('version')) is not int or row['version'] < 1 for row in page['orders']):
                raise CloudError('Invalid shared order response.', 'retry')
            identities = [row['order_key'] for row in page['orders']]
            if len(identities) > 500 or identities != sorted(set(identities)) or any(key <= cursor for key in identities):
                raise CloudError('Shared report order could not be verified.', 'retry')
            rows.extend(page['orders'])
            if len(rows) > 100000:
                raise CloudError('Shared report exceeds the supported local cache size.')
            following = page.get('next_cursor')
            if not following:
                return dict(page, orders=rows)
            if not isinstance(following, str) or not identities or following != identities[-1] or following <= cursor:
                raise CloudError('Shared report pagination could not be verified.')
            cursor = following


class CloudOutbox:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS cloud_outbox (
                workspace TEXT NOT NULL, preview_id INTEGER NOT NULL, operation TEXT NOT NULL UNIQUE,
                digest TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
                receipt TEXT, error TEXT, PRIMARY KEY(workspace,preview_id))''')

    @staticmethod
    def validate_database(db):
        for workspace, operation, digest, raw, state, attempts, retry_at, receipt in db.execute(
                'SELECT workspace,operation,digest,body,state,attempts,retry_at,receipt FROM cloud_outbox'):
            try:
                uuid.UUID(workspace)
                uuid.UUID(operation)
                body = json.loads(raw)
                if (set(body) != {'p_workspace', 'p_captured_at', 'p_payload'} or body['p_workspace'] != workspace
                        or hashlib.sha256(raw.encode()).hexdigest() != digest or not verified_capture(body['p_payload'])
                        or state not in ('pending', 'auth', 'review', 'conflict', 'accepted')
                        or type(attempts) is not int or attempts < 0 or not math.isfinite(retry_at) or retry_at < 0):
                    raise ValueError('Invalid outbox record')
                if state == 'accepted':
                    saved = json.loads(receipt)
                    uuid.UUID(saved['capture_id'])
                    if saved['state'] != 'accepted' or type(saved['sequence']) is not int or saved['sequence'] < 1:
                        raise ValueError('Invalid upload receipt')
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise ValueError('Backup contains invalid shared upload data. The current workspace was retained.') from exc

    def enqueue(self, workspace, preview, queue_scope):
        uuid.UUID(workspace)
        if not verified_capture(preview):
            raise ValueError('Only a verified complete capture can enter shared processing.')
        if not preview['rows']:
            raise ValueError('Empty captures require review before shared processing.')
        captured = datetime.fromisoformat(preview['created'].replace('Z', '+00:00'))
        if captured.tzinfo is None:
            raise ValueError('The capture timestamp must include its timezone.')
        payload = {'columns': preview['columns'], 'rows': preview['rows'],
                   'metadata': preview['metadata'], 'queue_scope': queue_scope}
        body = {'p_workspace': workspace, 'p_captured_at': preview['created'], 'p_payload': payload}
        encoded = json.dumps(body, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT operation,digest FROM cloud_outbox WHERE workspace=? AND preview_id=?', (workspace, preview['id'])).fetchone()
            if existing:
                if existing[1] != digest:
                    raise ValueError('A queued capture changed. Preserve both copies and review before sending.')
                return existing[0]
            operation = str(uuid.uuid4())
            db.execute('INSERT INTO cloud_outbox(workspace,preview_id,operation,digest,body) VALUES(?,?,?,?,?)',
                       (workspace, preview['id'], operation, digest, encoded))
            return operation

    def drain_one(self, workspace, rpc, now=None):
        now = time.time() if now is None else now
        with self.store.connect() as db:
            row = db.execute("SELECT preview_id,operation,body,state,attempts,retry_at,digest FROM cloud_outbox WHERE workspace=? AND state!='accepted' ORDER BY preview_id LIMIT 1", (workspace,)).fetchone()
        if not row or row[3] != 'pending' or row[5] > now:
            return False
        number, operation, raw, _, attempts, _, digest = row
        try:
            if hashlib.sha256(raw.encode()).hexdigest() != digest:
                raise CloudError('Saved upload failed its integrity check. Restore or review this capture before retrying.')
            receipt = rpc.call('tv_submit_capture', dict(json.loads(raw), p_operation=operation))
            if not isinstance(receipt, dict) or not isinstance(receipt.get('capture_id'), str) or type(receipt.get('sequence')) is not int or receipt['sequence'] < 1 or receipt.get('state') != 'accepted':
                raise CloudError('Capture receipt could not be verified. Saved operation will retry.', 'retry')
            uuid.UUID(receipt['capture_id'])
        except CloudError as exc:
            state = 'pending' if exc.kind == 'retry' else exc.kind
            delay = max(exc.retry_after, min(900, 30 * 2 ** min(attempts, 5)))
            with self.store.connect() as db:
                # Another sender may already have verified this same receipt.
                db.execute("UPDATE cloud_outbox SET state=?,attempts=attempts+1,retry_at=?,error=? WHERE workspace=? AND preview_id=? AND state!='accepted'",
                           (state, now + delay, str(exc), workspace, number))
            return False
        except ValueError:
            with self.store.connect() as db:
                db.execute("UPDATE cloud_outbox SET retry_at=?,error=? WHERE workspace=? AND preview_id=? AND state!='accepted'",
                           (now + 30, 'Invalid capture receipt; retrying the same operation.', workspace, number))
            return False
        with self.store.connect() as db:
            db.execute("UPDATE cloud_outbox SET state='accepted',receipt=?,error=NULL WHERE workspace=? AND preview_id=?",
                       (json.dumps(receipt), workspace, number))
        # Acceptance is not proof of Sheets publication; do not mark legacy sync_jobs synced.
        return True

    def resume_auth(self, workspace):
        with self.store.connect() as db:
            db.execute("UPDATE cloud_outbox SET state='pending',retry_at=0,error=NULL WHERE workspace=? AND state='auth'", (workspace,))

    def status(self, workspace):
        with self.store.connect() as db:
            return [{'preview_id': r[0], 'operation': r[1], 'state': r[2], 'error': r[3],
                     'receipt': json.loads(r[4]) if r[4] else None} for r in db.execute(
                'SELECT preview_id,operation,state,error,receipt FROM cloud_outbox WHERE workspace=? ORDER BY preview_id', (workspace,))]
