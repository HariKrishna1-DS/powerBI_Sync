import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';
import path from 'node:path';

async function setup(page){
  const fixture=workspaceFixture();
  await page.route('**/api/**',route=>{const req=route.request();return route.fulfill({json:fixture.response(new URL(req.url()).pathname,req.postData()?req.postDataJSON():{})});});
  await page.goto('/');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  return fixture;
}

test('capture library searches, preserves selection and remains usable with a collapsed sidebar',async({page})=>{
  await setup(page);
  await page.getByLabel('Search saved captures').fill('September');
  await expect(page.locator('.preview-select')).toHaveCount(1);
  await page.locator('.preview-select').click();
  await expect(page.getByRole('heading',{name:'Capture library',exact:true})).toBeVisible();
  await expect(page.getByLabel('Selected capture',{exact:true})).toHaveValue('30');
  await page.getByRole('button',{name:'Collapse sidebar'}).click();
  await expect(page.locator('.workspace')).toHaveClass(/sidebar-collapsed/);
  await page.getByLabel('Find saved capture').fill('preview31');
  await page.getByLabel('Selected capture',{exact:true}).selectOption('31');
  await expect(page.locator('.context-preview')).toContainText('preview31');
  await page.reload();
  await expect(page.locator('.workspace')).toHaveClass(/sidebar-collapsed/);
  await expect(page.getByLabel('Appearance')).toBeVisible();
  await page.getByRole('button',{name:'Expand sidebar'}).click();
  await expect(page.getByLabel('Search saved captures')).toBeVisible();
});

test('sheet segments use the correct sources and keep search and sorting available',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Full Title 120',exact:true}).click();
  await expect(page.locator('.metric').filter({hasText:'Visible orders'}).locator('strong')).toHaveText('120');
  await expect(page.locator('.orders-table')).not.toContainText('Current Owner');
  await page.getByLabel('Search rows').fill('TV-62000');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'All columns',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'County'})).toBeVisible();
  await page.getByRole('button',{name:'Order Number',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'Order Number'})).toHaveAttribute('aria-sort','ascending');
  await page.getByLabel('Search rows').fill('');
  await page.getByRole('button',{name:'Remaining Products 120',exact:true}).click();
  await expect(page.locator('.orders-table')).toContainText('Current Owner');
  await expect(page.locator('.orders-table')).not.toContainText('Full Title');
});

test('chart drilldowns reflect active filters and native dialogs restore keyboard focus',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:'Clear chart filters',exact:true}).click();
  await page.getByRole('button',{name:'Chart filters',exact:true}).click();
  await page.locator('.dropdown-slicer summary').filter({hasText:'Client'}).click();
  await page.getByRole('checkbox',{name:'Northstar Title & Escrow 80'}).check();
  await page.getByRole('button',{name:'Online: 60 (75.0%)',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Online/ Ground: Online',exact:true});
  await expect(dialog).toContainText('60 matching records');
  await expect(dialog.locator('tbody')).not.toContainText('Pacific Coast');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Online: 60 (75.0%)',exact:true})).toBeFocused();
});

test('schedule confirms writes and does not claim success after failure',async({page})=>{
  await setup(page);
  await page.getByText('AutoLogin Trigger',{exact:true}).click();
  await page.route('**/api/sync-schedule',route=>route.fulfill({status:503,json:{error:'Schedule storage unavailable'}}));
  await page.getByRole('button',{name:'Save AutoLogin Trigger',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Schedule storage unavailable');
  await expect(page.getByText('Schedule saved. Times are in IST.',{exact:true})).toHaveCount(0);
  await page.route('**/api/sync-schedule',route=>route.fulfill({json:route.request().postDataJSON()}));
  await page.getByRole('button',{name:'Save AutoLogin Trigger',exact:true}).click();
  await expect(page.getByText('Schedule saved. Times are in IST.',{exact:true})).toBeVisible();
});

test('failed product preference save retains the last confirmed selection',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.route('**/api/remaining-products',route=>route.fulfill({status:503,json:{error:'Storage unavailable'}}));
  await page.getByRole('button',{name:'Clear chart filters',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Product selection was not saved');
  await expect(page.getByRole('button',{name:'Chart filters (2)',exact:true})).toBeVisible();
});

for(const theme of ['light','dark'])test(`all primary screens fit desktop and narrow windows in ${theme} mode`,async({page})=>{
  test.setTimeout(120000);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await setup(page);
  await page.getByLabel('Appearance').selectOption(theme);
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080],[640,900]]){
    await page.setViewportSize({width,height});
    for(const name of ['Overview','Data Sheets','Daily Orders','Monthly report','Changes','Captures','Activity']){
      await page.getByRole('button',{name,exact:true}).click();
      await expect(page.locator('#workspace-content h1')).toBeVisible();
      await expect(page.locator('.loading')).toHaveCount(0);
      const sizes=await page.locator('main').evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth}));
      expect(sizes.scroll,`${name} at ${width}`).toBeLessThanOrEqual(sizes.client+1);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      if(process.env.TV_TRACKER_SCREENSHOTS&&width===1440)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`${theme}-${name.toLowerCase().replaceAll(' ','-')}.png`)});
    }
    await expect(page.getByLabel('Appearance')).toBeVisible();
  }
  expect(errors).toEqual([]);
});
