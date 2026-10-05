# Tv Tracker 2.3.0 implementation review

Date: 2 October 2026. Branch: `tv-tracker`. Baseline: `854fd2b`, version 2.2.1.

This local release candidate adds the new desktop workspace and strengthens recovery, diagnostics, imports and release validation. Google Sheets remains the production authority. No Render, PostgreSQL, Neon or Redis service is required. The full roadmap status is in `TV_TRACKER_IMPLEMENTATION_LEDGER.md`; the entire roadmap is not yet complete.

## Master prompt and validation

`TV_TRACKER_MASTER_PROMPT.md` contains the reusable execution brief. It was checked against the repository, refreshed remote branch, existing architecture, ranked roadmap and UI direction before implementation. It defines compatibility constraints and required evidence. Brief validation confirms the instructions are coherent; implementation quality is established separately by testing.

## What changed

- Orders: production table, quick search, attention/product/column filters, sorting, 50-row pages and up to 12 named views.
- Order inspector: current production fields and matches from the latest 100 local captures; moves below the table in narrower windows.
- Overview: actual production counts, statuses, pending sync, capture counts and freshness.
- Shared light/dark/system palette, clearer navigation, accessible control names, focus indicators and reduced motion.
- Existing captures, comparisons, daily/monthly reports, SLA editing, exports, connection settings and updates remain available.
- Background capture discovery preserves search. Failed refreshes retain already-loaded production data with an offline label.
- Activity survives restarts and labels interrupted work. Diagnostics export uses a metadata allowlist that excludes credentials, paths, account names and order contents.

Rendered previews in `output/ui` show the implemented app with synthetic review data, not the user's production Sheet.

## Reliability and recovery

The additive SQLite `operation_history` table retains 200 operation entries with type, timestamps, status, optional capture ID and a coarse failure category. Capture and sync-receipt retention remains unchanged. Startup marks unfinished entries interrupted rather than claiming success.

Connected imports recover existing preview numbering before saving. A separate lock protects capture creation; imports may still queue behind an active sync. Capture/maintenance conflicts return a busy response. Existing conflict/readback and manual-field protections are retained.

Schedule writes use a temporary file and atomic replacement. Invalid containers and more than 48 scheduled entries are rejected. Existing catch-up combines missed times today into one run and does not replay prior days. The app must be running and the computer awake.

Updates initiated from 2.3.0 create `backups/before-update-*.zip` under the engine's maintenance gate. A failed backup leaves the engine available and blocks installation. Users upgrading from 2.2.1 should create a backup first: the new protection applies to update installation initiated by 2.3.0. New backups should be restored using a compatible version; older executables may reject the additional table.

CSV export neutralizes formula-looking values before download. Existing authenticated loopback, DPAPI vault, renderer sandbox, context isolation and navigation restrictions remain intact.

## Dependencies and contracts

No runtime dependency was added or upgraded. Desktop version/output directory becomes 2.3.0. The application ID and Windows profile location remain stable.

| Contract | Behavior |
| --- | --- |
| `GET /api/activity` | Bounded operation metadata, protected by existing desktop authentication. |
| `GET /api/order-history?order=…` | Parameterized exact trimmed, case-insensitive match in latest 100 captures; `events` plus `capture_limit`. |
| `GET /api/desktop/diagnostics` | Authenticated metadata export without raw logs or source records. |
| `POST /api/desktop/shutdown`, `backup:true` | Requires idle state; writes recovery ZIP before shutdown. |
| SQLite `operation_history` | Additive table included in backup/restore. |
| UI preferences | Native appearance/views use the encrypted settings vault across port changes; browser development uses local storage. Excluded from workspace ZIPs. |
| Signing secrets | `TV_TRACKER_CSC_LINK` and `TV_TRACKER_CSC_KEY_PASSWORD`, supplied by an authorized signing owner; none created here. |

CI validates desktop pushes and PRs even if the version already exists. The build job has read-only repository access; a separate publish job runs only on `tv-tracker`, consumes tested artifacts and requires a valid Authenticode installer signature. PR builds receive no signing credentials. Remote CI execution has not been claimed as locally verified.

