import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

test('source switches replace every report dataset and tracker labels show saved captures',async({page})=>{
  const fixture=workspaceFixture(8), errors=[];
  let mode='tracker';
  const selectedRows=()=>fixture.rows.slice(0,mode==='tracker'?3:7);
  const workspace=()=>({mode,data_revision:`${mode}-source`,enabled:false,publication_state:'synced',
    files:[],imports:[],row_count:7,duplicate_row_count:4,source_overlap_count:613});
  page.on('pageerror',error=>{errors.push(error.message);console.error(error.message);});
  await page.route('**/*',async route=>{
    const name=new URL(route.request().url()).pathname;
    if(!name.startsWith('/api/')){
      const filename=path.join(import.meta.dirname,'../dist',name==='/'?'index.html':name.slice(1));
      try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
      catch{return route.fulfill({status:404,body:''});}
    }
    if(name==='/api/report-source')mode=route.request().postDataJSON().mode;
    const rows=selectedRows(), settings=workspace();
    let body=fixture.response(name);
    if(name==='/api/state')body={...body,report_workspace:settings};
    if(['/api/report-workspace','/api/report-source'].includes(name))body={...settings,publication:{synced:true}};
    if(name==='/api/live-sheets')body={...body,mode,source:mode==='tracker'?'Saved previews':'Imported Excel',
      data_revision:settings.data_revision,report_origin:mode==='tracker'?'previews':'excel',preview_count:2,preview_name:'preview32',
      sheets:{Overview:{columns:fixture.columns,rows},'Full Title':{columns:fixture.columns,rows},'Remaining Products':{columns:fixture.columns,rows:[]}}};
    if(name==='/api/daily-orders')body={...body,mode,rows:body.rows.map(day=>({...day,rows,'Today Orders':rows.length}))};
    if(name==='/api/monthly-orders')body={...body,mode,rows:body.rows.map(month=>({...month,rows,'Month Orders':rows.length}))};
    return route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  const context=page.getByLabel('Workspace context');
  await expect(context).toContainText('Saved previews');
  await expect(page.getByRole('button',{name:/Preview orders/})).toContainText('3');
  await expect(page.getByRole('button',{name:/Saved captures/})).toContainText('2');
  await expect(page.getByRole('button',{name:/Duplicate Orders/})).toHaveCount(0);
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.getByRole('button',{name:/All Products/})).toContainText('3');
  await page.getByRole('button',{name:'Import Excel report',exact:true}).click();
  await expect(context).toContainText('Imported Excel');
  await expect(page.getByRole('button',{name:/All Products/})).toContainText('7');
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('button',{name:/Imported orders/}).first()).toContainText('7');
  await expect(page.getByRole('button',{name:'Duplicate Orders 4',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Tracker report',exact:true}).click();
  await expect(page.getByRole('button',{name:/Preview orders/})).toContainText('3');
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await expect(context).toContainText('Saved previews');
  await expect(page.getByRole('heading',{name:'Daily production orders',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Monthly Orders',exact:true}).click();
  await expect(context).toContainText('Saved previews');
  expect(errors).toEqual([]);
});
