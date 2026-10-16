# Tv Tracker 1.0.8

Date: 16 October 2026. Branch: `tv-tracker-app`.

## SLA Status for a selected preview

- In Tracker report mode, SLA Status uses only orders in the selected saved preview. The latest preview is selected by default; the dropdown also opens earlier captures.
- Future SLA, Negative SLA, Today SLA and Grand Total cards, status rows, chart, detail tables and the Excel download all use the same selected preview.
- Queue deadlines without a year and relative durations use the capture timestamp. Existing tracker business statuses are matched only to orders present in that preview.
- Google Sheets updates the SLA Status tab for the selected preview, preserving its formatting rules, chart colors and chart position. Other report tabs keep their existing sources and layout.
- Import Excel report continues to calculate SLA Status from imported orders.
- Preview-specific status edits retain the raw captures and are scoped to the selected preview. Local preview results remain available while the Sheet is offline.

## Release scope

Production, imported Excel, daily and monthly reports retain their existing behavior. Capacity Report and PR Excel continue to group Saturday and Sunday receipts and completions under the preceding Friday.

Existing user connections, captures and imported files remain in the application profile. Local runtime files, credentials and captures are excluded from release source.

This release continues the existing unsigned Windows distribution. Windows may show an unknown-publisher warning.
