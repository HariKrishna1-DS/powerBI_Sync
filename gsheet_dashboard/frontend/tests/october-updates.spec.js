import {test, expect} from '@playwright/test';

test.use({timezoneId:'America/Los_Angeles'});

test('charts show values and selected periods, production overview is available, and IST ignores the PC clock', async ({page}) => {
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  await page.addInitScript(()=>{Date.now=()=>Date.parse('2035-01-01T00:00:00Z');});
  const started=performance.now();
  const rows=[{'Order Number':'A','Product':'Full Title','Status':'Completed and Delivered'},
              {'Order Number':'B','Product':'Current Owner','Status':'Cancelled'},
              {'Order Number':'C','Product':'Full Title','Status':'Awaiting for Clarification'}];
  const columns=['Order Number','Product','Status'];
  const preview={id:2,name:'preview2',created:'2026-10-02T06:30:00Z',source:'Capture',row_count:3};
  const history=Array.from({length:30},(_,i)=>({Date:`2026-09-${String(i+1).padStart(2,'0')}`,Previews:['preview2'],
    'Received':i===29?297:1,'Missing':i===29?21:0,'Completed':0,
    'In-House Pending':i===29?190:1,'Clarification':i===29?72:0,
    columns,rows,missing_ids:[],new_ids:[],unchanged_ids:[]})).reverse();
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let body={};
    if(path==='/api/state')body={previews:[preview],job:{running:false,stage:'Ready'},schedule:{enabled:true,times:['12:07']},
      clock:{epoch_ms:Date.parse('2026-10-02T06:30:00Z')+performance.now()-started,synchronized:true,timezone:'Asia/Kolkata'},remaining_products:[]};
    if(path.startsWith('/api/previews/'))body={...preview,rows,columns};
    if(path==='/api/live-sheets')body={mode:'tracker',sheets:{'All Products':{columns,rows},'Full Title':{columns,rows:rows.slice(0,1)},'Remaining Products':{columns,rows:rows.slice(1)}}};
    if(path==='/api/daily-orders')body={rows:history,selected_date:'2026-09-30'};
    if(path==='/api/monthly-orders')body={rows:[{Month:'2026-09',MonthLabel:'September 2026',Days:[],Previews:['preview2'],
      'Month Orders':4000,'Completed Orders':3000,'Unchanged':2900,'Awaiting for Clarification':200,'SLA On Time':90,'SLA Missed':10,
      rows,columns,missing_ids:[],completed_ids:[],new_ids:[],unchanged_ids:[],sla_rows:[]}],selected_month:'2026-09',sla_error:null};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await expect(page.getByRole('button',{name:'Overview',exact:true})).toHaveCount(1);
  await expect(page.getByRole('heading',{name:'Queue overview',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.locator('.status-summary-row').filter({hasText:'Cancelled'})).toContainText('1');
  await expect(page.locator('.status-summary-row').filter({hasText:'Completed and Delivered'})).toContainText('1');
  await page.getByText('AutoLogin Trigger',{exact:true}).click();
  await expect(page.getByTestId('indian-clock')).toContainText('02 Oct 2026');
  await expect(page.getByTestId('indian-clock')).toContainText('12:00:');
  await expect(page.getByTestId('next-trigger')).toContainText('12:07:00');
  const before=await page.getByTestId('indian-clock').textContent();
  await expect.poll(()=>page.getByTestId('indian-clock').textContent()).not.toBe(before);
  await page.getByText('AutoLogin Trigger',{exact:true}).click();
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  const daily=page.getByRole('region',{name:'Daily orders bar chart'});
  await expect(daily.locator('.recharts-label-list text').filter({hasText:/^297$/})).toBeVisible();
  await expect(daily.locator('.recharts-label-list text').filter({hasText:/^72$/})).toBeVisible();
  await expect(daily.locator('.chart-period-controls')).toContainText('Sep 30');
  expect(await daily.locator('.recharts-bar-rectangle path').count()).toBeGreaterThan(0);
  await daily.screenshot({path:'test-results/daily-chart-values.png'});
  await daily.getByRole('button',{name:'Earlier',exact:true}).click();
  await expect(page.getByLabel('Daily orders date')).toHaveValue('2026-09-27');
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  const monthly=page.getByRole('region',{name:'Monthly orders bar chart'});
  await expect(monthly.locator('.recharts-label-list text').filter({hasText:/^4,000$/})).toBeVisible();
  await monthly.screenshot({path:'test-results/monthly-chart-values.png'});
  expect(errors).toEqual([]);
});