## Test evidence

| Suite | Result |
| --- | --- |
| Engine | 142 passed, including interruption history, lookup, privacy, restore and failed-update-backup recovery. |
| Settings/updater | 13 passed, including bounded native preference validation. |
| Final browser suite | All 25 passed together after the preference fix, including production refresh, offline data, SLA editing, updates, saved views and 100,000-row search. |
| Extractor | 2 passed: browser/sandbox configuration and actual desktop extractor reading the two-page fixture. |
| Packaged native lifecycle | All 16 checks passed in an isolated Windows profile, including theme/saved-view persistence, privacy, encrypted settings, restart, import, restore and shutdown. |
| Frontend build | Successful; application JavaScript approximately 71.3 kB uncompressed, charts/report modules remain lazy. |
| Dependency advisory audit | Zero reported production npm vulnerabilities for desktop, extractor and frontend on this date. This excludes a complete audit of Python dependencies, the OS and Electron binary. |
| Release workflow | YAML parsed successfully; read-only build permission and dependent publish job verified locally. Remote execution not yet observed. |
| Visual review | Orders and inspector examined in light/dark; responsive tests at 1440/1024/800/640 px. |

An intermediate SLA test failed during concurrent source editing; the stable rerun passed without changing SLA behavior. A scheduled-worker test initially deleted its temporary profile before the journal write finished; it now waits for completion. The extractor harness was updated to use the installed desktop dependency instead of the historical browser-mode package.

## Measurements and limits

Five automated search round trips over 100,000 synthetic records were **1104, 304, 254, 250 and 252 ms**, including automation overhead. The first query builds the row-search cache. Builds also ran on this Windows machine during measurement. This small sample is not a production percentile or reference-device certification. Cold search exceeds the roadmap's 300 ms target.

The final combined browser run, concurrent with native validation and packaging, measured **1153, 464, 371, 363 and 331 ms**. The variation reinforces the need for an isolated benchmark; the 300 ms target is not marked achieved.

The initial native run caught appearance resetting across the randomly assigned engine port. Native preferences were moved into the encrypted vault; the corrected packaged run verifies both theme and saved-view persistence.

The corrected native run measured **9,258 ms** from automation launch to the first usable screen, **472 MB** summed Electron process working sets, four Electron processes, and **0%** reported Electron CPU after a five-second idle observation. Working sets can double-count shared memory and exclude the Python engine; this is not total private application RAM. Packaging ran concurrently. Startup does not meet the roadmap target in this observation. A dedicated reference-machine benchmark is still needed.

There are **198 passing automated tests/checks** across the suites above. No multi-hour soak, 200-run live campaign, complete accessibility audit or five-user study is claimed.

## Files changed

Paths below are relative to the repository root.

