# Tv Tracker 1.0.1

The application version is 1.0.1 on `tv-tracker-updates`. This project continues from the repository's earlier 2.6.0 source with the Excel report and extraction updates.

## Included changes

- Excel imports drive application dashboards and Google Sheets reports, including previous-month orders and all imported statuses.
- Saved files can be removed or uploaded again with updated rows.
- Queue extraction uses a visible browser, saves captures locally, and can be cancelled.
- Google Sheets receives seven report tabs, including Daily Status Report with SLA On Time and SLA Missing.
- Selecting a date in the application highlights its Daily Status Report row in Google Sheets.
- Credentials, local captures, generated reports, logs, and caches are excluded from source control.

## Version and installation

The desktop and web app manifests and their lockfiles use 1.0.1. Desktop packaging reads the version from `desktop/package.json`, including the displayed app version and installer filenames.

This source update does not create or publish a Windows installer. An installed 2.6.0 app needs a rebuilt 1.0.1 installer and manual installation because 1.0.1 is a lower version number. Existing 2.6.0 release records remain historical records.
