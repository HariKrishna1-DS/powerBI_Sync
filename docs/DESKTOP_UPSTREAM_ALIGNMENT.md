# Tv Tracker 2.1 — upstream alignment report

## Repository analysis

Analysis began before application edits. The existing desktop work was first preserved in commit `1fa4c59` (based on local Sheets-only reconciliation `969e0f1`). The remote was fetched, its history and changed files inspected, and `origin/main` at `db0c27457dd56ef4726490acf9df0f41e85d14be` was merged into a separate desktop branch. The final user-requested branch is **`tv-tracker`**; Git cannot use the space in the display name **Tv Tracker**. No changes are being merged or pushed to remote `main`.

The recent sequence reviewed, rather than just the newest diff:

| Commit (IST commit date) | Change and purpose |
| --- | --- |
| `2de4bef` — Sep 30, 15:36 | Flask/React dashboard, capture state and scheduled synchronization. Establishes the browser workflow reused by the desktop engine. |
| `11b28d0` — Sep 30, 16:47 | Reflect human Sheet edits and allow current-minute triggers, addressing stale reports and scheduling delay. |
| `1481bf3` — Sep 30, 17:28 | Recover numbered captures and schedule settings after Render storage loss. Desktop adapts recovery to durable per-user storage. |
| `ba5208e` — Oct 1, 12:54 | PostgreSQL experiment, Sheets API and SLA editing improvements. The desktop already removed the hosted database; it stays removed. |
| `5be43dc` — Oct 1, 14:54 | SLA comment API, data and frontend changes; basis of the existing desktop work. |
| `db0c274` — Oct 2, 11:54 | Tracker v2, historical baseline imports, stable tab names, local receipts, revised status/SLA rules, shared colors, network IST clock, and revised reports/charts. This was the one newly fetched remote commit after the prior desktop base. |

These are Git commit timestamps, not separately verified GitHub push-event timestamps. The history, actual code, tests and configuration were used to infer purpose where commit messages were broad.

## Architecture comparison and implementation plan

The plan was presented before implementation. The browser project and desktop share React/Vite and a Flask sync engine. Desktop additionally owns an Electron main/preload boundary, a DPAPI vault, authenticated loopback API, a frozen Python runtime, tray/lifecycle management, offline cache, and native backups. Desktop stores writable files in the user profile, not beside the frozen executable. Google Sheets remains production storage; local SQLite is the capture/retry/audit store.

| Upstream behavior | Desktop action and result |
| --- | --- |
| Stable tracker titles and baseline XLSX files | Package both workbook inputs; migrate only exact shipped aliases on sync, support custom titles, read legacy tabs without renaming on reads. |
| Tracker v2 identity/status rules | Adapt by trimmed/case-insensitive Order Number; retain disappeared orders, preserve manual columns/formulas, use valid Out Time as completion evidence. Clear Comments/Assignee/iAssignee per upstream rule; keep raw capture values. |
| Append-only raw capture history | Append to Sheet1 and All Products in the tracker update batch; compare archive content on retry. Empty captures use a reversible archive marker. |
| Local audit and failed sync jobs | Extend the existing SQLite schema, preserve old successful receipts, persist staged/committed reports and bounded failures; keep backup compatibility. |
| Automatic import/extraction sync | Serialize queued work; older failed captures block newer automatic work. Explicit retry can drain earlier failures in order. Failed uploads get at most three attempts. |
| Relative SLA/deadlines | Normalize against the capture timestamp; do not invent a wall-clock anchor. Use On Time/Missing; preserve compatibility with old stored Missed values. |
| Network Indian time | Use HTTPS Date plus monotonic elapsed time in backend and UI. Initial synchronization is required for schedules; an established anchor survives a temporary outage. |
| Data sheets and chart flow | Data sheets is the landing view with Status Report. Remove Overview navigation. Add selected-period, three-period charts with values. Retain deferred loading, offline banners, pagination and keyboard settings. |
| Local comparison/review | Changes compares local captures by Order Number; Sync activity shows the latest durable local receipt and review items. |
| Production export | Refresh report data from live trackers, export all ordinary tabs, confirm safe unique Excel tab aliases, apply shared row colors to Free Site too. Filtered CSV uses the visible production rows. |
| Native product rename | Tv Tracker appears in renderer, window, menus, tray, installer and ZIP names. Preserve legacy profile and installer ID to keep existing data and settings. |

