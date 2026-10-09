# Tv Tracker 1.0.3

Date: 9 October 2026. Branch: `tv-tracker-app`.

## Excel reports and Daily Orders

- Imported orders marked **Completed and Delivered** are assigned to a later completion month when **Out Time** contains a valid date in that month. A completed order without Out Time remains in its arrival month's completed list. Daily received dates continue to follow In-Time.
- Selecting a Daily Orders date highlights it in **Daily Status Report** and filters the shared Google Sheets **All Products** tab to that received day. A later selection replaces the filter; everyone viewing the same spreadsheet sees the current filter.
- Daily metric cards open the matching order table. Excel report mode now shows the category tables as well as the detailed imported-status tables.
- Chart filters, Status breakdown, and the custom chart start open. The selected report control and duplicate-order chips remain readable in dark mode.

## Project documentation

The root README and architecture guide now describe the Windows desktop flow, local stores, ordered capture sync, independent imported Excel reports, Sheets publication, and manual Power BI refresh.

## Validation

The report workspace regression suite covers the completion-month rule and selected-date filter request. The report interface suite covers metric navigation and expanded sections. The release workflow builds and validates the Windows installer and source package before publishing a GitHub release.

Installed applications receive these changes only through a newly built version. Existing per-user settings, captures, and report data remain in the same profile during an upgrade.

The Windows installer is unsigned for this version; Windows may show an unknown-publisher warning. The release includes update-manifest and SHA-256 checksums for downloaded assets.
