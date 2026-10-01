"""Copy SQLite preview history to Neon without overwriting conflicting IDs.

Run: python gsheet_dashboard/migrate_to_neon.py
The original database is retained, and a consistent SQLite backup is created.
"""

from datetime import datetime, timezone
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3

from preview_store import PreviewStore


def migrate(root=None):
    root = Path(root) if root else Path(__file__).resolve().parent / 'previews'
    source = root / 'previews.sqlite'
    if not source.is_file():
        raise RuntimeError('Source previews.sqlite was not found.')

    store = PreviewStore(root, database_url=os.getenv('DATABASE_URL', ''))
    if not store.database_url:
        raise RuntimeError('Set DATABASE_URL in gsheet_dashboard/.env before migrating.')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = root / f'previews-before-neon-{stamp}.sqlite'
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as local:
        with closing(sqlite3.connect(backup)) as snapshot:
            local.backup(snapshot)
    with closing(sqlite3.connect(backup.resolve().as_uri() + '?mode=ro', uri=True)) as snapshot:
        records = snapshot.execute(
            'SELECT id,created,source,columns_json,rows_json FROM previews ORDER BY id'
        ).fetchall()

    inserted = 0
    with store.connect() as remote:
        # Freeze destination writes during conflict checking and verification.
        remote.execute('LOCK TABLE previews IN SHARE ROW EXCLUSIVE MODE')
        for number, created, origin, columns, rows in records:
            expected = (created, origin, json.loads(columns), json.loads(rows))
            existing = remote.execute(
                'SELECT created,source,columns_json,rows_json FROM previews WHERE id=%s',
                (number,),
            ).fetchone()
            if existing is not None:
                if existing != expected:
                    raise RuntimeError(f'Preview {number} conflicts with Neon. No records were overwritten.')
                continue
            remote.execute(
                'INSERT INTO previews(id,created,source,columns_json,rows_json) '
                'VALUES(%s,%s,%s,%s::jsonb,%s::jsonb)',
                (number, created, origin, columns, rows),
            )
            inserted += 1

        # Check complete payloads, including ordering and duplicate rows.
        for number, created, origin, columns, rows in records:
            actual = remote.execute(
                'SELECT created,source,columns_json,rows_json FROM previews WHERE id=%s',
                (number,),
            ).fetchone()
            if actual != (created, origin, json.loads(columns), json.loads(rows)):
                raise RuntimeError(f'Preview {number} failed verification. Migration rolled back.')
        if records:
            store.advance_sequence(remote)

    row_count = sum(len(json.loads(record[4])) for record in records)
    print(f'Verified {len(records)} previews and {row_count} rows in Neon; {inserted} newly inserted.')
    print(f'SQLite backup: {backup}')
    print('Original SQLite database and export files retained.')


if __name__ == '__main__':
    try:
        migrate()
    except Exception as error:
        # Driver errors can include connection details; never print their text.
        if isinstance(error, RuntimeError):
            print(str(error))
        else:
            print(f'Migration failed ({type(error).__name__}). Check connection settings and database permissions.')
        raise SystemExit(1) from None
