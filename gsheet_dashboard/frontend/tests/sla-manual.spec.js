import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

const fullEta='ETA: Order has been assigned to the abstractor, and we will ensure completion within SLA.\n'+
  'The complete comment is available for review without shortening the sentence. '.repeat(12)+'End of full comment.';
async function setup(page,{rejectDelete=false,fullComments=false}={}){
  const fixture=workspaceFixture(20),errors=[],saves=[];
  const rows=[{'Order Number':'001',Borrower:'Original borrower',Product:'Current Owner',Status:'Typing in Progress','Task Name':'TypingModule','Task Status':'In Progress','SLA Expiration':'2026-10-20 17:00:00','SLA Category':'Future SLA',_sla_revision:'1'},
    {'Order Number':'002',Borrower:'Other borrower',Product:'Full Title',Status:'Search In Progress',Comment:'See order 001','SLA Expiration':'2026-10-19 17:00:00','SLA Category':'Today SLA',_sla_revision:'1'}];
  if(fullComments)Object.assign(rows[0],{Status:'Assign to ABS','ETA Comments':fullEta,Comment:'Complete order comment.',
    'Status Reason':'ETA Comments contains assigned to the abstractor'});
  let custom=[];
  const categories=['Future SLA','Negative SLA','Today SLA'],previews=[{id:7,name:'preview7',row_count:2,created:'2026-10-19T04:00:00Z'}];
  function report(){
    const summary=[...new Set([...rows.map(row=>row.Status),...custom])].sort().map(Status=>({Status,...Object.fromEntries(categories.map(c=>[c,rows.filter(r=>r.Status===Status&&r['SLA Category']===c).length])),'Grand Total':rows.filter(r=>r.Status===Status).length}));
    return {mode:'tracker',source:'Saved preview',report_scope:'preview',preview_id:7,preview_name:'preview7',preview_row_count:2,captured_order_count:2,manual_order_count:rows.length-2,previews,custom_statuses:custom,as_of:'2026-10-19',columns:['Order Number','Borrower','Product','Status','SLA Expiration','SLA Category'],rows,excluded_rows:[],excluded_count:0,summary,summary_columns:['Status',...categories,'Grand Total'],totals:{Status:'Grand Total',...Object.fromEntries(categories.map(c=>[c,rows.filter(r=>r['SLA Category']===c).length])),'Grand Total':rows.length}};
  }
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(()=>{Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{window.copiedOrder=value;}}});});
  await page.route('**/*',async route=>{
    const url=new URL(route.request().url()),name=url.pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      const settings={mode:'tracker',publication_state:'synced'};
      if(name==='/api/state')body={...body,previews,report_workspace:settings};
      if(name==='/api/report-workspace')body=settings;
      if(name==='/api/sla-status')body=report();
      if(name==='/api/sla-statuses'){
        const request=route.request().postDataJSON();
        if(request.action==='delete'){
          if(rejectDelete)return route.fulfill({status:409,json:{error:'Orders in this status changed. Reopen the delete dialog and try again.'}});
          const assigned=rows.filter(row=>row.Status===request.status);
          assigned.forEach(row=>{row.Status=request.replacement;row._sla_revision='3';});
          custom=custom.filter(status=>status!==request.status);
          body={status:request.status,deleted:true,moved:assigned.length,replacement:request.replacement,publication:{synced:true}};
        }else{custom=[...new Set([...custom.filter(s=>s!==request.previous),request.status])];body={status:request.status,publication:{synced:true}};}
      }
      if(name==='/api/sla-order'){
        if(route.request().method()==='GET'){
          const row=rows.find(r=>r['Order Number'].toLowerCase()===url.searchParams.get('order_number').toLowerCase());
          body={exists:!!row,row,fields:row,revision:row?._sla_revision||null};
        }else{
          const request=route.request().postDataJSON();saves.push(request);
          const row=rows.find(r=>r['Order Number'].toLowerCase()===request.order_number.toLowerCase());
          if(request.fields.Borrower==='Stale draft')return route.fulfill({status:409,json:{error:'This order changed. Look up the Order Number again before saving.'}});
          const values={...request.fields,Status:request.status,'SLA Expiration':request.fields['SLA Expiration'],'SLA Category':request.fields['SLA Expiration'].startsWith('2026-10-19')?'Today SLA':'Future SLA',_sla_revision:'2'};
          if(row)Object.assign(row,values);else rows.push({...values,'Order Number':request.order_number,'Queue Presence':'Manual addition'});
          body={order_number:request.order_number,status:request.status,created:!row,publication:{synced:true}};
        }
      }
      return route.fulfill({json:body});
    }
    try{return route.fulfill({body:await readFile(path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1))),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  return {errors,saves,rows};
}

test('empty custom status opens a table, looks up a preview order and moves it without increasing totals',async({page})=>{
  const {errors,saves}=await setup(page);
  await page.getByRole('button',{name:'Add manual SLA status',exact:true}).click();
  await page.getByLabel('Status name',{exact:true}).fill('In House Pending');
  await page.getByRole('button',{name:'Create status',exact:true}).click();
  const summary=page.getByRole('table',{name:'SLA status summary'});
  await expect(summary.getByRole('button',{name:'In House Pending, Grand Total: 0 orders',exact:true})).toBeVisible();
  await expect(summary.getByRole('button',{name:'Delete status In House Pending',exact:true})).toBeVisible();
  await summary.getByRole('button',{name:'In House Pending',exact:true}).click();
  const details=page.getByRole('dialog',{name:'In House Pending',exact:true});
  await expect(details.getByText('No matching rows',{exact:true})).toBeVisible();
  await details.getByRole('button',{name:'Add order',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Add SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('001');
  await expect(editor.getByRole('button',{name:'Add order',exact:true})).toBeDisabled();
  await editor.getByLabel('SLA Order Number',{exact:true}).press('Enter');
  await expect(editor.getByLabel('Borrower',{exact:true})).toHaveValue('Original borrower');
  await expect(editor.getByLabel('SLA order status',{exact:true})).toHaveValue('In House Pending');
  await expect(editor.getByRole('status')).toContainText('Saving moves it from Typing in Progress to In House Pending');
  await page.screenshot({path:'test-results/sla-manual-order-editor.png',fullPage:true});
  await editor.getByRole('button',{name:'Save order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(details.locator('tbody tr')).toHaveCount(1);
  await expect(details).toContainText('001');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  await expect(summary.getByRole('button',{name:'Typing in Progress',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'View current orders',exact:true}).click();
  const current=page.getByRole('dialog',{name:'Current queue orders',exact:true});
  await current.getByLabel('Search detail records',{exact:true}).fill('001');
  await expect(current.getByRole('status',{name:'Matching order status',exact:true})).toContainText('Current status: In House Pending');
  await expect(current.locator('tbody tr')).toHaveCount(1);
  expect(saves[0].expected_revision).toBe('1');
  expect(saves[0].status).toBe('In House Pending');
  expect(errors).toEqual([]);
});

test('new orders and editable copies have deadlines and explicit manual counts; pencil edits details',async({page})=>{
  const {errors,rows}=await setup(page);
  await page.getByRole('button',{name:'Add order to status Typing in Progress',exact:true}).click();
  let editor=page.getByRole('dialog',{name:'Add SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('NEW-003');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await expect(editor).toContainText('New order. Enter its details');
  await editor.getByLabel('Borrower',{exact:true}).fill('New borrower');
  await editor.getByRole('button',{name:'Add order',exact:true}).click();
  await expect(editor).toBeVisible(); // browser requires the missing SLA deadline
  await editor.getByLabel('SLA Expiration',{exact:true}).fill('2026-10-20T17:00');
  await editor.getByRole('button',{name:'Add order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(page.locator('.sla-total-equation')).toContainText('Grand Total 3');
  await expect(page.getByText('2 captured orders + 1 manually added order in preview7.',{exact:false})).toBeVisible();
  await page.getByRole('table',{name:'SLA status summary'}).getByRole('button',{name:'Typing in Progress',exact:true}).click();
  const detail=page.getByRole('dialog',{name:'Typing in Progress',exact:true});
  await detail.getByRole('button',{name:'Edit details NEW-003',exact:true}).click();
  editor=page.getByRole('dialog',{name:'Edit SLA order',exact:true});
  await expect(editor.getByLabel('SLA Order Number',{exact:true})).toHaveAttribute('readonly','');
  await expect(editor.getByLabel('Borrower',{exact:true})).toBeEnabled();
  await editor.getByLabel('Borrower',{exact:true}).fill('Corrected borrower');
  await editor.getByRole('button',{name:'Copy details',exact:true}).click();
  await expect(editor.getByRole('button',{name:'Copied',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>window.copiedOrder)).toContain('NEW-003\tTyping in Progress\tCorrected borrower');
  await editor.getByRole('button',{name:'Save order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(detail).toContainText('Corrected borrower');
  await detail.getByRole('button',{name:'Copy order 001',exact:true}).click();
  editor=page.getByRole('dialog',{name:'Copy SLA order',exact:true});
  await expect(editor.getByLabel('SLA Order Number',{exact:true})).toHaveValue('');
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('COPY-004');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await expect(editor.getByLabel('Borrower',{exact:true})).toHaveValue('Original borrower');
  await editor.getByRole('button',{name:'Add order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await expect(detail.locator('tbody tr')).toHaveCount(3);
  await page.screenshot({path:'test-results/sla-manual-order-actions.png',fullPage:true});
  await page.keyboard.press('Escape');
  await expect(page.locator('.sla-total-equation')).toContainText('Grand Total 4');
  expect(rows.find(row=>row['Order Number']==='001').Borrower).toBe('Original borrower');
  expect(errors).toEqual([]);
});

test('a stale edit keeps the form draft and lets the user look up the latest order',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'View current orders',exact:true}).click();
  await page.getByRole('button',{name:'Edit details 001',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Edit SLA order',exact:true});
  await expect(editor.getByLabel('Borrower',{exact:true})).toBeEnabled();
  await editor.getByLabel('Borrower',{exact:true}).fill('Stale draft');
  await editor.getByRole('button',{name:'Save order',exact:true}).click();
  await expect(editor.getByRole('alert')).toContainText('This order changed');
  await expect(editor.getByLabel('Borrower',{exact:true})).toHaveValue('Stale draft');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await expect(editor.getByLabel('Borrower',{exact:true})).toHaveValue('Original borrower');
  expect(errors).toEqual([]);
});

test('custom status delete removes an empty row and preserves report totals after reload',async({page})=>{
  const {errors}=await setup(page);
  await page.getByRole('button',{name:'Add manual SLA status',exact:true}).click();
  await page.getByLabel('Status name',{exact:true}).fill('In House Pending');
  await page.getByRole('button',{name:'Create status',exact:true}).click();
  await expect(page.getByRole('button',{name:'Delete status Typing in Progress',exact:true})).toHaveCount(0);
  await page.getByRole('button',{name:'Delete status In House Pending',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Delete manual SLA status',exact:true});
  await expect(dialog).toContainText('This status has no orders.');
  await dialog.getByRole('button',{name:'Delete status',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('table',{name:'SLA status summary'})).not.toContainText('In House Pending');
  await page.reload();
  await page.getByRole('button',{name:'SLA Status',exact:true}).click();
  await expect(page.getByRole('table',{name:'SLA status summary'})).not.toContainText('In House Pending');
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('deleting a populated manual status requires a destination and moves its orders exactly once',async({page})=>{
  const {errors,rows}=await setup(page);
  await page.getByRole('button',{name:'Add manual SLA status',exact:true}).click();
  await page.getByLabel('Status name',{exact:true}).fill('In House Pending');
  await page.getByRole('button',{name:'Create status',exact:true}).click();
  await page.getByRole('button',{name:'Add order to status In House Pending',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Add SLA order',exact:true});
  await editor.getByLabel('SLA Order Number',{exact:true}).fill('001');
  await editor.getByRole('button',{name:'Look up order',exact:true}).click();
  await editor.getByRole('button',{name:'Save order',exact:true}).click();
  await expect(editor).toHaveCount(0);
  await page.getByRole('button',{name:'Delete status In House Pending',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Delete manual SLA status',exact:true});
  await expect(dialog.getByRole('button',{name:'Delete status',exact:true})).toBeDisabled();
  await dialog.getByLabel('Move orders to',{exact:true}).selectOption('QC in Progress');
  await page.screenshot({path:'test-results/sla-delete-manual-status.png',fullPage:true});
  await dialog.getByRole('button',{name:'Delete status',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  const summary=page.getByRole('table',{name:'SLA status summary'});
  await expect(summary).not.toContainText('In House Pending');
  await expect(summary.getByRole('button',{name:'QC in Progress, Grand Total: 1 orders',exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Grand Total 2',exact:true})).toBeVisible();
  expect(rows.filter(row=>row['Order Number']==='001')).toHaveLength(1);
  expect(rows.find(row=>row['Order Number']==='001').Status).toBe('QC in Progress');
  expect(errors).toEqual([]);
});

test('a stale delete keeps the status and displays a recoverable error',async({page})=>{
  const {errors}=await setup(page,{rejectDelete:true});
  await page.getByRole('button',{name:'Add manual SLA status',exact:true}).click();
  await page.getByLabel('Status name',{exact:true}).fill('In House Pending');
  await page.getByRole('button',{name:'Create status',exact:true}).click();
  await page.getByRole('button',{name:'Delete status In House Pending',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Delete manual SLA status',exact:true});
  await dialog.getByRole('button',{name:'Delete status',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('Orders in this status changed');
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(page.getByRole('button',{name:'Delete status In House Pending',exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('searching an order number immediately shows its current status beside the number',async({page})=>{
  const {errors}=await setup(page);
  await page.setViewportSize({width:1200,height:900});
  await page.getByRole('button',{name:'View current orders',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Current queue orders',exact:true});
  await dialog.getByLabel('Search detail records',{exact:true}).fill(' 001 ');
  const match=dialog.getByRole('status',{name:'Matching order status',exact:true});
  await expect(match).toContainText('001');
  await expect(match).toContainText('Current status: Typing in Progress');
  await expect(dialog.locator('thead th').nth(1)).toContainText('Order Number');
  await expect(dialog.locator('thead th').nth(2)).toContainText('Status');
  await expect(dialog.locator('tbody tr')).toHaveCount(1);
  await page.screenshot({path:'test-results/sla-search-current-status.png',fullPage:true});
  await dialog.getByLabel('Search detail records',{exact:true}).fill('002');
  await expect(match).toContainText('Current status: Search In Progress');
  await dialog.getByLabel('Search detail records',{exact:true}).fill('unknown-order');
  await expect(match).toHaveCount(0);
  await expect(dialog.getByText('No matching rows',{exact:true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('full ETA comments wrap in the table, expand in the editor and show the exact classification reason',async({page})=>{
  const {errors}=await setup(page,{fullComments:true});
  await page.getByRole('button',{name:'View current orders',exact:true}).click();
  const details=page.getByRole('dialog',{name:'Current queue orders',exact:true});
  await details.getByLabel('Search detail records',{exact:true}).fill('001');
  const cell=details.locator('td.full-comment-cell').filter({hasText:'End of full comment.'});
  await expect(cell).toHaveCount(1);
  expect(await cell.textContent()).toBe(fullEta);
  expect(await cell.evaluate(node=>getComputedStyle(node).whiteSpace)).toBe('pre-wrap');
  await details.getByRole('button',{name:'Edit details 001',exact:true}).click();
  const editor=page.getByRole('dialog',{name:'Edit SLA order',exact:true});
  const eta=editor.getByLabel('ETA Comments',{exact:true});
  await expect(eta).toHaveValue(fullEta);
  await expect(editor.getByRole('region',{name:'Current SLA result',exact:true})).toContainText('Current status: Assign to ABS');
  await expect(editor.getByRole('region',{name:'Current SLA result',exact:true})).toContainText('assigned to the abstractor');
  await eta.scrollIntoViewIfNeeded();
  expect(await eta.evaluate(node=>node.scrollHeight<=node.clientHeight+2)).toBe(true);
  expect((await eta.boundingBox()).width).toBeGreaterThan(600);
  await page.screenshot({path:'test-results/sla-full-eta-comment.png',fullPage:true});
  await editor.getByRole('button',{name:'Copy details',exact:true}).click();
  expect(await page.evaluate(()=>window.copiedOrder)).toContain('End of full comment.');
  await editor.getByRole('button',{name:'Cancel',exact:true}).click();
  expect(errors).toEqual([]);
});
