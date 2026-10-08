import {test, expect} from '@playwright/test';
import fs from 'node:fs/promises';

const preview={id:1,name:'preview1',created:'2026-10-02T03:00:00Z',source:'Fixture',row_count:1};
const rows=[{'Order Number':'VISIBLE',Product:'Full Title',Status:'Search In Progress'},
            {'Order Number':'FILTERED-OUT',Product:'Full Title',Status:'Cancelled'}];

async function mockWorkspace(page, handler) {
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    if(await handler?.(route,url))return;
    if(url.pathname==='/api/state')return route.fulfill({json:{previews:[preview],job:{running:false,stage:'Ready'},schedule:{enabled:false,times:[]},
      failed_syncs:[{preview_id:1,preview_name:'preview1',error:'Connection failed'}]}});
    if(url.pathname==='/api/live-sheets')return route.fulfill({json:{mode:'tracker',sheets:{'All Products':{columns:Object.keys(rows[0]),rows}}}});
    if(url.pathname==='/api/previews/1')return route.fulfill({json:{...preview,columns:Object.keys(rows[0]),rows:[{...rows[0],'Order Number':'RAW-ONLY'}]}});
    await route.fulfill({json:{}});
  });
  await page.goto('/');
}

test('retry targets the failed capture and CSV downloads the filtered production rows',async({page})=>{
  const calls=[];
  await mockWorkspace(page,async(route,url)=>{
    if(url.pathname!=='/api/sync')return false;
    calls.push(route.request().postDataJSON());
    await route.fulfill({status:202,json:{accepted:true}});return true;
  });
  await page.getByRole('button',{name:'Retry sync',exact:true}).click();
  await expect.poll(()=>calls.length).toBe(1);
  expect(calls[0]).toEqual({preview:1});
  await page.getByRole('textbox',{name:'Search rows'}).fill('VISIBLE');
  await expect(page.getByRole('button',{name:'Open order VISIBLE',exact:true})).toBeVisible();
  const downloading=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV',exact:true}).click();
  const download=await downloading;
  const content=await fs.readFile(await download.path(),'utf8');
  expect(content).toContain('VISIBLE');
  expect(content).not.toContain('FILTERED-OUT');
  expect(content).not.toContain('RAW-ONLY');
});

test('selected report Excel export reports a failure and supports retry',async({page})=>{
  const calls=[];
  let fail=true;
  await mockWorkspace(page,async(route,url)=>{
    if(url.pathname!=='/api/export/report')return false;
    calls.push(url.search);
    if(fail){await route.fulfill({status:502,json:{error:'The selected report could not be exported.'}});return true;}
    await route.fulfill({status:200,body:'test-export',headers:{'Content-Disposition':'attachment; filename="Production_data.xlsx"','Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}});return true;
  });
  await page.getByRole('button',{name:'Export',exact:true}).click();
  await expect(page.getByText('The selected report could not be exported.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Export',exact:true})).toBeEnabled();
  expect(calls).toEqual(['']);
  fail=false;
  const downloading=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export',exact:true}).click();
  const download=await downloading;
  expect(download.suggestedFilename()).toBe('Production_data.xlsx');
  expect(calls).toEqual(['','']);
});
