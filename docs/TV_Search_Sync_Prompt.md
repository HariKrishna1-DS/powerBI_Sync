# TV Search Production Sync — Google Sheets specification (v3)

Analyze the queue, preserve production history, and automatically reconcile it with Google Sheets. Implement and validate these rules in DataTrace. Google Sheets is the only production reporting source. No PostgreSQL, Neon, database URL, database service, or database driver is required.

## 1. Storage and tracker names

Use the spreadsheet configured in `gsheet_dashboard/sync_config.json`. In this application the two master trackers are tabs in that spreadsheet:

| Product | Authoritative tracker tab |
| --- | --- |
| Full Title / Full Search | `TV_Search_Production_Report_Full_Search_-_September_2026` |
| Every other nonblank product | `TV_Search_Production_Report_C-O_and_Update_-_September_2026` |

The configured `full_tracker_title` and `remaining_tracker_title` may override these names for another reporting period. A product slicer changes the screen only; it never excludes orders from sync.

Migrate existing tracker tabs by title and header shape. The old `Full Title`, `Remaining Products`, or `TV Orders` tabs may contain tracker data that must be preserved. Rename a tracker `Sheet1` only if its headers identify it as a production tracker (`No`, `Order Number`, `Status`, without raw `Task Status`). A raw `Sheet1` remains raw. Never choose or rename tabs by their position. Do not change `Escalations` or unrelated tabs.

`Full Title` and `Remaining Products` are also short, generated report views. They are distinct from the long master tracker names after migration.

Retain numbered previews locally as a retry cache, with CSV/XLSX files and a local SQLite index. Local previews and cached corrections are never production reporting sources. Save successful snapshots to Google Sheets as well so all synced preview history can be recovered after loss of local storage.

## 2. Tracker columns

`No | Date | Order Number | TraceQ Id | State | County | Client | Online/Ground | Product | Status | ETA | Comments | Assignee | Searcher | Clarification Requested | Shift | Process date | Review/QC | Expense | In-Time | Out Time | SLA Expiration | Free Site | review`

Keep additional existing columns. Trim Order Numbers and compare without case sensitivity. Preserve their stored spelling. Do not match by task, parcel, or arrival time during production sync.

Reject a tracker containing duplicate Order Numbers or duplicate/blank headers before writing. Quarantine blank or duplicate Order Numbers in a preview, list their reasons, and continue with valid orders. A new order without a product cannot be routed and must be flagged.

## 3. Append and update rules

Append new orders at the bottom of the correct tracker. Continue its highest existing serial number. Fill the preview-owned fields; leave manual fields blank. Never delete, reorder, or renumber existing rows. Existing serial gaps require review rather than automatic repair.

For an existing order, only automation-owned fields may change: `Status`, `ETA`, `Comments`, `Assignee`, `Out Time`, `SLA Expiration`, and derived `Free Site`. An absent input column does not erase a tracker value. Explicit blank values in a supplied update column may clear that field. Preserve manual data, custom columns, and formulas by updating only allowed cells.

If an order changes product groups, keep it in its existing tracker and flag it for review. Do not silently move or duplicate it.

An order missing from the latest preview stays exactly as it is. Record it under **Not in latest preview**. Disappearance is never evidence of completion and never supplies an Out Time.

Compare each new successful preview with the last successfully synced preview, including across days. Failed previews remain in the local outbox and are processed in order before newer previews. A previously committed preview is a no-op; an older unsynced preview must not overwrite a newer committed one.

## 4. Status rules, first match wins

