# Tv Tracker 2.1 — validation record

Tested on Windows 11 x64 on 2 October 2026 using synthetic data and isolated desktop profiles. These results describe this build and machine, not a guarantee of defect-free behavior in every environment. The upstream reference is `db0c274`; the desktop branch is `tv-tracker`.

## Completed checks

| Check | Result |
| --- | --- |
| Python regression suite | 124 tests passed: tracker/reporting logic, clock, authentication, failed writes, receipts, queued retry ordering, upgrade and backup compatibility |
| Desktop settings tests | 5 tests passed, including encryption boundaries and migration of exact shipped tracker defaults |
| Production UI suite | 9 tests passed: revised charts/clock/navigation, retained orders, local audit, filtered CSV, export confirmation/cancel, retry target, offline cache, keyboard setup and 25,000-row search |
| Production frontend build | Passed with chart/report modules deferred |
| Frozen Python engine | Built with shared palette and both baseline workbooks present in packaged resources |
| Packaged native lifecycle | All 13 lifecycle scenarios passed, plus assertions for Tv Tracker app name, page title and visible brand; no uncaught renderer errors |
| Packaged extraction runtime | Bundled Electron Node 24.21.0 and puppeteer-core launched Chrome 154.0.8037.97 and rendered a local fixture; no portal access |
| Actual baseline inputs | Both parse: 1,311 Full Title rows and 5,468 Remaining Products rows; the latter includes 87 repeated identities handled by the conflict log |
| App signature | NotSigned, verified with Windows Authenticode inspection |

The packaged lifecycle test covered first launch, authenticated loopback access, sandbox/context isolation, keyboard navigation, Windows DPAPI encryption, settings-triggered engine restart, local import, saved capture viewing, backup export/restore, single-instance behavior, clean shutdown and persistence after reopening. It confirmed the backend port closed on application quit. Native dialogs were stubbed for backup file selection; the archive/database operations were real.

The new backend tests exercise old receipt and backup upgrades without duplicate uploads, new audit/failure backup retention, empty capture replay/recovery, corrupt tracker values despite unchanged IDs, custom/legacy tab reads, reserved-column rejection before writes, and older-failure blocking with explicit ordered retry. Existing tests cover additional partial failures, duplicate identity handling, manual formulas, current Sheet edits, schedule boundaries, SLA corrections and authentication.

## Measurements

| Measurement | Observation |
| --- | --- |
| Packaged launch to welcome | 12,760 ms under Playwright instrumentation while release compression was running |
| Electron processes | 4; summed working sets about 482 MB during the smoke test |
| Initial JavaScript | About 274 KB uncompressed |
| Deferred chart/report JavaScript | About 389 KB uncompressed |
| Capture rendering | 50 rows per page; search found the matching row in a 25,000-row fixture |
| 1,024 × 768 window | No document-level horizontal overflow in the large-capture test |

The memory figure excludes the separate Python engine, includes test overhead and may double-count shared pages. It is not a total-system benchmark. Native behavior, bundled runtimes and rendering consistency carry Electron's download/memory cost. Metadata-only polling, a shared 30-second production cache, lazy charts and pagination reduce avoidable work; very large Sheets still need a full tracker read when the cache refreshes.

## Verification boundaries

- Installed Edge exited before establishing a debugging connection in two fixture attempts. Chrome passed. Automatic desktop detection now prefers Chrome while retaining an explicit configured browser first and Edge as fallback. Edge-only environments require separate validation; no browser security setting was weakened.
- No production Google Sheets write or real TitleVision login was performed. Service-account permissions, expired credentials, quotas, portal changes and MFA need a controlled live check with the user's configured account. Network/API failure behavior was tested with injected failures.
- The packaged executable was launched; the installation wizard, uninstall behavior and a second clean Windows machine were not exercised interactively. The installer/profile identity is preserved for upgrade compatibility.
- The release is Windows x64 and unsigned. Other operating systems/architectures and public signed distribution are not validated.
- Extraction requires installed Edge or Chrome and internet access. Schedules require the app running, the computer awake, and an initial successful network clock synchronization. Already established clock anchors continue during transient outages.
- Baseline workbook inputs inherited from upstream contain historical tracker data, including duplicate identities recorded for review rather than inserted twice; they are intentionally packaged. Actual generated local captures, credential files, vaults and caches are excluded from the source archive.
- Cloud audit-tab deletion and historical cleanup utilities were not run. One active writer per spreadsheet remains required; independent machines are not coordinated by the local queue.

## Reproduce

Build with `desktop/build.ps1`. Use the locked Python dependencies to run `python -m unittest discover -s gsheet_dashboard -p "test_*.py"`; run `npm --prefix desktop test`; from `gsheet_dashboard/frontend`, run `npx playwright test --config playwright.production.config.js` after building the UI.

Set `DESKTOP_EXE` to the absolute path of `release/2.1.0/win-unpacked/Tv Tracker.exe`, then run `node desktop/smoke.cjs`. JSON and screenshots go to ignored `desktop/test-output`. The synthetic profile is isolated from the user's current data.

For packaged browser extraction dependencies, set `ELECTRON_RUN_AS_NODE=1` and run that executable with `desktop/check-packaged-browser.cjs`. This uses a local HTML fixture, not a portal. Remove the variable before starting the UI. Run `python make_bundle.py` to produce and integrity-check the source ZIP. Release artifacts stay outside Git.
