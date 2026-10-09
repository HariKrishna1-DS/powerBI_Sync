import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

test('Overview duplicate count opens all repeated orders and their source files',async({page})=>{
  const fixture=workspaceFixture(10),errors=[];
  const duplicates=fixture.rows.slice(0,6).map(row=>({...row,Date:'2026-10-05',
    'Earlier file':'full.xlsx','Earlier worksheet':'TV Orders',
    'Replacement file':'remaining.xlsx','Replacement worksheet':'Updates'}));
  const settings={mode:'excel',row_count:10,files:[],duplicate_row_count:6,duplicate_orders:duplicates};
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const name=new URL(route.request().url()).pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/live-sheets')body={...body,mode:'excel',source:'Imported Excel'};
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    const contentType=name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html';
    try{return route.fulfill({body:await readFile(filename),contentType});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByText('Filter insights',{exact:true})).toBeVisible();
  await expect(page.locator('details.status-report.analytics-status')).toHaveAttribute('open','');
  await expect(page.locator('details.advanced-chart')).toHaveAttribute('open','');
  const metric=page.getByRole('button',{name:'Duplicate Orders 6',exact:true});
  await expect(metric).toBeVisible();
  await expect(page.getByText('Imported files',{exact:true})).toHaveCount(0);
  await metric.click();
  const dialog=page.getByRole('dialog');
  await expect(dialog).toContainText('Duplicate orders · 6');
  await expect(dialog.locator('tbody tr')).toHaveCount(6);
  for(const row of duplicates)await expect(dialog.getByRole('cell',{name:row['Order Number'],exact:true})).toBeVisible();
  await expect(dialog).toContainText('full.xlsx');
  await expect(dialog).toContainText('remaining.xlsx');
  await page.screenshot({path:'test-results/duplicate-orders-dialog.png',fullPage:true});
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(metric).toBeFocused();
  expect(errors).toEqual([]);
});

test('batch report import, source switching, daily publication and capacity view',async({page})=>{
  const fixture=workspaceFixture(10),errors=[],requests=[];
  let mode='tracker',selected='2026-10-02';
  const columns=['Date','Received','Completed','Clarification','Cancelled','Vendor Pending','In-House Pending','Capacity','Ext capacity'];
  const days=['2026-10-02','2026-10-01'].map(Date=>({Date,Received:10,Completed:2,Clarification:1,Cancelled:1,'Vendor Pending':2,'In-House Pending':4,'SLA OnTime':1,Missing:1,Capacity:700,'Ext capacity':750,columns:fixture.columns,rows:fixture.rows,sla_rows:[],Previews:[]}));
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      const settings={mode,row_count:mode==='excel'?10:0,files:[],enabled:true};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/state')body={...body,report_workspace:settings};
      if(name==='/api/live-sheets')body={...body,mode,source:mode==='excel'?'Imported Excel':'Google Sheets'};
      if(name==='/api/report-source'){mode=route.request().postDataJSON().mode;requests.push(mode);body={mode,publication:{synced:true}};}
      if(name==='/api/report-import'){
        const data=route.request().postData();
        expect(data).toContain('one.csv');expect(data).toContain('two.csv');
        mode='excel';body={mode,row_count:10,publication:{synced:true}};
      }
      if(name==='/api/daily-orders')body={rows:days,selected_date:selected,source:mode==='excel'?'Imported Excel':'Google Sheets'};
      if(name==='/api/report-date'){selected=route.request().postDataJSON().date;requests.push(selected);body={date:selected,synced:true};}
      if(name==='/api/capacity-report')body={columns,monthly:[{...days[0],Date:'2026-10',Capacity:1400,'Ext capacity':1500}],daily:days,month:'2026-10',capacity:700,extended_capacity:750,source:mode==='excel'?'Imported Excel':'Google Sheets'};
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    const contentType=name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html';
    try{return route.fulfill({body:await readFile(filename),contentType});}catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  await page.getByRole('button',{name:'Import files',exact:true}).click();
  await page.getByLabel('Excel or CSV files').setInputFiles([
    {name:'one.csv',mimeType:'text/csv',buffer:Buffer.from('Order Number,Status,Product\n1,Cancelled,Update')},
    {name:'two.csv',mimeType:'text/csv',buffer:Buffer.from('Order Number,Status,Product\n2,Assign to ABS,Full Search')}
  ]);
  await page.getByRole('button',{name:'Import and update reports'}).click();
  await expect(page.getByText('Reports saved and Google Sheets updated.',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Import Excel report',exact:true})).toHaveAttribute('aria-pressed','true');
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'Vendor Pending',exact:true})).toBeVisible();
  await expect(page.getByRole('option',{name:'01-10-26',exact:true})).toHaveAttribute('value','2026-10-01');
  await page.getByRole('button',{name:'01-10-26',exact:true}).click();
  await expect(page.getByText('01-10-26 is highlighted in Daily Status Report and filtered in All Products.')).toBeVisible();
  await page.getByRole('button',{name:'Received 10',exact:true}).click();
  await expect(page.locator('#daily-orders-group-0')).toBeFocused();
  await page.getByRole('button',{name:'Completed 2',exact:true}).click();
  await expect(page.locator('#daily-orders-group-1')).toBeFocused();
  await page.getByRole('button',{name:'Capacity Report',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Daily capacity',exact:true})).toBeVisible({timeout:15000});
  await page.screenshot({path:'test-results/pdf-capacity-report.png',fullPage:true});
  await page.getByRole('button',{name:'Tracker report',exact:true}).click();
  await expect(page.getByRole('button',{name:'Tracker report',exact:true})).toHaveAttribute('aria-pressed','true');
  expect(requests).toContain('2026-10-01');expect(requests).toContain('tracker');
  expect(errors).toEqual([]);
});
