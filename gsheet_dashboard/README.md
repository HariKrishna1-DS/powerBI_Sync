# DataTrace Workspace

React dashboard for DataTrace queue captures, Google Sheets sync and Power BI exports.

Start with [SYNC_SETUP.md](SYNC_SETUP.md) for credentials and installation.
Run `run.bat`, then open the local URL printed by the launcher (normally
http://localhost:8510).

- Each extraction saves numbered Excel/CSV previews locally. Use the sync button to upload a selected preview to Google Sheets.
- Imports become new saved previews. No demo data or star schema is loaded.
- Compare any two previews, inspect field-level changes, and export DataTraceChanges to Power BI.
- Click column headers for unique values, counts and custom filters.
- Switch chart types, group by any column, and scroll or adjust the chart range.
- Add Status_1 to Status_2 replacements with the + button, then use Sync Filters.
- Sync colors complete data rows by status and updates the Status Report tab.

See the [project README](../README.md#folder-and-file-review) for required folders,
optional tools, cleanup candidates, and saved-data guidance.

The Python extraction CLI remains available: `python datatrace_sync.py`.
The React production build is served by `server.py`; `app.py` is a compatibility
entry point for the same server. For frontend development, run `npm run dev` in
`frontend` with the API running on port 8510.
