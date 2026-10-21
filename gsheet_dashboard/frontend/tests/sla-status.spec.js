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

test('SLA status edit renames long labels and merges into an existing QC status',async({page})=>{
  const {sla,longStatus,saves,errors}=await setup(page,{editable:true});
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  const table=page.getByRole('table',{name:'SLA status summary'});
  await page.getByRole('button',{name:`Edit status ${longStatus}`,exact:true}).click();
  const form=page.getByRole('form',{name:'Edit order status'});
  await expect(form).toContainText('all 1 orders');
  await form.getByLabel('New order status',{exact:true}).fill('SearchFix');
  await form.getByRole('button',{name:'Save status',exact:true}).click();
  await expect(table.getByRole('button',{name:'SearchFix',exact:true})).toBeVisible();
  await expect(table.getByRole('button',{name:longStatus,exact:true})).toHaveCount(0);
  expect(saves[0].order_numbers).toEqual([sla.rows[2]['Order Number']]);
  await page.getByRole('button',{name:'Edit status Cancelled',exact:true}).click();
  await form.getByLabel('New order status',{exact:true}).fill('QC in Progress');
  await expect(page.locator('#sla-existing-statuses option[value="QC in Progress"]')).toHaveCount(1);
  await form.getByRole('button',{name:'Save status',exact:true}).click();
  await expect(table.getByRole('button',{name:'Cancelled',exact:true})).toHaveCount(0);
  await expect(table.getByRole('button',{name:'QC in Progress',exact:true})).toHaveCount(1);
  await expect(table.getByRole('button',{name:'QC in Progress, Grand Total: 2 orders',exact:true})).toBeVisible();
  await table.screenshot({path:'test-results/sla-status-edited-summary.png'});
  expect(errors).toEqual([]);
});

test('SLA editor keeps the edit open when the source statuses have changed',async({page})=>{
  await setup(page,{editable:true,failSave:true});
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await page.getByRole('button',{name:'Edit status Cancelled',exact:true}).click();
  const form=page.getByRole('form',{name:'Edit order status'});
  await form.getByLabel('New order status',{exact:true}).fill('QC in Progress');
  await form.getByRole('button',{name:'Save status',exact:true}).click();
  await expect(form.getByRole('alert')).toContainText('Refresh SLA Status');
  await expect(form.getByLabel('New order status',{exact:true})).toHaveValue('QC in Progress');
});

test('SLA editor changes only the chosen order number and retains its unselected peers',async({page})=>{
  const {sla,saves,errors}=await setup(page);
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await page.getByRole('button',{name:'Edit status Assign to ABS',exact:true}).click();
  const form=page.getByRole('form',{name:'Edit order status'});
  await form.getByLabel('Orders to update',{exact:true}).selectOption('orders');
  await form.getByLabel('New order status',{exact:true}).fill('Completed and Delivered');
  await expect(form.getByRole('button',{name:'Save status',exact:true})).toBeDisabled();
  const number=sla.rows[1]['Order Number'];
  await form.getByLabel('Find order number',{exact:true}).fill(number);
  await form.getByRole('checkbox',{name:`Select order ${number}`,exact:true}).check();
  await expect(form).toContainText('1 selected');
  await form.screenshot({path:'test-results/sla-selected-order-editor.png'});
  await form.getByRole('button',{name:'Save status',exact:true}).click();
  const table=page.getByRole('table',{name:'SLA status summary'});
  await expect(table.getByRole('button',{name:'Assign to ABS, Grand Total: 2 orders',exact:true})).toBeVisible();
  await expect(table.getByRole('button',{name:'Completed and Delivered, Grand Total: 1 orders',exact:true})).toBeVisible();
  expect(saves[0].order_numbers).toEqual([number]);
  expect(saves[0].edit_scope).toBe('orders');
  expect(errors).toEqual([]);
});

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

test('Every monthly metric shows matching order numbers and full details',async({page})=>{
  const {month,errors}=await setup(page);
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  for(const [name,count,ids] of [['Month Orders',6,month.rows.map(row=>row['Order Number'])],['Completed Orders',2,month.completed_ids],['Unchanged',3,month.unchanged_ids],['Awaiting for Clarification',1,[month.rows[2]['Order Number']]],['SLA On Time',1,[month.rows[0]['Order Number']]],['SLA Missed',1,[month.rows[5]['Order Number']]]]){
    await page.getByRole('button',{name:new RegExp(`^${name} ${count} `)}).click();
    const dialog=page.getByRole('dialog');
    await expect(dialog.locator('tbody tr')).toHaveCount(count);
    for(const id of ids)await expect(dialog.getByRole('cell',{name:id,exact:true})).toBeVisible();
    await page.keyboard.press('Escape');
  }
  expect(errors).toEqual([]);
});

test('SLA Status has the reference summary, chart, drill downs and Excel download',async({page})=>{
  const {sla,errors}=await setup(page);
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await expect(page.getByRole('table',{name:'SLA status summary'})).toBeVisible();
  await expect(page.getByRole('region',{name:'SLA status bar chart'})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status');
  await expect(page.getByText('TITLE PRODUCTION',{exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Assign to ABS, Negative SLA: 1 orders',exact:true}).click();
  await expect(page.getByRole('dialog').locator('tbody tr')).toHaveCount(1);
  await expect(page.getByRole('dialog')).toContainText(sla.rows[1]['Order Number']);
  await page.keyboard.press('Escape');
  await page.locator('.recharts-bar-rectangle').first().click();
  await expect(page.getByRole('dialog')).toContainText(sla.rows[0]['Order Number']);
  await expect(page.getByRole('dialog').locator('tbody tr')).toHaveCount(1);
  await page.keyboard.press('Escape');
  await page.getByRole('heading',{name:'SLA Status',exact:true}).first().click();
  await page.screenshot({path:'test-results/sla-status-workspace.png',fullPage:true,animations:'disabled'});
  await page.emulateMedia({colorScheme:'dark'});
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await expect(page.getByRole('button',{name:'Assign to ABS, Negative SLA: 1 orders',exact:true})).toHaveCSS('color','rgb(112, 222, 199)');
  await page.screenshot({path:'test-results/sla-status-workspace-dark.png',fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'1 orders have missing or invalid SLA expiration'}).click();
  await expect(page.getByRole('dialog')).toContainText('Invalid SLA expiration');
  expect(errors).toEqual([]);
});
