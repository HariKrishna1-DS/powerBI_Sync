# Tv Tracker 1.0.7

Date: 16 October 2026. Branch: `tv-tracker-app`.

- Tracker Report uses only locally saved queue previews. Order Numbers appearing in several captures are consolidated into one order with the latest captured state. Earlier captured orders remain available, with existing completion and SLA evidence rules applied across captures.
- Overview, Data Sheets, Daily Orders, Monthly Orders, Capacity Report, SLA Status and report downloads use the selected source. Import Excel Report uses only uploaded workbooks; retained Google Sheets rows cannot enter either source through refresh or report publication.
- Preview reports retain queue details and identify each order's first and latest capture. Date-dialog edits and SLA corrections are stored separately, preserving the original preview files and imported workbook data.
- Google Sheets connection testing checks the destination without restoring old cloud captures. Reports remain available from their local source when the destination is unavailable.
- New captures and capture deletions change the report revision automatically. Source labels and Overview counts distinguish saved previews from imported workbooks. No default Excel workbook data is bundled or loaded.

Google Sheets remains the destination for publishing the selected reports. Existing local captures, uploaded files, connection settings and credentials are preserved during the upgrade.
