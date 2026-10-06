"""Explicit, recoverable local retention. Cloud evidence is never pruned here."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
from zipfile import ZipFile
from workspace_backup import make_backup, write_verified_backup
from backup_protection import protect, suffix


def storage_status(store):
    with store.connect() as db:
        captures = db.execute('SELECT COUNT(*) FROM previews').fetchone()[0]
        imports = db.execute('SELECT COUNT(*) FROM report_imports').fetchone()[0]
    root = store.root.parent
    return {'captures': captures, 'imports': imports,
            'database_bytes': (store.root / 'previews.sqlite').stat().st_size,
            'backup_bytes': sum(p.stat().st_size for p in (root / 'backups').glob('*') if p.is_file()),
            'legacy_backup_count': len(list((root / 'backups').glob('*.zip'))),
            'policy': 'Keep the newest 50 local captures and 10 imports; protect unsynced captures and the active import. Archive first. Cloud production and raw evidence are retained.'}


def archive_history(store, active_import=None, keep_captures=50, keep_imports=10):
    if type(keep_captures) is not int or keep_captures < 2 or type(keep_imports) is not int or keep_imports < 1:
        raise ValueError('Keep at least two captures and one import.')
    with store.connect() as db:
        candidates = [r[0] for r in db.execute("SELECT p.id FROM previews p JOIN sync_jobs j ON j.preview_id=p.id WHERE j.state='synced' AND p.id NOT IN (SELECT id FROM previews ORDER BY id DESC LIMIT ?)", (keep_captures,))]
        imports = [r[0] for r in db.execute('SELECT id FROM report_imports ORDER BY created DESC').fetchall()[keep_imports:] if r[0] != active_import]
    if not candidates and not imports:
        return {'archived_captures': 0, 'archived_imports': 0, 'backup': None}
    raw = make_backup(store).getvalue()
    folder = store.root.parent / 'backups'
    folder.mkdir(exist_ok=True)
    name = 'retention-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + suffix()
    destination = folder / name
    with ZipFile(BytesIO(raw)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if any(hashlib.sha256(archive.read(file)).hexdigest() != digest for file, digest in manifest['sha256'].items()):
            raise ValueError('Archive integrity check failed; active history was retained.')
    write_verified_backup(destination, protect(raw))
    with store.connect() as db:
        for number in candidates:
            db.execute('DELETE FROM previews WHERE id=?', (number,))
            for table in ('sync_jobs', 'sync_reports', 'sync_failures', 'sync_receipts', 'capture_metadata'):
                db.execute(f'DELETE FROM {table} WHERE preview_id=?', (number,))
        db.executemany('DELETE FROM report_imports WHERE id=?', [(identity,) for identity in imports])
    for number in candidates:
        for extension in ('csv', 'xlsx'):
            (store.root / f'preview{number}.{extension}').unlink(missing_ok=True)
    with store.connect() as db:
        db.execute('VACUUM')
    return {'archived_captures': len(candidates), 'archived_imports': len(imports), 'backup': name,
            'recovery': 'Restore this archive with the same Windows account in Settings > Restore backup. For recovery on another PC, create a password-encrypted backup in Settings before archiving. Restoring replaces the active workspace and creates a safety backup.'}
