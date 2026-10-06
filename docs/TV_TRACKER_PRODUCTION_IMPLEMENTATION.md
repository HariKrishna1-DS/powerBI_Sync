# Tv Tracker — PDF improvements and production hardening

Date: 6 October 2026. Base: `tv-tracker`, commit `6ba9757`, version 2.6.0. Candidate: **2.7.0**.

**Outcome: the PDF reporting features are implemented in a local development candidate, with substantial reliability safeguards. This is not yet a certified production release.** The installed profile and production workbook were not replaced or migrated during implementation. No release was published.

The complete executable engineering prompt is in [TV_TRACKER_PRODUCTION_MASTER_PROMPT.md](TV_TRACKER_PRODUCTION_MASTER_PROMPT.md). All four pages of `updates_traker.pdf` were extracted and visually inspected before implementation. Its features take priority over the broader hardening list.

## PDF requirements and implementation

| Priority | Requirement | Implemented behavior | Evidence |
|---|---|---|---|
| 1 | Daily Orders vocabulary | Date, Received, Completed, Clarification, Cancelled, Vendor Pending, In-House Pending, On time SLA, Missed SLA. One shared calculation serves reports and exports. | Backend arithmetic tests; browser tests; real packaged import/report test |
| 2 | Capacity Report | New navigation view, daily rows, monthly totals, calendar YTD, editable default/date targets, received/completed bars and capacity lines; matching Excel and Sheets chart requests. | Backend/export tests, rendered app inspection, packaged totals/export test; real Google API accepted the chart in the isolated QA workbook |
| 3 | Multiple Excel files | Up to 20 `.xlsx` files and 100,000 rows within a 20 MB upload. All recognized order sheets are examined. Schema/date validation, identical-duplicate removal, conflicting-duplicate rejection, summary-sheet reporting and a preview before activation. | Backend malformed-input/duplicate tests; real two-workbook packaged test |
| 4 | Select report source | Tracker report or Import Excel report controls dashboards, daily/monthly/capacity reports and production exports. Publishing uses the selected source. Tracker captures remain separate. Failed publishing retains the local source with a retry state. | Source-switch/failure/restart tests; packaged persistence test |
| 5 | Monthly detail schema | Full_search and Remaining monthly views use the shared production columns and preserve custom columns. | View/schema regression tests and generated workbook tests |
| 6 | Useful visible Sheet tabs | Publisher presents All Products, monthly full/remaining views, Daily Orders, Capacity Report, Monthly Orders and Status Report. Owned internal trackers/receipts are hidden; unknown user tabs are retained. Original All Products is preserved before conversion. | Atomic batch tests; no destructive live cleanup performed |
| 7 | Click a daily date | Published dates have links to the exact Daily Orders sheet ID and row range. Links are unavailable after failed publishing or restore until republished. Other dates and shared filters are preserved. | Backend range-link tests and browser link assertions |

### Explicit reporting assumptions

- Daily rows are **received-date cohorts**: Completed + Clarification + Cancelled + Vendor Pending + In-House Pending = Received. The PDF example mixed totals that did not reconcile; those sample values were not copied.
- `Assign to ABS` means Vendor Pending. `Need to assign ABS` remains In-House Pending until assigned.
- Defaults are editable planning targets of **700 / 750**, taken from the PDF. They are not historical staffing measurements. Only days represented by orders contribute to target totals. No weekend/holiday calendar was invented.
- Existing `Remaining_<MON>_<YEAR>` names are retained for compatibility.
- Inferred queue disappearance still follows the owner's completion rule, but a **Completion Evidence** field distinguishes it from recorded delivery timestamps. Inferred completions are excluded from confirmed SLA aggregate counts and shown as requiring verification. The existing row-level Free Site timing calculation is retained alongside that evidence.
- At the SLA deadline exactly, a valid recorded Out Time is On Time. Open/cancelled/suspended orders do not receive completion-based SLA results.

