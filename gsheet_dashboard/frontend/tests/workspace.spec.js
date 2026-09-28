import {test, expect} from '@playwright/test';

const columns=['Order Number','OPON','Arrival Date','Task Name','Task Status','Client','Product','County'];
const rows=Array.from({length:65},(_,i)=>({'Order Number':`ORD-${String(i).padStart(4,'0')}`,'OPON':String(i).padStart(4,'0'),'Arrival Date':`2026-09-${String(i%28+1).padStart(2,'0')}`,'Task Name':i%2?'UpdateSearch':'Search','Task Status':i%3?'Available':'Task Suspended','Client':i%2?'DATATREE':'CODLIS','Product':i%2?'Full Title':'Current Owner','County':i%2?'Ogle':'Emery'}));
const captures=[{id:3,name:'preview3',created:'2026-09-23T12:00:00Z',source:'Browser test fixture',row_count:65},{id:2,name:'preview2',created:'2026-09-22T12:00:00Z',source:'Browser test fixture',row_count:65},{id:1,name:'preview1',created:'2026-09-21T12:00:00Z',source:'Browser test fixture',row_count:65}];
async function fixtures(page) {
  const job={running:false,stage:'Ready',action:null,run_id:0,result:null};
  let schedule={enabled:false,time:'09:00',last_triggered_date:null};
  let activeCaptures=[...captures];
  let runs=0,syncs=0,syncPreview=null;
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let body;
    if(path==='/api/state') body={previews:activeCaptures,job,schedule,capabilities:{automatic_statuses:true},sheet_url:'https://docs.google.com'};
    else if(path==='/api/extract') {runs++;job.run_id=runs;job.action='extract';job.result={action:'extract',error:'Test credentials missing'};body={accepted:true};}
    else if(path==='/api/sync') {syncs++;syncPreview=route.request().postDataJSON().preview;job.run_id++;job.action='sync';job.result={action:'sync',error:null,preview_name:`preview${syncPreview}`,rows:65,worksheets:['Sheet1','All Products','Full Title','Remaining Products']};body={accepted:true};}
    else if(path==='/api/sync-schedule') {schedule={...schedule,...route.request().postDataJSON()};body=schedule;}
    else if(path.startsWith('/api/previews/')) {const id=Number(path.split('/')[3]);if(route.request().method()==='DELETE'){activeCaptures=activeCaptures.filter(c=>c.id!==id);body={deleted:id};}else body={...captures.find(c=>c.id===id),columns,rows};}
    else if(path==='/api/compare') {const request=route.request().postDataJSON();body={columns:['Change','Task Key','Column','Previous Value','Latest Value'],rows:[{Change:'Modified','Task Key':'0001',Column:'Task Status','Previous Value':'Available','Latest Value':'Completed'}],counts:{added:1,removed:1,modified:1,unchanged:63},record_columns:['Comparison Status',...columns],matched_rows:[{'Comparison Status':'Matched - changed',...rows[1],'Task Status':'Completed'},{'Comparison Status':'Unchanged',...rows[2]}],unmatched_rows:[{'Comparison Status':'Missing',...rows[3]},{'Comparison Status':'Newly Added',...rows[64]}],record_counts:{matched:64,missing:1,newly_added:1,unchanged:63},method:'Matched by Order Number',keys:['Order Number'],previous:`preview${request.previous}`,latest:`preview${request.latest}`,added_columns:[],removed_columns:[],order_append:{available:true,column:'Order Number',anchor_order:'ORD-0063',anchor_index:63,count:1,columns,rows:[rows[64]],message:`1 order found after ORD-0063 in preview${request.latest}.`}};}
    else return route.fallback();
    await route.fulfill({json:body});
  });
  return {runs:()=>runs,syncs:()=>syncs,syncPreview:()=>syncPreview};
}

test('real workspace starts without sample data or demo schema',async({page})=>{
  await page.goto('/');
  await expect(page.getByText('No queue data yet')).toBeVisible();
  await expect(page.getByText('Power BI demo Star Schema')).toHaveCount(0);
  await page.screenshot({path:'test-results/empty-desktop.png',fullPage:true});
});

