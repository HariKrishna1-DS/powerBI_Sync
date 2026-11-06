import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page){
  const fixture=workspaceFixture(240),errors=[];
  fixture.columns.push('Task Status','ETA Comments');
  fixture.rows.forEach((row,index)=>{row['Task Status']=index%2?'Available':'Workflow Suspended';row['ETA Comments']=index%2?'ON HOLD':'Ready';});
  fixture.rows[0].Client=fixture.rows[239].Client='';
  const summary=[{Status:'Attorney Approval','Future SLA':5,'Negative SLA':0,'Today SLA':1,'Grand Total':6},
    {Status:'Search In Progress','Future SLA':200,'Negative SLA':21,'Today SLA':13,'Grand Total':234}];
  const sla={preview_id:32,preview_name:'preview32',preview_row_count:240,report_scope:'preview',previews:fixture.previews,
    previous_preview_name:'preview31',captured_order_count:240,missing_order_count:0,as_of:'2026-10-19',columns:fixture.columns,
    rows:fixture.rows,excluded_rows:[],excluded_count:0,summary,summary_columns:['Status','Future SLA','Negative SLA','Today SLA','Grand Total'],
    totals:{Status:'Grand Total','Future SLA':205,'Negative SLA':21,'Today SLA':14,'Grand Total':240}};
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/'))return route.fulfill({json:name==='/api/sla-status'?sla:fixture.response(name)});
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  return {fixture,errors};
}

async function openFilter(scope,page,column){
  await scope.getByRole('button',{name:`Filter column ${column}`,exact:true}).click();
  const menu=page.getByRole('dialog',{name:`${column} filter`,exact:true});
  await expect(menu).toBeVisible();return menu;
}

test('detail dialogs filter beyond the first page, preserve the dialog on Escape and export exact matches',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:'Production orders 240',exact:true}).click();
  const detail=page.getByRole('dialog',{name:'Production orders',exact:true});
  let menu=await openFilter(detail,page,'Task Status');
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);await expect(detail).toBeVisible();
  menu=await openFilter(detail,page,'Order Number');
  await menu.getByLabel('Search filter values').fill('TV-62239');
  await menu.screenshot({path:'test-results/detail-column-filter.png'});
  await menu.getByRole('button',{name:'Apply',exact:true}).click();
  await expect(detail.locator('tbody tr')).toHaveCount(1);
  await expect(detail).toContainText('TV-62239');
  const download=page.waitForEvent('download');
  await detail.getByRole('button',{name:'Filtered CSV',exact:true}).click();
  const csv=await readFile(await (await download).path(),'utf8');
  expect(csv).toContain('TV-62239');expect(csv).not.toContain('TV-62000');
  await detail.getByRole('button',{name:'Clear table filters',exact:true}).click();
  await expect(detail.locator('tbody tr')).toHaveCount(50);
  expect(errors).toEqual([]);
});

test('blank and text conditions work in popup tables with Apply and Clear',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:'Production orders 240',exact:true}).click();
  const detail=page.getByRole('dialog',{name:'Production orders',exact:true});
  let menu=await openFilter(detail,page,'Client');
  await expect(menu.getByRole('checkbox',{name:'(Blanks)',exact:true})).toBeVisible();
  await menu.getByLabel('Filter condition').selectOption('blank');
  await menu.getByRole('button',{name:'Apply',exact:true}).click();
  await expect(detail.locator('tbody tr')).toHaveCount(2);
  menu=await openFilter(detail,page,'Client');
  await menu.getByRole('button',{name:'Clear filter',exact:true}).click();
  menu=await openFilter(detail,page,'ETA Comments');
  await menu.getByLabel('Filter condition').selectOption('contains');
  await menu.getByLabel('Condition value').fill('on hold');
  await menu.getByRole('button',{name:'Apply',exact:true}).click();
  await expect(detail).toContainText('120 of 240 rows');
  await expect(detail.locator('tbody tr')).toHaveCount(50);
  expect(errors).toEqual([]);
});
