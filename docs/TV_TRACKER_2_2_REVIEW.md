# Tv Tracker 2.2.0 implementation review

## Connection diagnosis

The provided account successfully opened Production_data using read-only Google Sheets scopes. Recovery found 29 previews, with the highest ID 34. The running installed app showed the correct spreadsheet URL and saved TitleVision credentials, but no imported Google service-account key. The Downloads JSON was validated without displaying its private key. App configuration was left pending when desktop control was stopped with Escape; the app must import the key and save settings to use it.

The connection test now recovers existing previews locally, marks recovered captures as already synced, and reports the next number. Recovery failure continues to block capture. Missing setup gets an actionable explanation instead of the generic connection warning. Diagnostics did not write to the production Sheet.

## Updates

The Electron main process owns the fixed public GitHub release feed. Narrow preload methods expose status, check, download, and install. The React Updates tab and native Help menu provide explicit user actions. Downloads and ordinary application quit do not trigger installation. Stable versions only, no downgrade, and the existing Windows application/profile ID is retained.

Shutdown takes the engine job lock before accepting an update and blocks new work. A launch error reported by the updater attempts to restart the local engine. Installer downloads retain electron-updater's integrity checks. A desktop-branch workflow builds and tests a new version, uploads all assets to a draft, and then publishes it. Existing published versions are never overwritten.

## Changed files

| File | Purpose |
| --- | --- |
| desktop/updater.cjs | Main-process update state, explicit operations, safe errors and recovery |
| desktop/main.cjs | Trusted IPC, native Help action, graceful installation and engine recovery |
| desktop/preload.cjs | Restricted update commands and event subscription |
| desktop/package.json / package-lock.json | Version 2.2.0, electron-updater 6.8.9, packaged module and GitHub feed |
| desktop/tests/updater.test.cjs | Update transitions, retries, duplicate operations, failures and job guards |
| desktop/smoke.cjs | Packaged update IPC and settings-tab coverage |
| gsheet_dashboard/server.py | Connection recovery diagnostics and atomic non-forced shutdown |
| gsheet_dashboard/test_desktop_connection.py | Number recovery, missing key, network failure and shutdown regressions |
| gsheet_dashboard/frontend/src/DesktopExperience.jsx | Updates UI and connection test's next-preview result |
| gsheet_dashboard/frontend/src/desktop.css | Download progress styling |
| gsheet_dashboard/frontend/tests/desktop-updates.spec.js | Explicit update actions and active-job UI checks |
| gsheet_dashboard/frontend/playwright.desktop.config.js | Isolated desktop UI suite using Chrome |
| .github/workflows/desktop-release.yml | Tested versioned Windows release publishing from tv-tracker |
| README.md | Desktop update entry point |
| docs/TV_TRACKER_UPDATE_PROMPT.md | Requested implementation prompt and plan |
| docs/DESKTOP_UPDATES.md | User setup, one-time upgrade, maintainer publishing and limitations |
| docs/TV_TRACKER_2_2_REVIEW.md | This report |

## Verification

- 128 Python regression tests passed.
- 12 Node settings/updater tests passed.
- 7 desktop browser tests passed, including a 25,000-row capture view.
- React production build passed.
- 14 real packaged Electron lifecycle checks passed; startup 5.2 seconds in the isolated test profile; no renderer errors.
- Google authentication and preview history reads passed against the supplied Sheet.
- Workflow YAML parsed and branch isolation checked locally. GitHub execution/publication status is reported separately with the delivery.

## Configuration and limits

No new application environment variables, database server, PostgreSQL, or hosting service. CI uses its temporary GitHub token; the application does not contain it. Existing Google/TitleVision credentials remain local. Windows installers remain unsigned. Portal login and a real newer-version installation were not performed against the user's running app. A published release and a version bump are required for subsequent updates; pushing raw code alone does not create a new app version.
