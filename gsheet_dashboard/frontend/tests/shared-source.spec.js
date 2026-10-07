import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';

async function setup(page, {cloudState='accepted', offline=false, failRefresh=false, viewer=false}={}) {
  const fixture=workspaceFixture(24);
  const preferences={shared:true,can_edit:!viewer,source:'tracker',revision:12,published_revision:11,publish_status:'pending'};
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    const body=fixture.response(path);
    if(path==='/api/state')Object.assign(body,{shared:{enabled:true,office_worker:false,can_capture:!viewer},pending_sync:1,
      capabilities:{desktop:true,google_configured:false,report_sources:true},report_preferences:preferences,
      job:{running:false,stage:'Ready',run_id:1,result:{action:'sync',preview_name:'preview32',cloud_state:cloudState,google_sheet:'pending'}}});
    if(path==='/api/live-sheets'&&failRefresh)return route.fulfill({status:503,json:{error:'Shared workspace temporarily unavailable.'}});
    if(['/api/live-sheets','/api/monthly-orders','/api/daily-orders'].includes(path))Object.assign(body,{source:'Shared workspace',report_preferences:preferences,offline});
    if(path==='/api/reporting')Object.assign(body,{preferences,imports:[]});
    if(path==='/api/reporting/storage')Object.assign(body,{captures:3,imports:0,database_bytes:1024,backup_bytes:0});
    if(path==='/api/reporting/shared-job')Object.assign(body,{shared:true,pending_captures:1,published_revision:11,revision:12});
    return route.fulfill({json:body});
  });
  await page.goto('/');
}

test('shared client distinguishes database acceptance from verified Sheets publication',async({page})=>{
  await setup(page);
  await expect(page.getByRole('button',{name:'Extract Queue',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Sync to Sheets',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Import Excel reports',exact:true})).toBeEnabled();
  await expect(page.getByRole('button',{name:'Publish reports',exact:true})).toBeEnabled();
  await expect(page.getByText('Shared workspace connected',{exact:false}).first()).toBeVisible();
  await expect(page.getByText('Accepted by the shared workspace; awaiting verified publication.',{exact:false})).toBeVisible();
  await expect(page.getByText('Google Sheets connected',{exact:false})).toHaveCount(0);
  await expect(page.getByText('Google Sheets tabs updated',{exact:false})).toHaveCount(0);
  await expect(page.getByText('undefined rows',{exact:false})).toHaveCount(0);
  await expect(page.getByText('The registered office PC processes them',{exact:false})).toBeVisible();
  await page.getByText('Storage and recovery',{exact:true}).click();
  await page.getByRole('button',{name:'Check shared publishing',exact:true}).click();
  await expect(page.getByText('Published revision 11 of 12',{exact:false})).toBeVisible();
  await expect(page.getByRole('button',{name:'Release interrupted publishing slot',exact:true})).toHaveCount(0);
  await expect(page.getByText('Then review and release its interrupted slot.',{exact:false})).toHaveCount(0);
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  await expect(page.locator('.report-context').filter({hasText:'Refreshed'})).toContainText('Shared workspace');
});

test('offline shared copy and pending upload retain accurate provenance',async({page})=>{
  await setup(page,{cloudState:'pending',offline:true});
  await expect(page.getByText('Viewing a saved shared workspace copy',{exact:true})).toBeVisible();
  await expect(page.getByText('Saved locally; shared upload pending.',{exact:false})).toBeVisible();
  await expect(page.getByText('Accepted by the shared workspace; awaiting verified publication.',{exact:false})).toHaveCount(0);
  await expect(page.getByText('Viewing a saved Google Sheets copy',{exact:true})).toHaveCount(0);
});

test('shared refresh failure is shown on a client with no Google credentials',async({page})=>{
  await setup(page,{failRefresh:true});
  await expect(page.getByRole('status').filter({hasText:'Could not refresh shared workspace reports.'})).toContainText('Shared workspace temporarily unavailable.');
});


test('shared viewer cannot start captures or schedules through the interface',async({page})=>{
  await setup(page,{viewer:true});
  await expect(page.getByRole('button',{name:'Extract Queue',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Sync to Sheets',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Import file',exact:true})).toBeDisabled();
  await expect(page.locator('.sync-schedule')).toHaveCount(0);
  await expect(page.getByText('Read-only access',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Export',exact:true})).toBeEnabled();
  await page.getByRole('button',{name:'Quick actions',exact:true}).click();
  await page.getByLabel('Find an action').fill('Import');
  await expect(page.getByRole('button',{name:'Import Excel or CSV',exact:true})).toHaveCount(0);
});
