# Architecture

React/Vite calls the Flask/Waitress API in `gsheet_dashboard/server.py`.
Puppeteer captures the portal queue; Python saves numbered CSV/XLSX snapshots in
SQLite and automatically syncs them through `tracker_sync.py`.

The two renamed production trackers in Google Sheets are the authoritative order
records. Immutable numbered local previews support comparisons; All Products and
Sheet1 accumulate raw Google Sheet history. Tracker values, raw history and reports
commit in one Google Sheets batch. SQLite provides sync receipts, pass reports,
process locking and pending job state. A valid Out Time date marks an order
Completed and Delivered.

The report API reads the current tracker cells for all dashboard totals. No external
SQL database is required. Secrets stay in local environment configuration.
See README.md and docs/TV_Search_Sync_Prompt.md for rules and operation.

`tracker_formatting.py` maintains row conditional formatting from `status_colors.json`,
including the Free Site column. Formatting is reconciled separately from value batches
so retries cannot duplicate conditional rules. `indian_clock.py` supplies network-anchored
IST to both the scheduler and the running clock in the UI.

`remove_cloud_audit_tabs.py` archives and removes numbered preview tabs and the
Preview History, Default conflicts, Changes and Ambiguous - Needs review tabs.
The archive is stored outside the project ZIP under `gsheet_dashboard/previews`.
