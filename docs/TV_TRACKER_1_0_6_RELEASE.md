# Tv Tracker 1.0.6

Date: 15 October 2026. Branch: `tv-tracker-app`.

## A fresh report for each user

- New installations contain no saved captures, imported orders, baseline workbooks or preset Google Sheet. Each Windows account keeps its own local workspace and connection settings.
- Production rows come from the user's imports, queue captures and connected spreadsheet. Shipped baseline orders are no longer inserted into trackers or used to populate manual fields.
- **Start new report** clears local captures, imported reports and activity, pauses scheduled runs, and restarts capture numbering at **preview1**. A recovery backup is saved before the reset. Connections and Google Sheets remain unchanged.
- Deleted previews stay deleted after refresh and restart. A fresh report does not automatically recover the previous cloud preview history. If an existing Sheet has conflicting preview numbers, the existing numbering-resolution flow remains available.
- Upgrading retains existing user data until that user explicitly chooses reset or deletion.

## Saved captures

- Use **View all saved captures** beside Saved Captures in the sidebar, or **Manage captures** in Capture library, to browse every local preview in an expanded window.
- Maximize and restore the window, search by name/date/source/row count, and open a capture's order details.
- Select individual previews with checkboxes, select all search results, clear selection, and delete multiple previews in one operation.
- Deletion requires an explicit confirmation and saves one recovery backup for the selected batch. Invalid/stale selections, active jobs and backup failures prevent deletion. Export files are restored if a file operation fails.
- The capture manager supports keyboard navigation, short desktop windows, and light/dark themes.

## Validation and downloads

The release pipeline runs engine, desktop, interface and packaged lifecycle checks before publication. Download the Windows x64 installer, portable ZIP or source archive from Assets. Update metadata and SHA256SUMS verify the published files.

This version continues the existing unsigned Windows release format.
