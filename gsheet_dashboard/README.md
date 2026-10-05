# TV Search Production Sync

The application follows `../docs/TV_Search_Sync_Prompt.md` with the later tracker
updates described here. Google Sheets supplies the live tracker and report data.
Saved local previews supply the Changes comparison. Status Report is on Data sheets.

## Run

Run `gsheet_dashboard/run.bat`, or install `gsheet_dashboard/requirements.txt`, build
`gsheet_dashboard/frontend` with `npm run build`, and run `gsheet_dashboard/server.py`.
The workspace normally opens at http://localhost:8510. Configure the service account
and portal login in `gsheet_dashboard/.env` using `.env.example`. Share the configured
Google Sheet with the service account as Editor. Never commit credentials.

## Trackers and history

The supplied September 2026 workbooks are bundled under `default_trackers` and loaded
automatically. The Google Sheet tracker names are:

- `TV_Search_Production_Report_Full_Search`
- `TV_Search_Production_Report_C-O_and_Update`

Existing tracker rows and manual fields are preserved. Missing default orders append
after existing rows. Duplicate default source rows are recorded in the local sync report; the
original workbooks remain intact. Extra manual columns are preserved.

Every extraction/import saves a numbered preview locally and syncs automatically.
`preview1`, `preview2`, etc. are immutable local snapshots in SQLite and CSV/XLSX.
`All Products` and `Sheet1` retain accumulated raw Google Sheet history with preview
names and timestamps. A smaller
preview never reduces tracker totals. Preview deletion is available only as an
explicit human action in the sidebar; raw Google Sheet history stays available.

Orders match by trimmed, case-insensitive Order Number. A new order starts as Search
In Progress, except workflow-suspended orders, which become Awaiting for Clarification.
For existing orders, changed status-driving fields can apply those same two explicit
rules. Since 2.5.3, an order disappearing between valid saved previews retains its
tracker row and becomes Completed and Delivered at the first missing preview's
timestamp. Cancelled/suspended rows and precise manual completion times are
preserved. Empty or malformed previews cannot infer completion. See
[current completion and SLA rules](../docs/TV_TRACKER_2_5_3_RELEASE.md).

Status, ETA, Out Time and SLA Expiration update on existing orders. Comments and
Assignee are always blank in both production trackers, including new and absent orders.
Raw preview history retains its original values. Free Site is recalculated for all tracker rows. Manual Searcher, Shift, Review/QC,
Expense, Typer and other columns remain intact. Out Time uses an actual Completed Time
when the tracker status is Completed and Delivered; dates are never fabricated.
An explicit Out Time from a new preview is also accepted.

SLA countdowns use the capture timestamp in IST. Partial absolute dates use that
year. On Time includes equality with the SLA; late completion is Missing. Open orders
stay unclassified. Ambiguous dates such as PAUSED remain in the local sync report for review.

## Reliability and reporting

SQLite stores local snapshots and sync job receipts. No external SQL database is used.
An OS-released SQLite lock serializes sync processes. One atomic Google Sheets batch
writes tracker values, raw history and reports. A local SQLite receipt records the
pass after Google Sheets readback. The `Sheet1` Preview column proves whether a
preview committed after a lost reply, so replaying it is a no-op. Pending snapshots sync in order after restart. Automatic retries
are bounded; failures remain saved and appear in the dashboard for manual retry.
The scheduler operates while the server is running, using Asia/Kolkata times.
`indian_clock.py` reads time from an HTTPS response and advances it with a monotonic
clock. The browser uses that same network anchor. Changing the PC clock or timezone
does not change trigger times. Scheduled runs wait for the initial network time sync;
a later connection failure keeps the established clock running until it can refresh.

Daily/monthly API reports read the two live tracker tabs. The dashboard never substitutes
the latest raw preview for tracker totals if Google Sheets is unavailable. Changes
compares selected local snapshots by Order Number. Local SQLite stores pass
reports, changes and ambiguous rows. Google Sheets has no numbered preview or audit tabs.

Exports are named `Production_data.xlsx`. Because Excel limits tab names to 31
characters, the Export button requests approval to use Full Title and Remaining
Products in the exported copy. Google Sheet tab names remain unchanged.
`status_colors.json` holds the exact matching colors from the sample workbook.
Google Sheets conditional rules color full rows and respond to manual status edits.
Free Site cells inherit the row status color. Status Report and Excel exports
use the same palette.
Daily and monthly charts show labeled values for three periods with Earlier/Later navigation.

To initialize or resume a migration explicitly, run `gsheet_dashboard/migrate_trackers.py`.
Keep the `previews` directory on persistent storage for locally saved, unsynced captures.
Committed previews can be recovered from Google Sheets after loss of local storage.

## Regression checks

From `gsheet_dashboard`, run `python -m unittest test_tracker_v2 test_october_updates` and
`npm --prefix frontend run build`. Legacy tests which assert that missing orders are
automatically completed describe the superseded behavior; the v2 regression suite
tests preservation, status rules, SLA boundaries and atomic/idempotent history writes.

To reapply the column cleanup and recalculate current tracker SLA values, run
`gsheet_dashboard/refresh_production_trackers.py`. It saves a backup under `previews`,
keeps row order and raw history, and refreshes the cached reports. Blank Out Time
keeps Free Site blank; a missing or ambiguous deadline needs review before classification.

The removed Google Sheet preview and audit tabs are backed up under `previews` as
`removed-cloud-tabs-*.json.gz`. Run `remove_cloud_audit_tabs.py` to repeat the
backup and cleanup if those tabs appear again. The local preview database and raw
`Sheet1` history support comparisons without numbered cloud tabs.