test('column unique values, filters, charts, comparison and repeat run',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const activity=await fixtures(page);
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Queue overview',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'preview3 - All Products',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Data sheets',exact:true}).click();
  await expect(page.getByRole('heading',{name:'preview3 - All Products',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'preview3 - Full Title',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'preview3 - Remaining Products',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Task Name',exact:true}).first().click();
  const panel=page.getByRole('complementary',{name:'Column filters'});
  await expect(panel.getByRole('checkbox',{name:'UpdateSearch'})).toBeVisible();
  await panel.getByRole('checkbox',{name:'UpdateSearch'}).uncheck();
  await expect(page.locator('.filter-toolbar .row-tally')).toHaveText('33 / 65 rows');
  await panel.getByRole('button',{name:'Reset column'}).click();
  await panel.getByLabel('Condition').selectOption('contains');
  await panel.getByLabel('Filter value').fill('Update');
  await expect(page.locator('.filter-toolbar .row-tally')).toHaveText('32 / 65 rows');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button',{name:'Filtered CSV'}).first().click();
  expect((await downloadEvent).suggestedFilename()).toContain('filtered.csv');
  await panel.getByRole('button',{name:'Reset column'}).click();
  await panel.getByRole('button',{name:'Close filter'}).click();
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  for(const type of ['line','area','horizontal','pie','donut','bar']) {
    await page.getByLabel('Chart type').selectOption(type);
    await expect(page.locator('.recharts-surface').first()).toBeVisible();
  }
  const overflow=await page.locator('.chart-scroll').evaluate(el=>el.scrollWidth>el.clientWidth);
  expect(overflow).toBeTruthy();
  expect(await page.locator('.recharts-bar-rectangle path').first().evaluate(el=>el.getBBox().height)).toBeGreaterThan(100);
  await page.locator('.recharts-bar-rectangle path').first().click();
  await expect(page.locator('.chart-drilldown')).toBeVisible();
  await page.getByRole('button',{name:'Close chart details'}).click();
  await page.getByRole('button',{name:'Data sheets',exact:true}).click();
  await page.locator('.preview-select').filter({hasText:'preview2'}).click();
  await expect(page.getByRole('heading',{name:'preview2 - All Products',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Sync preview2 to Sheets'}).click();
  expect(activity.syncs()).toBe(1);
  expect(activity.syncPreview()).toBe(2);
  await page.getByText('Sync trigger',{exact:true}).click();
  await page.getByRole('checkbox',{name:'Daily sync enabled'}).check();
  await page.getByLabel('Daily sync time').fill('14:30');
  await page.getByRole('button',{name:'Save trigger'}).click();
  await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Changes',exact:false}).first().click();
  await expect(page.getByText('Matched by Order Number')).toBeVisible();
  await page.getByLabel('Previous preview').selectOption('1');
  await expect(page.getByLabel('Latest preview')).toHaveValue('2');
  await expect(page.getByText('Orders added after it')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Orders after ORD-0063'})).toBeVisible();
  await expect(page.getByRole('heading',{name:/Matched orders/})).toBeVisible();
  await expect(page.getByRole('heading',{name:'New orders'})).toHaveCount(0);
  await expect(page.getByText('Newly added',{exact:true})).toBeVisible();
  await expect(page.getByRole('cell',{name:'Completed',exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/changes-desktop.png',fullPage:true});
  const runButton=page.getByRole('button',{name:'Run AutoLogin & Extract Queue'});
  await runButton.click();await expect(runButton).toBeEnabled();
  await runButton.click();await expect(runButton).toBeEnabled();
  expect(activity.runs()).toBe(2);
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Delete preview1'}).click();
  await expect(page.getByText('preview1',{exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});

test('mobile layout and filters stay inside viewport',async({page})=>{
  await fixtures(page);await page.setViewportSize({width:390,height:844});await page.goto('/');
  await expect(page.getByRole('heading',{name:'Queue overview',exact:true})).toBeVisible();
  await page.getByLabel('Choose column filter').selectOption('Task Name');
  await expect(page.getByRole('complementary',{name:'Column filters'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/overview-mobile.png',fullPage:true});
});
