# Tv Tracker 1.0.2

Date: 8 October 2026. Branch: `tv-tracker-online`.

## Google Sheets connection recovery

- Preview recovery preserves the original authentication or network error instead of showing only a generic recovery warning. A failed recovery does not allocate a new capture number.
- Invalid JWT signature errors identify the saved service-account email and key ID, with instructions appropriate to desktop/local settings or a hosted backend. Private keys and raw token responses are excluded from these messages.
- Network errors identify connectivity, firewall, proxy, and HTTPS certificate checks.
- Captures blocked by authentication, network access, or a missing key resume automatically in order after a successful connection check. Failed checks are spaced five minutes apart.
- Validation conflicts remain blocked for review, including when a later capture has an authentication failure. The saved connection test remains read-only.

A matching JSON file hash establishes that the files are identical; it does not establish that Google accepts the key. Each PC must save an active service-account key with access to the shared spreadsheet. Credentials, encrypted settings, saved captures, and generated data are excluded from this source update.

## In-app production updates

Version 1.0.1 is the production baseline. The installed app checks GitHub's published **Latest** release in `HariKrishna1-DS/powerBI_Sync`, reads that release's `latest.yml`, and downloads its matching Windows installer. Version 1.0.2 and future production versions are discovered dynamically. Removed testing releases and tags without published releases do not become update candidates. Future testing builds should be prereleases; the production updater excludes prereleases and downgrades.

Use **Connections & settings → Updates → Check for updates → Download → Restart and install**. Background checks also notify users when an update is available. Download and installation remain explicit choices; installing waits for active work and backs up saved settings.

Each future production release must publish the installer, blockmap and matching `latest.yml`, then be marked Latest. The desktop release workflow performs this after validation. Existing 1.0.1 installations already use this GitHub repository and can discover 1.0.2 without a new configuration.

## Version and validation

The desktop and frontend manifests and root lockfile records use `1.0.2`. Dependency versions and the Windows application/profile identity are unchanged.

The 16 targeted authentication, desktop connection, and automatic recovery checks pass. The local server was also checked against Google Sheets: the saved active key connected successfully, its failed capture synced, report publication completed, and no pending or failed captures remained.

Installed applications need a new Windows build to receive these source changes. Build from this version using `desktop/build.ps1`; changing the source version alone does not update installed applications.