Planned files: sync/store/reporting/server modules, desktop settings/build configuration, React views, backup/cache, tests and documentation. No new dependency was necessary. Main risks were repeated uploads after schema migration, runtime writes inside the installation, conflicting configured tab names, failed/reordered uploads, ambiguous completion evidence, lost Google replies, and changed SLA month semantics. Tests below address these with isolated fixtures.

## Dependencies, configuration and data flow

- No new npm or Python dependency; existing locked `requests`, `pandas`, `openpyxl`, `gspread`, Electron, Flask/Waitress, and PyInstaller are reused. Desktop package version is **2.1.0**, package name `tv-tracker`, product name `Tv Tracker`.
- Packaging now includes `status_colors.json` and both upstream `default_trackers/*.xlsx`. Output is `release/2.1.0/`.
- No new required environment variable. Existing native settings supply `DATATRACE_DATA_DIR`, desktop token, spreadsheet ID, tracker titles and credentials; the internal names remain compatible.
- Exact old default tab names are upgraded to month-independent names. Other custom names remain unchanged.
- Existing `previews`, `sla_corrections`, and `sync_receipts` stay compatible. Added `sync_jobs`, `sync_reports`, `sync_failures`; old successful receipts are migrated as already synced. Old and new backup archives remain readable.
- Added read-only `/api/sync-reports`; `/api/state` includes network clock and failed-sync metadata. Existing desktop authentication and same-origin protections apply.
- Export can return `409` with `requires_short_names` and `proposed_names`; confirmation retries with `short_names=true`. Sync completion responses omit private readback payloads.
- Production flow: capture → durable local preview → ordered worker → staged local report → atomic tracker/raw/report batch → verify actual tracker values → commit local receipt → invalidate cached reports. A lost reply is resolved from archived capture content plus staged expected tracker cells.
- The profile remains `%APPDATA%/DataTrace Studio`, and installer/startup identity remains `com.datatrace.studio`. Startup configuration is refreshed for the renamed executable; isolated test profiles skip Windows startup registration. These internal compatibility names intentionally differ from the displayed brand.

## Testing and final behavior review

The full backend suite passed **124 tests**. Coverage includes existing extraction/scheduling/reporting/SLA workflows, missing/duplicate data, failed network writes, unchanged manual cells, current Google Sheet edits, lost replies, malformed/ambiguous data, old schema and backup migration, local receipts, reserved metadata columns, empty capture replay/recovery, wrong-value readback with unchanged IDs, configured tracker names, failure ordering and explicit retry. Credential-free API authorization tests verify rejection of unauthenticated desktop requests. Error messages in test logs are intentional injected failure cases.

**5 desktop settings tests passed**, including encrypted vault boundaries and exact legacy-default migration while preserving a custom name. **9 production UI tests passed**, covering the new clock/charts, retained orders, offline cache, 25,000-row capture search, keyboard setup, deferred charts, local audit flow, filtered CSV, retry target and export confirmation/cancellation. Production Vite build passed: initial JavaScript about 274 KB, deferred chart/report chunks about 389 KB (uncompressed).

Packaged runtime checks and release measurements are recorded in [DESKTOP_VALIDATION.md](DESKTOP_VALIDATION.md). Live production authentication and writes were not performed; mock Google APIs and isolated local profiles were used. No real TitleVision account was accessed. Real-world service permissions, portal login/MFA and API quotas still require a controlled live check. The packaged Chrome fixture passed; installed Edge failed to establish a debugging connection on this machine, so automatic browser selection now prefers Chrome. Edge-only environments remain unverified.

## Intentional differences and remaining limits

1. No PostgreSQL, Render requirement, automatic cloud deployment, or external hosted backend. Retained legacy browser/Streamlit utilities are optional and outside desktop startup.
2. Existing desktop month reports continue assigning SLA completions to their actual Out Time month, including orders received in a different month. The new upstream arrival-cohort SLA grouping would regress this established behavior and was not copied.
3. Relative SLA without a capture timestamp stays unresolved instead of depending on the current computer date. Undated rows keep the existing Undated label.
4. Unconfigured startup does not create/seed production trackers. Baselines are integrated during actual synchronization. Baseline files contain upstream historical tracker data and are intentionally present in packages/source ZIPs. They parse as 1,311 Full Title rows and 5,468 Remaining rows; Remaining contains 87 repeated identities. Sync keeps a single identity and records conflicting baseline rows locally for review.
5. Automatic CSV scanning on every store construction was not adopted: durable SQLite and explicit cloud recovery avoid repeated disk work and resurrecting deleted captures.
6. Cloud audit-tab deletion and historical refresh utilities are included from upstream but were **not run**. Existing Sheet tabs/data were not deleted. Optional destructive maintenance must be deliberately invoked separately.
7. Native backup/restore, offline copies, secure credential handling and installed Edge/Chrome extraction were retained. The app has no direct Power BI service authentication; it supplies the existing workbook/CSV formats for downstream reporting.
8. One active writer per spreadsheet remains the operating requirement. The queue/profile lock serializes this app, not unrelated machines or human edits. Readback mismatches are retained for review rather than acknowledged as successful.
9. The generated Windows build is unsigned; installation/uninstallation on a second clean machine and live customer service access are outside the local validation performed. No zero-defect claim is made.

