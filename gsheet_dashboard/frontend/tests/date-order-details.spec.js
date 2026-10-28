import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page,{rejectSave=false,legacyDetailsOnce=false,sameNumberAcrossFiles=false,repeatedWithinFile=false}={}){
  const fixture=workspaceFixture(80),writes=[],errors=[],changes=[];
  const legacyPaths=new Set();
  fixture.rows[0]._month='2026-09';
  const columns=fixture.columns.concat('Out Time'),day='2026-10-01';
  if(sameNumberAcrossFiles||repeatedWithinFile){
    columns.push('Source workbook');
    fixture.rows[1]['Order Number']=fixture.rows[0]['Order Number'];
    for(const [index,source] of [[0,'full.xlsx'],[1,'other.xlsx']]){
      const workbook=repeatedWithinFile?'full.xlsx':source;
      fixture.rows[index]['Source workbook']=workbook;
      if(repeatedWithinFile)fixture.rows[index]['Source row ID']=`TV Orders!${index+2}`;
      fixture.rows[index]._record_key=JSON.stringify([workbook,fixture.rows[index]['Order Number'].toLowerCase(),...(repeatedWithinFile?[fixture.rows[index]['Source row ID']]:[])]);
    }
    if(repeatedWithinFile)columns.push('Source row ID');
  }
  const capacityColumns=['Date','Received','Completed','Clarification','Cancelled','Vendor Pending','In-House Pending','Capacity','Ext capacity'];
  const settings={mode:'excel',row_count:80,data_revision:'date-details',files:[]};
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      if(legacyDetailsOnce&&name.endsWith('/details')&&!legacyPaths.has(name)){
        legacyPaths.add(name);return route.fulfill({status:404,contentType:'text/html',body:'<h1>Not Found</h1>'});
      }
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,mode:'excel'};
      if(name==='/api/capacity-report')body={completion_date_basis:'out_time',columns:capacityColumns,monthly:[{Date:'2026-08',Received:1},{Date:'2026-09',Received:6},{Date:'2026-10',Received:80,Completed:3,Clarification:16,Cancelled:5,'Vendor Pending':9,'In-House Pending':47}],
        daily:[{Date:day,Received:65,Completed:2,Clarification:12,Cancelled:3,'Vendor Pending':6,'In-House Pending':42},{Date:'2026-10-02',Received:15,Completed:1,Clarification:4,Cancelled:2,'Vendor Pending':3,'In-House Pending':5}],month:'2026-10',capacity:700,extended_capacity:750,source:'Imported Excel'};
      if(name==='/api/capacity-report/details')body={completion_date_basis:'out_time',date:day,previous_date:'2026-09-30',next_date:'2026-10-02',raw_received:65,rollover_received:0,
        mode:'excel',source:'Imported Excel',columns,groups:[
          {key:'received',label:'Received',rows:fixture.rows.slice(0,65)},
          {key:'completed',label:'Completed',rows:fixture.rows.slice(4,6)},
          {key:'clarification',label:'Clarification',rows:fixture.rows.slice(6,18)},
          {key:'cancelled',label:'Cancelled',rows:fixture.rows.slice(18,21)},
          {key:'vendor',label:'Vendor Pending',rows:fixture.rows.slice(21,27)},
          {key:'in_house',label:'In-House Pending',rows:fixture.rows.slice(0,4).concat(fixture.rows.slice(27,65))},
          {key:'changes',label:'Recorded changes',rows:changes},
        ]};
      if(name==='/api/daily-orders')body={rows:[{Date:day,Received:60,Completed:2,Clarification:12,Cancelled:0,'Vendor Pending':6,'In-House Pending':40,'SLA OnTime':2,Missing:0,status_counts:{'Search In Progress':36,'Search Completed':12,'Awaiting for Clarification':12},columns,rows:fixture.rows.slice(0,60),sla_rows:[],Previews:[]}],selected_date:day,mode:'excel',source:'Imported Excel'};
      if(name==='/api/daily-orders/details')body={date:day,mode:'excel',source:'Imported Excel',columns,groups:[{key:'received',label:'Received',rows:fixture.rows.slice(0,60)},{key:'changes',label:'Recorded changes',rows:changes}]};
      if(name==='/api/report-date'){settings.data_revision='selected-date';body={date:day,synced:true,highlighted_date:day};}
      if(name==='/api/capacity-report/details'&&url.searchParams.get('month')){
        const month=url.searchParams.get('month'),august=month==='2026-08';
        const daily=august?[{Date:'2026-08-20',Received:1,Completed:0}]:[{Date:'2026-09-25',Received:5,Completed:1},{Date:'2026-09-30',Received:1,Completed:0}];
        const date=url.searchParams.get('date')||daily[0].Date;
        const rows=august?fixture.rows.slice(0,1):date==='2026-09-25'?fixture.rows.slice(0,5):fixture.rows.slice(5,6);
        body={...body,date,month,month_label:august?'August 2026':'September 2026',daily,capacity_columns:capacityColumns,
          previous_date:null,next_date:date==='2026-09-25'?'2026-09-30':null,raw_received:rows.length,rollover_received:0,
          groups:[{key:'received',label:'Received',rows},{key:'changes',label:'Recorded changes',rows:changes}]};
      }
      if(name==='/api/order-details'){
        if(route.request().method()==='GET'){
          expect(url.searchParams.get('month')).toBe('');
          const row=fixture.rows.find(row=>row['Order Number']===url.searchParams.get('order')&&(!sameNumberAcrossFiles||row['Source workbook']===url.searchParams.get('source_workbook'))&&(!repeatedWithinFile||row._record_key===url.searchParams.get('record_key')));
          body={order:row,record_key:row._record_key,source_workbook:row['Source workbook']||'',editable_columns:['Status','Out Time','Client'],mode:'excel',month:'',version:'test-version'};
        }else{
          const saved=route.request().postDataJSON();writes.push(saved);
          if(rejectSave)return route.fulfill({status:409,json:{error:'This order changed since you opened it. Reopen the editor to review the latest values.'}});
          const row=fixture.rows.find(row=>row['Order Number']===saved.order_number&&(!sameNumberAcrossFiles||row['Source workbook']===saved.source_workbook)&&(!repeatedWithinFile||row._record_key===saved.record_key));
          for(const [column,value] of Object.entries(saved.changes)){
            changes.push({...row,Column:column,'Previous Value':row[column]||'','New Value':value,'Changed At':'2026-10-15T09:00:00Z'});
            row[column]=value;
          }
          body={updated:1,order_number:saved.order_number,publication:{queued:true}};
        }
      }
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('/');
  return {fixture,writes,errors};
}

