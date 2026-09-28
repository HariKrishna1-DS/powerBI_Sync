import {test, expect} from '@playwright/test';

test('comparison can recover after a failed request', async ({page}) => {
  const preview={id:2,name:'preview2',row_count:1,created:'2026-09-28T10:00:00Z',columns:['Order Number','Task Status'],rows:[{'Order Number':'A','Task Status':'Available'}]};
  let fail=true;
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/state') return route.fulfill({json:{previews:[preview,{...preview,id:1,name:'preview1'}],job:{running:false,stage:'Ready'}}});
    if(path==='/api/compare') {
      if(fail) return route.fulfill({status:503,json:{error:'Comparison temporarily unavailable'}});
      return route.fulfill({json:{previous:'preview1',latest:'preview2',record_columns:['Comparison Status',...preview.columns],matched_rows:[{...preview.rows[0],'Comparison Status':'Unchanged'}],unmatched_rows:[],record_counts:{matched:1,missing:0,newly_added:0,unchanged:1},added_columns:[],removed_columns:[],method:'Matched by Order Number'}});
    }
    return route.fulfill({json:preview});
  });
  await page.goto(process.env.DASHBOARD_TEST_URL || 'http://127.0.0.1:8520');
  await page.getByRole('button',{name:'Changes',exact:false}).first().click();
  await expect(page.getByRole('button',{name:'Retry comparison'})).toBeVisible();
  fail=false;
  await page.getByRole('button',{name:'Retry comparison'}).click();
  await expect(page.getByRole('heading',{name:'Matched orders · preview1 and preview2'})).toBeVisible();
  await expect(page.getByRole('cell',{name:'A',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Retry comparison'})).toHaveCount(0);
});

test('automatic statuses, comparison labels and daily order tables', async ({page}) => {
  test.setTimeout(120000);
  const base = {'Client':'A', 'Product':'Full Title', 'Online/ Ground':'Online'};
  const rows = [
    {...base,'Order Number':'001','Task Status':'Workflow Suspended'},
    {...base,'Order Number':'002','Task Status':'Available'},
    {...base,'Order Number':'004','Task Status':'In Progress'}
  ];
  const missing = {...base,'Order Number':'003','Task Status':'Task Suspended','Comparison Status':'Missing'};
  const preview = {id:2,name:'preview2',created:'2026-09-25T12:00:00Z',source:'Test',row_count:3,columns:Object.keys(rows[0]),rows};
  const older = {...preview,id:1,name:'preview1'};
  const diff = {record_columns:['Comparison Status',...preview.columns],
    matched_rows:rows.slice(0,2).map(row=>({...row,'Comparison Status':'Unchanged'})),
    unmatched_rows:[missing,{...rows[2],'Comparison Status':'Newly Added'}],
    record_counts:{matched:2,missing:1,newly_added:1,unchanged:2},
    counts:{added:1,removed:1,unchanged:2,modified:0}, previous:'preview1',latest:'preview2',
    method:'Matched by Order Number',added_columns:[],removed_columns:[]};
  let synced;
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/sync') {synced=route.request().postDataJSON();return route.fulfill({json:{accepted:true}});}
    let data=preview;
    if(path==='/api/state') data={previews:[preview,older],job:{running:false,stage:'Ready'},capabilities:{automatic_statuses:true},sheet_url:'https://docs.google.com'};
    if(path==='/api/compare') data=diff;
    if(path==='/api/daily-orders') data={rows:[{Date:'2026-09-25',Previews:['preview1','preview2'],'Today Orders':4,'Missing (Completed Orders)':1,'Newly Orders':1,Unchanged:2,columns:preview.columns,rows:[...rows,{...missing,'Task Status':'Completed and Delivered'}],missing_ids:['003'],new_ids:['004'],unchanged_ids:['001','002']}]};
    await route.fulfill({json:data});
  });
  await page.goto(process.env.DASHBOARD_TEST_URL || 'http://127.0.0.1:8520');
  await expect(page.getByLabel('Status_1',{exact:true})).toHaveCount(0);
  await expect(page.getByLabel('Status_2',{exact:true})).toHaveCount(0);
  await expect(page.locator('.status-report-table')).toContainText('Awaiting for Clarification');
  await expect(page.locator('.status-report-table')).toContainText('In Progress');
  await expect(page.locator('.dropdown-slicer')).toHaveCount(3);
  await page.getByRole('button',{name:'Sync preview2 to Sheets',exact:true}).click();
  await expect.poll(()=>synced?.preview).toBe(2);
  expect(synced.previous).toBe(1);
  expect(synced.status_rules).toBeUndefined();
  await page.getByRole('button',{name:'Changes',exact:false}).first().click();
  await expect(page.locator('.metrics')).toContainText('Missing (Completed Orders)');
  await expect(page.getByRole('heading',{name:'New orders'})).toHaveCount(0);
  const missingTable = page.locator('.table-section').filter({has:page.getByRole('heading',{name:'Missing (Completed Orders)',exact:true})});
  await expect(missingTable).toContainText('003');
  await expect(missingTable).toContainText('Completed and Delivered');
  await expect(missingTable).not.toContainText('004');
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Daily capture history'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Missing (Completed Orders) · 1',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Unchanged · 2',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Today Orders · 4',exact:true})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Newly Orders · 1',exact:true})).toBeVisible();
  await expect(page.getByLabel('Previous preview')).toHaveCount(0);
  await expect(page.getByLabel('Latest preview')).toHaveCount(0);
  await expect(page.locator('.daily-orders')).toContainText('preview1, preview2');
  await expect(page.locator('.daily-orders')).toContainText('003');
  await page.getByLabel('Daily orders date').selectOption('2026-09-25');
  const chart=page.getByRole('region',{name:'Daily orders bar chart'});
  await expect(chart.getByRole('heading',{name:'Daily Orders by Date'})).toBeVisible();
  await expect(chart.locator('.recharts-bar-rectangle path')).toHaveCount(4);
  await chart.locator('.recharts-bar-rectangle path').first().hover();
  await expect(chart.locator('.recharts-tooltip-wrapper')).toContainText('Today Orders');
  await page.getByRole('button',{name:'Expand daily orders chart'}).click();
  await expect(page.locator('.maximized-modal .recharts-surface')).toBeVisible();
  await page.getByRole('button',{name:'Close modal',exact:true}).click();
  await chart.locator('.recharts-bar-rectangle path').first().click();
  await expect(page.getByLabel('Daily orders date')).toHaveValue('2026-09-25');
  await chart.screenshot({path:'test-results/daily-chart-desktop.png'});
  await page.screenshot({path:'test-results/daily-orders-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await chart.screenshot({path:'test-results/daily-chart-mobile.png'});
  await page.screenshot({path:'test-results/daily-orders-mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});
