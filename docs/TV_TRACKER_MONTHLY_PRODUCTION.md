# Tv Tracker 2.4.0 — monthly production

This update adds the monthly reporting workflow from `DataTrace_Monthly_Report_Prompt.md` to the existing desktop application. Google Sheets remains the production authority. Captures, receipts, preferences and recoverable maintenance previews stay local. No new service, database server or package is required.

## Using the feature

1. Open **Reports → Monthly report → Monthly setup, import and rollover**.
2. Choose **Set up monthly tabs**. Review the preview, then **Confirm monthly setup**. Existing unsuffixed production tabs are copied to backup tabs and renamed to September 2026 in place; their sheet IDs and data remain. The October pair is created if absent. Existing monthly data is never overwritten by setup. Multiple competing legacy tabs stop setup for review.
3. Select the October workbooks using the separately labeled **Full Search workbook** and **C-O and Update workbook** fields. Full Search reads `TV Orders`; C-O reads `Sheet1`. `Escalations` is ignored. Choose **Preview workbook import**, check read/added/updated/unchanged/skipped counts and review items, then **Confirm import**. The toolbar's existing **Import file** still imports a raw capture and is a different workflow.
4. Select a month in **Monthly production orders** and use **Download Excel**. The file is named `TV_Search_Production_Report_<Mon>_<YYYY>.xlsx`, with Full Search, C-O and Update, and Summary worksheets. A missing month returns a clear error. Summary SLA percentages use classified SLA orders as their denominator; other percentages use Month Orders, matching the existing cards.
5. To carry October's unfinished orders into November, select October, choose **Run month rollover**, review the source/target counts, and choose **Confirm rollover**. A preview does not change Google Sheets. **Cancel preview** cancels only that preview screen.
6. Review **Activity → Monthly production activity** for operation reports and each moved order's source, destination and reason. Download the complete JSON report to retain counts and review items. A saved preview can be resumed after a restart. If a save times out, retry the same confirmation to recover its receipt.

The report's normal default is the current Indian-calendar month if it contains data, otherwise the most recent available month. A manually selected month is retained during refreshes. Empty new tabs do not inflate the month list.

## Month ownership policy

- New preview orders enter their arrival month. A newly imported order with a valid Out Time uses its completion month. Missing or invalid arrival time uses the selected import month, or the capture month for a new preview, and creates a review item. Invalid arrivals sort last.
- Blank Out Time does **not** immediately push an October order into November. Carry happens only through rollover. This resolves the brief's conflict between “new orders land in October” and “unfinished orders go to November.”
- Rollover moves blank-Out-Time orders to the next month, preserving In-Time and recording `Carried From`. December correctly rolls into January of the next year.
- An uncarried order whose valid completion belongs to another month is reconciled to that month during confirmed rollover. A carried order stays in its current month after completion. Later captures and repeated imports retain current ownership instead of sending a carried order back to its original arrival month.
- A blank value in an older workbook cannot erase valid completion evidence already held in production.
- Invalid nonblank Out Time is a review item, not proof that an order is incomplete or complete. Such an order is retained during rollover.
- September 2026 is an archive. It is not reseeded or reimported in monthly mode and cannot be rolled over or edited through the SLA endpoint. Its historical orders remain in September reports; current Orders excludes the archive. Historical archive rows may also have a current record in a later month. Uniqueness is enforced across **active months**.
- The established status mapping, manual-field ownership, blank Comments/Assignee rules, SLA calculations, capture identity checks and raw history receipts remain in place. A disappearance from the queue is still not completion evidence.

## Automatic rollover and confirmation

While the desktop engine is running, it opens the current month's missing empty tab pair and saves rollover previews for completed months. A missed month boundary is discovered after the next launch. Creating empty tabs does not move or overwrite production rows. Actual data moves wait for confirmation of fresh counts.

This deliberately applies the brief's explicit instruction: “Show the dry-run counts first so I can confirm before the data moves.” It does not silently authorize unattended deletion from source tabs. The app cannot run while the computer/app is closed. Preview tokens expire after 30 minutes; stale or changed data requires a new preview. A completed operation's receipt can still be recovered after expiration.

