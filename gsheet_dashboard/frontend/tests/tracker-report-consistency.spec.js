import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function reports(page){
  const fixture=workspaceFixture(5),syncs=[];
  const statuses=[' COMPLETED  AND DELIVERED ','','Canceled',' Assign  to ABS ','Search In Progress'];
  fixture.rows.forEach((row,index)=>{row.Status=statuses[index];row['In-Time']='10/22/2026 09:00 AM';});
  fixture.rows[0]['Order Number']='MiXeD-1';
  fixture.rows[1]['Task Status']=' Awaiting   for Clarification ';
  fixture.previews.forEach(preview=>preview.row_count=5);
  const settings={mode:'tracker',duplicate_row_count:12,source_overlap_count:2,files:[]};
  const counts={Received:5,Completed:1,Clarification:1,Cancelled:1,'Vendor Pending':1,'In-House Pending':1,'SLA OnTime':0,Missing:0};
  const day={Date:'2026-10-22',...counts,rows:fixture.rows,columns:fixture.columns,sla_rows:[],Previews:['preview32']};
  const month={...fixture.report,...counts,'Month Orders':5,'Completed Orders':1,'Awaiting for Clarification':1,
    'SLA On Time':0,'SLA Missed':0,completed_ids:['MiXeD-1'],completed_keys:['mixed-1'],sla_rows:[]};
  const capacityColumns=['Date','Received','Completed','Clarification','Cancelled','Vendor Pending','In-House Pending','Capacity','Ext capacity'];
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings,pending_sync:2};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,source:'Google Sheets',pending_sync:2};
      if(name==='/api/daily-orders')body={rows:[day],selected_date:day.Date,source:'Google Sheets',mode:'tracker'};
      if(name==='/api/monthly-orders')body={rows:[month],source:'Google Sheets',mode:'tracker'};
      if(name==='/api/capacity-report')body={columns:capacityColumns,monthly:[{Date:'2026-10',Received:2,Completed:1,Capacity:700,'Ext capacity':750}],
        daily:[{Date:'2026-10-22',Received:2,Completed:1,Capacity:700,'Ext capacity':750}],month:'2026-10',scope_label:'October 2026',capacity:700,extended_capacity:750,mode:'excel',source:'Imported Excel'};
      if(name==='/api/sync'){syncs.push(route.request().postDataJSON());body={started:true};}
      return route.fulfill({json:body});
    }
    const file=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  return {fixture,syncs};
}

test('Daily and monthly use tracker statuses while capacity shows its independent Excel source',async({page})=>{
  await reports(page);
  await page.goto('/');
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await expect(page.getByText('Daily Orders and Monthly Orders are available in Import Excel report.',{exact:false})).toBeVisible();
  await expect(page.getByLabel('Daily orders date')).toHaveCount(0);
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  await expect(page.getByText('Daily Orders and Monthly Orders are available in Import Excel report.',{exact:false})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Completed Orders · 1',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Daily capacity',exact:true})).toBeVisible();
  await expect(page.locator('.page-heading .muted')).toHaveText('Imported Excel orders');
  await expect(page.locator('.workspace-context .context-preview')).toHaveText('Excel report');
  const daily=page.locator('section.table-section').filter({has:page.getByRole('heading',{name:'Daily capacity',exact:true})});
  const values=await daily.locator('tbody tr').first().locator('td').allTextContents();
  expect(values).toEqual(['22-10-26','2','1','0','0','0','0','700','750']);
  await expect(page.getByText('Imported Excel Â· October 2026',{exact:true})).toBeVisible();
  await expect(page.getByText('Tracker reports are waiting for 2 saved captures to sync.',{exact:true})).toHaveCount(0);
  await page.screenshot({path:'test-results/tracker-report-capacity.png',fullPage:true});
});
