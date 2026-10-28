# Tv Tracker 1.0.11

This update corrects imported capacity reports and queue SLA classification after 1.0.10.

## Changes since 1.0.10

- **Excel capacity source:** Capacity Report, its search and editable detail tables, and PR Excel downloads read the saved imported Excel data independently of the source selected for other reports. Queue captures cannot add tracker orders to capacity. Without an import, capacity stays empty and asks for Excel files.
- **Friday grouping:** Saturday and Sunday receipts, pending statuses and completions belong to the preceding Friday, including month and year boundaries. Detail rows retain the original received date, original completion date and reporting date. Monthly and YTD totals use those same dates.
- **Completion dates:** Completed and Delivered rows require valid Out Time values for capacity completion counts. Prior-month receipts count on their completion reporting date. Blank or invalid Out Time values are reported rather than replaced with today's date or the received date. A day can show completions with zero new receipts.
- **Repeated imported orders:** Every source occurrence is counted, including multiple appearances of one Order Number in the same workbook. Source row IDs keep each occurrence separate through editing, search, exports and Sheets reconciliation. An upgrade restores retained source occurrences from older imports, preserves saved edits on the matching occurrence, and creates a local safety backup.
- **Queue SLA dates:** The latest source Arrival Time supplies the report date without an India-time date shift. Relative SLA countdowns remain tied to capture time.
- **Queue SLA statuses:** Need to Assign ABS joins Assign to ABS. Active queue orders are classified from queue conditions instead of inheriting Completed and Delivered from historical production rows or old overrides. Captured-row and unique-order totals explain repeated queue rows and provide their details.
- **Sync recovery:** Pending captures can resolve conflicting preview numbers with a backup before syncing in order. Sheets quota retries wait for the quota window. Tracker reports expose pending-sync context and recalculate older cached summaries.

## What 1.0.10 introduced

Version 1.0.10 restored the complete working application omitted from 1.0.9: manual SLA statuses and order editing in Tracker and Import Excel reports, order search, column filters, complete ETA comments and arrival details, imported report-date selection, and completion handling. Those features and the desktop startup, recovery, and updater protections remain in 1.0.11. See the [original 1.0.10 notes](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/tag/v1.0.10).

## Validation and installation

Local validation passed 393 backend tests, 111 browser tests, 28 desktop tests and 2 extractor tests, plus the production frontend build.

The release workflow runs engine, desktop, extractor and browser regressions, builds the Windows installer, and checks packaged startup, connection recovery, shutdown, source archives and update-file integrity before publication. Pull-request builds do not publish a release.

Install the Windows x64 installer or update from 1.0.10 using the installed application's update controls. The release keeps the existing unsigned Windows distribution policy. Existing captures, imported data, connections and settings remain in the local profile. Credentials and personal workbooks are excluded from source commits and release artifacts.
