// Real packaged engine + renderer; disposable files/profile, no external credentials.
const {_electron: electron, expect} = require('../gsheet_dashboard/frontend/node_modules/@playwright/test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');

(async () => {
  assert.ok(process.env.DESKTOP_EXE, 'Use a packaged test candidate');
  const root = path.resolve(__dirname, '..');
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tv-tracker-report-test-'));
  const script = `from pathlib import Path
from openpyxl import Workbook
import sys
for name,number,product,status in [('full','001','Full Title','Completed and Delivered'),('remaining','002','Update','Assign to ABS')]:
 b=Workbook();s=b.active
 s.append(['Order Number','Product','Status','In-Time','Out Time','SLA Expiration','Custom reference'])
 s.append([number,product,status,'10/01/2026 09:00 AM','10/01/2026 10:00 AM','10/01/2026 10:00 AM','preserved'])
 b.save(Path(sys.argv[1])/(name+'.xlsx'))
`;
  execFileSync(process.env.TV_TRACKER_PYTHON || 'python', ['-c', script, profile], {env: {...process.env, PYTHONPATH: path.join(root, '.desktop-build/deps')}, windowsHide: true});
  const env = {...process.env, DATATRACE_TEST_USER_DATA: profile};
  delete env.ELECTRON_RUN_AS_NODE;
  let app;
  const errors = [];
  try {
    app = await electron.launch({executablePath: process.env.DESKTOP_EXE, env, timeout: 60000});
    const page = await app.firstWindow();
    page.setDefaultTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    await page.getByRole('button', {name: 'Import Excel reports', exact: true}).click();
    await page.getByLabel('Excel report workbooks').setInputFiles([path.join(profile, 'full.xlsx'), path.join(profile, 'remaining.xlsx')]);
    await page.getByRole('button', {name: 'Validate import', exact: true}).click();
    await page.getByRole('heading', {name: '2 validated orders'}).waitFor();
    await page.getByRole('button', {name: 'Use this import and publish reports'}).click();
    await page.waitForFunction(async () => (await (await fetch('/api/reporting')).json()).preferences.publish_status === 'failed');
    await expect(page.getByRole('combobox', {name: 'Report source', exact: true})).toHaveValue('import');
    const state = await page.evaluate(async () => (await fetch('/api/state?light=1')).json());
    assert.equal(state.previews.length, 0, 'Report imports must never become queue captures');
    await page.getByRole('button', {name: 'Daily Orders', exact: true}).click();
    await page.getByRole('heading', {name: 'Daily production orders'}).waitFor();
    await expect(page.locator('.report-metric').filter({hasText: /^Received/}).locator('strong')).toHaveText('2');
    await expect(page.locator('.report-metric').filter({hasText: /^On time SLA/}).locator('strong')).toHaveText('1');
    const exported = await page.evaluate(async () => {const r = await fetch('/api/reporting/export');return {status: r.status, bytes: (await r.arrayBuffer()).byteLength};});
    assert.equal(exported.status, 200);assert.ok(exported.bytes > 5000);
    await page.getByRole('button', {name: 'Capacity Report', exact: true}).click();
    await page.getByText('2026 YTD', {exact: true}).waitFor();
    await page.getByRole('heading', {name: 'Daily capacity', exact: true}).scrollIntoViewIfNeeded();
    const output = path.join(__dirname, 'test-output');fs.mkdirSync(output, {recursive: true});
    await page.screenshot({path: path.join(output, 'packaged-capacity-report.png')});
    await page.reload();
    await page.getByRole('combobox', {name: 'Report source', exact: true}).waitFor();
    await expect(page.getByRole('combobox', {name: 'Report source', exact: true})).toHaveValue('import');
    assert.deepEqual(errors, []);
    const result = {passed: true, checks: ['real multiple workbook validation', 'source activation', 'publish failure recovery state', 'capture isolation', 'daily SLA equality', 'real workbook export', 'capacity totals', 'reload persistence'], rendererErrors: errors};
    fs.writeFileSync(path.join(output, 'packaged-report-smoke.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  } finally {
    if (app) {
      const closed = app.waitForEvent('close', {timeout: 20000});
      await app.evaluate(({Menu}) => Menu.getApplicationMenu().items[0].submenu.items.find(item => item.label === 'Quit Tv Tracker').click());
      await closed;
    }
  }
})().catch(error => {console.error(error);process.exitCode = 1;});
