import {test, expect} from '@playwright/test';

async function setup(page,{fail=false,role='owner',mode='shadow'}={}) {
  await page.addInitScript(({fail,role,mode})=>{
    let state={configured:true,projectUrl:'https://qontoybecrqpbjzoajqf.supabase.co',signedIn:false,email:''};
    const workspace={id:'00000000-0000-0000-0000-000000000001',name:'Tv Tracker QA',role,mode};
    window.cloudActions=[];
    window.desktop={
      getSettings:async()=>({spreadsheetId:'',queueUrl:'https://tv.datatracetitle.com/Queues.aspx',fullTrackerTitle:'Full',remainingTrackerTitle:'Remaining',username:'',passwordSet:false,serviceAccountEmail:'',googleConfigured:false,browserPath:'',browserDetected:true,closeToTray:true,startAtLogin:false,cloudConfig:{publishableKey:'sb_publishable_fixtureonly123'}}),
      discardSettings:async()=>{},onCommand:()=>()=>{},getCloudState:async()=>state,
      signInCloud:async({email})=>{if(fail)throw Error('Account access was rejected.');return state={...state,signedIn:true,email};},
      getCloudWorkspaces:async()=>[workspace],
      runCloudAction:async value=>{
        window.cloudActions.push(value);
        if(value.action==='review')return {id:'00000000-0000-0000-0000-000000000002',created:'2026-10-07T10:00:00Z',next_sequence:48,state:'review',counts:[{tab:'TV_Search_Production_Report_C-O_and_Update_OCT_2026',orders:42}]};
        if(value.action==='activate'){if(!value.reviewed||!value.legacy_stopped)throw Error('Review both migration checks.');workspace.mode='active';return {id:value.plan,created:'2026-10-07T10:00:00Z',next_sequence:48,state:'active',counts:[{tab:'TV_Search_Production_Report_C-O_and_Update_OCT_2026',orders:42}]};}
        return {revision:3,orders:42,worker:value.action==='worker'?{state:'processed'}:null};
      },
      setCloudMember:async value=>{window.cloudActions.push(value);return {user:value.user,role:value.role};},
      signOutCloud:async()=>state={...state,signedIn:false,remoteRevoked:true,email:''},
    };
  },{fail,role,mode});
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
  await expect(page.getByText('Production migration · office PC',{exact:true})).toHaveCount(0);
  const fits=await page.getByRole('dialog').evaluate(dialog=>{const rect=dialog.getBoundingClientRect();return rect.left>=0&&rect.right<=innerWidth&&rect.top>=0&&rect.bottom<=innerHeight;});
  expect(fits).toBe(true);
});

test('migration requires both owner reviews and wraps long tracker names at small size',async({page})=>{
  await page.setViewportSize({width:980,height:680});
  await setup(page);
  await page.getByLabel('Workspace email',{exact:true}).fill('qa@example.test');
  await page.getByLabel('Workspace password',{exact:true}).fill('fixture-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Workspace',{exact:true}).selectOption('00000000-0000-0000-0000-000000000001');
  await page.getByText('Production migration · office PC',{exact:true}).click();
  await page.getByRole('button',{name:'Review production baseline',exact:true}).click();
  const activate=page.getByRole('button',{name:'Activate reviewed workspace',exact:true});
  await expect(activate).toBeDisabled();
  await page.getByLabel('I reviewed these counts and the encrypted migration snapshot.').check();
  await expect(activate).toBeDisabled();
  await page.getByLabel('All older captures and publishing jobs have stopped on every PC.').check();
  await expect(activate).toBeEnabled();
  const fits=await page.getByRole('region',{name:'Migration review',exact:true}).evaluate(region=>region.scrollWidth<=region.clientWidth);
  expect(fits).toBe(true);
  await activate.click();
  await expect(page.getByRole('button',{name:'Run office worker on this PC',exact:true})).toBeVisible();
  await expect(activate).toHaveCount(0);
});

test('team access and restored worker recovery require specific owner acknowledgements',async({page})=>{
  await page.setViewportSize({width:980,height:680});
  await setup(page,{mode:'active'});
  await page.getByLabel('Workspace email',{exact:true}).fill('owner@example.test');
  await page.getByLabel('Workspace password',{exact:true}).fill('fixture-only');
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByLabel('Workspace',{exact:true}).selectOption('00000000-0000-0000-0000-000000000001');
  await page.getByText('Team access',{exact:true}).click();
  await page.getByLabel('Registered user UUID').fill('00000000-0000-0000-0000-000000000002');
  await expect(page.getByRole('button',{name:'Save team access',exact:true})).toBeDisabled();
  await page.getByLabel('I verified this user’s identity and the permission above.').check();
  await page.getByRole('button',{name:'Save team access',exact:true}).click();
  await expect(page.getByText('Workspace access saved.',{exact:false})).toBeVisible();
  await page.getByText('Recover office worker on a replacement PC',{exact:true}).click();
  const recover=page.getByRole('button',{name:'Verify restored worker recovery',exact:true});
  await expect(recover).toBeDisabled();
  await page.getByLabel('The previous office worker is stopped and cannot restart.').check();
  await recover.click();
  await expect(page.getByText('Recovered worker identity verified.',{exact:false})).toBeVisible();
  const actions=await page.evaluate(()=>window.cloudActions);
  expect(actions).toContainEqual({workspace:'00000000-0000-0000-0000-000000000001',user:'00000000-0000-0000-0000-000000000002',role:'editor'});
  expect(actions).toContainEqual({workspace:'00000000-0000-0000-0000-000000000001',action:'recover-worker',legacy_stopped:true});
});
