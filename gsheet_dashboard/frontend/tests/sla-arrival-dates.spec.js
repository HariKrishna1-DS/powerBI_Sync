import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page,{failDate=false}={}){
  const fixture=workspaceFixture(3),errors=[],saves=[],dates=[];
  const settings={mode:'excel',files:[{file:'full.xlsx',sheet:'Orders',rows:3}],row_count:3,publication_state:'synced'};
  let selected='2026-10-13';
  const records=[
    {'Order Number':'LATEST-001',Status:'Search In Progress','Arrival Date':'2026-10-13','Arrival Time':'10/13/2026 01:02:03 PM','SLA Category':'Future SLA','SLA Expiration':'2026-10-14'},
    {'Order Number':'LATEST-002',Status:'Search In Progress','Arrival Date':'2026-10-13','Arrival Time':'10/13/2026 09:05 AM','SLA Category':'Today SLA','SLA Expiration':'2026-10-13'},
    {'Order Number':'EARLIER-001',Status:'Search In Progress','Arrival Date':'2026-10-12','Arrival Time':'10/12/2026 08:10 AM','SLA Category':'Today SLA','SLA Expiration':'2026-10-12'},
  ];
  function report(){
    const rows=records.filter(row=>row['Arrival Date']===selected),categories=['Future SLA','Negative SLA','Today SLA'];
    const counts=rows=>Object.fromEntries(categories.map(category=>[category,rows.filter(row=>row['SLA Category']===category).length]));
    return {as_of:selected,mode:'excel',source:'Imported Excel',report_scope:'imported_date',report_date:selected,
      report_dates:[{date:'2026-10-13',orders:2},{date:'2026-10-12',orders:1}],imported_order_count:3,date_order_count:rows.length,undated_order_count:0,
      columns:['Order Number','Status','SLA Expiration','Arrival Date','Arrival Time'],rows,excluded_rows:[],excluded_count:0,
      summary_columns:['Status',...categories,'Grand Total'],
      summary:[...new Set(rows.map(row=>row.Status))].map(Status=>({Status,...counts(rows.filter(row=>row.Status===Status)),'Grand Total':rows.filter(row=>row.Status===Status).length})),
      totals:{Status:'Grand Total',...counts(rows),'Grand Total':rows.length}};
  }
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,mode:'excel',source:'Imported Excel'};
      if(name==='/api/sla-status')body=report();
      if(name==='/api/sla-report-date'){
        const change=route.request().postDataJSON();dates.push(change.date);
        if(failDate)return route.fulfill({status:400,json:{error:'That date is no longer in the imported report.'}});
        selected=change.date;body={...report(),publication:{synced:true}};
      }
      if(name==='/api/order-status'){
        const change=route.request().postDataJSON();saves.push(change);
        records.forEach(row=>{if(change.order_numbers.includes(row['Order Number'])&&row['Arrival Date']===change.sla_report_date)row.Status=change.replacement;});
        body={updated:change.order_numbers.length,status:change.replacement,publication:{queued:true}};
      }
      return route.fulfill({json:body});
    }
    try{return route.fulfill({body:await readFile(path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1))),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('/');
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  return {errors,records,saves,dates};
}

test('latest imported date has matching totals, download date and arrival fields in table and CSV',async({page})=>{
  const {errors}=await setup(page);
  await expect(page.getByRole('combobox',{name:'SLA report date'})).toHaveValue('2026-10-13');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status&date=2026-10-13');
  await expect(page.getByText('2 orders received on 2026-10-13 out of 3 imported orders.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Grand Total 2',exact:true}).click();
  const dialog=page.getByRole('dialog');
  const headers=dialog.locator('thead th');
  expect((await headers.allTextContents()).slice(0,5).map(value=>value.trim())).toEqual(['Order Number','Status','SLA Category','Arrival Date','Arrival Time']);
  await expect(dialog.getByRole('cell',{name:'10/13/2026 01:02:03 PM',exact:true})).toBeVisible();
  await dialog.getByLabel('Search detail records').fill('LATEST-001');
  const downloaded=page.waitForEvent('download');
  await dialog.getByRole('button',{name:'Filtered CSV'}).click();
  const csv=await readFile(await (await downloaded).path(),'utf8');
  expect(csv).toContain('Arrival Date');expect(csv).toContain('Arrival Time');expect(csv).toContain('10/13/2026 01:02:03 PM');
  expect(csv).not.toContain('LATEST-002');
  await dialog.screenshot({path:'test-results/sla-arrival-details.png'});
  expect(errors).toEqual([]);
});

test('earlier date changes report, download and status edit scope together',async({page})=>{
  const {errors,saves,records,dates}=await setup(page);
  await page.getByRole('combobox',{name:'SLA report date'}).selectOption('2026-10-12');
  await expect(page.getByRole('button',{name:'Grand Total 1',exact:true})).toBeVisible();
  await expect(page.getByRole('combobox',{name:'SLA report date'})).toHaveValue('2026-10-12');
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status&date=2026-10-12');
  await expect(page.getByText('Today SLA: due on 2026-10-12.',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Edit status Search In Progress',exact:true}).click();
  const form=page.getByRole('form',{name:'Edit order status'});
  await expect(form).toContainText('all 1 orders');
  await form.getByLabel('New order status',{exact:true}).fill('QC in Progress');
  await form.getByRole('button',{name:'Save status',exact:true}).click();
  await expect(page.getByRole('table',{name:'SLA status summary'}).getByRole('button',{name:'QC in Progress',exact:true})).toBeVisible();
  expect(saves[0].sla_report_date).toBe('2026-10-12');expect(saves[0].order_numbers).toEqual(['EARLIER-001']);
  expect(records[0].Status).toBe('Search In Progress');expect(dates).toEqual(['2026-10-12']);
  await page.locator('.sla-status-workspace').screenshot({path:'test-results/sla-import-earlier-date.png'});
  expect(errors).toEqual([]);
});

test('a rejected date selection retains the last valid report and download',async({page})=>{
  await setup(page,{failDate:true});
  await page.getByRole('combobox',{name:'SLA report date'}).selectOption('2026-10-12');
  await expect(page.getByRole('alert')).toContainText('That date is no longer');
  await expect(page.getByRole('combobox',{name:'SLA report date'})).toHaveValue('2026-10-13');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status&date=2026-10-13');
});
