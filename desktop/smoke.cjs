// Real Electron lifecycle test. All credentials and captured data below are test fixtures.
const { _electron: electron } = require('../gsheet_dashboard/frontend/node_modules/playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {once} = require('node:events');

(async()=>{
  const root=path.resolve(__dirname,'..');
  const output=path.join(__dirname,'test-output');fs.mkdirSync(output,{recursive:true});
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'datatrace-desktop-test-'));
  const executable=process.env.DESKTOP_EXE || require('electron');
  const args=process.env.DESKTOP_EXE?[]:[__dirname];
  const env={...process.env,DATATRACE_TEST_USER_DATA:profile,DATATRACE_DEV_DEPS:path.join(root,'.desktop-build','deps')};
  delete env.ELECTRON_RUN_AS_NODE;
  const started=performance.now();
  let app;
  let base;
  const errors=[];
  try {
    app=await electron.launch({executablePath:executable,args,env,timeout:60000});
    const page=await app.firstWindow();
    page.on('pageerror',e=>errors.push(e.message));
    await page.getByRole('heading',{name:'Clear work. Confident decisions.'}).waitFor({timeout:30000});
    assert.equal(await page.title(), 'Tv Tracker');
    assert.equal(await app.evaluate(({app})=>app.getName()), 'Tv Tracker');
    assert.equal((await page.locator('.brand').innerText()).replace(/\s+/g, ' '), 'Tv TRACKER');
    const startupMs=Math.round(performance.now()-started);
    base=new URL(page.url()).origin;
    assert.equal((await fetch(base+'/api/health')).status,401,'unauthenticated API access must fail');
    const prefs=await app.evaluate(({BrowserWindow})=>{const p=BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();return {sandbox:p.sandbox,nodeIntegration:p.nodeIntegration,contextIsolation:p.contextIsolation};});
    assert.deepEqual(prefs,{sandbox:true,nodeIntegration:false,contextIsolation:true});
    assert.equal(await page.evaluate(()=>typeof window.require),'undefined');
    const initial=await page.evaluate(()=>window.desktop.getSettings());
    assert.equal(initial.googleConfigured,false);
    assert.equal('password' in initial,false);
    assert.equal('serviceAccount' in initial,false);
    await page.screenshot({path:path.join(output,'desktop-welcome.png')});
    await page.keyboard.press('Control+k');
    await page.getByLabel('Find an action').fill('connections');
    await page.getByLabel('Find an action').press('Enter');
    await page.getByRole('heading',{name:'Connections & settings'}).waitFor();
    await page.getByLabel('Username',{exact:true}).fill('desktop-test-user');
    await page.getByLabel('Password',{exact:true}).fill('desktop-test-secret-123');
    await page.screenshot({path:path.join(output,'desktop-settings.png')});
    await page.getByRole('button',{name:'Save settings',exact:true}).click();
    await page.waitForURL(url=>url.origin!==base,{timeout:30000});
    base=new URL(page.url()).origin;
    await page.getByRole('heading',{name:'Clear work. Confident decisions.'}).waitFor();
    assert.equal(fs.readFileSync(path.join(profile,'settings.vault')).includes('desktop-test-secret-123'),false);
    const saved=await page.evaluate(()=>window.desktop.getSettings());
    assert.equal(saved.passwordSet,true);
    assert.equal(saved.username,'desktop-test-user');
    const file=path.join(profile,'capture.csv');
    fs.writeFileSync(file,'Order Number,Task Status,Product\nDESKTOP-001,Available,Full Title\n');
    await page.locator('input[type=file]').setInputFiles(file);
    await page.getByText('preview1',{exact:true}).first().waitFor({timeout:15000});
    await page.getByRole('button',{name:'Saved captures',exact:true}).click();
    await page.getByRole('cell',{name:'DESKTOP-001',exact:true}).waitFor();
    const state=await page.evaluate(()=>fetch('/api/state').then(r=>r.json()));
    assert.equal(state.pending_sync,1);
    const backupFile=path.join(profile,'workspace-backup.zip');
    await app.evaluate(({dialog},file)=>{dialog.showSaveDialog=async()=>({canceled:false,filePath:file});},backupFile);
    const backup=await page.evaluate(()=>window.desktop.backup());
    assert.equal(backup.saved,true);
    assert.ok(fs.statSync(backupFile).size>100);
    fs.writeFileSync(file,'Order Number,Task Status,Product\nDESKTOP-002,Available,Full Title\n');
    await page.locator('input[type=file]').setInputFiles(file);
    await page.getByText('preview2',{exact:true}).first().waitFor();
    await app.evaluate(({dialog},file)=>{dialog.showOpenDialog=async()=>({canceled:false,filePaths:[file]});dialog.showMessageBox=async()=>({response:1});},backupFile);
    const restored=await page.evaluate(()=>window.desktop.restoreBackup());
    assert.equal(restored.restored,true);
    await page.waitForEvent('load');
    await page.getByRole('button',{name:'Saved captures',exact:true}).click();
    await page.getByRole('cell',{name:'DESKTOP-001',exact:true}).waitFor();
    assert.equal((await page.evaluate(()=>fetch('/api/state').then(r=>r.json()))).previews.length,1);
    const child=spawn(executable,args,{env,windowsHide:true,stdio:'ignore'});
    await Promise.race([once(child,'exit'),new Promise((_,reject)=>setTimeout(()=>reject(Error('Second instance did not exit')),15000))]);
    assert.equal(await app.evaluate(({BrowserWindow})=>BrowserWindow.getAllWindows().length),1);
    const metrics=await app.evaluate(async({app})=>({processes:app.getAppMetrics().length,workingSetMB:Math.round(app.getAppMetrics().reduce((sum,item)=>sum+(item.memory?.workingSetSize||0),0)/1024)}));
    await page.screenshot({path:path.join(output,'desktop-capture.png')});
    assert.deepEqual(errors,[],'renderer must not have uncaught errors');
    await app.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(item=>item.label==='Quit Tv Tracker').click());
    await app.waitForEvent('close',{timeout:15000});app=null;
    await assert.rejects(fetch(base+'/api/health'),undefined,'backend must stop on app quit');
    // Reopen the same user profile to verify persisted settings and capture data.
    app=await electron.launch({executablePath:executable,args,env,timeout:60000});
    const reopened=await app.firstWindow();
    await reopened.getByRole('button',{name:'Saved captures',exact:true}).click();
    await reopened.getByRole('cell',{name:'DESKTOP-001',exact:true}).waitFor({timeout:15000});
    assert.equal((await reopened.evaluate(()=>window.desktop.getSettings())).passwordSet,true);
    await app.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(item=>item.label==='Quit Tv Tracker').click());
    await app.waitForEvent('close',{timeout:15000});app=null;
    const result={passed:true,packaged:!!process.env.DESKTOP_EXE,startupMs,...metrics,rendererErrors:errors,checks:['first launch','authenticated loopback','renderer isolation','keyboard navigation','DPAPI vault','settings restart','local import','saved captures','backup export','backup restore','single instance','clean shutdown','data persistence']};
    fs.writeFileSync(path.join(output,process.env.DESKTOP_EXE?'packaged-smoke.json':'development-smoke.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result,null,2));
  } catch(error) {
    if(app) {
      const failedPage=await app.firstWindow().catch(()=>null);
      if(failedPage){console.error((await failedPage.locator('body').innerText().catch(()=>'' )).slice(0,7000));await failedPage.screenshot({path:path.join(output,'desktop-failure.png')}).catch(()=>{});}
      console.error('Renderer errors:',errors);
    }
    throw error;
  } finally {
    if(app)await app.close().catch(()=>{});
    // Test profiles are kept for failure diagnostics; they contain synthetic data only.
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
