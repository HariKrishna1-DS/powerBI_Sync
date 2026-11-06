import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page){
  const fixture=workspaceFixture(4),errors=[],saves=[];
  const identity=row=>JSON.stringify([row['Source workbook'].toLowerCase(),row['Order Number'].toLowerCase()]);
  const rows=[{ 'Order Number':'001','Source workbook':'full.xlsx',Borrower:'Full borrower',Product:'Full Title',Status:'Typing in Progress',Date:'2026-10-13'},
    {'Order Number':'001','Source workbook':'remaining.xlsx',Borrower:'Other borrower',Product:'Current Owner',Status:'Search In Progress',Date:'2026-10-13'},
    {'Order Number':'old','Source workbook':'full.xlsx',Product:'Full Title',Status:'QC in Progress',Date:'2026-10-12'}]
    .map(row=>({...row,_record_key:identity(row),'SLA Expiration':'2026-10-14 17:00:00','SLA Category':'Future SLA',_revision:'1'}));
  let selected='2026-10-13';const custom={};
  function report(){
    const current=rows.filter(row=>row.Date===selected),categories=['Future SLA','Negative SLA','Today SLA'];
    return {mode:'excel',source:'Imported Excel',report_scope:'imported_date',report_date:selected,
      report_dates:['2026-10-13','2026-10-12'].map(date=>({date,orders:rows.filter(row=>row.Date===date).length})),
      source_workbooks:[...new Set(rows.map(row=>row['Source workbook']))],custom_statuses:custom[selected]||[],as_of:selected,
      imported_order_count:rows.length,date_order_count:current.length,manual_order_count:current.filter(row=>row._manual).length,
      columns:['Order Number','Status','Source workbook','Borrower','Product','SLA Expiration','SLA Category'],rows:current,excluded_rows:[],excluded_count:0,
      summary:[...new Set([...current.map(row=>row.Status),...(custom[selected]||[])])].sort().map(Status=>({Status,'Future SLA':current.filter(row=>row.Status===Status).length,'Negative SLA':0,'Today SLA':0,'Grand Total':current.filter(row=>row.Status===Status).length})),
      summary_columns:['Status',...categories,'Grand Total'],totals:{Status:'Grand Total','Future SLA':current.length,'Negative SLA':0,'Today SLA':0,'Grand Total':current.length}};
  }
  const settings=()=>({mode:'excel',row_count:rows.length,files:[],publication_state:'synced'});
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/state')body={...body,report_workspace:settings()};
      if(name==='/api/report-workspace')body=settings();
      if(name==='/api/live-sheets')body={...body,mode:'excel',source:'Imported Excel'};
      if(name==='/api/sla-status')body=report();
      if(name==='/api/sla-report-date'){selected=route.request().postDataJSON().date;body={...report(),publication:{queued:true}};}
      if(name==='/api/sla-statuses'){
        const change=route.request().postDataJSON();saves.push(change);
        expect(change.mode).toBe('excel');expect(change.preview_id).toBeUndefined();
        const names=custom[change.report_date]||[];
        if(change.action==='delete'){
          for(const row of rows)if(change.order_numbers.includes(row._record_key))row.Status=change.replacement;
          custom[change.report_date]=names.filter(value=>value!==change.status);
          body={status:change.status,deleted:true,moved:change.order_numbers.length,replacement:change.replacement,publication:{queued:true}};
        }else{custom[change.report_date]=[...new Set([...names.filter(value=>value!==change.previous),change.status])];body={status:change.status,publication:{queued:true}};}
      }
      if(name==='/api/sla-order'){
        if(route.request().method()==='GET'){
          const source=url.searchParams.get('source_workbook'),number=url.searchParams.get('order_number');
          const matches=rows.filter(row=>row.Date===url.searchParams.get('date')&&row['Order Number'].toLowerCase()===number.toLowerCase()&&(!source||row['Source workbook']===source));
          if(matches.length>1)return route.fulfill({status:400,json:{error:'This Order Number occurs in multiple workbooks. Choose its workbook before looking it up.'}});
          const row=matches[0];body={exists:!!row,row,fields:row,revision:row?._revision||null,source_workbook:row?.['Source workbook']||source||'Manual SLA orders'};
        }else{
          const change=route.request().postDataJSON();saves.push(change);
          expect(change.mode).toBe('excel');expect(change.report_date).toBe(selected);expect(change.preview_id).toBeUndefined();
          const row=rows.find(row=>row['Order Number'].toLowerCase()===change.order_number.toLowerCase()&&row['Source workbook']===change.source_workbook);
          const values={...change.fields,Status:change.status,_revision:'2'};
          if(row)Object.assign(row,values);else{const added={...values,'Order Number':change.order_number,'Source workbook':change.source_workbook,Date:selected,'SLA Category':'Future SLA',_manual:true};added._record_key=identity(added);rows.push(added);}
          body={order_number:change.order_number,status:change.status,created:!row,publication:{queued:true}};
        }
      }
      if(name==='/api/order-status'){
        const change=route.request().postDataJSON();saves.push(change);expect(change.sla_report_date).toBe(selected);
        for(const row of rows)if(change.order_numbers.includes(row._record_key))row.Status=change.replacement;
        body={updated:change.order_numbers.length,status:change.replacement,publication:{queued:true}};
      }
      return route.fulfill({json:body});
    }
    try{return route.fulfill({body:await readFile(path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1))),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('/');
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Add status',exact:true})).toBeVisible();
  return {rows,saves,errors};
}

