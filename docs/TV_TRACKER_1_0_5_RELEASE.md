# Tv Tracker 1.0.5

Date: 15 October 2026. Branch: `tv-tracker-app`.

## Imported Excel reports

- Full_Search contains only orders from the Full Search workbook. Remaining_Search contains only orders from the C-O/Update workbook, regardless of Product. All Products contains both source groups.
- A repeated Order Number within one workbook retains the later occurrence. Matching numbers across different workbooks remain separate normal orders in Overview, production reports, SLA Status and exports.
- Duplicate Orders separates within-workbook repeats from an informational Across workbooks list, with filenames and worksheet row references. Import details distinguish source data rows from retained orders and exclude headers.
- Imported received dates use Date / Received Date first, with In-Time as a fallback. A later processing timestamp no longer creates a false received date.
- Google Sheets publication clears obsolete rows and verifies the published reports. Existing imported Sheet edits are preserved and remain associated with their source workbook.

## Capacity and order details

- Saturday and Sunday receipts and completions are added to the preceding Friday in Capacity Report, PR Excel, the chart and exports. This applies across month and year boundaries and uses one capacity target for the combined day. Source dates remain unchanged.
- The live daily capacity table shows the current month. Historical months remain in the monthly summary and open their daily dates in the same popup.
- Daily Orders and Capacity dates open searchable tables with sorting, pagination and filtered CSV downloads. Capacity details show new receipts, carryover, completions and activity on the next reporting date.
- Order details can be edited from the date popup. Saves create a recovery backup, reject stale edits and record field changes. Matching numbers in different workbooks edit the selected source record.

## SLA and appearance

- SLA Status uses the active report source throughout the app, Google Sheets and Excel download. Orders without valid SLA expiration remain visible separately and are excluded from deadline-category totals.
- The SLA Excel download includes source workbook details and a native summary PivotTable.
- Updated typography, metric cards, tables and dialogs support light and dark themes, clear selection states and narrow screens.
- The local launcher can open the workspace in an external browser after the server is ready.

## Release

The release workflow builds the Windows x64 installer, portable ZIP, source archive and update metadata. Engine, desktop, interface and packaged lifecycle checks run before publication. Hashes verify the installer and downloadable assets.

Version 1.0.5 continues the existing unsigned Windows release format. Windows may show an unknown-publisher warning. Existing per-user connections, captures and imported reports remain in the same application profile during an upgrade.
