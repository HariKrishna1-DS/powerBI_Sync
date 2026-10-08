import {test, expect} from '@playwright/test';

async function setup(page) {
  const preview={id:31,name:'preview31',created:'2026-10-01T06:38:14Z',source:'Test',
    columns:['Order Number','Task Status','Product'],rows:[{'Order Number':'001','Task Status':'Available',Product:'Full Title'}]};
  const rows=Array.from({length:31},(_,index)=>({'Order Number':String(index+1).padStart(3,'0'),
    'Product Group':index%2?'Remaining Products':'Full Title',Product:index%2?'Update':'Full Title',
    'In Time':'10/01/2026 09:00 AM','Out Time':'10/01/2026','SLA Expiration':'10/01/2026 10:00 AM',
    'Free Site':index===0?'Missing':'On Time',completion_date:'2026-10-01'}));
  const report={Month:'2026-10',MonthLabel:'October 2026',Previews:['preview31'],Days:['2026-10-01'],
    'Month Orders':31,'Completed Orders':31,Unchanged:0,'Awaiting for Clarification':0,
    columns:preview.columns,rows:preview.rows,missing_ids:[],unchanged_ids:[],sla_rows:rows};
  const updateTotals=()=>{
    report['SLA On Time']=rows.filter(row=>row['Free Site']==='On Time').length;
    report['SLA Missed']=rows.filter(row=>row['Free Site']==='Missing').length;
  };
  updateTotals();
  const requests=[];
  const control={fail:false};
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/state') await route.fulfill({json:{previews:[{...preview,row_count:1}],
      job:{running:false,stage:'Ready',result:null},schedule:{enabled:false,times:['09:00']},daily_completed_ids:[]}});
    else if(path==='/api/previews/31') await route.fulfill({json:preview});
    else if(path==='/api/live-sheets') await route.fulfill({json:{mode:'tracker',preview_name:'preview31',sheets:{
      'All Products':preview,'Full Title':preview,'Remaining Products':{columns:preview.columns,rows:[]},
      'Status Report':{columns:['Status','Orders'],rows:[{Status:'Available',Orders:1}]}}}});
    else if(path==='/api/monthly-orders') await route.fulfill({json:{rows:[report],sla_error:null}});
    else if(path==='/api/sla-comments'||path==='/api/sla-comments/bulk') {
      const body=route.request().postDataJSON();requests.push(body);
      if(control.fail) return route.fulfill({status:502,json:{error:'The Google Sheets save could not be confirmed. Refresh the report before retrying.'}});
      const orders=body.orders||[body];
      orders.forEach(order=>{rows.find(row=>row['Order Number']===order.order_number)['Free Site']=body.status;});
      updateTotals();
      const message=body.orders?`${orders.length} orders saved as ${body.status} in report history.`:`Order ${body.order_number} saved as ${body.status} in Google Sheets and report history.`;
      await route.fulfill({json:{saved:true,rows:[report],message}});
    } else await route.fulfill({json:{}});
  });
  await page.goto(process.env.DASHBOARD_TEST_URL||'/');
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  await expect(page.getByRole('table',{name:'SLA orders',exact:true})).toBeVisible();
  return {requests,control};
}

test('SLA detail filters, pagination, and edits in both directions update report totals',async({page})=>{
  const {requests}=await setup(page);
  const section=page.getByRole('region',{name:'SLA order details',exact:true});
  const table=page.getByRole('table',{name:'SLA orders',exact:true});
  await expect(table.getByRole('columnheader',{name:'In Time',exact:true})).toBeVisible();
  await expect(table.getByRole('columnheader',{name:'Out Time',exact:true})).toBeVisible();
  await expect(section.getByText('31 / 31 orders')).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(25);
  await page.getByRole('button',{name:'Next SLA page'}).click();
  await expect(table.locator('tbody tr')).toHaveCount(6);
  await page.getByLabel('Filter SLA product group').selectOption('Remaining Products');
  await expect(section.getByText('15 / 31 orders')).toBeVisible();
  await expect(table.locator('tbody tr')).toHaveCount(15);
  await page.getByLabel('Filter SLA product group').selectOption('');
  await page.getByRole('button',{name:/^SLA Missed/}).click();
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'Edit SLA for order 001',exact:true}).click();
  await page.getByLabel('Edit Free Site',{exact:true}).selectOption('On Time');
  await page.getByRole('button',{name:'Save SLA',exact:true}).click();
  await expect(section.getByRole('status')).toContainText('Order 001 saved as On Time');
  await expect(page.getByRole('button',{name:/^SLA On Time/}).locator('strong')).toHaveText('31');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('0');
  await expect(section.getByText('No matching SLA orders')).toBeVisible();
  expect(requests[0]).toEqual({order_number:'001',completion_date:'2026-10-01',expected_status:'Missing',status:'On Time'});
  await page.getByLabel('Filter SLA status').selectOption('On Time');
  await page.getByLabel('Search SLA orders').fill('002');
  await page.getByRole('button',{name:'Edit SLA for order 002',exact:true}).click();
  await page.getByLabel('Edit Free Site',{exact:true}).selectOption('Missing');
  await page.getByRole('button',{name:'Save SLA',exact:true}).click();
  await expect(section.getByRole('status')).toContainText('Order 002 saved as Missing');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('1');
  await page.getByRole('button',{name:'Refresh SLA',exact:true}).click();
  await page.getByLabel('Filter SLA status').selectOption('Missing');
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.locator('tbody')).toContainText('002');
  await page.screenshot({path:test.info().outputPath('sla-comments.png'),fullPage:false});
});

