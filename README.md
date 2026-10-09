# Tv Tracker 1.0.3 — Windows desktop

Tv Tracker is a local desktop workspace for TitleVision extraction, Google Sheets production tracking, saved captures, comparisons, and Power BI exports. Its Python and Node runtimes are bundled. No Render hosting or PostgreSQL service is required.

The current source version is **1.0.3** on `tv-tracker-app`. Desktop and React package manifests and lockfiles use this version. See [the 1.0.3 release notes](docs/TV_TRACKER_1_0_3_RELEASE.md) for the included changes.

## Desktop branch

**`tv-tracker-app`** contains the desktop application source, based on the earlier 2.6.0 code. `main` remains the upstream browser/sync project. This application branch was previously named `tv-tracker-online`.

```powershell
git fetch origin
git switch tv-tracker-app
git pull --ff-only origin tv-tracker-app
```

The 2.1.0 integration incorporates upstream `db0c274` plus the existing desktop implementation. See [analysis, mapping, changes and validation](docs/DESKTOP_UPSTREAM_ALIGNMENT.md).

## Install and connect

Install the Windows `.exe` from the [latest published release](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/latest), or extract its portable ZIP and open **Tv Tracker.exe**. Configure the Google spreadsheet, service-account JSON key, and TitleVision credentials through **Connections & settings** (Ctrl+,). Each Windows profile saves its own connection; share the exact configured spreadsheet with that key's service-account email as Editor.

The app includes a single native window, system tray, encrypted credentials, an authenticated loopback engine, dated offline reports, backup/restore, and keyboard quick actions. Internet is required for extraction and Sheets sync. Saved captures and cached production reports remain available offline. Schedules need the app running and the computer awake.

The rename preserves the previous DataTrace Studio profile and installer identity for upgrades. The Windows x64 build is unsigned.

## Current workflow

- **Data sheets:** combined production trackers, individual trackers, and Status Report. Live production values come from Google Sheets.
- **Saved captures:** immutable imported/extracted queues, available locally with raw Excel and filtered CSV downloads.
- **Daily Orders / Monthly Orders:** retained production orders with period navigation, status tables, and labeled charts. Daily metric cards jump to their order tables. Chart filters, status breakdown, and the custom chart start open.
- **Import Excel report:** a separate local report source built from uploaded XLSX/CSV files. The latest occurrence of a repeated Order Number wins. Daily received dates follow In-Time. A **Completed and Delivered** order moves to its Out Time month when completion is later than arrival; with no Out Time it remains in its arrival month's completed list.
- **Selected daily date in Sheets:** clicking a Daily Orders date highlights it in **Daily Status Report** and applies a basic filter to **All Products**, showing that day's received orders. Selecting another date replaces the shared All Products filter for everyone viewing that spreadsheet.
- **Sync activity:** local sync receipt, missing-order and ambiguity review. Cloud audit tabs are not required.
- **Changes:** compare saved captures by trimmed, case-insensitive Order Number and export the comparison for Power BI.
- **Export:** `Production_data.xlsx` with consistent status colors; confirms shortened Excel tab names before downloading.

Stable tracker names replace the shipped September-only defaults; custom names remain supported. The upstream baseline workbooks are bundled and missing baseline orders are added during sync. Since 2.5.3, disappearance between valid saved queues marks completion at the first missing preview timestamp, with cancelled/suspended exceptions and manual timestamp preservation. See the [completion, SLA and monthly schema rules](docs/TV_TRACKER_2_5_3_RELEASE.md). Manual tracker columns are preserved except Comments, Assignee and iAssignee, which the upstream rules intentionally clear. Raw captures preserve original values.

Queue imports/extractions sync automatically when configured. A failed write gets bounded retries and remains saved with a retry action. Newer captures wait behind unresolved older failures. After configuration, unsynced local captures are picked up by the running app. Google Sheets is authoritative for tracker production data; SQLite also stores the separate imported Excel report source, report settings, and change history. Failed report publication leaves the imported files available locally for retry.

## Build, test, and contribute

- [Desktop install, configuration, backup, and build guide](docs/DESKTOP_GUIDE.md)
- [Validation record and release limits](docs/DESKTOP_VALIDATION.md)
- [Architecture](PROJECT_ARCHITECTURE.md)
- [Upstream production rules](docs/TV_Search_Sync_Prompt.md)
- [Optional legacy browser/Streamlit development](docs/LEGACY_WEB_README.md)

Build with `desktop/build.ps1`. Installer and portable output go to `release/<version>/`. Run `python make_bundle.py` to create the matching source ZIP with a SHA-256 source manifest. Dependencies are recorded in lockfiles; 2.2.0 added electron-updater for Windows releases.

For a contribution, branch from `tv-tracker-app`, make a focused change, run the relevant Python, desktop-settings and Playwright suites, and open a pull request targeting `tv-tracker-app`. Keep credentials, captures, runtime data, and generated release files out of commits. The baseline XLSX files already supplied by upstream are required application inputs and are included in packages/source bundles.

## Tv Tracker desktop updates

Use **Download version** in the toolbar or **Connections & settings → Updates**. The installed app checks for published releases, but downloads start only when you click **Download**. After downloading, choose **Install & open** to install and launch the new version. Closing the app does not install an update. See [setup and release instructions](docs/DESKTOP_UPDATES.md). Users moving from a 2.x installation to a 1.0.x version need a manual installer upgrade because the updater prevents downgrades.
