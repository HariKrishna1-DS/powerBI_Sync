import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page,{empty=false,comparison=false}={}){
  const fixture=workspaceFixture(35);
  const previews=empty?[]:[3,2,1].map((id,index)=>({id,name:`preview${id}`,row_count:[3,4,2][index],created:`2026-10-${16-index}T04:00:00Z`}));
  let selected=3,mode='tracker';
  const publications=[],refreshes=[];
  const columns=['Order Number','Status','Product','SLA Expiration','SLA Category'];
  function report(id){
    const preview=previews.find(p=>p.id===id);
    const count=mode==='excel'?1:preview?.row_count||0;
    const rows=Array.from({length:count},(_,i)=>({'Order Number':`${mode==='excel'?'import':`preview${id}`}-${i}`,
      Status:['Assign to ABS','Cancelled','Completed and Delivered','QC in Progress'][i%4],Product:'Full Search',
      ...(comparison?{'Queue Presence':i===count-1?'Missing from selected preview':'In selected preview','Status Reason':i===count-1?'Order missing from preview3 compared with preview2':'Saved preview Status'}:{}),
      'SLA Expiration':'2026-10-16 05:00 PM','SLA Category':['Future SLA','Negative SLA','Today SLA'][i%3]}));
    const categories=['Future SLA','Negative SLA','Today SLA'];
    const summary=[...new Set(rows.map(row=>row.Status))].map(Status=>({Status,
      ...Object.fromEntries(categories.map(category=>[category,rows.filter(r=>r.Status===Status&&r['SLA Category']===category).length])),
      'Grand Total':rows.filter(row=>row.Status===Status).length}));
    return {as_of:'2026-10-16',mode,source:mode==='excel'?'Imported Excel':'Saved preview',columns,rows,summary,
      report_scope:mode==='tracker'?'preview':null,preview_id:mode==='tracker'&&preview?id:null,
      ...(comparison?{previous_preview_name:'preview2',captured_order_count:count-1,missing_order_count:1}:{}),
      preview_name:mode==='tracker'&&preview?preview.name:null,preview_row_count:count,previews,
      summary_columns:['Status',...categories,'Grand Total'],excluded_count:0,excluded_rows:[],
      totals:{Status:'Grand Total',...Object.fromEntries(categories.map(category=>[category,rows.filter(r=>r['SLA Category']===category).length])),'Grand Total':count}};
  }
  const settings=()=>({mode,row_count:1,files:[{file:'full.xlsx',rows:1,sheet:'Orders'}],publication_state:'synced'});
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,previews,report_workspace:settings()};
      if(name==='/api/report-workspace')body=settings();
      if(name==='/api/live-sheets')body={...body,mode,source:mode==='tracker'?'Google Sheets':'Imported Excel'};
      if(name==='/api/report-source'){mode=route.request().postDataJSON().mode;body={...settings(),publication:{synced:true}};}
      if(name==='/api/sla-status')body=report(Number(url.searchParams.get('preview_id')||selected));
      if(name==='/api/sla-preview'){
        selected=route.request().postDataJSON().preview_id;publications.push(selected);
        body={...report(selected),publication:{synced:true,tabs:['SLA Status']}};
      }
      if(name==='/api/report-refresh')refreshes.push(name);
      return route.fulfill({json:body});
    }
    const file=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(file),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  return {errors,publications,refreshes};
}

test('preview selection updates SLA cards, statuses, detail rows, chart and download without changing Overview',async({page})=>{
  const {errors,publications,refreshes}=await setup(page);
  const select=page.getByRole('combobox',{name:'SLA preview'});
  await expect(select).toHaveValue('3');
  await expect(page.getByRole('button',{name:'Grand Total 3',exact:true})).toBeVisible();
  const table=page.getByRole('table',{name:'SLA status summary'});
  await expect(table.getByRole('button',{name:'Completed and Delivered, Grand Total: 1 orders',exact:true})).toBeVisible();
  await select.selectOption('2');
  await expect(select).toBeEnabled();
  await expect(select).toHaveValue('2');
  await expect(page.getByRole('button',{name:'Grand Total 4',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Future SLA 2',exact:true})).toBeVisible();
  await expect(table.getByRole('button',{name:'QC in Progress, Grand Total: 1 orders',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status&preview_id=2');
  await expect(page.getByRole('region',{name:'SLA status bar chart'})).toBeVisible();
  await page.getByRole('button',{name:'Grand Total 4',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.locator('tbody tr')).toHaveCount(4);
  await expect(dialog).toContainText('preview2-0');
  await expect(dialog).not.toContainText('preview3-0');
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'Refresh SLA Status',exact:true}).click();
  await expect(select).toBeEnabled();
  expect(publications).toEqual([2,2]);
  expect(refreshes).toEqual([]);
  await page.screenshot({path:'test-results/sla-preview-selector.png',fullPage:true,animations:'disabled'});
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('button',{name:'Production orders 35',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('Import Excel report keeps its own SLA report and Tracker remembers the selected preview',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('combobox',{name:'SLA preview'}).selectOption('1');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Import Excel report',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'SLA preview'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Grand Total 1',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download SLA Status'})).toHaveAttribute('href','/api/export/report?sheet=SLA%20Status');
  await page.getByRole('button',{name:'Tracker report',exact:true}).click();
  await expect(page.getByRole('combobox',{name:'SLA preview'})).toHaveValue('1');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('an empty preview history shows zero SLA totals and never the production report',async({page})=>{
  const {errors}=await setup(page,{empty:true});
  await expect(page.getByRole('combobox',{name:'SLA preview'})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Grand Total 0',exact:true})).toBeVisible();
  await expect(page.getByText('No orders with a valid SLA expiration.',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('SLA status shows only selected-preview orders and its category counts reconcile',async({page})=>{
  const {errors}=await setup(page);
  await expect(page.getByText('Only orders in preview3 are included.',{exact:false})).toBeVisible();
  await expect(page.locator('.sla-total-equation')).toHaveText('Future SLA 1 + Negative SLA 1 + Today SLA 1 = Grand Total 3');
  await expect(page.getByRole('button',{name:'View missing orders',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'View current orders',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await expect(dialog.locator('tbody tr')).toHaveCount(3);
  await expect(dialog).toContainText('preview3-2');
  await expect(dialog).not.toContainText('preview2-');
  expect(errors).toEqual([]);
});
