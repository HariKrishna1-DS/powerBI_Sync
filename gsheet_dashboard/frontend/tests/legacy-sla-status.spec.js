import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page,{editable=false,failSave=false}={}){
  const fixture=workspaceFixture(10);
  fixture.columns.push('Typer','SLA Expiration','Arrival Date');
  fixture.rows.forEach((row,index)=>{row.Typer=`Typer ${index}`;row['SLA Expiration']='2026-10-14 16:00:00';});
  const files=[{file:'full.xlsx',sheet:'Orders',rows:6},{file:'remaining.xlsx',sheet:'Orders',rows:4}];
  const settings={mode:'excel',files,row_count:10,publication_state:'synced'};
  const monthlyRows=fixture.rows.slice(0,6);
  monthlyRows[0].Status=monthlyRows[5].Status='Completed and Delivered';
  const month={Month:'2026-10',MonthLabel:'2026-10',Previews:[],columns:fixture.columns,rows:monthlyRows,
    'Month Orders':6,'Completed Orders':2,Unchanged:3,'Awaiting for Clarification':1,
    'SLA On Time':1,'SLA Missed':1,completed_ids:[monthlyRows[0]['Order Number'],monthlyRows[5]['Order Number']],
    unchanged_ids:monthlyRows.slice(1,4).map(row=>row['Order Number']),
    sla_rows:[{...monthlyRows[0],'Free Site':'On Time'},{...monthlyRows[5],'Free Site':'Missing'}]};
  const sla={as_of:'2026-10-14',source:'Imported Excel',summary_columns:['Status','Future SLA','Negative SLA','Today SLA','Grand Total'],
    columns:[...fixture.columns,'SLA Category'],rows:fixture.rows.slice(0,3).map((row,index)=>({...row,Status:'Assign to ABS','SLA Category':['Future SLA','Negative SLA','Today SLA'][index]})),
    excluded_count:1,excluded_rows:[{...fixture.rows[3],'SLA issue':'Invalid SLA expiration'}],
    summary:[{Status:'Assign to ABS','Future SLA':1,'Negative SLA':1,'Today SLA':1,'Grand Total':3}],
    totals:{Status:'Grand Total','Future SLA':1,'Negative SLA':1,'Today SLA':1,'Grand Total':3}};
  const longStatus='Need to request Judgement WALKER PATRICK JUD 05/06/2010 NL1529-063 JUD 12/03/2022 C-16-JG-22-006254';
  function rebuild(){
    sla.summary=[...new Set(sla.rows.map(row=>row.Status))].map(Status=>({Status,
      ...Object.fromEntries(['Future SLA','Negative SLA','Today SLA'].map(category=>[category,sla.rows.filter(row=>row.Status===Status&&row['SLA Category']===category).length])),
      'Grand Total':sla.rows.filter(row=>row.Status===Status).length}));
  }
  if(editable){sla.rows.forEach((row,index)=>row.Status=['Cancelled','QC in Progress',longStatus][index]);rebuild();}
  const saves=[];
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const name=new URL(route.request().url()).pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,mode:'excel',source:'Imported Excel'};
      if(name==='/api/monthly-orders')body={rows:[month],source:'Imported Excel',mode:'excel',statuses:[]};
      if(name==='/api/sla-status')body=sla;
      if(name==='/api/order-status'){
        const change=route.request().postDataJSON();saves.push(change);
        if(failSave)return route.fulfill({status:409,json:{error:'Orders in this status changed. Refresh SLA Status and try again.'}});
        const status=change.replacement.toLowerCase()==='qc in progress'?'QC in Progress':change.replacement;
        sla.rows.forEach(row=>{if(change.order_numbers.includes(row['Order Number']))row.Status=status;});rebuild();
        body={updated:change.order_numbers.length,status,publication:{queued:true}};
      }
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  return {fixture,month,sla,errors,longStatus,saves};
}

test('custom chart starts with Status and allows manual grouping changes',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  const chart=page.locator('details.advanced-chart');
  await expect(chart.getByRole('combobox',{name:'Group by',exact:true})).toHaveValue('Status');
  await expect(chart.getByRole('heading',{name:'Orders by Status',exact:true})).toBeVisible();
  await chart.getByRole('combobox',{name:'Group by',exact:true}).selectOption('Client');
  await expect(chart.getByRole('heading',{name:'Orders by Client',exact:true})).toBeVisible();
  await chart.getByRole('combobox',{name:'Group by',exact:true}).selectOption('Arrival Date');
  await expect(chart.getByRole('heading',{name:'Orders by Arrival Date',exact:true})).toBeVisible();
  await chart.getByRole('combobox',{name:'Group by',exact:true}).selectOption('Status');
  await expect(chart.getByRole('heading',{name:'Orders by Status',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('Overview and Data Sheets counts open the exact records and worksheet metadata',async({page})=>{
  const {fixture,errors}=await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByText('TITLE PRODUCTION',{exact:true})).toHaveCount(0);
  const attention=fixture.rows.filter(row=>/clarification|hold|suspend|review|missing|rejected/i.test(row.Status));
  for(const [name,count] of [['Imported orders',10],['Need attention',attention.length],['Imported worksheets',2]]){
    await page.getByRole('button',{name:`${name} ${count}`,exact:true}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.locator('tbody tr')).toHaveCount(count);
    if(name==='Imported worksheets')await expect(dialog).toContainText('remaining.xlsx');
    else await expect(dialog.getByRole('columnheader',{name:'Typer Sort Typer'})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await page.getByRole('button',{name:/C-O & Update file \d/}).click();
  await page.getByLabel('Search rows',{exact:true}).fill('TV-62002');
  await page.getByRole('button',{name:'Visible orders 1',exact:true}).click();
  await expect(page.getByRole('dialog').locator('tbody tr')).toHaveCount(1);
  await expect(page.getByRole('dialog').getByRole('cell',{name:'TV-62002',exact:true})).toBeVisible();
  await expect(page.getByText('TITLE PRODUCTION',{exact:true})).toHaveCount(0);
  expect(errors).toEqual([]);
});