test('capacity totals sum direct counts and dates open exact received, completed and status groups',async({page})=>{
  const {fixture,writes,errors}=await setup(page);
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await expect(page.getByText('Capacity Report uses imported Excel orders. Saturday and Sunday receipts and completions are included on the preceding Friday.',{exact:true})).toBeVisible();
  const dailyTotal=page.locator('.capacity-daily-total');
  await expect(dailyTotal.locator('td')).toHaveText(['Total','80','3','16','5','9','47','0','0']);
  await expect(page.locator('.capacity-total').first().locator('td')).toHaveText(['2026 YTD Total','87','3','16','5','9','47','0','0']);
  await page.screenshot({path:'test-results/capacity-direct-counts.png',fullPage:true});
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Capacity orders · 01-10-26'});
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Received: 65 orders on this reporting date.');
  await expect(dialog.getByRole('button',{name:/Carryover|next reporting date|Still incomplete/})).toHaveCount(0);
  await expect(dialog.locator('tbody tr')).toHaveCount(50);
  await dialog.getByRole('button',{name:'Next page',exact:true}).click();
  await expect(dialog.locator('tbody tr')).toHaveCount(15);
  await dialog.getByLabel('Search detail records').fill(fixture.rows[64]['Order Number']);
  await expect(dialog.locator('tbody tr')).toHaveCount(1);
  const downloaded=page.waitForEvent('download');
  await dialog.getByRole('button',{name:'Filtered CSV'}).click();
  expect((await downloaded).suggestedFilename()).toContain('filtered.csv');
  await dialog.getByRole('button',{name:'Completed 2',exact:true}).click();
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  await expect(dialog.getByLabel('Search detail records')).toHaveValue('');
  for(const [label,count] of [['Clarification',12],['Cancelled',3],['Vendor Pending',6],['In-House Pending',42]]){
    await dialog.getByRole('button',{name:`${label} ${count}`,exact:true}).click();
    await expect(dialog.locator('tbody tr')).toHaveCount(count);
  }
  await page.screenshot({path:'test-results/capacity-date-orders.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect(dialog).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/capacity-date-orders-mobile.png',fullPage:true});
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  expect(writes).toEqual([]);expect(errors).toEqual([]);
});

