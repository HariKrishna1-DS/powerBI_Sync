# Tv Tracker 2.2.1 — end-to-end quality review

Date: 2 October 2026. Desktop branch: `tv-tracker`.

## Issues found and corrected

1. **False failed sync after a successful Google commit.** The live `preview35` contained 335 rows. Sheets stored numeric values such as `240.0` as `240`; retry compared their formatted strings and incorrectly rejected the snapshot. Archive readback now uses unformatted values and compares numeric source cells numerically. It still rejects changed values, differing row counts, changed text identifiers, and conflicting receipt hashes.
2. **False changes after cloud history recovery.** Sheets' `TRUE`/`FALSE` strings differed from local JSON booleans. Comparison now treats their boolean representations consistently without changing identifier matching. The verified preview34/35 comparison is 330 matched, 55 missing, five added, and 177 unchanged; actual status and suspension changes remain visible.
3. **Report crash with omitted optional detail lists.** Daily/monthly detail filters now tolerate missing ID lists. This was reproduced by an older SLA response fixture; production responses with complete lists remain unchanged.
4. **Slow full-workbook export.** Coloring through `worksheet[row_number]` repeatedly scanned all cells to determine worksheet dimensions. The export now iterates explicit bounds and reuses color/font objects. Synthetic coloring of 1,000 × 31 cells improved from 11.793 s to 1.935 s; 10,000 × 31 cells took 20.997 s on this machine. These are coloring measurements, not total download times.

## Verification completed

| Check | Evidence |
| --- | --- |
| Backend regressions | 133 tests passed, including numeric retries, real-conflict rejection, boolean recovery, export complexity, synchronization, backup, network/auth failures and reporting |
| Desktop controller tests | 12 passed: settings, vault, navigation boundaries, update states, failures and active-work protection |
| Browser workflows | 14 passed: first run, keyboard setup, cached/offline data, 25,000-row pagination/search, exports, updates, charts, timezones, tracker history and SLA single/bulk saves and failures |
| Packaged lifecycle | 14 checks passed locally and in the final release CI: authenticated loopback, renderer isolation, update IPC, encrypted settings, restart, import, backup/restore, single instance, shutdown and persistence |
| Existing live sync | Read-only inspection confirmed all 335 preview35 rows were already archived and all 6,990 expected tracker records matched; no duplicate upload was needed |
| Retry correction | Replayed the actual failed snapshot against the real archive using read-only Google credentials and a backup copy; recovered the original pass report successfully |
| Native upgrade | Installed 2.2.0 over 2.1.0; normal Windows launch retained the live account and all 30 saved captures |
| Native connection test | Connected, 6,990 production orders, next capture `preview36` |
| Native reports | Daily, monthly, SLA, sync activity and comparison screens opened against real data |
| Native capture search | Exact order returned one result; no-match returned zero; clearing restored all 335 rows |
| Native Excel capture export | Opened successfully: 335 rows × 31 columns |
| Complete workbook export | Read-only live endpoint returned HTTP 200, a valid 5,131,316-byte Excel file with all eight tabs in 171.71 s, including 9,668-row history sheets and 6,990 tracker orders; Google tab names were preserved |
| Final native workbook export | Installed 2.2.1 completed the export and saved `C:\Users\Mayank\Downloads\Production_data.xlsx` (5,066,256 bytes); openpyxl validated all eight tabs, both 9,668-row history sheets, 1,368 Full Title rows and 5,622 Remaining Products rows |
| Recovery backup | Saved `Tv-Tracker-backup-2026-10-02.zip`; database integrity check passed, containing 30 captures / 9,393 captured rows |

## Published release and native upgrade

Release [v2.2.1](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/tag/v2.2.1) was published from `e06aaf6` after [CI run 36989904616](https://github.com/HariKrishna1-DS/powerBI_Sync/actions/runs/36989904616) passed all build, regression, packaged lifecycle and source archive checks. Superseded CI builds were cancelled before publishing so the release includes all QC fixes.

All five release assets are present: installer, blockmap, updater manifest, portable ZIP and source ZIP. Downloaded installer SHA-512 matches `latest.yml`; source ZIP integrity and exclusion of local credentials/capture data passed. Installer SHA-256: `b2131456b0c66a7bd95d4d840e2fa682ef6dbde8c55724305015282e781b0d73`.

Final CI recorded 12 desktop tests, 14 browser workflows, 133 engine tests and 14 packaged lifecycle checks. The packaged CI run started in 2,031 ms, used four processes with a combined 388 MB working set, and reported no renderer errors. These measurements describe the CI host, not a guaranteed performance target for every PC.

The native 2.2.0 app offered 2.2.1, downloaded it through the update screen, and launched the installer using **Restart & install**. The installer recognized the existing per-user installation and upgraded it. Tv Tracker reopened automatically; the installed executable reports 2.2.1. All 30 captures, the connected Google Sheet and encrypted TitleVision credentials were retained.

The native **Retry preview35 sync** action succeeded with 335 rows. Independent read-only cloud inspection confirmed preview35 still has exactly 335 rows, 6,990 tracker orders, zero duplicate order IDs and zero changed manual-field records. The pending-sync indicator cleared. The native preview34/35 comparison showed the corrected 177 unchanged orders.

### Live portal availability limitation

Fresh capture was attempted from the installed application. TitleVision authentication succeeded, but the configured queue `23656` returned an empty results panel after **Refresh View** and timed out. The user confirmed that intermittent server outages occur with this portal; the configured queue and credentials were left unchanged. A successful new capture-to-cloud run could not be verified during this outage and must be checked when the portal responds normally.

Failure containment passed against real data: all 30 captures remained, preview35 still had 335 cloud rows, tracker order count stayed at 6,990, duplicate IDs remained zero and the SHA-256 of all existing manual-field records was unchanged. No partial preview36 or stale snapshot was uploaded. Temporary local extraction diagnostics were removed, and the installed extractor was restored byte-for-byte to the published version with its SHA-256 verified.

## Files and configuration

- `desktop/package.json`, `desktop/package-lock.json`: version 2.2.1 and matching output directory.
- `gsheet_dashboard/tracker_sync.py`: unformatted archive reads and numeric/boolean readback equality.
- `gsheet_dashboard/preview_store.py`: recovered boolean comparison normalization.
- `gsheet_dashboard/server.py`: bounded workbook coloring and reused styles.
- `gsheet_dashboard/frontend/src/WorkspaceViews.jsx`: optional report detail lists no longer crash rendering.
- `gsheet_dashboard/test_tracker_v2.py`, `gsheet_dashboard/test_sync_performance.py`: targeted regression coverage.
- `gsheet_dashboard/frontend/playwright.desktop.config.js`: include report, tracker and SLA checks in every desktop release.
- `gsheet_dashboard/frontend/tests/sla-comments.spec.js`: use the configured test server and current `Missing` status contract.
- `README.md`: current installer/build references and link to this review.
- `docs/TV_TRACKER_2_2_1_QC.md`: fixes, automated and native validation, release evidence and the live portal limitation.

No new dependencies, database service, environment variables, account permissions or Google Sheet schema changes. Credentials remain local and encrypted. Google Sheets and TitleVision still require internet access; schedules require an awake computer with the app running.

## Scope and limits

Failure, destructive restore/delete, invalid-input and bulk-SLA mutation cases use isolated fixtures. Real business SLA values were not changed to test editing. Automated tests and observed workflows provide evidence for the tested paths; they cannot establish that every future network condition, portal change or Windows environment is bug-free.
