import {test, expect} from '@playwright/test';

async function setup(page, running=false) {
  await page.addInitScript(()=>{
    let listener=()=>{};
    window.updateCalls=[];
    let state={status:'idle',currentVersion:'2.2.0',version:'',message:'Check for a new Windows release.',percent:0};
    const send=value=>{state={...state,...value};listener(state);return state;};
    window.desktop={
      getSettings:async()=>({spreadsheetId:'',queueUrl:'https://tv.datatracetitle.com/Queues.aspx',fullTrackerTitle:'Full',remainingTrackerTitle:'Remaining',username:'',passwordSet:false,serviceAccountEmail:'',googleConfigured:false,browserPath:'',browserDetected:true,closeToTray:true,startAtLogin:false}),
      discardSettings:async()=>{},onCommand:()=>()=>{},getUpdateState:async()=>state,
      onUpdateState:callback=>{listener=callback;return()=>{listener=()=>{};};},
      checkForUpdates:async()=>{window.updateCalls.push('check');return send({status:'available',version:'2.3.0',message:'Version 2.3.0 is available.'});},
      downloadUpdate:async()=>{window.updateCalls.push('download');send({status:'downloading',percent:50,message:'Downloading update…'});await new Promise(resolve=>setTimeout(resolve,200));return send({status:'downloaded',percent:100,message:'Update ready. Restart when your work is finished.'});},
      installUpdate:async()=>{window.updateCalls.push('install');return send({status:'installing',message:'Closing Tv Tracker to install the update…'});},
    };
  });
  await page.route('**/api/**',route=>route.fulfill({status:route.request().url().endsWith('/api/state')?200:502,json:route.request().url().endsWith('/api/state')?{previews:[],job:{running,stage:running?'Syncing':'Ready'},schedule:{enabled:false,times:['09:00']},capabilities:{desktop:true,google_configured:false}}:{error:'Offline'}}));
  await page.goto('/');
  await page.getByRole('button',{name:'Connections & settings',exact:true}).click();
  await page.getByRole('tab',{name:'Updates',exact:true}).click();
}
test('check, download, and installation are three explicit user choices',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await setup(page);
  await expect(page.getByText('Installed version 2.2.0.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Check for updates',exact:true}).click();
  expect(await page.evaluate(()=>window.updateCalls)).toEqual(['check']);
  await page.getByRole('button',{name:'Download 2.3.0',exact:true}).click();
  await expect(page.getByRole('button',{name:'Restart & install 2.3.0',exact:true})).toBeEnabled();
  expect(await page.evaluate(()=>window.updateCalls)).toEqual(['check','download']);
  await page.getByRole('button',{name:'Restart & install 2.3.0',exact:true}).click();
  await expect(page.getByText('Closing Tv Tracker to install the update…',{exact:true})).toBeVisible();
  expect(await page.evaluate(()=>window.updateCalls)).toEqual(['check','download','install']);
  expect(errors).toEqual([]);
});
test('active sync disables the restart action',async({page})=>{
  await setup(page,true);
  await page.getByRole('button',{name:'Check for updates',exact:true}).click();
  await page.getByRole('button',{name:'Download 2.3.0',exact:true}).click();
  await expect(page.getByRole('button',{name:'Restart & install 2.3.0',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>window.updateCalls)).toEqual(['check','download']);
});