test('failed SLA save keeps the draft, row and totals unchanged and allows retry',async({page})=>{
  const {control}=await setup(page);
  control.fail=true;
  await page.getByLabel('Search SLA orders').fill('001');
  await page.getByRole('button',{name:'Edit SLA for order 001',exact:true}).click();
  await page.getByLabel('Edit Free Site',{exact:true}).selectOption('On Time');
  await page.getByRole('button',{name:'Save SLA',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('save could not be confirmed');
  await expect(page.getByLabel('Edit Free Site',{exact:true})).toHaveValue('On Time');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('1');
  await expect(page.getByRole('table',{name:'SLA orders',exact:true}).locator('tbody')).toContainText('Missing');
  control.fail=false;
  await page.getByRole('button',{name:'Save SLA',exact:true}).click();
  await expect(page.getByRole('region',{name:'SLA order details'}).getByRole('status')).toContainText('saved as On Time');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('bulk selection carries across pages and sends one update for selected orders only',async({page})=>{
  const {requests}=await setup(page);
  await page.getByRole('checkbox',{name:'Select order 001',exact:true}).check();
  await page.getByRole('checkbox',{name:'Select order 002',exact:true}).check();
  await expect(page.getByRole('checkbox',{name:'Select all orders on this page'})).toHaveJSProperty('indeterminate',true);
  await page.getByRole('button',{name:'Next SLA page'}).click();
  await page.getByRole('checkbox',{name:'Select order 026',exact:true}).check();
  await expect(page.getByText('3 orders selected',{exact:true})).toBeVisible();
  await page.getByLabel('Bulk SLA status',{exact:true}).selectOption('Missing');
  await page.getByRole('group',{name:'Update selected SLA orders',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:test.info().outputPath('sla-bulk-selection.png'),fullPage:false});
  await page.getByRole('button',{name:'Update 3 selected',exact:true}).click();
  expect(requests).toHaveLength(1);
  expect(requests[0].orders.map(order=>order.order_number)).toEqual(['001','002','026']);
  expect(requests[0].status).toBe('Missing');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('3');
  await expect(page.getByRole('group',{name:'Update selected SLA orders',exact:true})).toHaveCount(0);
  await page.getByLabel('Filter SLA status').selectOption('Missing');
  await expect(page.getByRole('table',{name:'SLA orders',exact:true}).locator('tbody tr')).toHaveCount(3);
});

test('select page, select all filtered, deselect and filter reset are explicit',async({page})=>{
  const {requests}=await setup(page);
  await page.getByRole('checkbox',{name:'Select all orders on this page'}).check();
  await expect(page.getByText('25 orders selected',{exact:true})).toBeVisible();
  await page.getByRole('checkbox',{name:'Select order 001',exact:true}).uncheck();
  await expect(page.getByText('24 orders selected',{exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Select all 31 matching orders',exact:true}).click();
  await expect(page.getByText('31 orders selected',{exact:true})).toBeVisible();
  await page.getByLabel('Filter SLA product group').selectOption('Remaining Products');
  await expect(page.getByRole('group',{name:'Update selected SLA orders',exact:true})).toHaveCount(0);
  await page.getByRole('checkbox',{name:'Select all orders on this page'}).check();
  await expect(page.getByText('15 orders selected',{exact:true})).toBeVisible();
  await page.getByLabel('Bulk SLA status',{exact:true}).selectOption('Missing');
  await page.getByRole('button',{name:'Update 15 selected',exact:true}).click();
  expect(requests[0].orders).toHaveLength(15);
  expect(requests[0].orders.every(order=>Number(order.order_number)%2===0)).toBe(true);
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('16');
  await page.getByRole('checkbox',{name:'Select all orders on this page'}).check();
  await page.getByLabel('Bulk SLA status',{exact:true}).selectOption('On Time');
  await page.getByRole('button',{name:'Update 15 selected',exact:true}).click();
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('1');
});

test('bulk save failure retains selection and chosen status for retry',async({page})=>{
  const {requests,control}=await setup(page);
  control.fail=true;
  await page.getByRole('checkbox',{name:'Select all orders on this page'}).check();
  await page.getByRole('button',{name:'Select all 31 matching orders',exact:true}).click();
  await page.getByLabel('Bulk SLA status',{exact:true}).selectOption('On Time');
  await page.getByRole('button',{name:'Update 31 selected',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('save could not be confirmed');
  await expect(page.getByText('31 orders selected',{exact:true})).toBeVisible();
  await expect(page.getByLabel('Bulk SLA status',{exact:true})).toHaveValue('On Time');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('1');
  control.fail=false;
  await page.getByRole('button',{name:'Update 31 selected',exact:true}).click();
  await expect(page.getByRole('region',{name:'SLA order details'}).getByRole('status')).toContainText('31 orders saved as On Time');
  await expect(page.getByRole('button',{name:/^SLA Missed/}).locator('strong')).toHaveText('0');
  expect(requests).toHaveLength(2);
  expect(requests[1]).toEqual(requests[0]);
});