## Ten production-readiness improvements

| Rank | State | Delivered | Remaining release requirement |
|---|---|---|---|
| 1 — Completion/SLA | Implemented safeguards | Reject empty/count-mismatched/duplicate captures; capture completeness metadata; unverified imports cannot establish queue disappearance; completion provenance and uncertain-SLA counts. | Validate current portal pagination/count indicators with representative live captures. Historical captures have no retroactive proof of completeness. |
| 2 — Shared Sheets | Implemented for cooperating clients | Atomic designated-writer claim; simultaneous-claim test; authorization rechecked before each guarded mutation; other writers and failed ownership reads fail closed; capture/scheduling checks and existing canonical fingerprint/receipt protections. | All writing installations must adopt the protocol. Older clients, manual editors and direct API clients can bypass a client protocol; Google permissions remain the security boundary. |
| 3 — Backup/recovery | Implemented and tested | Matching create/restore limits, SQLite integrity checks, file hashes, capture-count manifest, flushed/readback-verified safety backups, restore validation and invalidated publication receipts after restore. Recoverable local retention. | Independent/off-device backup and a full real upgrade/recovery cycle with the eventual release assets. |
| 4 — Security | Partly complete | Python and desktop secret redaction, existing encrypted credential vault preserved, source bundle excludes writer identity; recognizable private-key/token scanning in CI and packaging; dependency audits passed. Production workbook sharing changed from Anyone with link to Restricted, retaining intended users; the service-account connection still passed a read-only check. | The owner explicitly requested continued compatibility with the existing key. The replacement JSON has not reached the local vault; rotation/revocation remains deferred. Desktop exports are now password-encrypted; automatic safety copies use Windows current-user protection. Older ZIPs require explicit migration and independent copies remain necessary. |
| 5 — Updates/releases | Release gate retained | Existing checksum/asset validation, explicit install, pre-install backup and failure recovery tests retained; CI now includes report smoke tests, lint/security and performance gates. | The owner-selected no-purchase distribution policy is now version-independent: unsigned or validly signed installers are accepted, invalid signatures are rejected, and unsigned releases disclose their status. Publication requires an explicit acceptance run and hosted-asset hash verification. The real next-version upgrade/recovery cycle remains open. |
| 6 — Retention | Local and cloud controls implemented | Explicit archive action keeps newest 50 captures/10 imports, protects unsynced captures and active import, verifies a full recovery archive before pruning and compacts SQLite. | Cloud cleanup explicitly archives eligible generated backup tabs beyond the latest five recorded operations before deleting them. Archive restore preserves formulas, notes and formatting. Raw business history and unrecognized tabs remain retained; independent backup storage remains an operator responsibility. |
| 7 — Reliability | Automated and packaged checks passed | Normal/invalid/duplicate/offline/publish-failure/restart/claim-race/archive-failure tests plus existing schedule, sync and lifecycle regressions. | A 303-second actual packaged run passed 18 cycles, two simulated renderer network outages, encrypted exports and capture preservation. Windows sleep/resume, prolonged outages and live portal observations remain open; this is not a multi-day soak. |
| 8 — Performance | Measured improvement | Bounded date parsing cache, lazy chart loading, read-only preferences polling, fixed fixture budgets, full Windows process-tree measurement including Python. | Representative larger imports and production workbook latency on target machines; current budgets are regression ceilings, not universal response guarantees. |
| 9 — UI/accessibility | Tested core interactions | New responsive report controls/tables, light/dark views, focus return, keyboard dialog close, source feedback and clear loading values. Existing sidebar/window-size tests retained. | Automated axe WCAG A/AA audit now passes all nine main screens and the import dialog in light/dark themes. Manual assistive-technology and Windows scaling checks remain release acceptance work. |
| 10 — Maintainability | Improved | Reporting metrics, import persistence, publishing, routes, writer protocol, retention and redaction are separate modules. Shared arithmetic and automated quality gates added. | Existing large legacy modules and migration-specific September 2026 constants remain; no speculative rewrite was attempted. |

