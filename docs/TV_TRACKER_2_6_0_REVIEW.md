# Tv Tracker 2.6.0 — incremental upgrade from 2.5.3

Baseline: `7992510` on `tv-tracker`. The working tree was clean and the remote
desktop branch matched this commit. Preserve the Electron/React/Python desktop,
Google Sheets production ownership, local SQLite captures, Windows encrypted
credentials, and the existing installer/profile identity.

## Scope and compatibility

| Priority | Requirement | Implementation / existing foundation |
|---|---|---|
| P0 | Lightweight background work | Opt-in compact status polling keeps counts, omits large detail arrays; full reports and default API responses remain available. |
| P0 | Sheets reads and freshness | Batch formatted production reads (up to 50 ranges per request); share concurrent refreshes; content revisions allow unchanged reads to return metadata only. |
| P0 | Reliable operations | Retain single-instance native lock, process sync lock, operation journal, bounded extraction/HTTP timeouts, and recoverable sync receipts. |
| P0 | Scheduling | Retain IST/network clock and one attempt for missed times today; expose last attempt, outcome and last successful scheduled run from retained history. |
| P0 | Backups and recovery | Save an atomic workspace recovery ZIP before capture deletion; abort deletion if backup fails. Existing backup/restore preserves original capture IDs and receipts. |
| P0 | Measurement | Repeatable synthetic engine benchmark, browser load/search timing, packaged startup/resource measurements, and bounded API latency diagnostics. |
| P1 | Large datasets | Retain pagination, deferred search and lazy charts; unchanged refreshes reuse existing row objects. |
| P1 | Data context | Overview/Data Sheets source opens the configured Google spreadsheet; explicit Refresh; accurate offline and disk-cache warning states. |
| P1 | Interface | Preserve established layout and calm teal/neutral appearance; add aligned, keyboard-accessible table controls. |
| P1 | Tables | Persist column visibility, widths, identifier pinning and text wrapping; export schemas and data are unaffected. |
| P1 | Accessibility | Focusable table scroll region, labelled controls, Escape closes layout panel, readable theme states and narrow-window checks. |
| P1 | Offline use | Retain cached production and local capture workflows; malformed cache does not prevent online recovery. |
| P1 | Credentials | Retain DPAPI vault and authenticated loopback service. Diagnostics include route templates, never query strings or order contents. |
| P2 | Reusable components | Dedicated table-layout component/hook/styles and shared production-read coordinator. No broad business-logic refactor. |
| P2 | Themes | New controls use existing shared theme tokens; light/dark and responsive regression coverage. |
| P2 | Diagnostics | API request counts/errors/mean/max latency; operation duration and accurate activity-loading feedback. |
| P2 | Delivery | Version 2.6.0 with compatible app/profile identity; existing updater, lifecycle, recovery and installer checks. Public automatic release retains the signing gate. |

No dependencies, database migration or new user configuration are required.
`uiPreferences.tableLayout` is an optional validated addition. Existing profiles
without this preference use the familiar compact table.

### Reporting invariants

The first valid later preview where an observed order disappears supplies inferred
Out Time. Cancelled/suspended exceptions and precise manual times remain intact.
Only completed orders with valid timing receive Free Site; equality at the SLA
deadline is On Time. Invalid timing stays unclassified. Monthly views keep the
Full Search production schema, including custom columns. Existing exports,
worksheet names, retained rows, report periods, matching and comparisons remain.

## Verification evidence

Baseline: 186 backend tests, 20 desktop tests and 50 UI tests passed. Test fixtures
use disposable profiles and mock external writes. The initial sandbox blocked
dependency reads/subprocesses; reruns with the existing runtime completed.

The first full upgraded UI run exposed mocks that matched `/api/state` without
allowing its new optional query string. Those fixtures now match the pathname;
assertions remain intact. Visual inspection also corrected checkbox-label layout.

Final local checks:

| Check | Result |
|---|---|
| Backend regression suite | 201 passed |
| Desktop settings/updater unit suite | 21 passed |
| Extractor fixture suite | 2 passed |
| Browser regression coverage | All 57 cases passed across the full run and targeted rerun: 53 initially passed; 21 targeted cases then passed, including all four corrected fixtures and all seven new cases. |
| Final light/dark visual checks | 2 passed after waiting for the fully rendered Overview; 390, 760, 1024 and 1440 px viewports checked. |
| Packaged native lifecycle | Passed; no renderer errors. Import, export/restore, single instance, encrypted settings, theme/table preference persistence, production URL handoff, restart and shutdown checked. |
| Locked/corrupt connection recovery | Passed, including accessible Updates, encrypted backup recovery and a second restart. |
| Stalled-engine shutdown | Passed in 7.9 seconds; engine stopped and the capture survived restart. |
| Installer/update artifacts | Product version 2.6.0, source ZIP integrity and installer SHA-512 against latest.yml verified. |

The workbook browser-handoff test intercepts the external open request and checks
the exact configured URL; browser tests intercept the destination too. Neither
test contacts the production workbook. Updated controls also preserve CSV data,
column ordering, active filters, selected order, pagination and scroll on refresh.
Existing regression suites cover reporting, spreadsheet schema/formatting,
monthly setup, update UI and 100,000-row pagination/search.

