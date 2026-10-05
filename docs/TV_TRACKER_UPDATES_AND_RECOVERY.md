# Tv Tracker 2.4.1 — updates and connection recovery

## Installed application

The Windows installer upgrades the existing per-user installation. The app ID remains `com.datatrace.studio` and the profile remains `%APPDATA%\DataTrace Studio`, so renaming or upgrading the application does not move saved captures or connections.

If encrypted settings cannot be read, Tv Tracker opens the local workspace and Updates screen in recovery mode. It preserves the original settings, pauses scheduled work, and asks the user to reconnect. A readable last-known-good settings backup can be restored automatically. Preference changes cannot overwrite an unreadable vault. Explicitly saving replacement connections retains the original encrypted vault and `Local State` together under `connection-backups`.

Settings writes verify encryption before replacing the primary file, flush the temporary file, and retain a previous encrypted copy. A pre-installation backup preserves encrypted connections and their profile metadata; the engine also creates its workspace backup before shutdown. Keep the entire Windows profile backup together: copying an encrypted settings file between unrelated profiles is not a supported migration.

## Normal update flow

1. After startup, the installed app checks GitHub after 15 seconds and every six hours while running. A failed background check retries after 15 minutes. Settings → Updates and Help → Check for updates remain available immediately.
2. A new stable release shows **Update available** in the toolbar. Downloads require a click and are verified against the release checksum. The updater rejects downgrades and prereleases, and does not accept web installers.
3. **Restart & install** is enabled only after a completed download. The backend must be idle and backup creation must succeed. The per-user NSIS upgrade runs silently and reopens Tv Tracker. Ordinary app exit does not install a downloaded update.
4. A locally installed version newer than the public release explicitly identifies the older GitHub version; it is never offered as a downgrade.

Checks use the fixed `HariKrishna1-DS/powerBI_Sync` GitHub release feed. No GitHub access token is stored in the desktop app. Building an installer locally or pushing source alone does not make a public update available.

## Publishing future versions

1. Increment `desktop/package.json` and the package-lock version. The output directory follows `${version}` automatically.
2. Push the reviewed changes to `tv-tracker`. The release workflow builds and runs engine, interface, desktop and packaged lifecycle checks.
3. The workflow verifies `latest.yml`, installer version, SHA-512 and size, and the presence of the blockmap, portable ZIP and source ZIP before retaining the build.
4. Publication requires an authorized Windows signing certificate in repository secrets `TV_TRACKER_CSC_LINK` and `TV_TRACKER_CSC_KEY_PASSWORD`. The workflow checks the installer’s Authenticode status. Without these, build artifacts are available but the public release is blocked.
5. The workflow stages a draft, uploads the complete asset set, then publishes it as the latest release. It never overwrites an existing published version. Inspect an unfinished draft before retrying that version.

Signing credentials are supplied by the application owner; this local repair does not purchase a certificate or change Windows security settings. The local 2.4.1 installer can be installed for this user without publishing a release.

The owner subsequently authorized distributing the tested 2.4.1 build on GitHub so other users can upgrade. This release uses the verified local unsigned installer, with that status disclosed in the release notes. The automated publication workflow retains its signing requirement for future releases.

## Recovery of this installation

The original vault did not authenticate with the current profile key or the available Tv Tracker test-profile keys. The original encrypted vault and workspace were backed up. Google Sheets was restored from the existing local service-account file and verified with a read-only request. The old TitleVision username/password were not recoverable; enter them in Connections & settings to complete reconnection. Automatic work remains paused until valid connection fields are saved. No Google Sheets production data is moved by the repair.

## Verification on 5 October 2026

- 20 desktop tests passed, covering encrypted backups, unreadable vault protection, release integrity, concurrent update actions, network/checksum errors and installer recovery.
- All 31 desktop UI regressions passed, including the background-update indicator and accessible recovery/settings controls.
- 11 focused engine/connection tests passed, including recovery-mode scheduling protection.
- Packaged lifecycle checks passed for startup, secure IPC, encrypted settings, backup/restore, saved data and clean shutdown. The final recovery build also passed three real Electron launches proving corrupt-vault recovery and persistence.
- The final packaged 2.4.1 app automatically contacted the real GitHub feed after startup and correctly reported that GitHub still publishes 2.2.1. No downgrade was offered.
- `latest.yml` matches the 151,752,771-byte installer and its SHA-512. The installer reports product version 2.4.1. This local installer is unsigned and has not been published.

The interactive local upgrade from installed 2.2.1 to 2.4.1 completed on 5 October 2026 through a temporary loopback update feed using an isolated test profile. The downloaded installer matched SHA-256 `59dea91034e04783797766accf73addf656dfd65ab3dbb29246a24629dd10f90`. The installation now reports 2.4.1, and its permanent feed still points to the official GitHub repository. The temporary feed was closed after the installer handoff.

The installed executable was then launched with the normal production profile. Native UI checks confirmed that Orders displays 7,257 retained tracker orders, Google Sheets remains configured, encrypted settings are readable, and the local saved-capture count remains zero, matching the pre-upgrade baseline. Both the automatic startup check and the manual Check for updates button contacted GitHub successfully and reported public version 2.2.1 without offering a downgrade. The app was left open on Connections & settings for the user to re-enter the missing TitleVision credentials. Capture and scheduled-work verification require those credentials; automatic installer relaunch was not independently observed in this session.
