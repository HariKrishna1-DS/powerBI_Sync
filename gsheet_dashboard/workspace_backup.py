"""Credential-free local backups with strict restore validation."""
from datetime import datetime, timezone
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile

SETTINGS = ('remaining_products.json', 'sync_schedule.json', 'production-cache.json')
TABLES = {'previews', 'sla_corrections', 'sync_receipts', 'sync_jobs', 'sync_reports', 'sync_failures', 'operation_history', 'monthly_operations', 'report_workspace', 'import_excel_changes', 'sqlite_sequence'}


def save_safety_backup(store, reason):
    if reason not in ('before-delete', 'before-update'):
        raise ValueError('Unknown backup reason.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    destination = store.root.parent / 'backups' / f'{reason}-{stamp}.zip'
    destination.parent.mkdir(exist_ok=True)
    temporary = destination.with_suffix('.tmp')
    try:
        temporary.write_bytes(make_backup(store).getvalue())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def make_backup(store):
    stream = BytesIO()
    with tempfile.TemporaryDirectory() as folder:
        database = Path(folder) / 'previews.sqlite'
        with store.connect() as source, closing(sqlite3.connect(database)) as target:
            source.backup(target)
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps({'format': 'datatrace-workspace', 'version': 1, 'created': datetime.now(timezone.utc).isoformat()}))
            archive.write(database, 'previews.sqlite')
            for name in SETTINGS:
                file = store.root.parent / name
                if file.is_file():
                    archive.write(file, name)
    stream.seek(0)
    return stream


def restore_backup(store, raw):
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
        members = archive.infolist()
        names = {item.filename for item in members}
        if len(names) != len(members) or not {'manifest.json', 'previews.sqlite'} <= names or names - {'manifest.json', 'previews.sqlite', *SETTINGS}:
            raise ValueError('Unexpected backup contents.')
        if sum(item.file_size for item in members) > 256 * 1024 * 1024:
            raise ValueError('Expanded backup exceeds 256 MB.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'datatrace-workspace' or manifest.get('version') != 1:
            raise ValueError('Unsupported backup format.')
        for name in names & set(SETTINGS):
            parsed = json.loads(archive.read(name))
            if name == 'remaining_products.json' and (not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed)):
                raise ValueError('Invalid product preferences.')
            if name != 'remaining_products.json' and not isinstance(parsed, dict):
                raise ValueError('Invalid workspace settings.')
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
                if ('table', 'sync_receipts') in schema:
                    connection.execute('SELECT preview_id,report_json FROM sync_receipts LIMIT 1')
                connection.execute('SELECT order_number,completion_date,status,updated FROM sla_corrections LIMIT 1')
                if ('table', 'report_workspace') in schema:
                    for number, payload in connection.execute('SELECT id,payload FROM report_workspace'):
                        try:
                            value = json.loads(payload)
                            if number != 1 or not isinstance(value, dict) or value.get('mode') not in ('tracker', 'excel'):
                                raise ValueError('Invalid report source.')
                            imported = value.get('imported')
                            if imported is not None and (not isinstance(imported, dict) or
                                    not isinstance(imported.get('rows'), list) or not all(isinstance(row, dict) for row in imported['rows']) or
                                    not isinstance(imported.get('columns'), list) or not all(isinstance(c, str) for c in imported['columns'])):
                                raise ValueError('Invalid imported report.')
                        except (ValueError, TypeError) as exc:
                            raise ValueError('Backup contains invalid report data.') from exc
                if ('table', 'import_excel_changes') in schema:
                    for action, order_number, payload in connection.execute('SELECT action,order_number,payload FROM import_excel_changes'):
                        try:
                            value = json.loads(payload)
                            if (action not in ('Added', 'Updated', 'Removed') or not isinstance(order_number, str) or
                                    not order_number.strip() or not isinstance(value, dict) or
                                    value.get('Change') != action or value.get('Order Number') != order_number or
                                    not isinstance(value.get('Before'), dict) or not isinstance(value.get('After'), dict)):
                                raise ValueError('Invalid imported order history.')
                        except (ValueError, TypeError) as exc:
                            raise ValueError('Backup contains invalid imported order history.') from exc
                invalid = connection.execute("SELECT COUNT(*) FROM previews WHERE NOT json_valid(rows_json) OR NOT json_valid(columns_json)").fetchone()[0]
                if invalid:
                    raise ValueError('Backup contains invalid preview data.')
                invalid = connection.execute("SELECT COUNT(*) FROM previews WHERE json_type(rows_json) != 'array' OR json_type(columns_json) != 'array'").fetchone()[0]
                if invalid:
                    raise ValueError('Backup contains invalid preview rows.')
        except sqlite3.DatabaseError as exc:
            raise ValueError('Backup database is invalid.') from exc
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        safety = store.root.parent / 'backups' / f'before-restore-{stamp}.zip'
        safety.parent.mkdir(exist_ok=True)
        safety.write_bytes(make_backup(store).getvalue())
        # Replace the cache directory as a unit; old exports remain in the safety directory.
        previous = store.root.parent / f'previews-before-restore-{stamp}'
        previous_settings = {name: (store.root.parent / name).read_bytes() if (store.root.parent / name).exists() else None for name in SETTINGS}
        store.root.rename(previous)
        try:
            store.root.mkdir()
            shutil.copy2(database, store.root / 'previews.sqlite')
            store.__init__(store.root)  # Upgrade v2.0 backups before servicing another request.
            for name in SETTINGS:
                target = store.root.parent / name
                if name in names:
                    temporary = target.with_suffix('.restore-tmp')
                    temporary.write_bytes(archive.read(name))
                    temporary.replace(target)
                elif target.exists():
                    target.unlink()
        except Exception:
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
