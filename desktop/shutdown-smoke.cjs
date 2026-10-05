// The native shell must finish an explicit quit even if the engine's shutdown reply stalls.
const {_electron:electron}=require('../gsheet_dashboard/frontend/node_modules/playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const os=require('node:os');
const path=require('node:path');
(async()=>{
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'tv-tracker-shutdown-test-'));
  const env={...process.env,DATATRACE_TEST_USER_DATA:profile};delete env.ELECTRON_RUN_AS_NODE;
  let app;
  const launch=async()=>{app=await electron.launch({executablePath:process.env.DESKTOP_EXE,env,timeout:60000});return app.firstWindow();};
  const quit=async()=>{const closed=app.waitForEvent('close',{timeout:15000});await app.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(item=>item.label==='Quit Tv Tracker').click());await closed;app=null;};
  try{
    const page=await launch();
    await page.getByRole('heading',{name:'Clear work. Confident decisions.'}).waitFor();
    const file=path.join(profile,'capture.csv');fs.writeFileSync(file,'Order Number,Task Status,Product\nSHUTDOWN-QC,Available,Full Title\n');
    await page.locator('input[type=file]').setInputFiles(file);
    await page.getByText('preview1',{exact:true}).first().waitFor();
    await page.waitForFunction(async()=>!(await fetch('/api/health').then(r=>r.json())).running);
    const origin=new URL(page.url()).origin;
    await app.evaluate(()=>{const original=globalThis.fetch;globalThis.fetch=(url,options)=>String(url).endsWith('/api/desktop/shutdown')?new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true})):original(url,options);});
    const started=performance.now();await quit();const quitMs=Math.round(performance.now()-started);
    assert.ok(quitMs<12000,`Unresponsive shutdown took ${quitMs}ms`);
    await assert.rejects(fetch(origin+'/api/health'),undefined,'The engine must stop on quit');
    const reopened=await launch();
    await reopened.getByRole('button',{name:'Captures',exact:true}).click();
    await reopened.getByRole('cell',{name:'SHUTDOWN-QC',exact:true}).waitFor();
    assert.equal((await reopened.evaluate(()=>fetch('/api/state').then(r=>r.json()))).previews.length,1);
    await quit();
    console.log(JSON.stringify({passed:true,quitMs,checks:['bounded quit with stalled engine reply','engine termination','saved capture preserved after restart']},null,2));
  }finally{if(app){try{await quit();}catch{app?.process().kill();}}}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
