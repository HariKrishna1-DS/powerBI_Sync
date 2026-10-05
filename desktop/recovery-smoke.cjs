// Packaged regression: unreadable connections cannot brick Updates or lose captures.
const {_electron: electron} = require('../gsheet_dashboard/frontend/node_modules/playwright');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');
(async()=>{
  const profile=fs.mkdtempSync(path.join(os.tmpdir(),'tv-tracker-recovery-test-'));
  const file=path.join(profile,'settings.vault');
  fs.writeFileSync(file,'unreadable fixture');
  const env={...process.env,DATATRACE_TEST_USER_DATA:profile};delete env.ELECTRON_RUN_AS_NODE;
  let app;
  async function launch(){
    app=await electron.launch({executablePath:process.env.DESKTOP_EXE,env,timeout:60000});
    const page=await app.firstWindow({timeout:30000});
    page.setDefaultTimeout(30000);
    await page.waitForFunction(()=>!!window.desktop,{},{timeout:30000});
    return page;
  }
  async function quit(){const done=app.waitForEvent('close',{timeout:20000});await app.evaluate(({Menu})=>Menu.getApplicationMenu().items[0].submenu.items.find(i=>i.label==='Quit Tv Tracker').click());await done;app=null;}
  try {
    console.log('Recovery check: opening a profile with an unreadable vault.');
    let page=await launch();
    assert.equal((await page.evaluate(()=>window.desktop.getSettings())).connectionRecovery.status,'locked');
    console.log('Recovery check: checking settings and Updates remain accessible.');
    await page.getByRole('button',{name:'Review connections',exact:true}).click();
    await page.getByRole('tab',{name:'Updates',exact:true}).click();
    await page.getByRole('button',{name:'Check for updates',exact:true}).waitFor();
    assert.match(await page.evaluate(async()=>{try{await window.desktop.savePreferences({theme:'dark'});return 'unexpected success';}catch(e){return e.message;}}),/Reconnect/);
    assert.equal(fs.readFileSync(file,'utf8'),'unreadable fixture');
    console.log('Recovery check: creating synthetic encrypted backups.');
    await app.evaluate(({safeStorage,app})=>{
      const {createVault,DEFAULTS}=process.mainModule.require('./settings.cjs');
      const path=process.mainModule.require('node:path');
      const vault=createVault(path.join(app.getPath('userData'),'settings.vault'),safeStorage);
      vault.readRecoverably();vault.write({...DEFAULTS,username:'recovered-fixture',password:'fixture-password'},{replaceUnreadable:true});
      vault.write({...DEFAULTS,username:'newer-fixture',password:'fixture-password'});
    });
    await quit();
    fs.writeFileSync(file,'simulate interrupted/corrupt storage');
    console.log('Recovery check: reopening and restoring the verified backup.');
    page=await launch();
    const restored=await page.evaluate(()=>window.desktop.getSettings());
    assert.equal(restored.connectionRecovery.status,'restored');
    assert.equal(restored.username,'recovered-fixture');assert.equal(restored.passwordSet,true);
    assert.ok(fs.readdirSync(path.join(profile,'connection-backups')).length>=2);
    await quit();
    console.log('Recovery check: verifying persistence after a second restart.');
    page=await launch();
    const persisted=await page.evaluate(()=>window.desktop.getSettings());
    assert.equal(persisted.username,'recovered-fixture');assert.equal(persisted.connectionRecovery,null);
    await quit();
    console.log('PASS: packaged locked-vault startup, accessible Updates, protected preference save, encrypted backup restoration and clean restart.');
  } finally {
    if(app){
      // A normal window close minimizes to the tray. Quit the isolated test app explicitly.
      try{await quit();}catch{app?.process().kill();}
    }
  }
})().catch(error=>{console.error(error.message);process.exitCode=1;});
