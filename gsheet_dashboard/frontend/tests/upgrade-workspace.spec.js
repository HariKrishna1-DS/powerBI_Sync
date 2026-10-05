import {test,expect} from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture';

const sheetUrl='https://docs.google.com/spreadsheets/d/test-production-workbook/edit';
async function setup(page, override, count=240){
  const fixture=workspaceFixture(count);
  await page.route('**/api/**',async route=>{
    const req=route.request(),url=new URL(req.url());
    if(override&&await override(route,url,fixture))return;
    const data=fixture.response(url.pathname,req.postData()?req.postDataJSON():{});
    if(url.pathname==='/api/state')data.sheet_url=sheetUrl;
    await route.fulfill({json:data});
  });
  await page.goto('/');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  return fixture;
}

test('Live Google Sheets opens the configured production workbook in a separate tab',async({page,context})=>{
  await context.route('https://docs.google.com/**',route=>route.fulfill({contentType:'text/html',body:'<h1>Production workbook test destination</h1>'}));
  await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  const link=page.getByRole('link',{name:'Live Google Sheets'});
  await expect(link).toHaveAttribute('href',sheetUrl);
  const popupPromise=page.waitForEvent('popup');
  await link.click();
  const popup=await popupPromise;
  await expect(popup).toHaveURL(sheetUrl);
  await expect(page.getByRole('heading',{name:'Overview',exact:true})).toBeVisible();
  await popup.close();
});

test('column visibility, widths, wrapping and pinning persist without changing exports',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'All columns',exact:true}).click();
  await page.getByText('Columns & layout',{exact:true}).click();
  await page.getByLabel('Show Client',{exact:true}).uncheck();
  await page.getByLabel('Width for Order Number',{exact:true}).selectOption('240');
  await page.getByLabel('Wrap cell text',{exact:true}).check();
  await expect(page.getByRole('columnheader',{name:'Client',exact:true})).toHaveCount(0);
  const id=page.getByRole('columnheader',{name:'Order Number',exact:true});
  await expect(id).toHaveClass(/pinned-identifier/);
  expect((await id.boundingBox()).width).toBeCloseTo(240,0);
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV',exact:true}).click();
  const csv=await fs.readFile(await(await downloadPromise).path(),'utf8');
  expect(csv.split('\n')[0]).toContain('"Client"');
  expect(csv).toContain('Northstar Title & Escrow');
  await page.reload();
  await expect(page.locator('.orders-table')).toHaveClass(/wrap-cells/);
  await expect(page.getByRole('columnheader',{name:'Client',exact:true})).toHaveCount(0);
  expect((await id.boundingBox()).width).toBeCloseTo(240,0);
});

test('explicit refresh reuses unchanged rows and retains search, page, selection and scroll',async({page})=>{
  let reads=0;
  const requests=[];
  await setup(page,async(route,url,fixture)=>{
    if(url.pathname!=='/api/live-sheets')return false;
    requests.push(url.searchParams.toString());reads++;
    await route.fulfill({json:reads===1?{...fixture.response(url.pathname),revision:'stable'}:
      {revision:'stable',unchanged:true,offline:false,updated_at:'2026-10-05T06:00:00Z',source:'Google Sheets'}});
    return true;
  });
  await page.getByRole('button',{name:'Next orders page'}).click();
  await page.getByRole('button',{name:'Open order TV-62050',exact:true}).click();
  const table=page.getByRole('region',{name:'Scrollable production orders'});
  await table.evaluate(el=>{el.scrollTop=150;});
  await page.getByRole('button',{name:'Refresh production data',exact:true}).click();
  await expect.poll(()=>reads).toBe(2);
  expect(requests[1]).toContain('revision=stable');
  expect(requests[1]).toContain('refresh=1');
  await expect(page.getByRole('complementary',{name:'Order details'})).toContainText('TV-62050');
  await expect(page.locator('.orders-pagination')).toContainText('Page 2 of 5');
  expect(await table.evaluate(el=>el.scrollTop)).toBe(150);
  await page.getByLabel('Search rows').fill('TV-62050');
  await page.getByRole('button',{name:'Refresh production data',exact:true}).click();
  await expect(page.getByLabel('Search rows')).toHaveValue('TV-62050');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
});

test('unchanged offline response remains honest and recovery clears the saved-copy message',async({page})=>{
  let reads=0;
  await setup(page,async(route,url,fixture)=>{
    if(url.pathname!=='/api/live-sheets')return false;
    reads++;
    await route.fulfill({json:reads===1?{...fixture.response(url.pathname),revision:'stable'}:
      {revision:'stable',unchanged:true,offline:reads===2,updated_at:'2026-10-05T05:32:00Z'}});
    return true;
  });
  await page.getByRole('button',{name:'Refresh production data',exact:true}).click();
  await expect(page.locator('.context-source')).toHaveText('Saved Google Sheets copy');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  await page.getByRole('button',{name:'Refresh production data',exact:true}).click();
  await expect(page.locator('.context-source')).toHaveText('Live Google Sheets');
});

for(const theme of ['light','dark'])test(`table layout controls fit narrow and scaled windows in ${theme} mode`,async({page})=>{
  await setup(page);
  await page.getByLabel('Appearance').selectOption(theme);
  await page.getByText('Columns & layout',{exact:true}).click();
  for(const size of [{width:1440,height:900},{width:1024,height:640},{width:760,height:600},{width:390,height:740}]){
    await page.setViewportSize(size);
    await expect(page.getByRole('region',{name:'Table layout preferences'})).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    const panel=await page.getByRole('region',{name:'Table layout preferences'}).boundingBox();
    expect(panel.x).toBeGreaterThanOrEqual(0);
    expect(panel.x+panel.width).toBeLessThanOrEqual(size.width+1);
  }
  await page.setViewportSize({width:1440,height:900});
  if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`upgrade-table-${theme}.png`)});
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Status summary',exact:true})).toBeVisible();
  if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`upgrade-overview-${theme}.png`)});
});

test('large dataset loading and filtering report measured timings',async({page})=>{
  const start=performance.now();
  await setup(page,null,7000);
  const loadMs=performance.now()-start;
  const filterStart=performance.now();
  await page.getByLabel('Search rows').fill('TV-68999');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  const filterMs=performance.now()-filterStart;
  expect(await page.getByRole('button',{name:'Open order TV-68999',exact:true}).count()).toBe(1);
  if(process.env.TV_TRACKER_SCREENSHOTS)await fs.writeFile(path.join(process.env.TV_TRACKER_SCREENSHOTS,'browser-performance.json'),JSON.stringify({rows:7000,loadMs,filterMs},null,2));
});