async function createStatus(page,name){
  await page.getByRole('button',{name:'Add status',exact:true}).click();
  await page.getByLabel('Status name',{exact:true}).fill(name);
  await page.getByRole('button',{name:'Create status',exact:true}).click();
  await expect(page.getByRole('button',{name:`${name}, Grand Total: 0 orders`,exact:true})).toBeVisible();
}

test('Excel report shows Add status and moves/edits the chosen workbook order with stable totals',async({page})=>{
  const {rows,errors}=await setup(page);
  await createStatus(page,'Manual review');
  await page.getByRole('button',{name:'Add order to status Manual review',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Add SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('001');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await expect(editor.getByRole('alert')).toContainText('multiple workbooks');
  await editor.getByLabel('SLA source workbook',{exact:true}).selectOption('full.xlsx');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await expect(editor.getByLabel('Borrower',{exact:true})).toHaveValue('Full borrower');
  await editor.getByLabel('Borrower',{exact:true}).fill('Edited from SLA');
  await editor.getByRole('button',{name:'Save order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  expect(rows.find(row=>row['Source workbook']==='full.xlsx'&&row['Order Number']==='001').Borrower).toBe('Edited from SLA');
  expect(rows.find(row=>row['Source workbook']==='remaining.xlsx').Status).toBe('Search In Progress');
  await page.getByRole('button',{name:'Edit status Manual review',exact:true}).click();
  await page.getByLabel('New order status',{exact:true}).fill('QC in Progress');
  await page.getByRole('button',{name:'Save status',exact:true}).click();
  await expect(page.getByRole('button',{name:'QC in Progress, Grand Total: 1 orders',exact:true})).toBeVisible();
  await page.screenshot({path:'test-results/excel-sla-status-controls.png',fullPage:true});
  expect(errors).toEqual([]);
});

test('Excel report adds and copies orders then deletes a populated custom status without losing rows',async({page})=>{
  const {rows,errors}=await setup(page);
  await createStatus(page,'Manual review');
  await page.getByRole('button',{name:'Add order to status Manual review',exact:true}).click();
  let editor=page.getByRole('dialog',{name:'Add SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('new-099');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await editor.getByLabel('Product',{exact:true}).fill('Full Title');
  await editor.getByLabel('SLA Expiration',{exact:true}).fill('2026-10-14T17:00');
  await editor.getByRole('button',{name:'Add order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Grand Total 3',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Manual review',exact:true}).click();
  let detail=page.getByRole('dialog',{name:'Manual review',exact:true});
  await detail.getByRole('button',{name:'Copy order new-099',exact:true}).click();
  editor=page.getByRole('dialog',{name:'Copy SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('copy-100');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await editor.getByRole('button',{name:'Add order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Grand Total 4',exact:true})).toBeVisible();
  await page.getByRole('combobox',{name:'SLA report date'}).selectOption('2026-10-12');
  await expect(page.getByRole('button',{name:'Manual review',exact:true})).toHaveCount(0);
  await page.getByRole('combobox',{name:'SLA report date'}).selectOption('2026-10-13');
  await page.getByRole('button',{name:'Delete status Manual review',exact:true}).click();
  const remove=page.getByRole('dialog',{name:'Delete manual SLA status',exact:true});
  await remove.getByLabel('Move orders to',{exact:true}).selectOption('Typing in Progress');
  await remove.getByRole('button',{name:'Delete status',exact:true}).click();
  await expect(remove).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Grand Total 4',exact:true})).toBeVisible();
  expect(rows.filter(row=>row._manual&&row.Status==='Typing in Progress')).toHaveLength(2);
  expect(errors).toEqual([]);
});
