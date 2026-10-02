const {app, BrowserWindow, Menu, Tray, dialog, shell, ipcMain, safeStorage, nativeImage} = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawn, execFile} = require('node:child_process');
const {createVault, publicSettings, validateSettings, validateServiceAccount, allowedExternal} = require('./settings.cjs');

app.setName('Tv Tracker');
app.setAppUserModelId('com.datatrace.studio');
// Keep the v2.0 profile and installer identity so a name change is a safe upgrade.
app.setPath('userData', process.env.DATATRACE_TEST_USER_DATA || path.join(app.getPath('appData'), 'DataTrace Studio'));
const root = path.resolve(__dirname, '..');
let window, tray, backend, backendUrl = '', settings, vault, pendingAccount;
let quitting = false, restarting = false, quitRequested = false;
const token = crypto.randomBytes(32).toString('hex');
const icon = path.join(__dirname, 'assets', 'icon.png');
const dataPath = path.join(app.getPath('userData'), 'workspace');
const logPath = path.join(app.getPath('userData'), 'logs');
const settingsPath = path.join(app.getPath('userData'), 'settings.vault');
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.exit(0);

function detectBrowser() {
  return [settings.browserPath,
    path.join(process.env.ProgramFiles || '', 'Google/Chrome/Application/chrome.exe'),
    path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/Application/chrome.exe'),
    path.join(process.env['ProgramFiles(x86)'] || '', 'Microsoft/Edge/Application/msedge.exe'),
    path.join(process.env.ProgramFiles || '', 'Microsoft/Edge/Application/msedge.exe'),
  ].find(file => file && fs.existsSync(file)) || '';
}
function safeError(error) {
  let message = String(error?.message || error);
  for (const secret of [token, settings?.password, settings?.serviceAccount]) if (secret) message = message.split(secret).join('[redacted]');
  return message.slice(0, 2000);
}
function publicState() {
  return {...publicSettings(settings), version: app.getVersion(), dataPath, browserDetected: !!detectBrowser(), packaged: app.isPackaged};
}
function configureStartup(preserveDisabled = false) {
  // Retain the v2.0 registry entry name but update its executable after an upgrade.
  // Isolated test profiles must never change the user's Windows startup settings.
  if (app.isPackaged && !process.env.DATATRACE_TEST_USER_DATA) {
    const existing = preserveDisabled ? app.getLoginItemSettings().launchItems?.find(item => item.name === 'com.datatrace.studio') : null;
    app.setLoginItemSettings({openAtLogin: settings.startAtLogin, name: 'com.datatrace.studio', enabled: existing?.enabled ?? true});
  }
}
async function engineRequest(route, options = {}) {
  const response = await fetch(`${backendUrl}${route}`, {...options, signal: AbortSignal.timeout(30000), headers: {...options.headers, 'X-DataTrace-Token': token}});
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw Error(result.error || `The local engine returned ${response.status}.`);
  }
  return response;
}
function log(message) {
  fs.appendFileSync(path.join(logPath, 'desktop.log'), `${new Date().toISOString()} ${safeError(message)}\n`);
}
async function startBackend() {
  fs.mkdirSync(dataPath, {recursive: true});
  fs.mkdirSync(logPath, {recursive: true});
  const logFile = path.join(logPath, 'desktop.log');
  if (fs.existsSync(logFile) && fs.statSync(logFile).size > 5 * 1024 * 1024) fs.renameSync(logFile, `${logFile}.previous`);
  const executable = app.isPackaged ? path.join(process.resourcesPath, 'backend', 'datatrace-engine.exe') : process.env.DATATRACE_PYTHON || 'python';
  const args = app.isPackaged ? [] : [path.join(root, 'gsheet_dashboard', 'desktop_engine.py')];
  const env = {...process.env, PYTHONUNBUFFERED: '1', DATATRACE_DESKTOP: '1',
    DATATRACE_DATA_DIR: dataPath, DATATRACE_DESKTOP_TOKEN: token,
    DATATRACE_SPREADSHEET_ID: settings.spreadsheetId, DATATRACE_QUEUE_URL: settings.queueUrl,
    DATATRACE_FULL_TRACKER: settings.fullTrackerTitle, DATATRACE_REMAINING_TRACKER: settings.remainingTrackerTitle,
    DATATRACE_USERNAME: settings.username, DATATRACE_PASSWORD: settings.password,
    GOOGLE_SERVICE_ACCOUNT_JSON: settings.serviceAccount, DATATRACE_HEADLESS: 'true',
    DATATRACE_NODE_EXECUTABLE: process.execPath,
    DATATRACE_EXTRACTOR_DIR: app.isPackaged ? path.join(process.resourcesPath, 'extractor') : path.join(root, '.desktop-build', 'extractor'),
    PUPPETEER_EXECUTABLE_PATH: detectBrowser(),
  };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.RENDER;
  delete env.PORT;
  const child = spawn(executable, args, {env, cwd: dataPath, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe']});
  backend = child;
  await new Promise((resolve, reject) => {
    let pending = '', settled = false;
    const timer = setTimeout(() => finish(Error('The local engine did not become ready within 45 seconds. Open the logs folder for details.')), 45000);
    function finish(error) { if (settled) return; settled = true; clearTimeout(timer); error ? reject(error) : resolve(); }
    child.once('error', error => finish(error));
    child.once('exit', code => {
      finish(Error(`The local engine stopped during startup (code ${code}).`));
      if (settled && !quitting && !restarting && backend === child && window) showRecovery('The local engine stopped. Your saved data is still on this computer.');
    });
    child.stdout.on('data', chunk => {
      pending += chunk.toString();
      const lines = pending.split('\n'); pending = lines.pop();
      for (const line of lines) {
        if (line.startsWith('DATATRACE_READY ')) {
          try { const ready = JSON.parse(line.slice(16)); backendUrl = `http://127.0.0.1:${ready.port}`; finish(); }
          catch (error) { finish(error); }
        } else if (line.trim()) log(line);
      }
    });
    child.stderr.on('data', chunk => log(chunk.toString()));
  });
  await engineRequest('/api/health');
}
async function stopBackend(force = false) {
  const child = backend;
  if (!child || child.exitCode !== null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  try { await engineRequest('/api/desktop/shutdown', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({force})}); } catch { /* process may already have exited */ }
  await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 3000))]);
  if (child.exitCode === null) {
    await new Promise(resolve => execFile('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], {windowsHide: true}, () => resolve()));
  }
  if (backend === child) backend = null;
}
async function showRecovery(message) {
  const {response} = await dialog.showMessageBox(window, {type: 'error', title: 'Tv Tracker', message, detail: 'Restart the local engine or open its logs to diagnose the problem.', buttons: ['Restart engine', 'Open logs', 'Quit'], defaultId: 0, cancelId: 2});
  if (response === 1) { await shell.openPath(logPath); return; }
  if (response === 2) return requestQuit();
  restarting = true;
  try { await stopBackend(true); await startBackend(); configureSession(); await window.loadURL(backendUrl); }
  catch (error) { dialog.showErrorBox('Could not start Tv Tracker', safeError(error)); }
  finally { restarting = false; }
}
function configureSession() {
  const session = window.webContents.session;
  session.setPermissionRequestHandler((_, __, callback) => callback(false));
  session.setPermissionCheckHandler(() => false);
  session.webRequest.onBeforeSendHeaders((details, callback) => {
    if (details.url.startsWith(`${backendUrl}/`)) details.requestHeaders['X-DataTrace-Token'] = token;
    callback({requestHeaders: details.requestHeaders});
  });
  session.webRequest.onBeforeRequest((details, callback) => {
    callback({cancel: !details.url.startsWith(`${backendUrl}/`) && !details.url.startsWith('blob:') && !details.url.startsWith('devtools:')});
  });
}
function focusWindow() { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } }
function sendCommand(command) { focusWindow(); window?.webContents.send('desktop:command', command); }
async function requestQuit() {
  if (quitRequested || quitting) return;
  quitRequested = true;
  try {
    const state = backendUrl && backend?.exitCode === null ? await (await engineRequest('/api/health')).json().catch(() => ({})) : {};
    if (state.running) {
      const {response} = await dialog.showMessageBox(window, {type: 'warning', message: 'An extraction or sync is still running.', detail: 'Keep the app open to let it finish. Quitting cancels active work; saved previews remain available for retry.', buttons: ['Keep running', 'Quit and cancel'], defaultId: 0, cancelId: 0});
      if (response === 0) return;
    }
    quitting = true;
    await stopBackend(true);
    tray?.destroy();
    app.quit();
  } catch (error) { log(error); quitting = true; await stopBackend(true); app.quit(); }
  finally { quitRequested = false; }
}
function registerIpc() {
  const handle = (channel, handler) => ipcMain.handle(channel, async (event, payload) => {
    if (!window || event.sender !== window.webContents || event.senderFrame !== window.webContents.mainFrame || new URL(event.senderFrame.url).origin !== backendUrl) throw Error('This request is not from the trusted application window.');
    try { return await handler(payload); } catch (error) { throw Error(safeError(error)); }
  });
  handle('desktop:settings', () => publicState());
  handle('desktop:discard-settings', () => { pendingAccount = undefined; });
  handle('desktop:import-account', async () => {
    const result = await dialog.showOpenDialog(window, {title: 'Import Google service-account key', properties: ['openFile'], filters: [{name: 'Google JSON key', extensions: ['json']}]});
    if (result.canceled) return null;
    if (fs.statSync(result.filePaths[0]).size > 65536) throw Error('This key file is too large.');
    pendingAccount = validateServiceAccount(fs.readFileSync(result.filePaths[0], 'utf8'));
    return {email: JSON.parse(pendingAccount).client_email};
  });
  handle('desktop:choose-browser', async () => {
    const result = await dialog.showOpenDialog(window, {title: 'Choose Microsoft Edge or Google Chrome', properties: ['openFile'], filters: [{name: 'Browser application', extensions: ['exe']}]});
    return result.canceled ? null : result.filePaths[0];
  });
  handle('desktop:save-settings', async input => {
    const health = await (await engineRequest('/api/health')).json();
    if (health.running) throw Error('Wait for the current extraction or sync to finish before changing connections.');
    const next = validateSettings(input, settings);
    if (pendingAccount) next.serviceAccount = pendingAccount;
    if (input.clearServiceAccount === true) next.serviceAccount = '';
    vault.write(next); settings = next; pendingAccount = undefined;
    configureStartup();
    restarting = true;
    try { await stopBackend(); await startBackend(); configureSession(); }
    finally { restarting = false; }
    // Reply before navigating so the invoking renderer receives its result.
    setTimeout(() => window?.loadURL(backendUrl), 250);
    return publicState();
  });
  handle('desktop:open-data', () => shell.openPath(dataPath));
  handle('desktop:backup', async () => {
    const result = await dialog.showSaveDialog(window, {title: 'Back up local workspace', defaultPath: `Tv-Tracker-backup-${new Date().toISOString().slice(0, 10)}.zip`, filters: [{name: 'Workspace backup', extensions: ['zip']}]});
    if (result.canceled) return {cancelled: true};
    const response = await engineRequest('/api/desktop/backup');
    fs.writeFileSync(result.filePath, Buffer.from(await response.arrayBuffer()));
    return {saved: true, path: result.filePath};
  });
  handle('desktop:restore', async () => {
    const choice = await dialog.showOpenDialog(window, {title: 'Restore a Tv Tracker backup', properties: ['openFile'], filters: [{name: 'Workspace backup', extensions: ['zip']}]});
    if (choice.canceled) return {cancelled: true};
    const confirmation = await dialog.showMessageBox(window, {type: 'warning', message: 'Replace the local workspace with this backup?', detail: 'Google Sheets and encrypted credentials are unchanged. A safety copy of the current local workspace will be retained.', buttons: ['Cancel', 'Restore backup'], defaultId: 0, cancelId: 0});
    if (confirmation.response !== 1) return {cancelled: true};
    const file = choice.filePaths[0];
    if (fs.statSync(file).size > 100 * 1024 * 1024) throw Error('Backups are limited to 100 MB.');
    const response = await engineRequest('/api/desktop/restore', {method: 'POST', headers: {'Content-Type': 'application/zip'}, body: fs.readFileSync(file)});
    setTimeout(() => window?.reload(), 250);
    return response.json();
  });
}
async function launch() {
  vault = createVault(settingsPath, safeStorage); settings = vault.read();
  configureStartup(true);
  await startBackend();
  window = new BrowserWindow({title: 'Tv Tracker', width: 1440, height: 960, minWidth: 980, minHeight: 680, backgroundColor: '#f5f6fa', show: false, icon,
    webPreferences: {preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true, spellcheck: false}});
  configureSession(); registerIpc();
  window.webContents.on('will-navigate', (event, url) => { if (!url.startsWith(`${backendUrl}/`) && url !== backendUrl) event.preventDefault(); });
  window.webContents.setWindowOpenHandler(({url}) => { if (allowedExternal(url)) shell.openExternal(url); return {action: 'deny'}; });
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  window.webContents.on('render-process-gone', (_, details) => { if (!quitting) showRecovery(`The interface stopped (${details.reason}).`); });
  window.webContents.session.on('will-download', (_, item) => item.setSaveDialogOptions({title: 'Save export', defaultPath: path.join(app.getPath('downloads'), path.basename(item.getFilename()))}));
  window.once('ready-to-show', () => window.show());
  window.on('close', event => { if (quitting) return; event.preventDefault(); if (settings.closeToTray) window.hide(); else requestQuit(); });
  const menu = [
    {label: 'Workspace', submenu: [{label: 'Connections & settings', accelerator: 'CmdOrCtrl+,', click: () => sendCommand('settings')}, {label: 'Quick actions', accelerator: 'CmdOrCtrl+K', click: () => sendCommand('commands')}, {type: 'separator'}, {label: 'Quit Tv Tracker', accelerator: 'Alt+F4', click: requestQuit}]},
    {label: 'Edit', submenu: [{role: 'undo'}, {role: 'redo'}, {type: 'separator'}, {role: 'cut'}, {role: 'copy'}, {role: 'paste'}, {role: 'selectAll'}]},
    {label: 'View', submenu: [{role: 'resetZoom'}, {role: 'zoomIn'}, {role: 'zoomOut'}, {role: 'togglefullscreen'}]},
    {label: 'Help', submenu: [{label: 'Open local data', click: () => shell.openPath(dataPath)}, {label: 'Open logs', click: () => shell.openPath(logPath)}, {label: 'About Tv Tracker', click: () => dialog.showMessageBox(window, {message: 'Tv Tracker', detail: `Version ${app.getVersion()}\nLocal Windows workspace. Google Sheets and TitleVision require internet access.\nSchedules run while the app is open or in the tray.`})}]},
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(menu));
  tray = new Tray(nativeImage.createFromPath(icon).resize({width: 20, height: 20}));
  tray.setToolTip('Tv Tracker · running locally');
  tray.setContextMenu(Menu.buildFromTemplate([{label: 'Open Tv Tracker', click: focusWindow}, {label: 'Connections & settings', click: () => sendCommand('settings')}, {type: 'separator'}, {label: 'Quit', click: requestQuit}]));
  tray.on('double-click', focusWindow);
  await window.loadURL(backendUrl);
}
app.on('second-instance', focusWindow);
app.on('activate', focusWindow);
app.on('before-quit', event => { if (!quitting) { event.preventDefault(); requestQuit(); } });
app.on('window-all-closed', () => { if (quitting) app.quit(); });
if (gotLock) app.whenReady().then(launch).catch(async error => {
  quitting = true;
  await stopBackend(true);
  dialog.showErrorBox('Tv Tracker could not start', `${safeError(error)}\n\nLogs: ${logPath}`);
  app.quit();
});
