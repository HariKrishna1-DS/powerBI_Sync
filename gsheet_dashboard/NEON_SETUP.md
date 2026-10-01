# Neon preview storage

Set `DATABASE_URL` in `gsheet_dashboard/.env` to the complete Neon PostgreSQL
connection string, including SSL parameters. On Render, set the same variable
on the backend service and rebuild/deploy so the new dependencies are installed.
The Flask API, extraction pipeline, and Streamlit dashboard share this store.
When the variable is absent or empty, previews use the existing local SQLite database.
Connection failures do not silently fall back to SQLite.

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r gsheet_dashboard\requirements.txt
.\.venv\Scripts\python.exe gsheet_dashboard\check_neon.py
.\.venv\Scripts\python.exe gsheet_dashboard\migrate_to_neon.py
```

Pause extraction/import operations during migration. The script takes a consistent
SQLite backup, preserves preview IDs, source labels, timestamps, columns, duplicate
rows and row ordering, and verifies every payload before committing the transaction.
It can be rerun: matching IDs are skipped; differing records cause a rollback rather
than an overwrite. Original SQLite and CSV/XLSX files remain in `previews/`.
The PostgreSQL table is `previews`; new preview numbers follow its sequence.
Monthly report SLA edits use the `sla_corrections` table, created automatically at
startup. Corrections are keyed by order number and completion date, so they survive
server restarts without rewriting original captures. Existing Google Sheet values
remain authoritative when an order is present there. With no `DATABASE_URL`, the
same correction table is stored in local SQLite.

This migration covers numbered preview history. Google Sheets content, credentials,
schedule settings, and the unnumbered queue baseline files are not migrated.
CSV/XLSX downloads are generated from stored previews, so losing local exports
on Render does not lose the migrated preview data.

Custom preview roots default to SQLite, keeping temporary test stores isolated
even when `.env` contains a live database URL. Pass `database_url` explicitly
to `PreviewStore` when a custom root should use PostgreSQL.
Optional `test_neon_storage.py` checks use `NEON_TEST_URL` and create/drop only a
uniquely named disposable schema; they do not modify the application's previews.
