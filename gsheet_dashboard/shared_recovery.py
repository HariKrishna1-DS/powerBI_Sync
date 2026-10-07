"""Credential-free recovery material for central migration and worker jobs.

Callers encrypt the entire portable container. Local migration snapshots are
re-protected with the destination Windows account on restore. Existing job
ownership is never replaced by an older backup.
"""
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

from backup_protection import protect, unprotect

UUID = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
MIGRATION = re.compile(rf'^migration-snapshots/({UUID})\.tvmigration$')
WORKER = re.compile(rf'^shared-worker/({UUID})/worker-state\.sqlite$')
MAX_BYTES=256*1024*1024-65536


def recognized(name):
    return bool(MIGRATION.fullmatch(name) or WORKER.fullmatch(name))


def worker_tokens(raw):
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'state.sqlite'
        path.write_bytes(raw)
        try:
            with closing(sqlite3.connect(path)) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('Shared worker recovery database is damaged.')
                schema=db.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
                if schema!=[('table','job_tokens')]:
                    raise ValueError('Unsupported shared worker recovery schema.')
                rows=db.execute('SELECT workspace,token FROM job_tokens ORDER BY workspace').fetchall()
                if len(rows)>1000:
                    raise ValueError('Too many shared worker recovery tokens.')
                for workspace,token in rows:
                    uuid.UUID(workspace);uuid.UUID(token)
                return rows
        except sqlite3.DatabaseError as error:
            raise ValueError('Shared worker recovery database is invalid.') from error


def validate(name,raw):
    if match:=MIGRATION.fullmatch(name):
        from cloud_backend.publication import digest
        try:
            plan=json.loads(raw)
            if (plan['id']!=match[1] or plan['format']!='tv-tracker-migration-1'
                    or digest(plan['tables'])!=plan['digest'] or not isinstance(plan['rows'],list)
                    or type(plan['next_sequence']) is not int or plan['next_sequence']<1):
                raise ValueError('Migration recovery integrity check failed.')
            for field in ('id','workspace','seed_operation','activation_operation'):
                uuid.UUID(plan[field])
            if plan.get('worker'):
                uuid.UUID(plan['worker'])
        except (KeyError,TypeError,json.JSONDecodeError) as error:
            raise ValueError('Migration recovery snapshot is invalid.') from error
    elif match:=WORKER.fullmatch(name):
        if any(workspace!=match[1] for workspace,_ in worker_tokens(raw)):
            raise ValueError('Shared worker recovery belongs to a different workspace.')
    else:
        raise ValueError('Unexpected shared recovery file.')


def collect(root):
    root=Path(root)
    payloads={}
    for folder in ('migration-snapshots','shared-worker'):
        if (root/folder).is_symlink():
            raise ValueError('Shared recovery directory cannot be a symbolic link.')
    def retain(name,raw):
        if len(payloads)>=1000 or sum(len(value) for value in payloads.values())+len(raw)>MAX_BYTES:
            raise ValueError('Shared recovery material exceeds the supported backup size.')
        payloads[name]=raw
    for path in (root/'migration-snapshots').glob('*.tvmigration'):
        name='migration-snapshots/'+path.name
        if not recognized(name) or path.is_symlink():
            raise ValueError('Invalid local migration recovery path.')
        if path.stat().st_size>101_000_000:
            raise ValueError('Migration recovery snapshot exceeds the supported size.')
        raw=unprotect(path.read_bytes())
        validate(name,raw)
        retain(name,raw)
    for path in (root/'shared-worker').glob('*/worker-state.sqlite'):
        name=f'shared-worker/{path.parent.name}/worker-state.sqlite'
        if not recognized(name) or path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Invalid local shared worker recovery path.')
        if path.stat().st_size>101_000_000:
            raise ValueError('Shared worker recovery database exceeds the supported size.')
        with tempfile.TemporaryDirectory() as folder:
            saved=Path(folder)/'worker.sqlite'
            with closing(sqlite3.connect(path)) as source,closing(sqlite3.connect(saved)) as target:
                source.backup(target)
            raw=saved.read_bytes()
        validate(name,raw)
        retain(name,raw)
    return payloads


def check_destination(root,name,raw):
    validate(name,raw)
    path=Path(root)/name
    if path.is_symlink() or path.parent.is_symlink() or (Path(root)/name.split('/')[0]).is_symlink():
        raise ValueError('Shared recovery destination cannot be a symbolic link.')
    if path.exists():
        current=unprotect(path.read_bytes()) if MIGRATION.fullmatch(name) else path.read_bytes()
        equal=worker_tokens(current)==worker_tokens(raw) if WORKER.fullmatch(name) else json.loads(current)==json.loads(raw)
        if not equal:
            raise ValueError('Existing shared recovery state differs from this backup. Preserve both and reconcile job ownership before restoring.')


def install(root,name,raw):
    from workspace_backup import write_verified_backup
    check_destination(root,name,raw)
    path=Path(root)/name
    if path.exists():
        return None
    write_verified_backup(path,protect(raw) if MIGRATION.fullmatch(name) else raw)
    return path


def recover_worker(rpc, config, access, root, workspace):
    """Resume restored ownership; never delete a job or assign another identity."""
    from cloud_backend.transport import OfficeWorkerRpc
    from shared_backend import CloudError
    state = rpc.call('tv_workspace_status', {'p_workspace': workspace})
    candidates = []
    for path in (Path(root)/'migration-snapshots').glob('*.tvmigration'):
        raw = unprotect(path.read_bytes())
        validate('migration-snapshots/'+path.name, raw)
        plan = json.loads(raw)
        if plan['workspace'] == workspace and plan.get('state') == 'active':
            candidates.append(plan)
    if state.get('mode') != 'active' or not any(plan.get('worker') == state.get('worker')
            and plan['spreadsheet'] == state.get('spreadsheet') for plan in candidates):
        raise CloudError('Restore the verified migration backup for this active workspace before recovering its office worker.', 'conflict')
    if state.get('job'):
        path = Path(root)/'shared-worker'/workspace/'worker-state.sqlite'
        tokens = worker_tokens(path.read_bytes()) if path.exists() else []
        token = next((token for identity, token in tokens if identity == workspace), None)
        if not token:
            raise CloudError('A pending central job needs its original worker-token backup. Job ownership was retained.', 'conflict')
        office = OfficeWorkerRpc(config['url'], config['publishableKey'], lambda: access, state['worker'])
        claim = office.call('tv_claim_job', {'p_workspace':workspace,'p_token':token})
        if not isinstance(claim, dict) or claim.get('busy') or (not claim.get('completed') and
                (claim.get('job', {}).get('token') != token or claim['job'].get('workspace_id') != workspace)):
            raise CloudError('The restored backup does not own the pending central job. Preserve both recovery copies.', 'conflict')
    return {'worker':state['worker'],'state':'recovered','pending_job':bool(state.get('job'))}
