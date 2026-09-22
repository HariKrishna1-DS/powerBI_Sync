import {test, expect} from '@playwright/test';

const columns=['OPON','Arrival Date','Task Name','Task Status','Client','County'];
const rows=Array.from({length:65},(_,i)=>({'OPON':String(i).padStart(4,'0'),'Arrival Date':`2026-09-${String(i%28+1).padStart(2,'0')}`,'Task Name':i%2?'UpdateSearch':'Search','Task Status':i%3?'Available':'Task Suspended','Client':i%2?'DATATREE':'CODLIS','County':i%2?'Ogle':'Emery'}));
const captures=[{id:2,name:'preview2',created:'2026-09-22T12:00:00Z',source:'Browser test fixture',row_count:65},{id:1,name:'preview1',created:'2026-09-21T12:00:00Z',source:'Browser test fixture',row_count:65}];
async function fixtures(page) {
  const job={running:false,stage:'Ready',run_id:0,result:null};
  let runs=0;
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let body;
    if(path==='/api/state') body={previews:captures,job,sheet_url:'https://docs.google.com'};
    else if(path==='/api/extract') {runs++;job.run_id=runs;job.result={error:'Test credentials missing'};body={accepted:true};}
    else if(path.startsWith('/api/previews/')) {const id=Number(path.split('/')[3]);body={...captures.find(c=>c.id===id),columns,rows};}
    else if(path==='/api/compare') body={columns:['Change','Task Key','Column','Previous Value','Latest Value'],rows:[{Change:'Modified','Task Key':'0001',Column:'Task Status','Previous Value':'Available','Latest Value':'Completed'}],counts:{added:0,removed:0,modified:1,unchanged:64},method:'Matched by OPON',keys:['OPON'],previous:'preview1',latest:'preview2',added_columns:[],removed_columns:[]};
    else return route.fallback();
    await route.fulfill({json:body});
  });
  return ()=>runs;
}

test('real workspace starts without sample data or demo schema',async({page})=>{
  await page.goto('/');
  await expect(page.getByText('No queue data yet')).toBeVisible();
  await expect(page.getByText('Power BI demo Star Schema')).toHaveCount(0);
  await page.screenshot({path:'test-results/empty-desktop.png',fullPage:true});
});

test('column unique values, filters, charts, comparison and repeat run',async({page})=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const runs=await fixtures(page);
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'preview2',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Task Name',exact:true}).click();
  const panel=page.getByRole('complementary',{name:'Column filters'});
  await expect(panel.getByRole('checkbox',{name:'UpdateSearch'})).toBeVisible();
  await panel.getByRole('checkbox',{name:'UpdateSearch'}).uncheck();
  await expect(page.locator('.row-tally')).toHaveText('33 / 65 rows');
  await panel.getByRole('button',{name:'Reset column'}).click();
  await panel.getByLabel('Condition').selectOption('contains');
  await panel.getByLabel('Filter value').fill('Update');
  await expect(page.locator('.row-tally')).toHaveText('32 / 65 rows');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button',{name:'Filtered CSV'}).click();
  expect((await downloadEvent).suggestedFilename()).toContain('filtered.csv');
  await panel.getByRole('button',{name:'Reset column'}).click();
  await panel.getByRole('button',{name:'Close filter'}).click();
  for(const type of ['line','area','horizontal','pie','donut','bar']) {
    await page.getByLabel('Chart type').selectOption(type);
    await expect(page.locator('.recharts-surface').first()).toBeVisible();
  }
  const overflow=await page.locator('.chart-scroll').evaluate(el=>el.scrollWidth>el.clientWidth);
  expect(overflow).toBeTruthy();
  expect(await page.locator('.recharts-bar-rectangle path').first().evaluate(el=>el.getBBox().height)).toBeGreaterThan(100);
  await page.screenshot({path:'test-results/overview-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Changes',exact:false}).first().click();
  await expect(page.getByText('Matched by OPON')).toBeVisible();
  await expect(page.getByRole('cell',{name:'Completed',exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/changes-desktop.png',fullPage:true});
  const runButton=page.getByRole('button',{name:'Run AutoLogin & Extract Queue'});
  await runButton.click();await expect(runButton).toBeEnabled();
  await runButton.click();await expect(runButton).toBeEnabled();
  expect(runs()).toBe(2);
  expect(errors).toEqual([]);
});

test('mobile layout and filters stay inside viewport',async({page})=>{
  await fixtures(page);await page.setViewportSize({width:390,height:844});await page.goto('/');
  await expect(page.getByRole('heading',{name:'preview2',exact:true})).toBeVisible();
  await page.getByLabel('Choose column filter').selectOption('Task Name');
  await expect(page.getByRole('complementary',{name:'Column filters'})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/overview-mobile.png',fullPage:true});
});
