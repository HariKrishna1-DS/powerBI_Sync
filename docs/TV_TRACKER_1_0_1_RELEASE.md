# Tv Tracker 1.0.1

The application version is 1.0.1 on `tv-tracker-online`. This project continues from the repository's earlier 2.6.0 source with the Excel report and extraction updates.

## Included changes

- Excel imports drive application dashboards and Google Sheets reports, including previous-month orders and all imported statuses.
- Saved files can be removed or uploaded again with updated rows.
- Queue extraction uses a visible browser, saves captures locally, and can be cancelled.
- Google Sheets receives seven report tabs, including Daily Status Report with SLA On Time and SLA Missing.
- Selecting a date in the application highlights its Daily Status Report row in Google Sheets.
- Credentials, local captures, generated reports, logs, and caches are excluded from source control.

## Version and installation

The desktop and web app manifests and their lockfiles use 1.0.1. Desktop packaging reads the version from `desktop/package.json`, including the displayed app version and installer filenames.

The GitHub release provides `Tv-Tracker-1.0.1-x64.exe`, a portable Windows ZIP, the source ZIP, and integrity hashes. Download the installer from the Assets section of the [1.0.1 release](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/tag/v1.0.1).

The Windows installer is unsigned. Windows may ask you to confirm the publisher before running it. Chrome or Edge is required for queue extraction.

Install this version manually when replacing an installed 2.x version because 1.0.1 is a lower version number. This release does not replace 2.8.0 as the repository's latest release. Existing release records remain historical records.
