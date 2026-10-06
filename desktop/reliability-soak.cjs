// Real application endurance check with a disposable profile and synthetic data.
const {_electron: electron} = require('../gsheet_dashboard/frontend/node_modules/playwright');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const assert = require('node:assert/strict');
const {setTimeout: delay} = require('node:timers/promises');
(async () => {
  assert.ok(process.env.DESKTOP_EXE, 'Supply the packaged candidate');
  const seconds = Number(process.env.TV_TRACKER_SOAK_SECONDS || 600);
  assert.ok(Number.isInteger(seconds) && seconds >= 60 && seconds <= 3600);
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tv-tracker-soak-'));
  const env = {...process.env, DATATRACE_TEST_USER_DATA: profile}; delete env.ELECTRON_RUN_AS_NODE;
  const fixture = path.join(profile, 'orders.csv');
  fs.writeFileSync(fixture, 'Order Number,Task Status,Product\nTV-QA-SOAK-1,Available,Full Title\n');
  let app, cycles = 0;
  const errors = [], latencies = [];
  const started = Date.now();
  try {
    app = await electron.launch({executablePath: process.env.DESKTOP_EXE, env, timeout: 60000});
    const page = await app.firstWindow(); page.setDefaultTimeout(30000);
    page.on('pageerror', error => errors.push(error.message));
    await page.locator('input[type=file]').first().setInputFiles(fixture);
    await page.getByText('preview1', {exact: true}).first().waitFor();
    const initial = await page.evaluate(async()=> (await (await fetch('/api/state?light=1')).json()).previews);
    while (Date.now() - started < seconds * 1000) {
      const tick = Date.now();
      const state = await page.evaluate(async()=>{const response=await fetch('/api/state?light=1');if(!response.ok)throw Error('State failed');return response.json();});
      assert.equal(state.previews.length, initial.length);
      latencies.push(Date.now() - tick);
      await page.getByLabel('Appearance', {exact: true}).selectOption(cycles % 2 ? 'dark' : 'light');
      if (cycles === 1 || cycles === 10) {
        await page.context().setOffline(true);
        await delay(12000);
        await page.context().setOffline(false);
        await page.reload();
        await page.getByText('preview1', {exact: true}).first().waitFor();
      }
      if (cycles === 3 || cycles === 12) {
        await app.evaluate(({dialog}, file)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:file});}, path.join(profile, `backup-${cycles}.tvbackup`));
        assert.equal((await page.evaluate(()=>window.desktop.backup('Fixture soak password 2026!'))).saved, true);
      }
      cycles++;
      if (cycles % 4 === 0) console.log(JSON.stringify({progress: true, cycles, elapsedSeconds: Math.round((Date.now()-started)/1000)}));
      await delay(15000);
    }
    assert.deepEqual(errors, []);
    const final = await page.evaluate(async()=> (await (await fetch('/api/state?light=1')).json()).previews);
    assert.deepEqual(final, initial);
    const result = {passed: true, seconds: Math.round((Date.now()-started)/1000), cycles, maxStateMs: Math.max(...latencies), rendererErrors: errors,
      checks: ['real packaged polling', 'theme changes', 'two renderer network outages and recovery', 'encrypted exports during sustained use', 'capture identity preservation'],
      limitations: ['synthetic profile', 'does not simulate Windows sleep', 'not a multi-day portal soak']};
    fs.mkdirSync(path.join(__dirname, 'test-output'), {recursive:true});
    fs.writeFileSync(path.join(__dirname, 'test-output', 'reliability-soak.json'), JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } finally {
    if (app) { const done=app.waitForEvent('close',{timeout:20000});await app.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(item=>item.label==='Quit Tv Tracker').click());await done; }
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