## Verification results

| Check | Result |
|---|---|
| Python backend suite | **232 passed** after live Sheets fixes and durable retention archiving |
| Desktop unit tests | **25 passed**, including redaction, distribution policy and verified backup writes |
| Extractor fixtures | **3 passed**, including completeness validation and two-page browser extraction |
| Complete browser regression suite | **63 passed**, including automated accessibility checks |
| Targeted final report/layout rerun | **23 passed** after table alignment/loading refinements |
| Production frontend build | Passed |
| Isolated Windows engine/package build | Passed; local development candidate, not a published installer |
| Packaged report workflow | Passed: actual two-workbook import, source activation/persistence, publish-failure state, queue isolation, daily SLA, workbook export and capacity totals |
| Packaged lifecycle | Passed: vault, backup/restore, settings restart, update IPC, persistence, single instance, clean shutdown and renderer isolation |
| Final packaged recovery/shutdown | Passed: corrupt-vault recovery, encrypted backup restoration, second restart and bounded termination of a stalled engine |
| New-module Ruff lint | Passed, scoped to syntax/name/unused-code checks (`E9,F`) |
| Dependency audits | No known vulnerabilities reported for pinned Python requirements and npm production dependencies in desktop, extractor and frontend at audit time |

### Measured performance

Same-process benchmark: 7,000 production orders, 35 local captures, three reporting samples per mode. Cached and uncached results were asserted equal.

| Measurement | Result |
|---|---:|
| Report calculation, cache enabled | 479.73 ms median |
| Same report, date cache disabled | 1,431.19 ms median |
| Improvement in this repeated-date fixture | Approximately 66% lower median time |
| Status polling | 19.60 ms median |
| Full cached payload | 1,728,430 bytes |
| Unchanged response | 237 bytes |
| Packaged first launch, final sampled run | 4.24 seconds |
| Entire sampled process tree, including Python | 729 MB working set |

The timestamp fixture contains substantial repetition, so its speedup must not be generalized to every workbook. CPU/memory values are snapshots on this machine. Automated ceilings: polling median <250 ms, 7,000-order reporting median <5 s, unchanged response <1 KB, packaged fixture launch <30 s, total fixture process tree <1.6 GB. The ceilings catch large regressions; they are not claimed product SLAs.

### Capture-count reconciliation

Read-only inspection of the installed workspace found 35 captures. The pre-update archive contained 31; every archived capture ID is still present, and the additional four are previews 37–40 recovered from Google Sheets. Of the shared captures, 29 matched exactly. Previews 35/36 retain the same order identities and row counts; their data differences normalize to boolean casing/numeric serialization, while recovery metadata differs. No capture IDs from that backup are missing. This inspection did not edit the installed profile.

## Configuration and operation

1. Import Excel reports from the report-source panel, validate all selected files, inspect the summary, then choose **Use this import and publish reports**. A cloud failure leaves the import usable locally.
2. Set planning targets in **Capacity Report**. Per-date targets override defaults. Saving also requests publication.
3. The first upgraded computer to write claims the workbook's hidden writer-control tab. Use that computer for capture/sync. There is no automatic takeover when it is offline; recovery must deliberately establish a replacement writer and stop the old one.
4. **Storage and recovery → Archive older local history** saves and verifies a full workspace archive before pruning eligible local history. Download and protect that archive. Restoring it replaces active workspace data and first creates a safety backup.
5. First report publication preserves original All Products and hides owned internal tabs. This behavior passed against synthetic orders in the separate QA workbook; production workbook rows were not migrated or changed.

No new runtime infrastructure, Redis, PostgreSQL, user-configured environment variables or paid services were added. The development-only accessibility runner is pinned to @axe-core/playwright 4.13.0. An internal extractor environment value points to a temporary capture-evidence sidecar. New SQLite tables store report imports, source preferences, capacity targets and capture metadata. `writer-device.id` remains local and is excluded from backups/source bundles. Development-only lint/audit tools are pinned in `desktop/quality-gates.ps1`.

