# TV Search Production Sync

The application follows `../docs/TV_Search_Sync_Prompt.md` with the later tracker
updates described here. Google Sheets supplies the live tracker and report data.
Saved local previews supply the Changes comparison. Status Report is on Data sheets.

## Run

### Report updates from updates_traker.pdf

- **Tracker report** uses the retained Google Sheets production trackers. **Import Excel report** uses a separately saved workbook dataset across Overview, Data Sheets, Daily Orders, Monthly Orders and Capacity Report. Switching sources republishes the selected reports; imported files never mark absent tracker orders completed.
- Select **Import files** beside Export to upload up to 30 XLSX/CSV files together (20 MB combined, 100,000 order rows). All worksheets with Order Number and Status/Task Status headers are read. A malformed file rejects the whole batch. Duplicate order numbers use the last uploaded occurrence and the import result lists duplicate counts. Existing tracker data remains available when switching back.
- Daily Orders uses Received, Completed, Clarification, Cancelled, Vendor Pending, In-House Pending, SLA OnTime and Missing. Assign to ABS is Vendor Pending. All other statuses outside completed, cancelled and clarification are In-House Pending. Selecting a date highlights the matching row in the Daily Status Report tab in Google Sheets.
- Capacity Report contains monthly totals, a year-to-date total, the selected month's daily rows, and a received/completed/capacity chart. Daily targets start at 700 and 750 and can be changed in the Capacity Report screen. Targets are counted only for dates present in the source; historical sample order counts are never inserted.
- Publishing exposes seven tabs: All Products, Full_Search_MON_YEAR, Remaining_Search_MON_YEAR, Daily Status Report, Capacity Report, Monthly Orders and Status Report. A date click updates only Daily Status Report; source publication refreshes the product reports. Both product views use the Full Search production columns. Other tabs are **hidden, not deleted**, because the existing tracker, capture receipt and recovery logic needs them. Replaced report values and sheet metadata are backed up under the workspace's `backups/reports` directory.
- A failed Sheets update keeps the imported dataset and selected mode locally and shows a retry message. Use **Publish current report** in the import dialog to retry. Export downloads the selected source with the seven report worksheets. Report mode and imported records are included in workspace backup/restore.

Restart the project app after updating the files. The frontend build in `frontend/dist` includes these changes; an already installed desktop executable must be rebuilt/reinstalled separately. No live Google Sheets migration is performed by editing these source files.

Targeted checks: `python -m unittest test_pdf_report_workspace test_report_refinements test_preview_completion test_monthly_sla_history test_monthly_production`. The isolated browser check is `npx playwright test --config=playwright.reports.config.js` after a frontend build; it uses installed Edge and mocked data.

Run `gsheet_dashboard/run.bat`, or install `gsheet_dashboard/requirements.txt`, build
`gsheet_dashboard/frontend` with `npm run build`, and run `gsheet_dashboard/server.py`.
The workspace normally opens at http://localhost:8510. Configure the service account
and portal login in `gsheet_dashboard/.env` using `.env.example`. Share the configured
Google Sheet with the service account as Editor. Never commit credentials.

On Windows, you can also open **Connections & settings** in the local browser to
enter the spreadsheet URL, tracker tab names, TitleVision login and queue URL, and
import a service-account JSON key. **Save settings** applies the connection immediately;
**Test saved Google Sheets connection** checks access without writing to the sheet.
These settings are encrypted for your Windows account in `settings.vault.browser`
and take precedence over `.env` on restart. Blank password and key fields preserve
the saved values. Browser connection settings are available only from localhost;
the Workspace and Updates tabs remain in the installed desktop app.

## Trackers and history

The supplied September 2026 workbooks are bundled under `default_trackers` and loaded
automatically. The Google Sheet tracker names are:

- `TV_Search_Production_Report_Full_Search`
- `TV_Search_Production_Report_C-O_and_Update`

Existing tracker rows and manual fields are preserved. Missing default orders append
after existing rows. Duplicate default source rows are recorded in the local sync report; the
original workbooks remain intact. Extra manual columns are preserved.

Every queue extraction or legacy capture import saves a numbered preview locally and syncs automatically. The separate **Import Excel report** workflow above saves report data without creating a queue capture.
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

In Tracker report mode, daily/monthly API reports read the live tracker tabs. The dashboard never substitutes
the latest raw preview for tracker totals if Google Sheets is unavailable. Changes
compares selected local snapshots by Order Number. Local SQLite stores pass
reports, changes and ambiguous rows. Google Sheets has no numbered preview or audit tabs.

Exports are named `Production_data.xlsx`. The main Export button exports the seven selected-source report tabs, whose names fit Excel's worksheet limits. The legacy full-workbook API still supports shortening long tracker names.
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

## Replacing imported report files

- Import files accepts repeated uploads. The same filename replaces that workbook; other saved files remain. The most recently uploaded occurrence of an Order Number wins.
- Remove file recomputes reports from the remaining workbooks. Remove all files leaves an empty Excel report. Select Replace all saved files when uploading a complete replacement batch.
- Imported reports include every status in Daily Orders, Monthly Orders, Capacity Report and Status Report. Tracker reports retain the tracker summaries.
- Imports save locally before publishing. Sync to Sheets or Publish current report retries a pending publication without re-importing.
- Workbook access for reports does not depend on a deleted initial worksheet (gid=0). Direct worksheet operations still require an existing worksheet ID or title.

## Report and queue fixes

Report edits save immediately and Google Sheets publication runs in the background. You can remove imported files during a capture or Sheets update. Removing the last file leaves an empty Excel report; select Tracker report explicitly to return to trackers.

Daily Status Report adds chronological dates, a Total row, SLA On Time and SLA Missing. Excel reports include every imported date, including earlier months, in Daily Status Report and daily capacity. Seven report tabs are visible. Blank rows in Status Report are uncolored and percentages are formatted for readability.

Full Search and Remaining Search preserve the corresponding uploaded workbook's orders across all dates, including other products within that workbook. Each detail tab has sequential No values. Shared Order Numbers can appear in both source reports; overall dashboard and status totals count each order once, using the latest uploaded values.

Queue extraction uses the installed Chrome or Edge on Windows. DATATRACE_HEADLESS=false opens a visible browser for login and extraction. Pagination checks the portal's record and page totals before saving a capture. Install its Node dependencies with npm install in gsheet_dashboard. Source changes invalidate old report requests and cached dashboard data.

Cancel extraction stops the running extractor and its browser. It preserves existing captures and imported reports; a capture already saved locally remains available for sync. Live progress reports login, paging and local saving. An empty new tracker worksheet is initialized during its first sync. Failed cloud syncs retain the local preview and offer Retry sync. Dashboard reads reconnect after a temporary server interruption.

The Google Sheets Daily Orders tab is retired and removed during report publication, with a local recovery copy in backups/reports. Date selections highlight the matching Daily Status Report row in blue and clear the previous highlight. All available dates remain in that report; date clicks do not rewrite the other report tabs.
