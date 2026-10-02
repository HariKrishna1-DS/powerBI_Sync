# Tv Tracker updates and setup

## Users

Install the Windows `.exe` from the repository's [latest release](https://github.com/HariKrishna1-DS/powerBI_Sync/releases/latest). Versions 2.1.0 and earlier require this one-time manual upgrade. Portable ZIP users can also install the `.exe` to use the normal installed-app workflow.

Open **Connections & settings → Updates**, or **Help → Check for updates**. Check for a published version, choose Download, then choose Restart & install after captures and syncs finish. Updates are never automatically downloaded or installed on an ordinary quit. A failed check or download leaves the current version installed; check again to retry.

The existing application ID and `%APPDATA%\DataTrace Studio` profile remain stable. Captures, connections, schedules, and preferences survive an upgrade. Do not delete the profile or its Local State file: Windows-encrypted settings rely on that profile. Workspace backups deliberately exclude credentials.

## Connect Google Sheets

1. In Connections, enter the spreadsheet URL or ID and the exact two production tab names.
2. Import the service-account JSON key. Sharing a Sheet with its email does not import the key into the app.
3. Save settings, reopen Connections, and select **Test saved Google Sheets connection**. This reads existing previews and production reports, and reports the next preview number without changing the Sheet.
4. Keep TitleVision username/password and the queue URL configured for extraction. A Google connection test does not validate the portal login.

## Maintainers

Work on `tv-tracker`. For a new release, bump the stable version in `desktop/package.json`, its build output directory, and `desktop/package-lock.json`, then commit and push. The desktop release workflow runs on each push but only builds/publishes a version that has no existing release. Ordinary pushes with an already published version do not change installed apps. Main stays separate.

CI builds the frozen engine, React frontend and NSIS installer; runs engine/unit and packaged lifecycle tests; verifies the source ZIP; stages installer, blockmap, latest.yml and ZIPs in a draft; and only then publishes. Keep all generated update assets together. Never overwrite an existing version. A failed upload leaves a draft for inspection; remove or finish that draft deliberately before rerunning. `workflow_dispatch` can also retry when GitHub exposes the workflow on the default branch. Push a follow-up desktop commit to trigger it while the workflow exists only on the desktop branch.

The built-in workflow token is used only in CI. The app uses the public repository's release feed and contains no GitHub credentials. Making the repository private would require a separate authenticated distribution design.

electron-updater verifies downloaded hashes from release metadata. These builds are currently unsigned; Windows may display an unknown-publisher/reputation prompt. Configure a Windows signing certificate and matching publisher identity in CI before requiring Authenticode publisher verification. Do not disable signature verification or change the app/profile ID to resolve update errors.

Updates use the [electron-builder / electron-updater NSIS workflow](https://www.electron.build/docs/features/auto-update/) and [GitHub release publishing](https://www.electron.build/v26/docs/publish/). No hosted app server is required.
