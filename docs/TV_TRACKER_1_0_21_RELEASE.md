# Tv Tracker 1.0.21

Released November 12, 2026.

- Adds an optional completed ExcelReport upload in Production Report. Matches completed production orders by order number and copies valid Completed Time (hours) timestamps into blank Out Time cells.
- Preserves all existing Out Time values. Repeated identical timestamps are deduplicated; conflicting completion timestamps are excluded and reported for review.
- Shows per-workbook completion counts and order details, alongside existing-date and unmatched-order counts. Completion changes use the existing Check, Proceed, backup and Revert workflow.
- Adds a Related Orders worksheet to the SLA Compare summary download, containing exactly the orders counted in the summary matrix, with statuses, SLA categories and order details.
- Centers the upload area and refreshes Full Search and C-O and Update cards with larger typography, aligned metrics and responsive spacing.
- Enlarges report table headers and data, including the Production Report order preview.

Local captures and encrypted connections are retained. The Windows installer follows the existing unsigned distribution process; Windows may show an unknown-publisher warning.