## Release decision

**2.7.0 is a tested release candidate, not yet a completed deployment acceptance.** All isolated live Sheets cases passed, including empty-category clearing and encrypted archive/restore. Packaged recovery and the five-minute reliability run passed. Actual installer execution, hosted-asset verification, live portal captures and representative workstation checks remain open. The owner explicitly deferred key rotation and requested old-key compatibility; valid existing service-account keys continue to work. No key-age restriction, forced rotation or Google authentication bypass was introduced.

Candidate binaries are under `release/2.7.0/`; the portable app is under `release/2.7.0/win-unpacked/`. Test profiles are separate from the installed application. Pushing source triggers build/test CI; client updates require a separately published stable release.

## Changed-file inventory

Paths below are relative to the repository root. Generated build outputs and test logs are excluded.

| File | Purpose |
|---|---|
| `docs/TV_TRACKER_PRODUCTION_MASTER_PROMPT.md` | Combined, validated PDF-first execution prompt and acceptance rules |
| `docs/TV_TRACKER_PRODUCTION_IMPLEMENTATION.md` | This delivery and release-readiness report |
| `gsheet_dashboard/report_metrics.py` | Shared status partitioning, SLA confidence and capacity arithmetic |
| `gsheet_dashboard/report_workspace.py` | Validated workbook imports, durable source preferences and targets |
| `gsheet_dashboard/report_routes.py` | Import/source/capacity/publish/export/retention APIs with operation gates |
| `gsheet_dashboard/report_publishing.py` | Selected-source Sheets views, publication receipt, charts and Excel export |
| `gsheet_dashboard/sheets_writer.py` | Designated-writer identity, atomic claim and guarded write operations |
| `gsheet_dashboard/workspace_retention.py` | Verified full archives before pruning eligible local history |
| `gsheet_dashboard/redaction.py` | Secret-safe Python log formatting |
| `gsheet_dashboard/capture_validation.cjs` | Portal advertised-count/completeness validation |
| `gsheet_dashboard/datatrace_sync.py` | Writer-wrapped Sheets access and extraction metadata persistence |
| `gsheet_dashboard/scrape_datatrace.js` | Pager-count collection, validation and metadata sidecar |
| `gsheet_dashboard/preview_store.py` | Capture evidence table and metadata lifecycle |
| `gsheet_dashboard/order_reporting.py` | Prevent unverified queue imports establishing completion by absence |
| `gsheet_dashboard/preview_completion.py` | Completion evidence labeling and unverified-history continuity checks |
| `gsheet_dashboard/tracker_sync.py` | Evidence column, recorded-timestamp provenance and shared report metrics |
| `gsheet_dashboard/monthly_views.py` | Persist completion evidence during repair and keep repeat sync idempotent |
| `gsheet_dashboard/monthly_production.py` | Bounded, semantics-preserving wall-clock parsing cache |
| `gsheet_dashboard/monthly_api.py` | Monthly export follows the selected import source |
| `gsheet_dashboard/server.py` | Active-source routing, state, publication, capture writer checks and logging |
| `gsheet_dashboard/workspace_backup.py` | Matching limits, hashes/counts, integrity validation and restored-source invalidation |
| `gsheet_dashboard/test_report_workspace.py` | Report arithmetic, import fidelity, export/publishing and backup tests |
| `gsheet_dashboard/test_report_safety.py` | Failure/restart/race/redaction/retention/recovery contracts |
| `gsheet_dashboard/test_capture_validation.cjs` | Incomplete and duplicate capture fixtures |
| `gsheet_dashboard/test_desktop_connection.py` | Lifecycle fixture supplies the new writer-authority dependency |
| `gsheet_dashboard/frontend/src/ReportWorkspace.jsx` | Source selection, multi-file import, Daily Orders, Capacity Report and storage controls |
| `gsheet_dashboard/frontend/src/ReportChart.jsx` | Lazy-loaded report/capacity visualization |
| `gsheet_dashboard/frontend/src/reportWorkspace.css` | Responsive controls, accent metrics and aligned report tables |
| `gsheet_dashboard/frontend/src/main.jsx` | Report navigation/source refresh/export integration |
| `gsheet_dashboard/frontend/src/WorkspaceViews.jsx` | Monthly source refresh, labels and imported-report edit protections |
| `gsheet_dashboard/frontend/src/WorkspaceShell.jsx` | Capacity navigation and accurate source context |
| `gsheet_dashboard/frontend/src/StudioWorkspace.jsx` | Capacity page title |
| `gsheet_dashboard/frontend/src/DesktopExperience.jsx` | Capacity command-palette navigation and encrypted backup controls |
| `gsheet_dashboard/frontend/tests/report-workspace.spec.js` | New workflow, keyboard, responsive and theme tests |
| `gsheet_dashboard/frontend/playwright.desktop.config.js` | Include new reports in the desktop UI regression suite |
| `desktop/redaction.cjs` | Desktop error redaction, including standalone/escaped private keys |
| `desktop/main.cjs` | Shared redaction and verified password-encrypted backup export/restore |
| `desktop/package.json` | Candidate version 2.7.0 and packaged recovery/crypto helpers |
| `desktop/tests/redaction.test.cjs` | Desktop secret-redaction tests |
| `desktop/build_backend.py` | Package extractor completeness helper |
| `desktop/report-smoke.cjs` | Actual packaged multi-workbook/report workflow test |
| `desktop/process-metrics.cjs` | Read-only Windows process-tree sampler including Python |
| `desktop/smoke.cjs` | Full-process memory/startup regression ceilings |
| `desktop/benchmark_workspace.py` | Fixed-data budgets, direct cache comparison and output equality assertion |
| `desktop/quality-gates.ps1` | Pinned lint/audit tooling and enforceable checks |
| `.github/workflows/desktop-release.yml` | New capture/report/security/performance release gates |
| `make_bundle.py` | Exclude local writer identity from source archives |

