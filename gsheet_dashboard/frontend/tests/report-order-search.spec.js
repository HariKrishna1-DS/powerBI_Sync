import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

test('SLA and Capacity search find order status, include excluded orders and handle no matches',async({page})=>{
  const fixture=workspaceFixture(3),errors=[];
  const rows=[{...fixture.rows[0],Status:'Completed and Delivered','Out Time':'10/13/2026 03:00 PM','SLA Category':'Future SLA'},
    {...fixture.rows[1],Status:'Assign to ABS','SLA Category':'Today SLA'},
    {...fixture.rows[2],Status:'QC in Progress','SLA issue':'Missing SLA expiration'}];
  const settings={mode:'excel',row_count:3,files:[],publication_state:'synced'};
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,mode:'excel'};
      if(name==='/api/sla-status')body={as_of:'2026-10-13',source:'Imported Excel',columns:[...fixture.columns,'Out Time','SLA Category'],
        rows:rows.slice(0,2),excluded_rows:[rows[2]],excluded_count:1,
        summary_columns:['Status','Future SLA','Negative SLA','Today SLA','Grand Total'],
        summary:[{Status:'Completed and Delivered','Future SLA':1,'Negative SLA':0,'Today SLA':0,'Grand Total':1}],
        totals:{Status:'Grand Total','Future SLA':1,'Negative SLA':0,'Today SLA':1,'Grand Total':2}};
      if(name==='/api/capacity-report')body={columns:['Date','Received','Completed','Capacity','Ext capacity'],
        monthly:[{Date:'2026-10',Received:3,Completed:1}],daily:[{Date:'2026-10-13',Received:3,Completed:1}],
        month:'2026-10',scope_label:'October 2026',capacity:700,extended_capacity:750,source:'Imported Excel'};
      if(name==='/api/report-order-search'){
        const query=url.searchParams.get('search');
        const exact=rows.filter(row=>row['Order Number'].toLowerCase()===query);
        const matches=exact.length?exact:rows.filter(row=>row['Order Number'].toLowerCase().includes(query));
        body={rows:matches,columns:[...fixture.columns,'Out Time'],total:matches.length};
      }
      return route.fulfill({json:body});
    }
    try{return route.fulfill({body:await readFile(path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1))),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('/');
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  const slaSearch=page.getByRole('region',{name:'SLA Status order search'});
  await page.getByLabel('Search SLA Status orders',{exact:true}).fill('tv-62000');
  await expect(slaSearch.getByRole('cell',{name:'Completed and Delivered',exact:true})).toBeVisible();
  await page.getByLabel('Search SLA Status orders',{exact:true}).fill('62002');
  await expect(slaSearch.getByRole('cell',{name:'QC in Progress',exact:true})).toBeVisible();
  await page.getByLabel('Search SLA Status orders',{exact:true}).fill('unknown');
  await expect(slaSearch.getByText('No orders match this order number.')).toBeVisible();
  await page.getByLabel('Search SLA Status orders',{exact:true}).fill('62000');
  await slaSearch.scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/sla-order-search.png',animations:'disabled'});
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  const capSearch=page.getByRole('region',{name:'Capacity Report order search'});
  await page.getByLabel('Search Capacity Report orders',{exact:true}).fill('62000');
  await expect(capSearch.getByRole('cell',{name:'Completed and Delivered',exact:true})).toBeVisible();
  await expect(capSearch.getByRole('cell',{name:'10/13/2026 03:00 PM',exact:true})).toBeVisible();
  await page.getByLabel('Search Capacity Report orders',{exact:true}).fill('unknown');
  await expect(capSearch.getByText('No orders match this order number.')).toBeVisible();
  await page.getByLabel('Search Capacity Report orders',{exact:true}).fill('TV-62000');
  await expect(capSearch.getByRole('cell',{name:'Completed and Delivered',exact:true})).toBeVisible();
  await capSearch.scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/capacity-order-search.png',animations:'disabled'});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});
