# DataTrace Workspace

React dashboard for TitleVision extraction, automatic Google Sheets production sync, and Power BI exports.

Start with [SYNC_SETUP.md](SYNC_SETUP.md). Run `run.bat`, then open the URL printed by the launcher, normally http://localhost:8510.

- Extraction, imports, and scheduled AutoLogin captures automatically sync without a confirmation click.
- Google Sheets stores the authoritative long-named tracker tabs, raw append-only history, report views, audit log, and review list.
- Missing orders remain unchanged. New orders append as Search In Progress, with workflow suspension taking precedence.
- Manual fields and formulas are preserved. SLA calculations retain timestamps and use capture time for countdowns.
- Overview, Data sheets, Daily Orders, Monthly report, and Changes read Google Sheets. Compare previews is a separate raw snapshot tool.
- Export downloads color-coded `Production_data.xlsx` from the live trackers. Individual preview downloads remain immutable raw snapshots.
- PostgreSQL/Neon dependencies and setup are removed. Local SQLite and numbered CSV/XLSX files serve only as retry/recovery cache.

See [the revised specification](../docs/TV_Search_Sync_Prompt.md) for every rule, conflict resolution, and operational limitation.
