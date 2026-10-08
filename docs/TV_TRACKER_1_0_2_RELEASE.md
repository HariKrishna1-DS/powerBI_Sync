# Tv Tracker 1.0.2

Date: 8 October 2026. Branch: `tv-tracker-app` (previously `tv-tracker-online`).

## Report downloads and formatting

- Capacity Report publishes as **PR Excel**, with columns Date through Ext capacity. Extra Status columns and formatting outside the table are cleared.
- Month labels use `MMM-YY`. Daily dates in PR Excel and Daily Orders downloads use `DD-MM-YY` and retain real spreadsheet date values.
- Excel downloads match the reference colors: peach headers, green monthly rows, blue YTD totals, gray daily date/capacity cells, and yellow totals.
- Monthly Orders ends at **SLA on Missing**. PR Excel, Monthly Orders, and Daily Orders each have a download for that report alone; the main Export retains the full workbook.

## Imported orders and Google Sheets edits

- Import details explain raw row counts, skipped rows, and repeated Order Numbers. The latest uploaded file wins for duplicate Order Numbers.
- **Duplicate Orders** replaces Imported files in Overview. Click the count to see the duplicate orders and their source files/worksheets.
- Edit **All Products**, **Full_Search_<MONTH>_<YEAR>**, or **Remaining_Search_<MONTH>_<YEAR>** in Google Sheets to add, update, or remove imported orders. The application reconciles edits and republishes the derived reports.
- A refresh button beside the Tv Tracker logo refreshes all workspaces. Automatic checks run about every 30 seconds while the application is running.
- **Import Excel Changes**, below Captures, records added/removed orders and field changes, including Order Number, previous/new values, source tabs, and a full details view. History is saved across restarts.
- Contradictory edits to the same field in different tabs show a conflict for resolution before publication.
- Retry sync notices have a dismiss button.

## Local settings

The local launcher `gsheet_dashboard/start-local.bat` starts the server under the normal Windows account. Passwords and service-account keys are encrypted for that account and remain saved after the server closes. Running the server under a restricted or different Windows identity can prevent Windows from unlocking those settings.

## Google Sheets connection recovery

- Preview recovery preserves the original authentication or network error instead of showing only a generic recovery warning. A failed recovery does not allocate a new capture number.
- Invalid JWT signature errors identify the saved service-account email and key ID, with instructions appropriate to desktop/local settings or a hosted backend. Private keys and raw token responses are excluded from these messages.
- Network errors identify connectivity, firewall, proxy, and HTTPS certificate checks.
- Captures blocked by authentication, network access, or a missing key resume automatically in order after a successful connection check. Failed checks are spaced five minutes apart.
- Validation conflicts remain blocked for review, including when a later capture has an authentication failure. The saved connection test remains read-only.

A matching JSON file hash establishes that the files are identical; it does not establish that Google accepts the key. Each PC must save an active service-account key with access to the shared spreadsheet. Credentials, encrypted settings, saved captures, and generated data are excluded from this source update.

## In-app production updates

Version 1.0.1 is the production baseline. The installed app checks GitHub's published **Latest** release in `HariKrishna1-DS/powerBI_Sync`, reads that release's `latest.yml`, and downloads its matching Windows installer. Version 1.0.2 and future production versions are discovered dynamically. Removed testing releases and tags without published releases do not become update candidates. Future testing builds should be prereleases; the production updater excludes prereleases and downgrades.

Use **Download version → Check for updates → Download → Install & open**. The download control is always available in the toolbar and Settings. Background checks also notify users when an update is available. Downloads start only when clicked, and installation requires a separate click. The updated application opens after installation; ordinary app shutdown does not install an update. Installing waits for active work and backs up saved settings. Local browser sessions link to GitHub’s latest installer downloads.

Each future production release must publish the installer, blockmap and matching `latest.yml`, then be marked Latest. The desktop release workflow performs this after validation. Existing 1.0.1 installations already use this GitHub repository and can discover 1.0.2 without a new configuration.

## Version and validation

The desktop and frontend manifests and root lockfile records use `1.0.2`. Dependency versions and the Windows application/profile identity are unchanged.

The running local workspace detected existing Google Sheets edits, saved their history, and published the refreshed reports. Closing and reopening the local server retained the imported data and change history. The release includes a newly built Windows installer, portable ZIP, source ZIP, matching update metadata, and file checksums.

Installed applications need a new Windows build to receive these source changes. Build from this version using `desktop/build.ps1`; changing the source version alone does not update installed applications.