| File | Purpose |
| --- | --- |
| `docs/TV_TRACKER_MASTER_PROMPT.md` | Validated execution brief. |
| `docs/TV_TRACKER_IMPLEMENTATION_LEDGER.md` | All 22 ranks and remaining gates. |
| `docs/TV_TRACKER_2_3_0_REVIEW.md` | This handover and evidence. |
| `docs/DESKTOP_GUIDE.md` | Updated navigation, recovery, diagnostics and build guidance. |
| `.github/workflows/desktop-release.yml` | Always-run validation, artifacts, separate publishing/signature gate. |
| `desktop/main.cjs` | Recovery backup before update shutdown and validated preference IPC. |
| `desktop/preload.cjs` | Narrow preference read/save methods. |
| `desktop/settings.cjs` | Bounded preference validation and isolation from connection settings. |
| `desktop/tests/settings.test.cjs` | Preference validation tests. |
| `desktop/package.json`, `desktop/package-lock.json` | Version/output 2.3.0; dependency versions unchanged. |
| `desktop/smoke.cjs` | Current navigation, privacy, theme and native metrics checks. |
| `gsheet_dashboard/operation_journal.py` | Durable bounded operational metadata. |
| `gsheet_dashboard/server.py` | APIs, import coordination, update backup and atomic schedules. |
| `gsheet_dashboard/workspace_backup.py` | Allow journal table in validated restores. |
| `gsheet_dashboard/test_operation_journal.py` | History, privacy, schedule and update recovery tests. |
| `gsheet_dashboard/test_october_updates.py` | Await worker completion before cleanup. |
| `gsheet_dashboard/test_scraper.cjs` | Desktop dependency and isolated portal fixture. |
| `gsheet_dashboard/frontend/src/StudioWorkspace.jsx` | New Overview/Orders/inspector/themes/Activity components. |
| `gsheet_dashboard/frontend/src/useWorkspacePreference.js` | Native durable preferences and browser fallback, with persistence error states. |
| `gsheet_dashboard/frontend/src/studio.css` | Shared visual tokens, layout, themes, focus and motion styles. |
| `gsheet_dashboard/frontend/src/main.jsx` | Navigation, integration, cached/deferred search and refresh context. |
| `gsheet_dashboard/frontend/src/DesktopExperience.jsx` | Dialog labels, diagnostics and schedule guidance. |
| `gsheet_dashboard/frontend/src/workspaceUtils.jsx` | CSV formula neutralization. |
| `gsheet_dashboard/frontend/playwright.desktop.config.js` | Current desktop regression suite. |
| `gsheet_dashboard/frontend/tests/studio-workspace.spec.js` | New workspace, theme, search, CSV and refresh tests. |
| `gsheet_dashboard/frontend/tests/desktop-alignment.spec.js` | Current order-control assertions. |
| `gsheet_dashboard/frontend/tests/desktop-ui.spec.js` | Current navigation and offline assertions. |
| `gsheet_dashboard/frontend/tests/live-sheet-refresh.spec.js` | Inspector reflects live Sheet edits. |
| `gsheet_dashboard/frontend/tests/october-updates.spec.js` | Overview/status summary plus existing reports. |
| `gsheet_dashboard/frontend/tests/production-sync.spec.js` | Production and offline behavior. |
| `gsheet_dashboard/frontend/tests/sync-performance.spec.js` | Portable test URL and current sync control. |
| `gsheet_dashboard/frontend/tests/tracker-v2.spec.js` | Retained production across historical capture selection. |
| `output/ui/Tv-Tracker-2.3-light.png`, `output/ui/Tv-Tracker-2.3-dark.png` | Rendered sample-data UI evidence. |

The existing roadmap PDF in `output/pdf` is a planning input and was not regenerated. Ignored build/test outputs and isolated profiles are not source changes.

## Remaining gates

Public release still requires Windows signing, exposed-key rotation, fresh healthy-portal capture/Sheets acceptance and extended performance/reliability/accessibility/user testing. A Playwright extractor pilot is pending; the production extractor remains Puppeteer. Cloud databases, Redis and a Tauri rewrite are intentionally conditional future work.

No new key, production credential or synthetic record was written to Google Sheets during this implementation. Local success and public publication are separate statuses.

## Build and publication status

The final Windows installer, portable ZIP and complete source ZIP are in `release/2.3.0`. Archive integrity and source-manifest hashes were checked. The portable ZIP's native application files and frontend assets match the final packaged directory. The packaged native source and UI entry also match the checked-out implementation. Update-feed SHA-512 hashes match their artifacts. The source archive passed credential-file/private-key checks and excludes dependency folders and captured workspaces.

Windows reports the installer as **NotSigned**. It is a local review candidate, not a signed public release. This session did not push the source changes, publish a GitHub release, replace the installed application or change the user's production configuration. The source changes remain reviewable in this worktree on `tv-tracker`.

Before installing over 2.2.1, create a workspace backup in the current app. The local installer is `Tv-Tracker-2.3.0-x64.exe`; the full source is `Tv-Tracker-2.3.0-source.zip`. `SHA256SUMS.txt` records the final local artifact hashes.
