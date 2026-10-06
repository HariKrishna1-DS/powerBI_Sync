import {test, expect} from '@playwright/test';

async function setup(page,{fail=false,role='owner'}={}) {
  await page.addInitScript(({fail,role})=>{
    let state={configured:true,projectUrl:'https://qontoybecrqpbjzoajqf.supabase.co',signedIn:false,email:''};
    const workspace={id:'00000000-0000-0000-0000-000000000001',name:'Tv Tracker QA',role,mode:'shadow'};
    window.desktop={
      getSettings:async()=>({spreadsheetId:'',queueUrl:'https://tv.datatracetitle.com/Queues.aspx',fullTrackerTitle:'Full',remainingTrackerTitle:'Remaining',username:'',passwordSet:false,serviceAccountEmail:'',googleConfigured:false,browserPath:'',browserDetected:true,closeToTray:true,startAtLogin:false,cloudConfig:{publishableKey:'sb_publishable_fixtureonly123'}}),
      discardSettings:async()=>{},onCommand:()=>()=>{},getCloudState:async()=>state,
      signInCloud:async({email})=>{if(fail)throw Error('Account access was rejected.');return state={...state,signedIn:true,email};},
      getCloudWorkspaces:async()=>[workspace],
      runCloudAction:async value=>({revision:3,orders:42,worker:value.action==='worker'?{state:'processed'}:null}),
      signOutCloud:async()=>state={...state,signedIn:false,remoteRevoked:true,email:''},
    };
  },{fail,role});
  await page.route('**/api/**',route=>route.fulfill({status:new URL(route.request().url()).pathname==='/api/state'?200:502,json:new URL(route.request().url()).pathname==='/api/state'?{previews:[],job:{running:false,stage:'Ready'},schedule:{enabled:false,times:[]},capabilities:{desktop:true,google_configured:false}}:{error:'Offline'}}));
  await page.goto('/');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByRole('tab',{name:'Shared workspace',exact:true}).click();
}

test('owner can sign in, inspect and run validation without a production switch',async({page})=>{
  await setup(page);
  await page.getByLabel('Workspace email',{exact:true}).fill('qa@example.test');
  await page.getByLabel('Workspace password',{exact:true}).fill('fixture-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Workspace',{exact:true}).selectOption('00000000-0000-0000-0000-000000000001');
  await page.getByRole('button',{name:'Check shared data',exact:true}).click();
  await expect(page.getByText('Revision 3 · 42 shared orders',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Run validation worker',exact:true}).click();
  await expect(page.getByText('Worker: processed',{exact:false})).toBeVisible();
  await expect(page.getByText('Validation mode does not publish to Sheets.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Sign out on this PC',exact:true}).click();
  await expect(page.getByLabel('Workspace password',{exact:true})).toHaveValue('');
});

test('failed sign-in clears the password and explains the error',async({page})=>{
  await setup(page,{fail:true});
  await page.getByLabel('Workspace email',{exact:true}).fill('qa@example.test');
  await page.getByLabel('Workspace password',{exact:true}).fill('fixture-only');
  await page.getByLabel('Workspace password',{exact:true}).press('Enter');
  await expect(page.getByRole('alert').filter({hasText:'Account access was rejected'})).toBeVisible();
  await expect(page.getByLabel('Workspace password',{exact:true})).toHaveValue('');
});

test('viewer gets no worker control and the small desktop dialog fits',async({page})=>{
  await page.setViewportSize({width:980,height:680});
  await setup(page,{role:'viewer'});
  await page.getByLabel('Workspace email',{exact:true}).fill('viewer@example.test');
  await page.getByLabel('Workspace password',{exact:true}).fill('fixture-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Workspace',{exact:true}).selectOption('00000000-0000-0000-0000-000000000001');
  await expect(page.getByRole('button',{name:'Run validation worker',exact:true})).toHaveCount(0);
  const fits=await page.getByRole('dialog').evaluate(dialog=>{const rect=dialog.getBoundingClientRect();return rect.left>=0&&rect.right<=innerWidth&&rect.top>=0&&rect.bottom<=innerHeight;});
  expect(fits).toBe(true);
});
