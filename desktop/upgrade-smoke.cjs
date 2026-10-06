// Isolated migration/update check. Actual NSIS execution is restricted to hosted CI.
const {_electron: electron} = require('../gsheet_dashboard/frontend/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const crypto = require('node:crypto');

(async () => {
  const version = require('./package.json').version;
  const folder = path.resolve('release', version);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tv-tracker-upgrade-check-'));
  const env = {...process.env, DATATRACE_TEST_USER_DATA: profile};
  const install = process.env.TV_TRACKER_TEST_INSTALL === '1';
  if (install && (process.env.GITHUB_ACTIONS !== 'true' || process.env.RUNNER_ENVIRONMENT !== 'github-hosted')) throw Error('Installer acceptance is restricted to disposable GitHub-hosted runners.');
  delete env.ELECTRON_RUN_AS_NODE;
  const allowed = new Set(['latest.yml', `Tv-Tracker-${version}-x64.exe`, `Tv-Tracker-${version}-x64.exe.blockmap`]);
  const server = http.createServer((req, res) => {
    const name = new URL(req.url, 'http://localhost').pathname.slice(1);
    if (!allowed.has(name)) { res.writeHead(404); res.end(); return; }
    const file = path.join(folder, name);
    res.writeHead(200, {'Content-Length': fs.statSync(file).size});
    if (req.method === 'HEAD') res.end(); else fs.createReadStream(file).pipe(res);
  });
  let app;
  async function launch(executablePath) {
    app = await electron.launch({executablePath, env, timeout: 60000});
    const page = await app.firstWindow(); page.setDefaultTimeout(30000);
    await page.waitForFunction(() => !!window.desktop);
    return page;
  }
  async function quit() {
    const closed = app.waitForEvent('close', {timeout: 20000});
    await app.evaluate(({Menu}) => Menu.getApplicationMenu().items[0].submenu.items.find(item => item.label === 'Quit Tv Tracker').click());
    await closed; app = null;
  }
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let page = await launch(process.env.BASELINE_EXE || path.resolve('release/2.6.0/win-unpacked/Tv Tracker.exe'));
    assert.equal((await page.evaluate(() => window.desktop.getUpdateState())).currentVersion, '2.6.0');
    console.log('Baseline: save connections and wait for engine restart.');
    const oldOrigin = new URL(page.url()).origin;
    await page.evaluate(() => window.desktop.saveSettings({username: 'upgrade-fixture', password: 'Fixture-only upgrade password'}));
    await page.waitForURL(url => url.origin !== oldOrigin);
    await page.waitForFunction(() => !!window.desktop);
    const fixture = path.join(profile, 'fixture.csv');
    fs.writeFileSync(fixture, 'Order Number,Task Status,Product\nUPGRADE-001,Available,Full Title\n');
    await page.locator('input[type=file]').first().setInputFiles(fixture);
    await page.getByText('preview1', {exact: true}).first().waitFor();
    console.log('Baseline: synthetic capture saved. Checking and downloading update.');
    await page.evaluate(() => window.desktop.savePreferences({theme: 'dark'}));
    const baseline = await page.evaluate(async () => (await (await fetch('/api/state')).json()).previews);
    await app.evaluate((_, config) => {
      const updater = process.mainModule.require('electron-updater').autoUpdater;
      Object.defineProperty(updater.app, 'baseCachePath', {value: config.cache});
      updater.downloadedUpdateHelper = null;
      updater.setFeedURL({provider: 'generic', url: config.url});
      updater.disableDifferentialDownload = true;
    }, {cache: path.join(profile, 'update-cache'), url: `http://127.0.0.1:${server.address().port}`});
    assert.equal((await page.evaluate(() => window.desktop.checkForUpdates())).status, 'available');
    assert.equal((await page.evaluate(() => window.desktop.downloadUpdate())).status, 'downloaded');
    const downloaded = await app.evaluate(() => process.mainModule.require('electron-updater').autoUpdater.downloadedUpdateHelper.file);
    assert.ok(path.resolve(downloaded).startsWith(path.join(profile, 'update-cache') + path.sep));
    const hash = file => crypto.createHash('sha512').update(fs.readFileSync(file)).digest('hex');
    assert.equal(hash(downloaded), hash(path.join(folder, `Tv-Tracker-${version}-x64.exe`)));
    console.log('Download verified. Testing installer handoff failure recovery.');
    // Exercise actual pre-update backup/engine shutdown and recovery after a failed handoff.
    await app.evaluate(() => {
      const updater = process.mainModule.require('electron-updater').autoUpdater;
      global.originalTestQuitAndInstall = updater.quitAndInstall.bind(updater);
      updater.quitAndInstall = () => { throw Error('Simulated installer handoff failure'); };
    });
    const beforeRecovery = new URL(page.url()).origin;
    await page.evaluate(() => { window.desktop.installUpdate().catch(() => {}); });
    await page.waitForURL(url => url.origin !== beforeRecovery);
    await page.getByText('preview1', {exact: true}).first().waitFor();
    assert.equal((await page.evaluate(() => window.desktop.getUpdateState())).status, 'downloaded');
    assert.deepEqual(await page.evaluate(async () => (await (await fetch('/api/state')).json()).previews), baseline);
    if (install) {
      console.log('Executing actual NSIS update on the disposable runner.');
      await app.evaluate(() => {
        const updater = process.mainModule.require('electron-updater').autoUpdater;
        // The harness launches the new app after validating the installed bytes.
        updater.quitAndInstall = silent => global.originalTestQuitAndInstall(silent, false);
      });
      const closed = app.waitForEvent('close', {timeout: 60000});
      await page.evaluate(() => { window.desktop.installUpdate().catch(() => {}); });
      await closed; app = null;
      const installedAsar = path.join(path.dirname(process.env.DESKTOP_EXE), 'resources/app.asar');
      const expectedHash = hash(process.env.CANDIDATE_ASAR);
      const deadline = Date.now() + 120000;
      let matches = false;
      while (Date.now() < deadline) {
        try { matches = hash(installedAsar) === expectedHash; } catch {}
        if (matches) break;
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      assert.ok(matches, 'NSIS must install the exact candidate application');
      await new Promise(resolve => setTimeout(resolve, 5000));
    } else await quit();
    console.log('Opening 2.7.0 with the existing 2.6.0 profile.');
    page = await launch(process.env.DESKTOP_EXE || path.join(folder, 'win-unpacked/Tv Tracker.exe'));
    assert.equal((await page.evaluate(() => window.desktop.getUpdateState())).currentVersion, version);
    const settings = await page.evaluate(() => window.desktop.getSettings());
    assert.equal(settings.username, 'upgrade-fixture'); assert.equal(settings.passwordSet, true);
    assert.equal((await page.evaluate(() => window.desktop.getPreferences())).theme, 'dark');
    assert.deepEqual(await page.evaluate(async () => (await (await fetch('/api/state')).json()).previews), baseline);
    const backups = path.join(profile, 'workspace/backups');
    const priorBackup = fs.readdirSync(backups).filter(name => name.startsWith('before-update-')).sort().at(-1);
    assert.ok(priorBackup, 'Actual update preparation must create a workspace backup');
    await app.evaluate(({dialog}, file) => {
      dialog.showOpenDialog = async () => ({canceled: false, filePaths: [file]});
      dialog.showMessageBox = async () => ({response: 1});
    }, path.join(backups, priorBackup));
    await page.evaluate(() => { window.desktop.restoreBackup('').catch(() => {}); });
    await page.waitForEvent('load', {timeout: 30000});
    assert.deepEqual(await page.evaluate(async () => (await (await fetch('/api/state')).json()).previews), baseline);
    console.log(JSON.stringify({passed: true, from: '2.6.0', to: version,
      installerExecuted: install,
      checks: ['actual updater download and SHA-512', 'isolated update cache', 'failed installer handoff recovery', 'version migration preserves capture and encrypted connections and preferences', 'restore real pre-update backup'],
      limitations: ['loopback transport, not hosted GitHub assets', ...(!install ? ['NSIS installation not executed'] : []), 'synthetic profile']}));
  } finally {
    if (app) await quit();
    server.close();
  }
})().catch(error => { console.error(error.message); process.exitCode = 1; });
