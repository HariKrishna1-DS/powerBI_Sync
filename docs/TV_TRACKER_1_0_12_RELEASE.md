# Tv Tracker 1.0.12

Released October 30, 2026.

TitleVision extraction now runs Refresh View before reading the queue, even when a table is already present. It waits for the refresh response and grid, preserves the saved previews, and fails instead of capturing stale results when refresh is unavailable. Native postback, AJAX and navigation refreshes have browser regression coverage.

SLA countdown anchors use US Central time (America/Chicago), including seasonal daylight-saving offsets. Portal arrival timestamps and absolute deadlines retain their source wall-clock values. The report reference remains the latest arrival date in the selected preview; this is a date-based queue snapshot, not a live overdue timer.

Suspended SearchFix/CRSP2 tasks, suspended orders with Cannot in Comment, suspended orders referencing abstraction or abstractors in ETA Comments, and Workflow Suspended orders with ON HOLD in ETA Comments take Awaiting for Clarification priority. ON HOLD without Workflow Suspended retains the existing rules. Manual status overrides remain supported.

Home Builder product matching includes Home Builder L.., Home Builder U.., Home Builders and the home buiders spelling.

Extracted orders with missing or invalid deadlines remain in the report under Unknown SLA. Cards, status totals, order details, charts, Google Sheets publication and Excel pivot exports reconcile to the included queue orders without inventing deadline dates. Imported Excel report behavior is unchanged.

Restart the source server after updating. Select a fresh preview to see current portal values; older previews retain their original task fields. Local captures and encrypted connections are retained.

The Windows installer follows the existing unsigned release process. Windows may show an unknown-publisher warning.
