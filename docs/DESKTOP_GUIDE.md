# DataTrace Studio 2.0

DataTrace Studio runs the existing production workspace as a Windows desktop application. There is no hosted backend, Render subscription, or PostgreSQL service. The packaged release includes Electron/Node and the Python engine. Google Sheets remains the production source of truth.

## Install or run

- **Installer:** open `DataTrace-Studio-2.0.0-x64.exe` and follow the per-user installation wizard. Administrator access is not required for the default location.
- **Portable:** extract the entire `DataTrace-Studio-2.0.0-x64.zip` into a permanent folder and open `DataTrace Studio.exe`. Keep its `resources` folder and other files together.
- This release targets Windows x64 and was tested on Windows 11. It is unsigned; a trusted code-signing certificate is needed before broad public distribution.
- Python, Node.js, npm, and a separately running web server are not required to use the packaged app. Queue extraction uses installed Microsoft Edge or Google Chrome.

## First connection

1. Select **Connect your workspace**, the settings icon, or press **Ctrl+,**.
2. Enter the Google spreadsheet URL or ID and the exact names of the two production tracker tabs. Defaults retain the existing September 2026 tracker names; change them if your Sheet uses other names.
3. Import a Google service-account JSON key. Enable the Google Sheets API in that Google Cloud project and share the spreadsheet with the displayed account email as **Editor**.
4. Enter your TitleVision username, password, and queue URL. The queue must use `https://tv.datatracetitle.com`.
5. Save settings. The local engine restarts automatically. Reopen settings and use **Test saved Google Sheets connection**.

The password and service-account JSON are encrypted with Windows DPAPI through Electron safeStorage. Settings reads expose credential-presence indicators and the service-account email, never the saved password or private key. These files belong to the Windows account that created them; do not copy the encrypted vault to another computer as a credential migration method. DPAPI protects against other Windows accounts; other software running as the same user remains within the local trust boundary.

## Everyday work

- **Overview / Data sheets / Daily Orders / Monthly report:** production reports from the configured Sheet. A dated offline banner identifies a previously cached copy. Live corrections require a connection.
- **Saved captures:** inspect an imported or extracted raw queue locally and export it as Excel or filtered CSV. A raw capture is not substituted for production reporting.
- **Compare previews:** compare two captures without changing tracker statuses.
- **Changes:** inspect the Sheet's sync audit trail and review items.
- **Ctrl+K:** find a page, open settings, or import a file.
- Google Sheets reads are shared and cached for 30 seconds. Saving a sync or SLA correction invalidates the cache. The connection test forces a fresh read.
- Imported files are saved locally even before credentials are configured. Pending uploads are retried once Sheets is configured. Conflicting preview IDs in an existing cloud history are rejected by the reconciliation guard rather than overwriting that history; resolve the conflict before retrying.

Internet is required for extraction and Google Sheets operations. Previously saved captures and production copies remain readable without it. The application does not solve portal CAPTCHA or MFA automatically; normal portal access is still required.

## Scheduling and closing

Schedule times use India Standard Time. The computer must be awake and DataTrace Studio must be running. Closing the window keeps it in the system tray by default; double-click the tray icon to reopen it. **Workspace → Quit** or the tray's **Quit** stops the app and local engine. An active job prompts before cancellation. Settings → Workspace can disable tray behavior or enable launch at Windows sign-in. Only one instance uses a given profile.

## Data, backup, and migration

Use **Settings → Workspace → Open data folder** for the exact location. The app stores writable data in `app.getPath('userData')/workspace`, outside installation files. Reinstalling or upgrading does not intentionally remove this data. The installer preserves app data when uninstalling.

**Create backup** writes a ZIP containing the SQLite preview history and receipts, local schedule/product preferences, and the dated production cache. Passwords, private keys, and logs are excluded. **Restore backup** validates the archive/database, saves a safety backup of the current workspace, and restores local data. Google Sheets is not changed. Safety copies are retained beside the workspace for recovery; remove them only when you no longer need them.

To migrate the earlier browser application's data, close both applications, make a copy of the old `gsheet_dashboard/previews` directory, and copy it into the desktop workspace as `previews`. Optionally copy `remaining_products.json` and `sync_schedule.json`. Configure credentials through Connections; do not copy a `.env` or key into the installed application. Keep the original project as your rollback copy. An empty workspace can recover previously synced captures from Google Sheets before its first extraction.

## Troubleshooting

- **Missing connection:** configure the Sheet and service-account key, then use the saved-connection test.
- **Authentication rejected:** import a current active key and verify Editor sharing and Sheets API access.
- **Browser not found:** install Edge/Chrome or select its executable in Settings → Workspace.
- **Startup failure:** use the displayed error and **Help → Open logs**. Backend crashes offer an engine restart. The app never binds to a public network interface.
- **Offline:** keep reading saved captures/reports; reconnect and retry. Pending previews remain stored locally.
- **Unreadable vault after changing Windows accounts:** use the original account or rename `settings.vault` and configure new credentials. Local workspace backups remain separately usable.
- **Installer warning:** this local release has no code-signing certificate. Verify the supplied SHA-256 manifest before distributing it internally; public distribution should use a signed build.

## Build from source

Build tools are needed only by developers: Python 3.12 x64 and Node.js 22.12 or newer. Dependency versions are recorded in `desktop/requirements-build.lock` and npm lockfiles.

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File desktop/build.ps1 -Python C:\Path\To\Python312\python.exe
```

The script installs Python build dependencies into `.desktop-build/deps`, installs locked npm dependencies, builds the UI and standalone engine, and writes the installer/portable ZIP to `release`. Pass `-DirectoryOnly` for an unpacked test build. It does not publish or upload a release.

For desktop development after building dependencies and the UI:

```powershell
$env:DATATRACE_PYTHON = 'C:\Path\To\Python312\python.exe'
$env:DATATRACE_DEV_DEPS = (Resolve-Path .desktop-build/deps).Path
npm.cmd --prefix desktop start
```

Tests:

```powershell
npm.cmd --prefix desktop test
node desktop/smoke.cjs
# To smoke-test the packaged application:
$env:DESKTOP_EXE = (Resolve-Path 'release/win-unpacked/DataTrace Studio.exe').Path
node desktop/smoke.cjs
```

See `docs/DESKTOP_VALIDATION.md` for the checks actually completed and their limits.

## Architecture decisions

Electron provides a predictable native window and a bundled Node runtime while retaining the tested React workflows. Its memory and download size exceed a minimal WebView shell; this release favors reliable integration and distribution. The Python engine is bundled with PyInstaller in directory mode, avoiding repeated executable extraction on each launch. The renderer is sandboxed with context isolation and without Node integration. A narrow preload API handles settings and native dialogs, checks IPC senders, and never provides generic filesystem or shell access. The local engine uses an OS-assigned loopback port and per-launch authentication. Windows Job Objects clean up extraction descendants when the engine exits.

References: [Electron security guidance](https://www.electronjs.org/docs/latest/tutorial/security), [Electron safeStorage](https://www.electronjs.org/docs/latest/api/safe-storage), [PyInstaller operating modes](https://pyinstaller.org/en/stable/operating-mode.html).
