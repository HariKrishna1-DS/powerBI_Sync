"""Durable, bounded operation metadata. No order content or credentials are stored."""
from datetime import datetime, timezone


def failure_kind(error):
    value = str(error or '').lower()
    if not value:
        return None
    if any(word in value for word in ('credential', 'permission', 'unauthorized', 'invalid_grant', 'sign in', 'login')):
        return 'authentication'
    if any(word in value for word in ('429', 'quota', 'rate limit')):
        return 'rate_limit'
    if any(word in value for word in ('timeout', 'timed out', 'network', 'connection', 'unreachable')):
        return 'connection'
    if any(word in value for word in ('pagination', 'queue table', 'results panel', 'no queue records')):
        return 'portal_results'
    if any(word in value for word in ('conflict', 'mismatch', 'duplicate', 'invalid', 'validation')):
        return 'validation'
    return 'operation_failed'


class OperationJournal:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS operation_history ('
                       'id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, status TEXT NOT NULL, '
                       'started TEXT NOT NULL, finished TEXT, preview_id INTEGER, error_code TEXT)')
            db.execute("UPDATE operation_history SET status='interrupted', finished=?, error_code='interrupted' WHERE status='running'",
                       (self.now(),))

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def begin(self, kind):
        if kind not in ('capture', 'sync', 'scheduled_capture'):
            raise ValueError('Unsupported operation.')
        with self.store.connect() as db:
            job_id = db.execute('INSERT INTO operation_history(kind,status,started) VALUES(?,?,?)',
                                (kind, 'running', self.now())).lastrowid
            db.execute('DELETE FROM operation_history WHERE status != ? AND id NOT IN '
                       '(SELECT id FROM operation_history ORDER BY id DESC LIMIT 200)', ('running',))
        return job_id

    def finish(self, job_id, result):
        result = result or {}
        code = failure_kind(result.get('error'))
        with self.store.connect() as db:
            db.execute('UPDATE operation_history SET status=?, finished=?, preview_id=?, error_code=? WHERE id=?',
                       ('cancelled' if result.get('cancelled') else 'failed' if code else 'completed', self.now(), result.get('preview_id'), code, job_id))

    def list(self):
        with self.store.connect() as db:
            cursor = db.execute('SELECT id,kind,status,started,finished,preview_id,error_code '
                                'FROM operation_history ORDER BY id DESC LIMIT 200')
            names = [item[0] for item in cursor.description]
            return [dict(zip(names, row)) for row in cursor]

    def scheduled_summary(self):
        with self.store.connect() as db:
            latest = db.execute("SELECT started,status,finished,error_code FROM operation_history WHERE kind='scheduled_capture' ORDER BY id DESC LIMIT 1").fetchone()
            success = db.execute("SELECT finished FROM operation_history WHERE kind='scheduled_capture' AND status='completed' ORDER BY id DESC LIMIT 1").fetchone()
        return {'last_attempt': latest[0] if latest else None, 'last_status': latest[1] if latest else None,
                'last_finished': latest[2] if latest else None, 'last_error_code': latest[3] if latest else None,
                'last_success': success[0] if success else None}