## Preservation, responsiveness and failure handling

- The positional workbook reader keeps original headers and order, including duplicate SLA headers. Internally those headers receive distinct canonical keys. Additional existing manual columns and the carry note are retained.
- In-Time is parsed as a local wall-clock datetime, including seconds; no timezone conversion is applied to arrival sorting. Invalid/missing dates go last. Ties use case-insensitive order-number order. Production numbering is regenerated after sorting. Raw capture snapshots keep their original order for receipt and comparison integrity.
- Duplicate orders in one file retain the last physical source row and are logged. Conflicting product groups and missing IDs are skipped and reported. Duplicate active ownership stops maintenance rather than deleting a potentially valid record.
- Production tabs use black text, white fills, bold headers and thin borders. Existing production conditional colors are removed. Other status summaries retain their established colors. Formatting uses batched requests, including after sync.
- Backups, renames, new tabs, source/destination replacements and an operation receipt are submitted together. Network retries use bounded exponential backoff for transient write errors. Reusing the same operation token checks its cloud receipt before replaying changes.
- Genuine existing formulas are identified by their Google Sheets value type and their relative references are adjusted when rows move. Imported formula-looking text and existing literal text remain literal. Unsupported formula relocation stops the operation.
- Confirmation rechecks the source snapshot so a preview cannot knowingly overwrite intervening edits. Existing operation locks prevent overlapping local capture/sync/maintenance writes. Google Sheets does not offer a compare-and-swap transaction against simultaneous human edits: avoid editing affected tabs during the short confirmation write. [Google's batch-update contract](https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate) documents atomic requests and this collaboration limitation.
- Unchanged active production tabs avoid value rewrites and backup copies during ordinary capture sync. Existing raw capture tabs and the receipt ledger use append-only writes when headers are unchanged; archive contents are rechecked before appending. Tables stay paginated. Monthly search is deferred, and completed-order membership uses a set instead of repeated scans through a large ID list. Refresh failures keep the loaded report visible with an offline indication.
- Dismissing one notification does not cancel sync or hide other notices. Dismissals survive navigation in the running app and reset for a new job.
- Backups are not automatically deleted. They consume Google Sheets capacity and should be retained or removed under an explicit retention policy. Names begin `__DataTrace_Backup_`; they are excluded from normal production reports/exports.

## API and storage additions

| Endpoint / storage | Purpose |
| --- | --- |
| `POST /api/monthly-maintenance/preview` | JSON setup/rollover, or multipart workbook import; returns a saved preview ID and counts |
| `POST /api/monthly-maintenance/apply` | Requires `{id, confirmed: true}`; rejects stale/expired previews and recovers committed operations |
| `GET /api/monthly-maintenance` | Recent preview/applied activity and complete move/review details |
| `GET /api/export/monthly?month=YYYY-MM` | Export exactly the selected month's live data and totals |
| SQLite `monthly_operations` | Durable local preview tokens and result reports; included in workspace backup/restore |
| Google Sheets `__DataTrace_MonthlyOps` | Hidden atomic-operation receipts and per-order move log |

All routes inherit the existing desktop loopback authentication. No environment variables or account settings were added.

## Files changed for this addition

| File | Purpose |
| --- | --- |
| `gsheet_dashboard/monthly_production.py` | Canonical month names, local dates, sorting, positional XLSX reader, import/rollover planning, backups, atomic writes, formulas, Excel export |
| `gsheet_dashboard/monthly_sync.py` | Adapt the established capture merge to current month ownership without reseeding September |
| `gsheet_dashboard/monthly_api.py` | Maintenance/export endpoints, durable confirmation previews and month-boundary planning |
| `gsheet_dashboard/tracker_sync.py` | Discover monthly tabs and produce month-aware, arrival-sorted reports; retain the legacy path before setup |
| `gsheet_dashboard/tracker_formatting.py` | Plain production styling and safe formatting retries |
| `gsheet_dashboard/server.py` | Aggregate current production across month tabs, preserve archive reporting, selected-month endpoints and export compatibility |
| `gsheet_dashboard/workspace_backup.py` | Accept monthly operation records during restore |
| `gsheet_dashboard/frontend/src/MonthlyMaintenance.jsx` | Import/rollover preview and confirmation, download state/errors, resumable previews and move activity |
| `gsheet_dashboard/frontend/src/DismissibleNotice.jsx` | Independent keyboard-accessible notification dismissal |
| `gsheet_dashboard/frontend/src/WorkspaceViews.jsx` | Selected-month controls, current-month selection and responsive report search |
| `gsheet_dashboard/frontend/src/main.jsx` | Wire notices, monthly activity and access to setup before the first capture |
| `gsheet_dashboard/frontend/src/StudioWorkspace.jsx` | Preserve the server's chronological default order |
| `gsheet_dashboard/frontend/src/studio.css` | Responsive import and preview layouts |
| `gsheet_dashboard/test_monthly_production.py` | Monthly rules, import fidelity, move/replay/failure, formula and API tests |
| `gsheet_dashboard/frontend/tests/monthly-production.spec.js` | UI confirmation, selected-month export, notification and responsive-window tests |
| `gsheet_dashboard/frontend/playwright.desktop.config.js` | Include monthly UI checks in the existing CI suite |
| `gsheet_dashboard/test_tracker_v2.py` | Update explicit chronological order and formatting-only replay expectations |
| `gsheet_dashboard/test_desktop_alignment.py` | Confirm replay refreshes formatting without rewriting capture data |
| `gsheet_dashboard/test_october_updates.py` | Verify the newly requested plain formatting |
| `gsheet_dashboard/test_production_sync.py` | Update Excel styling assertions; retain data/receipt regression checks |
| `desktop/package.json`, `desktop/package-lock.json` | Version the local build as 2.4.0; dependencies unchanged |
| `docs/TV_TRACKER_MONTHLY_PRODUCTION.md` | Usage, policies, safety limits and implementation inventory |

The earlier uncommitted desktop/UI work has been preserved.

## Live import status

The attached Markdown was available. The two October XLSX workbooks named inside it were not found in the Downloads search. Their stated 119/349 rows and 107/255 incomplete rows are **unverified expectations**, not an executed import report. No live production tabs have been renamed, overwritten or rolled over by this development task. Supply/select the actual workbooks to produce their concrete preview and confirm the live import and rollover.

## Verification recorded on 5 October 2026

- 169 backend tests passed, including 27 new monthly tests covering duplicate headers, text identifiers, duplicate rows, local dates, time-of-day sorting, missing/invalid dates, December rollover, protected September data, unique ownership, stale/expired previews, read-only dry runs, atomic failure, timeout-after-commit recovery, 429 retry, repeated confirmation, later-capture completion, literal text, formula relocation, exports, backup restore, append-only raw history, automatic empty month tabs and month-end preview.
- All 29 desktop browser tests passed with no skipped or flaky cases. New checks cover selected-month downloads and errors, current-month selection, keyboard dismissal, dismissal persistence across navigation, reset after sync, explicit rollover confirmation, and 640/800/1024/1440-pixel widths. Existing capture, comparison, SLA and 100,000-row interaction checks also passed.
- All 13 desktop settings and updater unit tests passed.
- Both extractor fixture checks passed, including pagination and decoy-table rejection. These used controlled responses, not a live TitleVision capture.
- The final packaged app passed 16 lifecycle checks: startup, authenticated loopback, renderer isolation, updates UI/IPC, keyboard use, credential encryption, settings restart, local capture import, saved history, backup export/restore, single instance, shutdown, persistence, diagnostics and theme persistence. The measured startup was 3.2 seconds in one local run; this is not a cross-device performance guarantee.
- Frontend compilation and the self-contained Python-engine build passed. No new packages were installed for this feature.
- These checks use controlled fixtures. They do not establish live import counts, the actual October workbooks' content, Google Sheets account permissions, or a completed production rollover.
- A separate read-only tab check could not start because the earlier referenced `Downloads/service_account.json` file was unavailable. The app's encrypted saved connection was not changed or diagnosed as broken.