1. Workflow suspension (`WorkflowSuspended` / `Is Suspended` true, or the portal's explicit Workflow Suspended status) gives **Awaiting for Clarification**.
2. Task Name **Search** and Task Status **Available** gives **Search In Progress**.
3. Otherwise retain the existing tracker status.

Every new order starts **Search In Progress**, except a workflow-suspended order. Task Suspended does not imply workflow suspension. CRSP2, SearchFix, N/A, Typing Module, queue disappearance, and other task names do not imply completion.

Completion is an explicitly recorded tracker status. For an existing completed order, update Out Time only from a valid preview Completed Time timestamp. A numeric duration, blank, or non-date text does not establish a completion timestamp. Never invent today's date.

| Status | Fill |
| --- | --- |
| Awaiting for Clarification | `#A66AD3` |
| Available | `#D9EAD3` |
| Search In Progress | `#FFFFFF` |
| In Progress / Typing in Progress | `#00B050` |
| Task Suspended | `#C9DAF8` |
| Completed and Delivered | `#FFF2CC` |

Apply the status fill consistently to processed tracker rows and generated reports. Match the Free Site fill separately.

## 5. SLA and Free Site

Keep the full time of day in In-Time, Out Time, and SLA Expiration. Dates use month/day ordering. Offset-bearing capture timestamps are converted to India Standard Time; timezone-free portal timestamps are interpreted consistently in that same reporting context.

Convert absolute SLA timestamps directly. For an SLA without a year, use the preview capture year. For countdowns such as `7h 41m`, resolve the expiration from the immutable preview capture timestamp, not the retry time, arrival time, or completion time. A leading negative sign applies to the entire duration (`-1d 4h 0m` means subtract 28 hours).

For an order processed in this pass:

- Blank Out Time: leave Free Site blank, including when its SLA is overdue.
- Valid Out Time and valid SLA: **On Time** when Out Time is less than or equal to SLA; otherwise **Missing**.
- Negative countdown with a valid Out Time: **Missing**.
- `PAUSED`, invalid dates, missing SLA, or ambiguous Out Time: leave Free Site blank and list the reason in **Needs review**.

On Time is green; Missing is red. Recalculate on each new pass. An order absent from the preview remains untouched. The monthly UI may label the canonical sheet value `Missing` as `Missed`; both mean the same SLA category.

## 6. Snapshot history and audit

Append raw snapshots to `Sheet1` and `All Products`, tagged with Preview and Captured At. Preserve earlier raw rows and union new input headers without deleting old columns. These two metadata names are reserved input headers. Preserve any legacy raw rows already in those tabs.

Store preview ID, name, capture time, source, input headers, fingerprint, and pass report in `__DataTrace_Previews`. Use this index and raw Sheet1 history to recover all synced previews with their original IDs and capture times. A changed payload under an already used preview name is a conflict, not a replacement.

For each successful pass, append to Google Sheets `Changes`:

- Preview name and timestamp; orders scanned, added, updated, and unchanged.
- Updated orders with old and new status.
- Orders from the preceding preview absent from this one.
- Unprocessed/ambiguous rows and reasons; also append these to `Needs review`.

The Changes production view reads this Sheet log. Keep raw preview comparison as a separately labeled inspection tool. Preview deletion is an explicit human action only; deleting a local preview does not delete the cloud archive or tracker rows.

## 7. Reports and exports

Overview, Data sheets, Daily Orders, Monthly report, Status Report, and Changes read Google Sheets. If Sheets is unavailable, show an unavailable/error state instead of presenting local previews as production results.

Daily and monthly order totals group unique retained tracker orders by their recorded Date/In-Time. Keep unparseable dates in an **Undated** bucket. Their sums equal the combined tracker total. Count completed orders from the actual tracker status, never from missing previews. SLA completion counts use actual Out Time; an order arriving in one month and completing in another belongs to the appropriate month for each metric.

After sync, regenerate the report views and check their totals against the trackers. Preserve the preview name and sync timestamp in Status Report. Direct manual Sheet edits must appear on the next live dashboard refresh and in exports.

Export `Production_data.xlsx` with short report tab names, raw preview history, and status/Free Site fills. Export values from the current Google Sheet. Use the existing short `Full Title` and `Remaining Products` report views; do not truncate or rename the long master tracker tabs to fit Excel. Other tabs exceeding Excel's 31-character limit require an explicit export name. Raw preview downloads remain immutable snapshot downloads and are labeled separately.

## 8. Automatic operation and validation

Automatically sync every newly saved extraction, import, and scheduled AutoLogin capture. No confirmation or sync-button click is required. Keep the manual retry button for failures.

Use a writer lock shared by backend and CLI processes on the same host, and a persistent local outbox. Run one backend writer per spreadsheet. Google Sheets alone does not provide a distributed compare-and-swap lock for multiple independent deployments.

Plan and validate tracker changes, snapshot history, reports, audit entries, and the preview receipt before sending one atomic Google Sheets batch. Use fixed cell ranges and explicit sheet IDs. On transient network/quota/server failures, retry up to three times with backoff. If a response times out after committing, verify the fingerprint receipt before replaying the batch. Never discard a failed preview. Display a failure alert in job status and retain it for unattended retry while the backend runs. No external notification channel is configured.

Verify that successful sync has no newly introduced duplicates, retains every previous tracker row and preview, preserves manual cells, records ambiguous values without guessing, matches tracker status/Out Time/Free Site on readback, and produces matching daily/monthly/status totals. Existing invalid serials and formula errors require review. Renamed standard Sheet references are updated by the Google Sheets rename operation; generated reports always use configured tracker titles.

When the local store is empty, recover cloud history before assigning a new preview number. If that connection is unavailable, retry after access is restored rather than reusing a number that may already exist.

The scheduler runs only while the backend is running. On hosting with ephemeral storage, unsynced local previews require a persistent disk. Google Sheets preserves synced history; it cannot recover a preview that never reached Sheets.
