# Tv Tracker 1.0.4

Date: 13 October 2026. Branch: `tv-tracker-app`.

## Connections and updates

- Connections & settings now has **SA Key**, **Google Sheets Enable**, and **Spreadsheet** links beside the Google Sheets heading. Each opens the requested Google page in the system browser.
- Google Sheets connection errors now show when the Sheets API is disabled for the imported key's project, instead of a generic permission error. The connection guide explains the per-user spreadsheet and service-account setup.
- The toolbar offers **Download version** only when a newer release is available. After the update is downloaded, installation remains available in Connections & settings → Updates.

## Production reports and schedules

- Daily Orders now includes **Reset date** to clear the selected date, highlight, and shared All Products filter. Date selection also keeps the All Products filter aligned with the selected day.
- Preview sync can resolve local preview-number conflicts without discarding pending captures. Report publication handles existing tabs and reports saved local data accurately while Sheets updates are pending or fail.
- AutoLogin Trigger supports every day, Monday through Friday, Saturday and Sunday, or custom days. Last attempt and Last success can be cleared from the schedule display.

## Release

The GitHub workflow builds the Windows installer, portable ZIP, update metadata, and source archive; runs its release checks; and publishes the complete set only after those checks pass. Existing per-user connections and local captures remain in their current profile during installation.

This version may use an unsigned Windows installer, as with versions 1.0.2 and 1.0.3. Windows may show an unknown-publisher warning. The release includes update-manifest integrity information and SHA-256 checksums.