## Files changed

This inventory is relative to the saved desktop checkpoint `1fa4c59`. It includes upstream files brought in by the merge as well as desktop adaptations. No source files were deleted. Existing tracked sample exports and the legacy workspace archive came from upstream; they are not the new desktop deliverables.

| File | Purpose |
| --- | --- |
| `DataTrace_Workspace.zip` | Legacy archive updated by upstream; retained as inherited history, excluded from new source ZIP. |
| `PROJECT_ARCHITECTURE.md` | Tv Tracker architecture and clearly labeled historical web reference. |
| `README.md` | Desktop branch, product name, current workflow, setup and contribution entry point. |
| `desktop/build_backend.py` | Package shared palette and baseline workbook runtime assets. |
| `desktop/main.cjs` | Rename native menus/window/tray, preserve profile/app/startup identities, isolate startup settings during tests, and prefer validated Chrome after an explicit browser override. |
| `desktop/check-packaged-browser.cjs` | Match native browser selection: explicit override, installed Chrome, then Edge. |
| `desktop/package-lock.json` | Matching desktop package name/version; dependency versions unchanged. |
| `desktop/package.json` | Tv Tracker metadata, 2.1.0 release filenames and versioned output directory. |
| `desktop/settings.cjs` | Stable defaults and exact old-default migration in the encrypted vault. |
| `desktop/smoke.cjs` | Packaged lifecycle checks plus renamed title/brand assertions. |
| `desktop/tests/settings.test.cjs` | Legacy tracker default migration and preservation of custom names. |
| `docs/DESKTOP_GUIDE.md` | Installation, workflows, clock/retry rules, upgrade compatibility and release paths. |
| `docs/DESKTOP_UPSTREAM_ALIGNMENT.md` | Commit analysis, pre-implementation mapping, adaptations and full file inventory. |
| `docs/DESKTOP_VALIDATION.md` | Current validation results and limits, replacing the previous-release record. |
| `docs/TV_Search_Sync_Prompt.md` | Upstream v2 production requirements; source material studied, not standalone execution authority. |
| `gsheet_dashboard/README.md` | Upstream browser/sync reference documentation. |
| `gsheet_dashboard/SYNC_SETUP.md` | Upstream Sheets and tracker setup instructions. |
| `gsheet_dashboard/datatrace_sync.py` | Tracker v2 entry point, shared colors, suspended metadata, Excel/timezone parsing and deterministic SLA anchors. |
| `gsheet_dashboard/default_trackers/co_update.xlsx` | Upstream Remaining Products historical baseline input, bundled at runtime. |
| `gsheet_dashboard/default_trackers/full_search.xlsx` | Upstream Full Title historical baseline input, bundled at runtime. |
| `gsheet_dashboard/desktop_engine.py` | Rename the direct-engine launch instruction to Tv Tracker. |
| `gsheet_dashboard/frontend/index.html` | Browser/native web-content title Tv Tracker. |
| `gsheet_dashboard/frontend/playwright.production.config.js` | Include upstream and desktop integration browser regressions. |
| `gsheet_dashboard/frontend/src/DesktopExperience.jsx` | Rename native settings UI and update quick-action navigation. |
| `gsheet_dashboard/frontend/src/WorkspaceViews.jsx` | Period chart navigation/value labels and Missing SLA vocabulary while preserving offline handling. |
| `gsheet_dashboard/frontend/src/main.jsx` | Tv Tracker branding, Data sheets landing/Status Report, local audit/compare, failure retry, clock, export confirmation and consistent filters. |
| `gsheet_dashboard/frontend/src/style.css` | Upstream chart controls and shared row-color styling. |
| `gsheet_dashboard/frontend/src/workspaceUtils.jsx` | Import the shared palette; attach monotonic receipt time to clock responses. |
| `gsheet_dashboard/frontend/tests/desktop-alignment.spec.js` | Retry target, filtered production CSV and export confirmation/cancel regressions. |
| `gsheet_dashboard/frontend/tests/october-updates.spec.js` | Network IST and labeled chart/period navigation regressions from upstream. |
| `gsheet_dashboard/frontend/tests/production-sync.spec.js` | Production integrity and updated local Sync activity expectations. |
| `gsheet_dashboard/frontend/tests/tracker-v2.spec.js` | Ensure selecting old captures cannot change current production totals. |
| `gsheet_dashboard/indian_clock.py` | Upstream HTTPS time anchor advanced by a monotonic clock. |
| `gsheet_dashboard/migrate_trackers.py` | Optional upstream tracker migration utility; not executed. |
| `gsheet_dashboard/order_reporting.py` | Prepare immutable capture metadata and derive reports from tracker rows. |
| `gsheet_dashboard/preview_store.py` | Backward-compatible receipt migration, staged/committed audits, failures and ordered pending work. |
| `gsheet_dashboard/production_cache.py` | Retain offline cache across exact default-title upgrades and synchronize cache reloads. |
| `gsheet_dashboard/queue_data_sheet2.csv` | Inherited upstream queue export update; not used as desktop production truth or shipped in new source ZIP. |
| `gsheet_dashboard/queue_data_sheet2.xlsx` | Inherited upstream queue export update; not bundled in desktop runtime or new source ZIP. |
| `gsheet_dashboard/refresh_production_trackers.py` | Optional upstream historical cleanup/reconciliation utility; not executed. |
| `gsheet_dashboard/remove_cloud_audit_tabs.py` | Optional upstream audit-tab backup/removal utility; not executed. |
| `gsheet_dashboard/server.py` | Serialized ordered sync, bounded failure handling, network clock, local audit API, Sheets reports, export confirmation and retained desktop auth/cache. |
| `gsheet_dashboard/sla_comments.py` | Upstream Missing vocabulary while accepting old Missed values. |
| `gsheet_dashboard/status_colors.json` | One palette for web UI, Sheets conditional rules and Excel. |
| `gsheet_dashboard/streamlit_app.py` | Inherited upstream report/SLA compatibility changes to the optional browser app. |
| `gsheet_dashboard/sync_config.py` | Month-independent exact defaults while retaining runtime paths and custom environment settings. |
| `gsheet_dashboard/test_desktop_alignment.py` | Upgrade/backup, empty replay, corrupt readback, naming, reserved headers and ordered retry regressions. |
| `gsheet_dashboard/test_new_features.py` | Inject deterministic network time for schedule tests. |
| `gsheet_dashboard/test_october_updates.py` | Upstream palette, dates, export, clock and scheduling checks; normalize hex-color expectation. |
| `gsheet_dashboard/test_previews.py` | Order Number comparison fixtures and deterministic queued/scheduled completion. |
| `gsheet_dashboard/test_production_sync.py` | Confirmed export names/new palette and bounded retry failure assertions. |
| `gsheet_dashboard/test_scheduled_capture.py` | Inject clock for the existing schedule boundary/recovery tests. |
| `gsheet_dashboard/test_sync.py` | Update legacy expected colors to the shared upstream palette. |
| `gsheet_dashboard/test_tracker_v2.py` | Upstream status, preservation, append, idempotency, lost-reply and automatic sync regression suite. |
| `gsheet_dashboard/tracker_formatting.py` | Upstream conditional-format reconciliation without duplicating owned rules. |
| `gsheet_dashboard/tracker_sync.py` | Adapt baseline/identity merge, atomic history writes, local staged receipts, writable paths, custom names and verified idempotent readback. |
| `gsheet_dashboard/update_row_colors.py` | Upstream maintenance utility now uses the shared formatting rules. |
| `gsheet_dashboard/update_sla_columns.py` | Upstream SLA maintenance changes. |
| `gsheet_dashboard/workspace_backup.py` | Recognize new local tables and upgrade old databases on restore. |
| `make_bundle.py` | Versioned Tv Tracker source archive with explicitly included baseline inputs and integrity manifest. |
| `render.yaml` | Inherited upstream removal of hosted database configuration; unused by desktop. |
