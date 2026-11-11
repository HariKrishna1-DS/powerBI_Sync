import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page){
  const fixture=workspaceFixture(3);
  let job={running:false,stage:'Ready',run_id:0};
  await page.clock.install();
  await page.route('**/api/**',async route=>{
    const name=new URL(route.request().url()).pathname;
    let body=fixture.response(name);
    if(name==='/api/extract'){job={running:true,action:'extract',stage:'Opening the extraction browser',run_id:job.run_id+1,result:null};body={started:true};}
    if(name==='/api/extract/cancel'){job={...job,running:false,stage:'Extraction cancelled',result:{cancelled:true}};body={ok:true};}
    if(name==='/api/state')body={...body,job};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await expect(page.locator('.activity-summary')).toContainText('Workspace ready');
  return async next=>{job={...job,...next};await page.clock.fastForward(11000);};
}

test('panel follows extraction through stages, navigation and Sheets sync',async({page})=>{
  const update=await setup(page);
  const panel=page.getByRole('complementary',{name:'Workspace activity'});
  await page.getByRole('button',{name:'Extract Queue',exact:true}).click();
  await expect(panel.locator('.activity-toggle')).toHaveAttribute('aria-expanded','true');
  await expect(panel.locator('.extraction-live-stage')).toHaveText('Opening the extraction browser');
  await update({stage:'Signing in to DataTrace'});
  await expect(panel.locator('[aria-current="step"]')).toContainText('Sign in');
  await update({stage:'Extracting 3 queue rows',result:{rows:3}});
  await expect(panel.locator('[aria-current="step"]')).toContainText('Extract queue orders');
  await panel.locator('.activity-toggle').click();
  await page.getByRole('button',{name:'Captures',exact:true}).click();
  await expect(panel.locator('.activity-toggle')).toHaveAttribute('aria-expanded','false');
  await update({action:'extract',stage:'Saving preview33 to local storage',result:{rows:3,preview_name:'preview33'}});
  await expect(panel.locator('.activity-summary')).toContainText('Saving preview33');
  await panel.locator('.activity-toggle').click();
  await expect(panel.locator('[aria-current="step"]')).toContainText('Save capture locally');
  await expect(panel.getByText('3 rows extracted · preview33')).toBeVisible();
  await page.screenshot({path:'test-results/queue-extraction-panel.png',animations:'disabled'});
  await update({running:false,stage:'Finished',result:{rows:3,preview_name:'preview33',google_sheet:'manual'}});
  await expect(panel.locator('.activity-summary')).toContainText('Queue extraction complete');
  await expect(panel).toContainText('preview33 saved · 3 rows · Saved locally');
  await expect(panel.locator('.is-complete')).toHaveCount(4);
  await expect(panel.locator('.activity-progress')).toHaveCount(0);
});

test('panel offers cancellation and reports the cancelled outcome',async({page})=>{
  await setup(page);
  const panel=page.getByRole('complementary',{name:'Workspace activity'});
  await page.getByRole('button',{name:'Extract Queue',exact:true}).click();
  await panel.getByRole('button',{name:'Cancel extraction',exact:true}).click();
  await expect(panel.locator('.activity-summary')).toContainText('Queue extraction cancelled');
  await expect(panel).toContainText('Existing captures are unchanged');
  await expect(panel.locator('.activity-progress')).toHaveCount(0);
});

test('panel shows failure without claiming completion',async({page})=>{
  const update=await setup(page);
  const panel=page.getByRole('complementary',{name:'Workspace activity'});
  await page.getByRole('button',{name:'Extract Queue',exact:true}).click();
  await update({running:false,stage:'Failed',result:{error:'Portal login failed'}});
  await expect(panel.getByRole('alert')).toHaveText('Portal login failed');
  await expect(panel.locator('.activity-summary')).toContainText('needs attention');
  await expect(panel.locator('.is-complete')).toHaveCount(0);
});

test('a rejected extraction request appears in the panel',async({page})=>{
  await setup(page);
  await page.route('**/api/extract',route=>route.fulfill({status:500,json:{error:'Extraction service unavailable'}}));
  await page.getByRole('button',{name:'Extract Queue',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Workspace activity'});
  await expect(panel.getByRole('alert')).toHaveText('Extraction service unavailable');
  await expect(panel.locator('.activity-summary')).toContainText('needs attention');
  await expect(panel.locator('.activity-progress')).toHaveCount(0);
});
