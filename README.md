# Tv Tracker — Windows desktop

Tv Tracker is a local desktop workspace for TitleVision extraction, Google Sheets production tracking, saved captures, comparisons, and Power BI exports. Its Python and Node runtimes are bundled. No Render hosting or PostgreSQL service is required.

## Desktop branch

**`tv-tracker`** is the dedicated desktop development branch. `main` remains the upstream browser/sync project. Desktop work belongs here; review upstream changes before merging them so native settings, local storage, and packaging remain compatible.

```powershell
git fetch origin
git switch tv-tracker
git pull --ff-only origin tv-tracker
```

The 2.1.0 integration incorporates upstream `db0c274` plus the existing desktop implementation. See [analysis, mapping, changes and validation](docs/DESKTOP_UPSTREAM_ALIGNMENT.md).

## Install and connect

Install the Windows `.exe` from the [latest release](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/latest), or extract the portable ZIP and open **Tv Tracker.exe**. Configure the Google spreadsheet, service-account key, and TitleVision credentials through **Connections & settings** (Ctrl+,).

The app includes a single native window, system tray, encrypted credentials, an authenticated loopback engine, dated offline reports, backup/restore, and keyboard quick actions. Internet is required for extraction and Sheets sync. Saved captures and cached production reports remain available offline. Schedules need the app running and the computer awake.

The rename preserves the previous DataTrace Studio profile and installer identity for upgrades. The Windows x64 build is unsigned.

## Current workflow

**2.7.1 shared-workbook fix:** all updated PCs can capture and publish one job at a time. Stop older jobs and update every writer before resuming. See [rollout, conflict review and recovery](docs/TV_TRACKER_2_7_1_RELEASE.md).

- **Data sheets:** combined production trackers, individual trackers, and Status Report. Live production values come from Google Sheets.
- **Saved captures:** immutable imported/extracted queues, available locally with raw Excel and filtered CSV downloads.
- **Daily Orders / Monthly report:** retained production orders with period navigation and labeled charts. Monthly SLA entries follow actual completion month.
- **Sync activity:** local sync receipt, missing-order and ambiguity review. Cloud audit tabs are not required.
- **Changes:** compare saved captures by trimmed, case-insensitive Order Number and export the comparison for Power BI.
- **Export:** `Production_data.xlsx` with consistent status colors; confirms shortened Excel tab names before downloading.

Stable tracker names replace the shipped September-only defaults; custom names remain supported. The upstream baseline workbooks are bundled and missing baseline orders are added during sync. Since 2.5.3, disappearance between valid saved queues marks completion at the first missing preview timestamp, with cancelled/suspended exceptions and manual timestamp preservation. See the [completion, SLA and monthly schema rules](docs/TV_TRACKER_2_5_3_RELEASE.md). Manual tracker columns are preserved except Comments, Assignee and iAssignee, which the upstream rules intentionally clear. Raw captures preserve original values.

Imports/extractions sync automatically when configured. A failed write gets bounded retries and remains saved with a retry action. Newer captures wait behind unresolved older failures. After configuration, unsynced local captures are picked up by the running app. Google Sheets is authoritative; SQLite holds local captures, receipts and failures only.

## Build, test, and contribute

- [Desktop install, configuration, backup, and build guide](docs/DESKTOP_GUIDE.md)
- [Validation record and release limits](docs/DESKTOP_VALIDATION.md)
- [Architecture](PROJECT_ARCHITECTURE.md)
- [Upstream production rules](docs/TV_Search_Sync_Prompt.md)
- [Optional legacy browser/Streamlit development](docs/LEGACY_WEB_README.md)

Build with `desktop/build.ps1`. Installer and portable output go to `release/<version>/`. Run `python make_bundle.py` to create the matching source ZIP with a SHA-256 source manifest. Dependencies are recorded in lockfiles; 2.2.0 added electron-updater for Windows releases.

For a contribution, branch from `tv-tracker`, make a focused change, run the relevant Python, desktop-settings and Playwright suites, and open a pull request targeting `tv-tracker`. Keep credentials, captures, runtime data, and generated release files out of commits. The baseline XLSX files already supplied by upstream are required application inputs and are included in packages/source bundles.

## Tv Tracker desktop updates

The desktop application is maintained on `tv-tracker`. Version 2.2.0 adds **Connections & settings → Updates** and **Help → Check for updates**. See [setup and release instructions](docs/DESKTOP_UPDATES.md) and the [implementation prompt](docs/TV_TRACKER_UPDATE_PROMPT.md). Users on 2.1.0 or earlier need one manual installer upgrade before in-app updates become available.

Version 2.2.1 fixes numeric sync retries, recovered boolean comparisons, optional report details and large-workbook export performance. See the [end-to-end QC report](docs/TV_TRACKER_2_2_1_QC.md).
