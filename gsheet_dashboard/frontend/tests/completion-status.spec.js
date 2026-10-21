import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

test('Daily Orders and Missing Previews show completed status, Out Time and completion color', async ({page}) => {
  const fixture=workspaceFixture(3),errors=[];
  fixture.rows[0].Status='Completed and Delivered';
  fixture.rows[0]['Out Time']='10/05/2026 10:00:00 AM';
  fixture.rows[2].Status='Completed and Delivered';
  fixture.rows[2]['Out Time']='10/05/2026 11:00:00 AM';
  const columns=[...fixture.columns,'Out Time'];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const name=new URL(route.request().url()).pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/daily-orders')body={mode:'tracker',source:'Google Sheets',selected_date:'2026-10-05',rows:[{
        Date:'2026-10-05',Received:3,Completed:2,Clarification:0,Cancelled:0,'Vendor Pending':0,'In-House Pending':1,
        'SLA OnTime':0,Missing:0,columns,rows:fixture.rows,sla_rows:[],Previews:[]}]};
      if(name==='/api/compare')body={previous:'preview31',latest:'preview32',method:'Matched by Order Number',
        record_columns:[...new Set(['Comparison Status','Order Number','Status','Out Time',...columns])],matched_rows:[],
        unmatched_rows:[{...fixture.rows[2],'Comparison Status':'Missing'}],
        record_counts:{matched:0,missing:1,newly_added:0,unchanged:0},added_columns:[],removed_columns:[]};
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://127.0.0.1:8534/');
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  const completed=page.locator('#daily-orders-group-1');
  await expect(completed.getByRole('heading',{name:'Completed · 2',exact:true})).toBeVisible();
  await expect(completed.getByRole('cell',{name:'Completed and Delivered',exact:true})).toHaveCount(2);
  await expect(completed.getByRole('cell',{name:'10/05/2026 10:00:00 AM',exact:true})).toBeVisible();
  for(const theme of ['light','dark']){
    await page.getByLabel('Appearance',{exact:true}).selectOption(theme);
    await expect(completed.locator('tbody tr').first().locator('td').first()).toHaveCSS('background-color','rgb(255, 255, 153)');
  }
  await completed.scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/completed-daily-orders.png',animations:'disabled'});
  await page.getByRole('button',{name:'Changes',exact:true}).click();
  await page.getByRole('button',{name:'Missing Previews 1',exact:true}).click();
  const missing=page.locator('#changes-orders-group-missing');
  await expect(missing.getByRole('cell',{name:'Completed and Delivered',exact:true})).toBeVisible();
  await expect(missing.getByRole('cell',{name:'10/05/2026 11:00:00 AM',exact:true})).toBeVisible();
  await expect(missing.locator('tbody tr td').first()).toHaveCSS('background-color','rgb(255, 255, 153)');
  await missing.scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/completed-missing-previews.png',animations:'disabled'});
  expect(errors).toEqual([]);
});
