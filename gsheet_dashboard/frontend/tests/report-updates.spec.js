import {test, expect} from '@playwright/test';

test('saved preview controls daily history and monthly SLA percentages render', async ({page})=>{
  const previews=[2,1].map(id=>({id,name:`preview${id}`,created:`2026-09-${28+id}T10:00:00Z`,row_count:1,source:'Test'}));
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    if(url.pathname==='/api/export/google-sheets') return route.fulfill({
      body:'workbook fixture',contentType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      headers:{'Content-Disposition':'attachment; filename=preview2_GoogleSheets.xlsx'}});
    const row={'Order Number':'1','Task Status':'Available'};
    let body={};
    if(url.pathname==='/api/state') body={previews,job:{running:false,stage:'Ready'},schedule:{enabled:false},sheet_url:'https://docs.google.com'};
    else if(url.pathname.startsWith('/api/previews/')) body={...previews.find(p=>p.id===Number(url.pathname.split('/')[3])),columns:Object.keys(row),rows:[row]};
    else if(url.pathname==='/api/daily-orders') {
      const id=Number(url.searchParams.get('preview_id'));
      const Date=`2026-09-${28+id}`;
      body={selected_date:Date,rows:[{Date,Previews:[`preview${id}`],'Today Orders':id,columns:Object.keys(row),rows:[row],missing_ids:[],new_ids:[],unchanged_ids:[]}]};
    } else if(url.pathname==='/api/monthly-orders') body={rows:[{Month:'2026-09',MonthLabel:'September 2026',Previews:['preview2'],'Month Orders':4,'Completed Orders':2,'Unchanged':1,'Awaiting for Clarification':1,'SLA On Time':3,'SLA Missed':1,columns:Object.keys(row),rows:[row],missing_ids:[],unchanged_ids:[]}]};
    else if(url.pathname==='/api/compare') body={counts:{},record_counts:{},columns:[],rows:[],matched_rows:[],unmatched_rows:[]};
    await route.fulfill({json:body});
  });
  await page.goto('http://127.0.0.1:8525');
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Export',exact:true}).click();
  expect((await downloadPromise).suggestedFilename()).toBe('preview2_GoogleSheets.xlsx');
  await page.locator('.sync-schedule summary').click();
  await expect(page.getByText('Indian Standard Time (UTC+05:30)',{exact:true})).toBeVisible();
  await page.locator('.sync-schedule summary').click();
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await expect(page.getByLabel('Daily orders date')).toHaveValue('2026-09-30');
  await page.locator('.preview-select').filter({hasText:'preview1'}).click();
  await expect(page.getByLabel('Daily orders date')).toHaveValue('2026-09-29');
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  await expect(page.getByRole('heading',{name:'SLA COMMENTS'})).toBeVisible();
  await expect(page.locator('.metric').filter({hasText:'SLA On Time'})).toContainText('75.0%');
  await expect(page.locator('.daily-orders')).not.toContainText('Newly Orders');
  await page.screenshot({path:'test-results/monthly-report-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'test-results/monthly-report-mobile.png',fullPage:true});
});