The Sheets chart requests follow Google's documented [chart batch-update contract](https://developers.google.com/workspace/sheets/api/samples/charts). This verifies the request design; it does not substitute for live workbook acceptance testing.

## Final recovery and release checkpoint — 6 October 2026

### Protection and retention

- `desktop/backup-crypto.cjs` uses AES-256-GCM with a random nonce/salt and scrypt-derived key for portable `.tvbackup` exports. Passwords must contain at least 12 characters and are not saved. Wrong passwords or modified ciphertext fail closed. Keep the password separately; the app cannot recover it.
- `gsheet_dashboard/backup_protection.py` protects desktop automatic recovery copies using Windows current-user DPAPI. **Protect older backups** migrates recognized ZIPs only after durable encrypted readback. Failure preserves the original. Windows-bound archives need the same Windows account; they are not independent disaster recovery.
- `gsheet_dashboard/cloud_retention.py` previews and archives generated backup tabs older than the five newest recorded operations, then verifies deletion. Unknown tabs, raw previews, canonical trackers and monthly evidence remain untouched. Restore refuses collisions and preserves cell values, formulas, notes and supported formatting. Customized backup tabs with unsupported objects fail safely instead of being deleted.
- Cloud archives are included in portable workspace exports; Windows encryption is removed inside the password-encrypted container and reapplied on restore. Existing exports retain their old format and can still be restored.
- Active local database files and historical pre-restore directories rely on Windows profile access controls; this change does not claim full disk encryption. Production history was not pruned and old local backups were not silently migrated.

### Verified evidence