test('capacity numbers open their matching categories, including zero counts and targets',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  for(const [column,count,group,rows] of [['Received',65,'Received',65],['Completed',2,'Completed',2],['Clarification',12,'Clarification',12],['Cancelled',3,'Cancelled',3],['Vendor Pending',6,'Vendor Pending',6],['In-House Pending',42,'In-House Pending',42],['Capacity',0,'Received',65],['Ext capacity',0,'Received',65]]){
    await page.getByRole('button',{name:`01-10-26, ${column}: ${count}`,exact:true}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByRole('button',{name:`${group} ${rows}`,exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(dialog.locator('tbody tr')).toHaveCount(Math.min(rows,50));
    if(column.includes('capacity')||column==='Capacity')await expect(dialog).toContainText('The table shows received orders against this target.');
    await page.keyboard.press('Escape');
  }
  expect(errors).toEqual([]);
});

test('monthly, daily total and YTD numbers request aggregate records',async({page})=>{
  const {fixture,errors}=await setup(page),requests=[];
  await page.route('**/api/capacity-report/details?*',route=>{
    requests.push(new URL(route.request().url()).searchParams);
    return route.fulfill({json:{date:'',columns:fixture.columns,raw_received:80,mode:'excel',source:'Imported Excel',groups:[
      {key:'received',label:'Received',rows:fixture.rows}, {key:'completed',label:'Completed',rows:fixture.rows.slice(0,3)}]}});
  });
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  for(const label of ['Oct-26, Completed: 3','Total, Completed: 3','2026 YTD Total, Completed: 3']){
    await page.getByRole('button',{name:label,exact:true}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByRole('button',{name:'Completed 3',exact:true})).toHaveAttribute('aria-pressed','true');
    await expect(dialog.locator('.table-section tbody tr')).toHaveCount(3);
    await page.keyboard.press('Escape');
  }
  expect(requests.map(query=>query.get('aggregate'))).toEqual(['true','true','true']);
  expect(requests.map(query=>query.get('month')||query.get('year'))).toEqual(['2026-10','2026-10','2026']);
  expect(errors).toEqual([]);
});

test('monthly capacity opens daily dates and editable orders inside the same popup',async({page})=>{
  const {fixture,writes,errors}=await setup(page);
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await page.getByRole('button',{name:'Aug-26',exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'Capacity orders · August 2026'});
  await expect(dialog.getByRole('button',{name:'20-08-26',exact:true})).toHaveAttribute('aria-pressed','true');
  await expect(dialog.locator('.table-section tbody tr')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Sep-26',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'Capacity orders · September 2026'});
  await expect(dialog).toContainText('Saturday and Sunday receipts and completions are included on the preceding Friday.');
  await expect(dialog.locator('.capacity-month-days tbody tr')).toHaveCount(2);
  await expect(dialog.locator('.table-section tbody tr')).toHaveCount(5);
  await dialog.getByRole('button',{name:'30-09-26',exact:true}).click();
  await expect(dialog.getByRole('heading',{name:'Orders · 30-09-26',exact:true})).toBeVisible();
  await expect(dialog.getByRole('button',{name:'30-09-26',exact:true})).toBeFocused();
  await expect(dialog.locator('.table-section tbody tr')).toHaveCount(1);
  await dialog.getByRole('button',{name:`Edit order ${fixture.rows[5]['Order Number']}`,exact:true}).click();
  await dialog.getByLabel('Edit Client',{exact:true}).fill('Monthly correction');
  await dialog.getByRole('button',{name:'Save order changes',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('saved');
  await expect(dialog.getByRole('button',{name:'30-09-26',exact:true})).toHaveAttribute('aria-pressed','true');
  expect(writes[0]).toMatchObject({report_date:'2026-09-30',changes:{Client:'Monthly correction'}});
  await page.screenshot({path:'test-results/capacity-month-drilldown.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/capacity-month-drilldown-mobile.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('same order number from different workbooks stays separate and edits the selected copy',async({page})=>{
  const {fixture,writes,errors}=await setup(page,{sameNumberAcrossFiles:true});
  const firstClient=fixture.rows[0].Client;
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Search detail records').fill(fixture.rows[0]['Order Number']);
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  await dialog.locator('tbody tr').filter({hasText:'other.xlsx'}).getByRole('button',{name:/^Edit order/}).click();
  await expect(dialog).toContainText('Source workbook: other.xlsx');
  await expect(dialog.getByLabel('Edit Source workbook',{exact:true})).toHaveCount(0);
  await dialog.getByLabel('Edit Client',{exact:true}).fill('Selected workbook client');
  await dialog.getByRole('button',{name:'Save order changes',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('saved');
  expect(writes[0].source_workbook).toBe('other.xlsx');
  expect(fixture.rows[0].Client).toBe(firstClient);
  expect(fixture.rows[1].Client).toBe('Selected workbook client');
  expect(errors).toEqual([]);
});

test('repeated order numbers in one workbook remain visible and edit only the selected occurrence',async({page})=>{
  const {fixture,writes,errors}=await setup(page,{repeatedWithinFile:true});
  const original={...fixture.rows[0]};
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByLabel('Search detail records').fill(fixture.rows[0]['Order Number']);
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  await dialog.locator('tbody tr').filter({hasText:'TV Orders!3'}).getByRole('button',{name:/^Edit order/}).click();
  await expect(dialog.getByLabel('Edit Source row ID',{exact:true})).toHaveCount(0);
  await dialog.getByLabel('Edit Client',{exact:true}).fill('Selected occurrence client');
  await dialog.getByRole('button',{name:'Save order changes',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('saved');
  expect(writes[0].record_key).toBe(fixture.rows[1]._record_key);
  expect(fixture.rows[0]).toEqual(original);
  expect(fixture.rows[1].Client).toBe('Selected occurrence client');
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  expect(errors).toEqual([]);
});

test('capacity orders can edit status and completion date and show recorded field changes',async({page})=>{
  const {fixture,writes,errors}=await setup(page);
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await dialog.getByRole('button',{name:`Edit order ${fixture.rows[0]['Order Number']}`,exact:true}).click();
  await dialog.getByLabel('Edit Status',{exact:true}).fill('Completed and Delivered');
  await dialog.getByLabel('Edit Out Time',{exact:true}).fill('10/03/2026 01:00 PM');
  await dialog.getByRole('button',{name:'Save order changes',exact:true}).click();
  await expect(dialog.getByRole('status')).toContainText('saved. Google Sheets reports are updating');
  await dialog.getByRole('button',{name:'Recorded changes 2',exact:true}).click();
  await expect(dialog.locator('tbody tr')).toHaveCount(2);
  await expect(dialog.getByRole('cell',{name:'10/03/2026 01:00 PM',exact:true}).first()).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({mode:'excel',version:'test-version',report_date:'2026-10-01',changes:{Status:'Completed and Delivered','Out Time':'10/03/2026 01:00 PM'}});
  expect(errors).toEqual([]);
});

test('daily date opens the same detail table and stale edits keep their values for review',async({page})=>{
  const {fixture,errors}=await setup(page,{rejectSave:true});
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Daily orders · 01-10-26'});
  await expect(dialog.locator('tbody tr')).toHaveCount(50);
  await dialog.getByLabel('Search detail records').fill(fixture.rows[1]['Order Number']);
  await expect(dialog.locator('tbody tr')).toHaveCount(1);
  await dialog.getByRole('button',{name:`Edit order ${fixture.rows[1]['Order Number']}`,exact:true}).click();
  await dialog.getByLabel('Edit Client',{exact:true}).fill('Updated client');
  // The state poll observes report-date's new revision while the editor is open.
  await page.waitForTimeout(11000);
  await expect(dialog.getByLabel('Edit Client',{exact:true})).toHaveValue('Updated client');
  await dialog.getByRole('button',{name:'Save order changes',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('changed since you opened it');
  await expect(dialog.getByLabel('Edit Client',{exact:true})).toHaveValue('Updated client');
  await expect(dialog.getByRole('button',{name:'Save order changes'})).toBeEnabled();
  expect(errors).toEqual([]);
});

test('an outdated server explains the missing route and both dialogs recover after retry',async({page})=>{
  await setup(page,{legacyDetailsOnce:true});
  for(const view of ['Capacity Report','Daily Orders']){
    await page.getByRole('button',{name:view,exact:true}).click();
    await page.getByRole('button',{name:'01-10-26',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.getByRole('alert')).toContainText('server needs a restart');
    await dialog.getByRole('button',{name:'Retry details',exact:true}).click();
    await expect(dialog.locator('tbody tr')).toHaveCount(50);
    await expect(dialog.getByRole('alert')).toHaveCount(0);
    await page.keyboard.press('Escape');
  }
});

test('report cards and tables have clear typography and states in light, dark and mobile layouts',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  const metrics=page.locator('.daily-orders>.metrics');
  await expect(metrics.locator('button')).toHaveCount(8);
  expect(await metrics.evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length)).toBe(4);
  expect(await page.locator('.status-report-table td').first().evaluate(element=>getComputedStyle(element).fontFamily)).toContain('Segoe UI');
  await page.screenshot({path:'test-results/reports-refresh-light.png',fullPage:true});
  await page.getByLabel('Appearance',{exact:true}).selectOption('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.screenshot({path:'test-results/reports-refresh-dark.png',fullPage:true});
  const received=metrics.getByRole('button',{name:'Received 60',exact:true});
  await received.click();
  await expect(received).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('#daily-orders-group-0')).toBeFocused();
  await page.setViewportSize({width:390,height:844});
  expect(await metrics.evaluate(element=>getComputedStyle(element).gridTemplateColumns.split(' ').length)).toBe(2);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/reports-refresh-mobile.png',fullPage:true});
});
