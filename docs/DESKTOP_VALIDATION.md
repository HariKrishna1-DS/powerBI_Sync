# DataTrace Studio 2.0 — validation record

Tested on Windows 11 x64 on 2 October 2026. Tests used synthetic data and isolated desktop profiles. Results describe this build and machine, not a guarantee that every environment or workflow is defect-free.

## Completed checks

| Check | Result |
| --- | --- |
| Python regression suite | 85 tests passed, including reconciliation, reporting, retries, preview storage, authentication, cache behavior, and backup validation |
| Desktop settings tests | 5 tests passed for validation, secret handling, and encrypted storage boundaries |
| Browser regression and desktop UI tests | 5 tests passed: production reports, offline states, first-run keyboard setup, deferred charts, and large capture search |
| Production frontend build | Passed |
| Frozen Python engine and Windows packaging | Passed; installer and portable ZIP generated |
| Final packaged desktop lifecycle test | All 13 scenarios below passed; no uncaught renderer errors |
| Packaged extraction runtime | Bundled Electron Node 24.21.0 and puppeteer-core launched installed Edge 154.0.4258.37 and rendered a local fixture successfully |

The packaged desktop test covered first launch, authenticated loopback access, renderer sandbox/context isolation, keyboard navigation, Windows DPAPI encryption, settings-triggered engine restart, local import, saved capture viewing, backup export, backup restore, single-instance behavior, clean shutdown, and persistence after reopening. It confirmed the backend port closed on application quit. Backup and restore used native-dialog test stubs and real archive/database operations.

The extraction runtime check used a local HTML fixture. It did not access TitleVision or authenticate to a real account.

## Measurements

| Measurement | Observation |
| --- | --- |
| Final packaged first launch to visible welcome screen | 6,513 ms under Playwright instrumentation while release packaging was running |
| Earlier packaged launch | 5,478 ms on the same machine |
| Search in a 25,000-row capture | 127 ms for typing the filter and observing the matching row in the browser test |
| Table rendering | 50 visible rows per page; a matching search reduced this to one row |
| Initial JavaScript | Approximately 273 KB before compression; approximately 469 KB of charts/report views deferred |
| Window sizing | No document-level horizontal overflow at 1,024 × 768 in the large-capture test |
| Electron processes during final smoke test | 4 processes; summed working sets approximately 531 MB |

The memory figure comes from Electron's process metrics. It excludes the separate Python backend, includes test/debug overhead, and may double-count shared pages. It is not a total-system memory benchmark. Electron provides consistent rendering and bundled runtimes at a higher download and memory cost than a minimal native WebView shell.

Additional performance work includes metadata-only preview listings, targeted capture reads, shared 30-second production caching, slower idle/background polling, lazy report/chart loading, and pagination. These reduce avoidable work; very large production Sheets still require a full tracker read when the cache expires.

## Verification boundaries

- Live Google Sheets authentication, permissions, synchronization, and TitleVision extraction need the user's real credentials and were not exercised against production services. Existing reconciliation behavior was checked with tests.
- The Windows release is unsigned. A code-signing certificate and signed release workflow are needed for public distribution.
- The unpacked application was launched and tested. The installation wizard, uninstall behavior, and a clean second Windows machine have not been tested interactively.
- Windows x64 is the release target. macOS, Linux, Windows ARM, and other Windows versions are not validated.
- Installed Edge or Chrome and internet access are required for portal extraction. Saved captures and cached reports are available locally. Scheduled jobs require the application to be running and the computer awake.
- No claim is made that every inherited workflow is keyboard-accessible or that every possible failure has been eliminated. The new Connections and quick-action dialogs were checked for keyboard focus and Escape handling.
- No repository push or public release upload was performed for this desktop build.

## Reproduce

Build using `desktop/build.ps1` as described in `DESKTOP_GUIDE.md`. Then run the Python suite from `gsheet_dashboard` with the locked dependencies available, the desktop settings suite with `npm.cmd --prefix desktop test`, and the frontend production suite with `npx playwright test --config playwright.production.config.js` from `gsheet_dashboard/frontend`.

For the packaged smoke test, set `DESKTOP_EXE` to the absolute path of `release/win-unpacked/DataTrace Studio.exe`, then run `node desktop/smoke.cjs`. Screenshots and the JSON result are written to `desktop/test-output`.

To verify the packaged browser dependency separately, set `ELECTRON_RUN_AS_NODE=1` and run `release/win-unpacked/DataTrace Studio.exe desktop/check-packaged-browser.cjs` from the repository root, waiting for process completion and capturing stdout/stderr. Remove that environment variable before launching the desktop UI.
