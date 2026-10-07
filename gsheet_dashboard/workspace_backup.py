"""Credential-free local backups with strict restore validation."""
from datetime import datetime, timezone
from contextlib import closing
from io import BytesIO
import json
import hashlib
from pathlib import Path
import shutil
import sqlite3
import tempfile
import os
import zipfile
import re
from backup_protection import protect, unprotect, suffix

SETTINGS = ('remaining_products.json', 'sync_schedule.json', 'production-cache.json')
TABLES = {'previews', 'sla_corrections', 'sync_receipts', 'sync_jobs', 'sync_reports', 'sync_failures', 'sync_retry', 'operation_history', 'monthly_operations', 'sqlite_sequence', 'report_imports', 'report_preferences', 'capacity_targets', 'capture_metadata', 'cloud_outbox', 'cloud_requests'}
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
CLOUD_FILE = re.compile(r'^cloud-archives/cloud-history-[a-f0-9]{32}\.tvcloud$')


def write_verified_backup(destination, raw):
    """Flush and read back an archive before making its final name visible."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=destination.name + '.', suffix='.tmp', delete=False) as output:
            temporary = Path(output.name)
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        if hashlib.sha256(temporary.read_bytes()).digest() != hashlib.sha256(raw).digest():
            raise ValueError('Backup verification failed. The previous backup and workspace were retained.')
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def save_safety_backup(store, reason):
    if reason not in ('before-delete', 'before-update'):
        raise ValueError('Unknown backup reason.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = store.root.parent / 'backups' / f'{reason}-{stamp}{suffix()}'
    return write_verified_backup(destination, protect(make_backup(store).getvalue()))


def make_backup(store):
    stream = BytesIO()
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / 'previews.sqlite'
        with store.connect() as source, closing(sqlite3.connect(database)) as target:
            source.backup(target)
        files = {'previews.sqlite': database}
        files.update({name: store.root.parent / name for name in SETTINGS if (store.root.parent / name).is_file()})
        cloud_files = {f'cloud-archives/{file.name}': file for file in (store.root.parent / 'cloud-archives').glob('*.tvcloud') if CLOUD_FILE.fullmatch(f'cloud-archives/{file.name}')}
        if sum(file.stat().st_size for file in [*files.values(), *cloud_files.values()]) > MAX_EXPANDED_BYTES - 65536:
            raise ValueError('Workspace exceeds the supported 256 MB recovery size. Archive older report imports/captures before creating a backup; nothing was replaced.')
        payloads = {name: file.read_bytes() for name, file in files.items()}
        # Remove the source Windows binding inside the portable container. The
        # desktop encrypts the entire export with the user's backup password.
        payloads.update({name: unprotect(file.read_bytes()) for name, file in cloud_files.items()})
        from shared_recovery import collect
        payloads.update(collect(store.root.parent))
        if sum(len(raw) for raw in payloads.values())>MAX_EXPANDED_BYTES-65536:
            raise ValueError('Workspace and shared recovery material exceed the supported 256 MB recovery size.')
        with closing(sqlite3.connect(database)) as saved:
            count = saved.execute('SELECT COUNT(*) FROM previews').fetchone()[0]
            if saved.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Workspace database integrity check failed; backup was not created.')
        manifest = {'format': 'datatrace-workspace', 'version': 1, 'created': datetime.now(timezone.utc).isoformat(),
                    'capture_count': count, 'sha256': {name: hashlib.sha256(raw).hexdigest() for name, raw in payloads.items()}}
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(manifest))
            for name, raw in payloads.items():
                archive.writestr(name, raw)
    if stream.tell() > MAX_ARCHIVE_BYTES:
        raise ValueError('Compressed backup exceeds the supported 100 MB restore limit. Archive older data before retrying.')
    stream.seek(0)
    return stream


def restore_backup(store, raw):
    if len(raw) > MAX_ARCHIVE_BYTES + 1024 * 1024:
        raise ValueError('Backup exceeds the supported encrypted upload limit.')
    raw = unprotect(raw)
    try:
        if len(raw) > MAX_ARCHIVE_BYTES:
            raise ValueError('Backup exceeds the 100 MB upload limit.')
        archive = zipfile.ZipFile(BytesIO(raw))
        members = archive.infolist()
        names = {item.filename for item in members}
        cloud_names = {name for name in names if CLOUD_FILE.fullmatch(name)}
        from shared_recovery import recognized, check_destination, install
        shared_names={name for name in names if recognized(name)}
        if len(names) != len(members) or not {'manifest.json', 'previews.sqlite'} <= names or names - {'manifest.json', 'previews.sqlite', *SETTINGS} - cloud_names - shared_names:
            raise ValueError('Unexpected backup contents.')
        if sum(item.file_size for item in members) > MAX_EXPANDED_BYTES:
            raise ValueError('Expanded backup exceeds 256 MB.')
        manifest = json.loads(archive.read('manifest.json'))
        if not isinstance(manifest, dict) or manifest.get('format') != 'datatrace-workspace' or manifest.get('version') != 1:
            raise ValueError('Unsupported backup format.')
        if 'sha256' in manifest:
            if not isinstance(manifest['sha256'], dict):
                raise ValueError('Invalid integrity manifest.')
            if set(manifest['sha256']) != names - {'manifest.json'}:
                raise ValueError('Backup integrity manifest is incomplete.')
            for name, digest in manifest['sha256'].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    raise ValueError('Backup contents do not match their integrity manifest.')
        for name in names & set(SETTINGS):
            parsed = json.loads(archive.read(name))
            if name == 'remaining_products.json' and (not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed)):
                raise ValueError('Invalid product preferences.')
            if name != 'remaining_products.json' and not isinstance(parsed, dict):
                raise ValueError('Invalid workspace settings.')
        for name in cloud_names:
            from cloud_retention import decode
            decode(archive.read(name))
            target = store.root.parent / name
            if target.exists() and unprotect(target.read_bytes()) != archive.read(name):
                raise ValueError('A cloud recovery archive with this name already exists and differs.')
        for name in shared_names:
            check_destination(store.root.parent,name,archive.read(name))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise ValueError(f'Invalid DataTrace backup: {exc}') from exc
    with tempfile.TemporaryDirectory(dir=store.root.parent, prefix='restore-') as folder:
        database = Path(folder) / 'previews.sqlite'
        database.write_bytes(archive.read('previews.sqlite'))
        try:
            with closing(sqlite3.connect(database)) as connection:
                if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('Backup database is damaged.')
                schema = connection.execute("SELECT type,name FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
                if any(kind != 'table' or name not in TABLES for kind, name in schema):
                    raise ValueError('Backup contains unsupported database objects.')
                connection.execute('SELECT id,created,source,columns_json,rows_json FROM previews LIMIT 1')
                if 'capture_count' in manifest and connection.execute('SELECT COUNT(*) FROM previews').fetchone()[0] != manifest['capture_count']:
                    raise ValueError('Backup capture count does not match its manifest.')
                if ('table', 'sync_receipts') in schema:
                    connection.execute('SELECT preview_id,report_json FROM sync_receipts LIMIT 1')
                if ('table', 'cloud_outbox') in schema:
                    from shared_backend import CloudOutbox
                    CloudOutbox.validate_database(connection)
                if ('table', 'cloud_requests') in schema:
                    from shared_requests import SharedRequests
                    SharedRequests.validate_database(connection)
                connection.execute('SELECT order_number,completion_date,status,updated FROM sla_corrections LIMIT 1')
                invalid = connection.execute("SELECT COUNT(*) FROM previews WHERE NOT json_valid(rows_json) OR NOT json_valid(columns_json)").fetchone()[0]
                if invalid:
                    raise ValueError('Backup contains invalid preview data.')
                invalid = connection.execute("SELECT COUNT(*) FROM previews WHERE json_type(rows_json) != 'array' OR json_type(columns_json) != 'array'").fetchone()[0]
                if invalid:
                    raise ValueError('Backup contains invalid preview rows.')
                for table, column, kind in (('report_imports', 'dataset_json', 'object'),
                                            ('report_preferences', 'value_json', 'object'),
                                            ('capture_metadata', 'metadata_json', 'object')):
                    if ('table', table) in schema:
                        if connection.execute(f'SELECT COUNT(*) FROM {table} WHERE NOT json_valid({column})').fetchone()[0]:
                            raise ValueError('Backup contains invalid report data.')
                        if connection.execute(f'SELECT COUNT(*) FROM {table} WHERE json_type({column}) != ?', (kind,)).fetchone()[0]:
                            raise ValueError('Backup contains invalid report settings.')
        except sqlite3.DatabaseError as exc:
            raise ValueError('Backup database is invalid.') from exc
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        safety = store.root.parent / 'backups' / f'before-restore-{stamp}{suffix()}'
        write_verified_backup(safety, protect(make_backup(store).getvalue()))
        # Replace the cache directory as a unit; old exports remain in the safety directory.
        previous = store.root.parent / f'previews-before-restore-{stamp}'
        previous_settings = {name: (store.root.parent / name).read_bytes() if (store.root.parent / name).exists() else None for name in SETTINGS}
        store.root.rename(previous)
        added_cloud = []
        try:
            store.root.mkdir()
            shutil.copy2(database, store.root / 'previews.sqlite')
            store.__init__(store.root)  # Upgrade v2.0 backups before servicing another request.
            with store.connect() as db:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='report_preferences'").fetchone():
                    # A restored archive cannot prove which workbook/source is live now.
                    db.execute("UPDATE report_preferences SET value_json=json_set(value_json,'$.publish_status','pending','$.published',json('null'),'$.revision',coalesce(json_extract(value_json,'$.revision'),0)+1)")
            for name in SETTINGS:
                target = store.root.parent / name
                if name in names:
                    temporary = target.with_suffix('.restore-tmp')
                    temporary.write_bytes(archive.read(name))
                    temporary.replace(target)
                elif target.exists():
                    target.unlink()
            for name in cloud_names:
                target = store.root.parent / name
                if not target.exists():
                    write_verified_backup(target, protect(archive.read(name)))
                    added_cloud.append(target)
            for name in shared_names:
                target=install(store.root.parent,name,archive.read(name))
                if target is not None:
                    added_cloud.append(target)
        except Exception:
            for target in added_cloud:
                target.unlink(missing_ok=True)
            if (store.root / 'previews.sqlite').exists():
                (store.root / 'previews.sqlite').unlink()
            store.root.rmdir()
            previous.rename(store.root)
            for name, data in previous_settings.items():
                target = store.root.parent / name
                if data is not None:
                    target.write_bytes(data)
                elif target.exists():
                    target.unlink()
            raise
    return str(safety)
