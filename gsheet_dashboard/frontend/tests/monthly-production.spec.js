import {test,expect} from '@playwright/test';

async function setup(page){
  await page.clock.install({time:new Date('2026-10-05T10:00:00+05:30')});
  const calls={applies:[],exports:[]};let run=1;
  const rows=[{'No':1,'Order Number':'A','Product':'Full Title','Status':'Search In Progress','In-Time':'10/2/2026 1:00 AM'}];
  const columns=Object.keys(rows[0]),preview={id:1,name:'preview1',created:'2026-10-05T04:30:00Z',row_count:1};
  const report=month=>({Month:month,Previews:[],columns,rows,'Month Orders':1,'Completed Orders':0,'Unchanged':1,'Awaiting for Clarification':0,'SLA On Time':0,'SLA Missed':0,completed_ids:[],sla_rows:[]});
  await page.route('**/api/**',async route=>{
    const request=route.request(),url=new URL(request.url());let body={};
    if(url.pathname==='/api/state')body={previews:[preview],job:{running:false,stage:'Ready',run_id:run,result:{action:'sync',preview_name:'preview1',rows:1,pass_report:{scanned:1,added:1,updated:0,unchanged:0,ambiguous:[{Reason:'Review'}]}}}};
    if(url.pathname==='/api/sync'){run++;body={started:true};}
    if(url.pathname==='/api/previews/1')body={...preview,columns,rows};
    if(url.pathname==='/api/live-sheets')body={sheets:{Overview:{columns,rows}},offline:false};
    if(url.pathname==='/api/monthly-orders')body={rows:[report('2026-11'),report('2026-10'),report('2026-09')],offline:false};
    if(url.pathname==='/api/monthly-maintenance')body={operations:[]};
    if(url.pathname==='/api/monthly-maintenance/preview')body={id:'preview-token',kind:request.postDataJSON().kind,counts:[{source:'TV_Search_Production_Report_Full_Search_Oct_2026',target:'TV_Search_Production_Report_Full_Search_Nov_2026',moved:107},{source:'TV_Search_Production_Report_C-O_and_Update_Oct_2026',target:'TV_Search_Production_Report_C-O_and_Update_Nov_2026',moved:255}],reviews:[],moves:[]};
    if(url.pathname==='/api/monthly-maintenance/apply'){calls.applies.push(request.postDataJSON());body={applied:true,moves:[]};}
    if(url.pathname==='/api/export/monthly'){
      calls.exports.push(url.searchParams.get('month'));
      return route.fulfill({status:200,headers:{'Content-Disposition':'attachment; filename=TV_Search_Production_Report_Sep_2026.xlsx','Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'},body:'fixture'});
    }
    await route.fulfill({json:body});
  });
  await page.goto('/');return calls;
}

test('each notification dismisses independently and returns after the next sync',async({page})=>{
  await setup(page);
  await expect(page.getByRole('button',{name:'Dismiss notification',exact:true})).toHaveCount(4);
  const connected=page.locator('.dismissible-notice').filter({hasText:'Google Sheets connected'});
  await connected.getByRole('button',{name:'Dismiss notification'}).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('button',{name:'Dismiss notification',exact:true})).toHaveCount(3);
  await expect(page.getByText('1 scanned',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(connected).toHaveCount(0);
  await page.getByRole('button',{name:'Sync to Sheets'}).click();
  await expect(page.getByRole('button',{name:'Dismiss notification',exact:true})).toHaveCount(4);
});

test('month defaults to current data and Excel uses the selected month',async({page})=>{
  const calls=await setup(page);
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  await expect(page.getByLabel('Monthly orders date')).toHaveValue('2026-10');
  await page.getByLabel('Monthly orders date').selectOption('2026-09');
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download Excel',exact:true}).click();
  expect((await download).suggestedFilename()).toBe('TV_Search_Production_Report_Sep_2026.xlsx');
  expect(calls.exports).toEqual(['2026-09']);
});

test('rollover is a dry run until confirmed and fits narrow windows',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const calls=await setup(page);
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  await page.getByText('Monthly setup, import and rollover',{exact:true}).click();
  await page.getByRole('button',{name:'Run month rollover',exact:true}).click();
  await expect(page.getByRole('region',{name:'Monthly operation preview'})).toContainText('107');
  expect(calls.applies).toEqual([]);
  for(const width of [1440,1024,800,640]){
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }
  await page.screenshot({path:'test-results/monthly-rollover-narrow.png',fullPage:true});
  await page.getByRole('button',{name:'Confirm rollover',exact:true}).click();
  await expect(page.getByText('Completed. 0 orders moved.',{exact:false})).toBeVisible();
  expect(calls.applies).toEqual([{id:'preview-token',confirmed:true}]);
  expect(errors).toEqual([]);
});

test('failed Excel download shows a clear error and can be retried',async({page})=>{
  await setup(page);
  await page.route('**/api/export/monthly?*',route=>route.fulfill({status:404,json:{error:'No production orders are available for 2026-10.'}}));
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  await page.getByRole('button',{name:'Download Excel',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('No production orders');
  await expect(page.getByRole('button',{name:'Download Excel',exact:true})).toBeEnabled();
});
