# Tv Tracker 1.0.10

Version 1.0.9 packaged the ETA assignment correction on an older application snapshot and omitted working local features. This release includes the complete current local application, while retaining the desktop startup, update, and backup compatibility fixes from the published branch.

- **SLA Status:** Add and rename custom statuses; add, edit, copy, and move orders; delete a manual status after moving its orders. The controls work in Tracker report and Import Excel report. Changes belong to the selected preview or imported report date and workbook; moving an existing order preserves the totals. Imported order edits also update search, capacity, daily/monthly reports, exports, and queued Sheets publication.
- **Order search:** Find an order number and its current status from SLA Status and Capacity Report, including orders excluded from SLA totals because their deadline is missing.
- **Column filters:** Filter production and report tables, combine filters, export matching rows, and retain saved view filters.
- **SLA details:** Show complete ETA comments, classification reasons, arrival dates and times, selected-preview context, current orders, and reconciled totals. Imported Excel SLA reports support report-date selection.
- **Queue classification:** Include the local task, product, hold, and abstractor rules. Abstract/abstractor, EOD, and sooner count as assignment evidence. A commitment date matching today in India produces Need to Assign ABS; other dates produce Assign to ABS. Received and fee-approval dates do not become commitment dates.
- **Completion and capacity:** Include the working local Out Time completion handling, report-date capacity calculations, reconciled drilldowns, and spreadsheet status refresh behavior.

Existing captures, connections, settings, manual edits, and report data remain in the user's local profile. Personal spreadsheet IDs, credentials, captures, and runtime files are not shipped.

Install 1.0.10 or use the desktop updater from 1.0.9. A new version number is necessary so installed 1.0.9 applications can discover this correction.