| Check | Result / local log |
|---|---|
| Backend | 232 passed — `.desktop-build/recovery-hardening-backend-final.log` |
| Desktop | 26 passed — `.desktop-build/old-key-compatibility-desktop.log`, including existing-key preservation |
| 2.6.0 → 2.7.0 updater/migration | Real updater download, SHA-512 equality, failed installer handoff recovery, and capture/connection/preference persistence passed — `.desktop-build/recovery-hardening-upgrade.log`. Loopback feed; NSIS execution remains untested. |
| Browser | 63 passed — `.desktop-build/recovery-hardening-ui.log` |
| Packaged lifecycle/report | Passed — `.desktop-build/recovery-hardening-packaged-lifecycle.log`, `recovery-hardening-packaged-report.log` |
| Packaged corrupt-vault recovery / stalled shutdown | Passed — `.desktop-build/recovery-hardening-recovery.log`, `recovery-hardening-shutdown.log` |
| Timed packaged reliability | 303 seconds, 18 cycles, zero renderer errors, maximum sampled state response 54 ms — `.desktop-build/recovery-hardening-soak.log` |
| Recovery lint | Passed scoped Ruff E9,F checks |
| Credential-pattern scan | 229 source files passed before final documentation updates; supplementary pattern coverage, not proof of absence of arbitrary secrets |

### Live Sheets acceptance

All writes targeted the Restricted **Tv Tracker acceptance QA — 2026-10-06** workbook (`1H9V7xogbxzPqzsMecuMa1qGIIwLKkRetkZ2EUBdKKwI`), with explicit approval. The test guards the workbook title and ID and refuses the production ID. Credentials enter via stdin and are not logged or bundled.

Passed: publication, deadline equality, synthetic source replacement, empty Remaining view clears stale rows, raw data preservation, common schemas, capacity chart, second-writer rejection, stable daily links, and a lost response after a real committed batch without replay. Evidence: `.desktop-build/live-sheets-acceptance-final.log`.

Cloud backup archive and restore passed against the real QA workbook, including formulas and notes, using a Windows-protected archive: `.desktop-build/cloud-retention-live.log`. A summary-output variable was shadowed in that test run and printed the last synthetic sheet ID as `test_workbook`; the guarded target was the QA workbook above. The summary variable was corrected afterward. Production rows were not changed.

### Remaining operational checks

The production workbook is Restricted and the existing account passed a read-only connection check. Google key import/revocation is deferred by owner instruction: old valid keys remain supported. A disabled or revoked key will still be rejected by Google. The installed profile lacks TitleVision login details, so the attempted live capture stopped before contacting the portal; it is not evidence of portal reliability. No production captures were saved by that attempt.

Actual NSIS upgrade, hosted release byte verification, sleep/resume, multi-day portal operation, manual screen-reader/display-scaling checks and independent backup storage remain acceptance work. The timed isolated test and automated accessibility checks do not certify those scenarios.

Additional files: `desktop/backup-crypto.cjs`, `desktop/tests/backup-crypto.test.cjs`, `desktop/upgrade-smoke.cjs`, `desktop/reliability-soak.cjs`, `desktop/distribution-policy.json`, `desktop/distribution-policy.cjs`, `desktop/tests/distribution-policy.test.cjs`, `desktop/secret_scan.py`, `desktop/verified-file.cjs`, `desktop/tests/verified-file.test.cjs`, `desktop/live-sheets-acceptance.py`, `gsheet_dashboard/backup_protection.py`, `gsheet_dashboard/cloud_retention.py`, `gsheet_dashboard/test_backup_protection.py`, `gsheet_dashboard/test_cloud_retention.py`, `gsheet_dashboard/test_release_secrets.py`, and `docs/TV_TRACKER_RELEASE_POLICY.md`. Package lockfiles pin the candidate version and development-only accessibility dependency; preload adds password arguments to backup IPC; `.gitignore` and the source bundler exclude recovery data. No new runtime database, cloud service or paid dependency was added.
