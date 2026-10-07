import {test, expect} from '@playwright/test';

test('connected Google Sheet edits refresh visible data without replacing preview history',async({page})=>{
  const preview={id:1,name:'preview1',created:'2026-09-30T10:00:00Z',source:'Test',row_count:1};
  const raw={'Order Number':'A1','Product':'Full Title','Comment':'Original','Task Status':'Available'};
  let sheetComment='Original';
  let calls=0;
  await page.clock.install({time:new Date('2026-09-30T10:00:00Z')});
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/state')return route.fulfill({json:{previews:[preview],job:{running:false,stage:'Ready'},schedule:{enabled:false,times:['14:00']},sheet_url:''}});
    if(path==='/api/previews/1')return route.fulfill({json:{...preview,columns:Object.keys(raw),rows:[raw]}});
    if(path==='/api/live-sheets'){
      calls++;
      const updated={...raw,Comment:sheetComment};
      return route.fulfill({json:{preview_name:'preview1',sheets:{
        'All Products':{columns:Object.keys(updated),rows:[updated]},
        'Full Title':{columns:Object.keys(updated),rows:[updated]},
        'Remaining Products':{columns:Object.keys(updated),rows:[]}}}});
    }
    if(path==='/api/compare')return route.fulfill({json:{counts:{},record_counts:{},columns:[],rows:[],matched_rows:[],unmatched_rows:[]}});
    return route.fulfill({json:{rows:[]}});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.getByRole('status').filter({hasText:'Reports read from Google Sheets'})).toBeVisible();
  await page.getByRole('button',{name:'Open order A1',exact:true}).click();
  await expect(page.getByText('Original',{exact:true}).first()).toBeVisible();
  sheetComment='Edited in Google Sheet';
  await page.clock.fastForward(30000);
  await expect.poll(()=>calls).toBeGreaterThan(1);
  await expect(page.getByText('Edited in Google Sheet',{exact:true}).first()).toBeVisible();
  await page.screenshot({path:'test-results/live-sheet-desktop.png'});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'test-results/live-sheet-mobile.png'});
});