Benchmark dataset: 7,000 synthetic production orders, 35 captures of 350 rows.
Recorded before/after reporting SHA-256 is identical:
`954b8a18fb4f7d32589e9baed8bfbbee2ff0ec36f632ee6ed7f5ddb08ededfd3`.
An unchanged cached response is 237 bytes compared with 1,728,430 bytes for the
full response (99.986% smaller). The unchanged response avoids the full copy.

| Fixture measurement | 2.5.3 baseline | Final 2.6.0 run |
|---|---:|---:|
| Engine app creation | 80.54 ms | 93.66 ms |
| Full status response, median | 5.13 ms | 13.95 ms |
| Saved capture load, median | 4.75 ms | 8.42 ms |
| Full warm cache response, median | about 73 ms | 90.16 ms |
| Unchanged cache response | unavailable | below 0.01 ms median, 0.02 ms max |
| Report calculation, median | 860.06 ms | 1202.96 ms |

These runs were not performed under identical machine load. Earlier upgrade runs
were closer to baseline (73.65 ms warm cache, 895.14 ms reporting); build activity
also produced slower samples. No general startup, reporting or CPU speedup is
claimed. Payload reduction and unchanged-response work avoidance are the
demonstrated improvements. These are local fixture measurements, not Google
network latency or a promise about every user's computer.

The packaged app reached its tested initial screen in 5.18 seconds. The native
smoke sample reported four Electron processes, 617 MB working set and 0% idle
Electron CPU; it is not a total-system memory measurement. The browser fixture
loaded 7,000 rows in 1.72 seconds and filtered to one order in 0.54 seconds,
including browser automation/assertion time. There is no comparable baseline for
these two UI measurements.

Local evidence lives in `.desktop-build/upgrade-evidence/`: light/dark Overview
and table screenshots, `engine-performance.json` and `browser-performance.json`.
Packaged evidence is under `desktop/test-output/`. These generated files are
excluded from source control and the source archive.

## Operational notes

- Local deliverables are under `release/2.6.0/`: the Windows installer, portable
  ZIP, source ZIP and update manifest. Quit Tv Tracker before running the installer;
  afterward use the normal Tv Tracker shortcut. Development launch and portable
  packaging remain supported. This verification did not replace the user's
  installed 2.5.3 app or alter its profile.
- Click Live Google Sheets on Overview or Data Sheets to open the saved production
  URL in the default browser. Offline source labels can still open that workbook.
- Columns & layout changes affect the display only. Reset layout restores defaults.
- Capture deletion writes `workspace/backups/before-delete-<timestamp>.zip` first.
  Settings > Local data & recovery > Open data folder locates it. Restore backup
  restores the whole workspace as of that backup, and retains a safety copy of the
  workspace being replaced. CSV/Excel captures can be downloaded again from the
  restored database. Recovery copies are not silently pruned.
- To roll back the application, quit it and reinstall 2.5.3. Profile paths and
  database schema are compatible. Keep a workspace backup before any downgrade.
  Display preferences added in 2.6.0 are ignored by 2.5.3.
- Scheduled last-success information reflects the retained 200-operation journal.
- API diagnostic metrics are in-memory aggregates and reset when the engine restarts.
- Live extraction, production writes and production schedule changes are excluded
  from this upgrade's fixture verification. Portal availability and production
  credentials still determine real capture success.
- Repository signing secrets were absent when checked. Public automatic publishing
  requires the existing authorized Windows signing identity. The signing gate is
  retained; Authenticode confirms this local installer is unsigned. Configure
  `TV_TRACKER_CSC_LINK` and `TV_TRACKER_CSC_KEY_PASSWORD` with an authorized Windows
  signing certificate and password, then rerun the desktop release workflow.
  Source publication alone does not make an update available to installed users.

## Files

Backend: `production_cache.py` (revision reads and offline accuracy), `sheet_reads.py`
(bounded batched reads), `monthly_production.py`/`tracker_sync.py` (read adapters),
`server.py` (optional compact APIs, freshness, diagnostics and deletion safety),
`operation_journal.py` (schedule history), `workspace_backup.py` (atomic recovery
copies), `request_metrics.py` (redacted latency counters).

UI: `productionResource.js` (shared reads), `TableLayout.jsx`/`tableLayout.css`
(persistent table controls), `WorkspaceShell.jsx` (source link/refresh),
`StudioWorkspace.jsx` (table/activity integration), `main.jsx` (refresh/status/
schedule/recovery feedback), `workspaceUtils.jsx` (combined abort and timeout).

Desktop: `settings.cjs` (preference validation), `package.json`/`package-lock.json`
(version), `benchmark_workspace.py` (disposable measurement).

Tests: `test_upgrade_reliability.py`, `desktop/tests/settings.test.cjs`, `desktop/smoke.cjs`,
`frontend/tests/upgrade-workspace.spec.js`, the desktop Playwright configuration,
and query-aware routes in `desktop-ui.spec.js`, `desktop-updates.spec.js` and
`studio-workspace.spec.js`. This review is `docs/TV_TRACKER_2_6_0_REVIEW.md`.
