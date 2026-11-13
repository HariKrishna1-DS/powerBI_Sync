import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

test('comparison status and order actions persist edits, copies and additions in the selected preview', async ({page}) => {
  const fixture = workspaceFixture(2), saves = [], errors = [];
  let custom = [], productionStatus = 'QC in Progress';
  const rows = [{'Order Number': 'EDIT-1', Status: 'Search In Progress', Borrower: 'Original borrower',
    'SLA Expiration': '2030-06-15 14:30:00', 'SLA Category': 'Future SLA', _sla_revision: 'r1'}];
  const previews = [{id: 7, name: 'preview7', row_count: 1}];
  function comparison() {
    const orders = rows.map(row => ({order_number: row['Order Number'], sla_status: row.Status,
      prod_status: productionStatus, match_type: 'status_moved', sla_category: 'Future SLA'}));
    return {has_production: true, selected_preview_id: 7, previews, preview_name: 'preview7', orders,
      metrics: {matched: rows.length, status_moved: rows.length}, transitions: [],
      sla_summary: {rows: [{Status: productionStatus, 'Future SLA': rows.length, 'Grand Total': rows.length}],
        totals: {'Future SLA': rows.length, 'Grand Total': rows.length}}};
  }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url()), name = url.pathname;
    let body = fixture.response(name);
    if (name === '/api/sla-compare') body = comparison();
    if (name === '/api/sla-status') body = {...body, report_scope: 'preview', preview_id: 7, preview_name: 'preview7',
      previews, preview_row_count: rows.length, rows, excluded_rows: [], custom_statuses: custom, summary: [{Status: 'Search In Progress'}]};
    if (name === '/api/sla-statuses') {
      const payload = route.request().postDataJSON(); saves.push(payload);
      custom = [...custom.filter(status => status !== payload.previous), payload.status]; body = {status: payload.status};
    }
    if (name === '/api/sla-compare/update-status') {
      const payload = route.request().postDataJSON(); saves.push(payload);
      if (payload.prod_status === 'Rejected status') return route.fulfill({status: 409, json: {error: 'Status changed. Refresh and try again.'}});
      productionStatus = payload.prod_status; body = {ok: true};
    }
    if (name === '/api/sla-order') {
      if (route.request().method() === 'GET') {
        const row = rows.find(row => row['Order Number'] === url.searchParams.get('order_number'));
        body = {exists: !!row, row, fields: row, revision: row?._sla_revision || null};
      } else {
        const payload = route.request().postDataJSON(); saves.push(payload);
        let row = rows.find(row => row['Order Number'] === payload.order_number);
        if (!row) {row = {'Order Number': payload.order_number}; rows.push(row);}
        Object.assign(row, payload.fields, {Status: payload.status, _sla_revision: 'r2'});
        body = {order_number: payload.order_number, status: payload.status};
      }
    }
    await route.fulfill({json: body});
  });
  page.on('pageerror', err => errors.push(err.message));
  await page.goto('/');
  await page.getByRole('button', {name: 'SLA Compare', exact: true}).click();
  await page.getByRole('button', {name: 'Edit status QC in Progress', exact: true}).click();
  let dialog = page.getByRole('dialog', {name: 'Edit comparison status name', exact: true});
  await dialog.getByRole('button', {name: 'Choose SLA order status'}).click();
  await expect(dialog.getByRole('option', {name: 'QC in Progress', exact: true})).toBeVisible();
  const list=dialog.getByRole('listbox');
  await expect(list).toHaveCSS('position','relative');
  const listBox=await list.boundingBox(),saveBox=await dialog.getByRole('button',{name:'Save status',exact:true}).boundingBox();
  expect(saveBox.y).toBeGreaterThanOrEqual(listBox.y+listBox.height);
  await dialog.getByRole('option', {name: 'Search In Progress', exact: true}).click();
  await expect(dialog.getByLabel('Comparison status name')).toHaveValue('Search In Progress');
  await expect(dialog.getByRole('listbox')).toHaveCount(0);
  await dialog.getByLabel('Comparison status name').fill('Rejected status');
  await dialog.getByRole('button', {name: 'Save status', exact: true}).click();
  await expect(dialog.getByRole('alert')).toContainText('Status changed');
  await dialog.getByLabel('Comparison status name').fill('Review pending');
  await dialog.getByRole('button', {name: 'Save status', exact: true}).click();
  await expect(page.getByRole('button', {name: 'Edit status Review pending', exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Review pending', exact: true}).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('columnheader', {name: 'Actions', exact: true})).toBeVisible();
  await page.screenshot({path: 'test-results/sla-compare-edit-actions.png', fullPage: true});
  await dialog.getByRole('button', {name: 'Edit details EDIT-1', exact: true}).click();
  let editor = page.getByRole('dialog', {name: 'Edit SLA order', exact: true});
  await expect(editor.getByLabel('Borrower', {exact: true})).toHaveValue('Original borrower');
  await editor.getByLabel('Borrower', {exact: true}).fill('Updated borrower');
  await editor.getByRole('button', {name: 'Save order', exact: true}).click();
  await expect(editor).toHaveCount(0);
  expect(saves.at(-1)).toMatchObject({preview_id: 7, order_number: 'EDIT-1', expected_revision: 'r1', fields: {Borrower: 'Updated borrower'}});
  await page.getByRole('button', {name: 'Review pending', exact: true}).click();
  await page.getByRole('dialog').getByRole('button', {name: 'Copy order EDIT-1', exact: true}).click();
  editor = page.getByRole('dialog', {name: 'Copy SLA order', exact: true});
  await expect(editor.getByLabel('SLA Order Number', {exact: true})).toHaveValue('');
  await editor.getByLabel('SLA Order Number', {exact: true}).fill('COPY-1');
  await editor.getByRole('button', {name: 'Look up order', exact: true}).click();
  await editor.getByRole('button', {name: 'Add order', exact: true}).click();
  await expect(editor).toHaveCount(0);
  expect(saves.at(-1)).toMatchObject({preview_id: 7, order_number: 'COPY-1', fields: {Borrower: 'Updated borrower'}});
  const addStatus = page.getByRole('button', {name: 'Add status', exact: true});
  await expect(addStatus).toBeVisible();
  await addStatus.click();
  await page.getByLabel('Comparison status name').fill('Manual review');
  await page.getByRole('button', {name: 'Save status', exact: true}).click();
  await page.getByRole('button', {name: 'Add order to status Manual review', exact: true}).click();
  editor = page.getByRole('dialog', {name: 'Add SLA order', exact: true});
  await expect(editor.getByLabel('SLA order status', {exact: true})).toHaveValue('Manual review');
  await editor.getByRole('button', {name: 'Cancel', exact: true}).click();
  const search = page.getByRole('textbox', {name: 'Search comparison orders', exact: true});
  await search.fill('EDIT-1');
  await page.getByRole('button', {name: 'Edit SLA order EDIT-1', exact: true}).click();
  await expect(page.getByRole('dialog', {name: 'Edit SLA order', exact: true})).toBeVisible();
  expect(errors).toEqual([]);
});

test('Negative SLA popup retains the SLA Status order set after production status edits', async ({page}) => {
  const fixture = workspaceFixture(3);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const orders = [
    {order_number: 'NEG-1', match_type: 'status_moved', sla_category: 'Negative SLA', sla_status: 'Search In Progress', prod_status: 'QC in Progress', sla_expiration: '-2d'},
    {order_number: 'NEG-2', match_type: 'sla_only', sla_category: 'Negative SLA', sla_status: 'Search In Progress', prod_status: 'Not in Production Report', sla_expiration: '-1h'},
    {order_number: 'TODAY', match_type: 'same_status', sla_category: 'Today SLA', sla_status: 'QC in Progress', prod_status: 'QC in Progress', sla_expiration: '1d'},
    {order_number: 'PROD-ONLY', match_type: 'prod_only', sla_category: 'Not in SLA Queue', sla_status: 'Not in SLA Queue', prod_status: 'QC in Progress', sla_expiration: ''},
    {order_number: 'HOME-1', match_type: 'sla_only', sla_category: 'Future SLA', sla_status: 'Home Builders', prod_status: 'Home Builders', sla_expiration: '2030-06-15 14:30:00'},
  ];
  await page.route('**/api/**', async route => {
    const name = new URL(route.request().url()).pathname;
    let body = fixture.response(name);
    if (name === '/api/sla-compare') body = {
      has_production: true, orders, preview_name: 'preview1', selected_preview_id: 1,
      previews: [{id: 1, name: 'preview1', row_count: 3, created: '2026-10-14T12:00:00Z'}],
      source_files: 'production.xlsx', metrics: {total_sla: 3, total_production: 3, matched: 2, status_moved: 1, same_status: 1, sla_only: 1, prod_only: 1},
      transitions: [], sla_summary: {
        rows: [{Status: 'QC in Progress', 'Negative SLA': 1, 'Today SLA': 1, 'Grand Total': 2},
          {Status: 'Home Builders', 'Future SLA': 1, 'Grand Total': 1}],
        totals: {'Negative SLA': 1, 'Today SLA': 1, 'Future SLA': 1, 'Grand Total': 3},
      },
    };
    if (name === '/api/sla-compare/update-status') body = {ok: true};
    await route.fulfill({json: body});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'SLA Compare', exact: true}).click();
  const negative = page.getByTitle('Click to open Pop Table for all Negative SLA orders', {exact: true});
  await expect(negative).toHaveText('1');
  await negative.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByRole('cell', {name: 'NEG-1', exact: true})).toBeVisible();
  await expect(dialog.getByRole('cell', {name: 'NEG-2', exact: true})).toHaveCount(0);
  await expect(dialog.getByRole('cell', {name: 'TODAY', exact: true})).toHaveCount(0);
  await expect(dialog.getByRole('cell', {name: 'PROD-ONLY', exact: true})).toHaveCount(0);
  await expect(dialog.getByRole('link', {name: 'Download (Excel)', exact: true})).toHaveAttribute('href', /category=Negative%20SLA/);
  await page.screenshot({path: 'test-results/sla-compare-negative.png', fullPage: true});
  await page.keyboard.press('Escape');
  const mainTable = page.getByRole('table', {name: 'SLA vs Production Orders Comparison'});
  await mainTable.getByRole('button', {name: 'Edit Production Status for NEG-1'}).click();
  await mainTable.locator('select.status-edit-select').selectOption('Completed and Delivered');
  await mainTable.getByRole('button', {name: 'Save Status', exact: true}).click();
  await expect(negative).toHaveText('1');
  await negative.click();
  await expect(dialog.getByRole('cell', {name: 'NEG-1', exact: true})).toBeVisible();
  await expect(dialog.getByRole('cell', {name: 'NEG-2', exact: true})).toHaveCount(0);
  await dialog.getByRole('button', {name: 'View in Main Table', exact: true}).click();
  await expect(mainTable.locator('tbody tr')).toHaveCount(1);
  await expect(page.getByRole('link', {name: 'Download Filtered Orders (Excel)', exact: true})).toHaveAttribute('href', /filter_type=summary/);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('columnheader', {name: 'Not in SLA Queue', exact: true})).toHaveCount(0);
  await expect(page.getByRole('columnheader', {name: 'Unknown SLA', exact: true})).toHaveCount(0);
  const search = page.getByRole('textbox', {name: 'Search comparison orders', exact: true});
  await search.fill('  pRoD-OnLy  ');
  await expect(mainTable.locator('tbody tr')).toHaveCount(1);
  await expect(mainTable.getByText('PROD-ONLY', {exact: true})).toBeVisible();
  await expect(page.getByRole('table', {name: 'SLA Status Summary Table', exact: true})).toBeHidden();
  expect((await mainTable.boundingBox()).y).toBeLessThan(650);
  await expect(page.getByRole('link', {name: 'Download Filtered Orders (Excel)', exact: true})).toHaveAttribute('href', /filter_type=all.*q=pRoD-OnLy/);
  await search.fill('NEG-2');
  await expect(mainTable.getByText('NEG-2', {exact: true})).toBeVisible();
  await search.fill('no-such-order');
  await expect(mainTable.getByText('No orders match the current search or column filters.', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Clear comparison search', exact: true}).click();
  await expect(page.getByRole('table', {name: 'SLA Status Summary Table', exact: true})).toBeVisible();
  await expect(mainTable.getByText('NEG-1', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Home Builders', exact: true}).click();
  await expect(dialog.locator('tbody tr')).toHaveCount(1);
  await expect(dialog.getByRole('cell', {name: 'HOME-1', exact: true})).toBeVisible();
  await expect(dialog.getByText('Not in Production Report', {exact: true})).toHaveCount(0);
  await expect(dialog.getByRole('link', {name: 'Download (Excel)', exact: true})).toHaveAttribute('href', /summary_status=Home%20Builders/);
  await page.keyboard.press('Escape');
  expect(errors).toEqual([]);
});

test('popup expiration edits save date and time, and Sheets updating opens a large dialog', async ({page}) => {
  const fixture = workspaceFixture(3);
  const settings = {mode: 'tracker', row_count: 3, publication_state: 'working', files: [], imports: []};
  let saved = [];
  let order = {order_number: 'NEG-1', match_type: 'status_moved', sla_category: 'Negative SLA',
    sla_status: 'Search In Progress', prod_status: 'QC in Progress', sla_expiration: '2026-10-13 10:00:00', sla_revision: 'revision1'};
  const comparison = () => ({has_production: true, orders: [order], preview_name: 'preview1', selected_preview_id: 1,
    previews: [{id: 1, name: 'preview1', row_count: 1, created: '2026-10-14T12:00:00Z'}],
    source_files: 'production.xlsx', metrics: {total_sla: 1, total_production: 1, matched: 1, status_moved: 1, same_status: 0, sla_only: 0, prod_only: 0},
    transitions: [], sla_summary: {rows: [{Status: 'QC in Progress', [order.sla_category]: 1, 'Grand Total': 1}],
      totals: {[order.sla_category]: 1, 'Grand Total': 1}}});
  await page.route('**/api/**', async route => {
    const name = new URL(route.request().url()).pathname;
    let body = fixture.response(name);
    if (name === '/api/state') body = {...body, report_workspace: settings};
    if (name === '/api/report-workspace') body = settings;
    if (name === '/api/sla-compare') body = comparison();
    if (name === '/api/sla-compare/expiration') {
      saved.push(route.request().postDataJSON());
      order = {...order, sla_expiration: '2030-06-15 14:30:00', sla_category: 'Future SLA', sla_revision: 'revision2'};
      body = {ok: true, result: comparison()};
    }
    await route.fulfill({json: body});
  });
  await page.goto('/');
  await page.getByRole('button', {name: 'SLA Compare', exact: true}).click();
  await page.getByTitle('Click to open Pop Table for all Negative SLA orders', {exact: true}).click();
  const popup = page.getByRole('dialog');
  await popup.getByRole('button', {name: 'Edit SLA expiration for NEG-1', exact: true}).click();
  const input = popup.getByRole('textbox', {name: 'SLA expiration for NEG-1'});
  await expect(popup.locator('input[type=datetime-local]')).toHaveValue('2026-10-13T10:00');
  await popup.getByRole('button', {name: 'Cancel SLA expiration edit', exact: true}).click();
  expect(saved).toEqual([]);
  await popup.getByRole('button', {name: 'Edit SLA expiration for NEG-1', exact: true}).click();
  await popup.locator('input[type=datetime-local]').fill('2030-06-15T14:30');
  await popup.getByRole('button', {name: 'Save SLA expiration for NEG-1', exact: true}).click();
  await expect(popup.getByText('2030-06-15 14:30', {exact: true})).toBeVisible();
  expect(saved).toEqual([{preview_id: 1, order_number: 'NEG-1', expiration: '2030-06-15T14:30', expected_revision: 'revision1'}]);
  await page.keyboard.press('Escape');
  await expect(page.getByTitle('Click to open Pop Table for all Negative SLA orders', {exact: true})).toHaveText('0');
  await page.getByRole('button', {name: 'Sheets updating', exact: true}).click();
  const imports = page.getByRole('dialog', {name: 'Import Excel reports', exact: true});
  await expect(imports).toBeVisible();
  const bounds = await imports.boundingBox();
  expect(bounds.width).toBeGreaterThan(1200);
  expect(bounds.height).toBeGreaterThan(850);
  const dropzone = imports.getByRole('region', {name: 'Excel report upload'});
  const chooser = imports.getByRole('button', {name: 'Choose files', exact: true});
  const zoneBounds = await dropzone.boundingBox(), chooserBounds = await chooser.boundingBox();
  expect(zoneBounds.height).toBeGreaterThan(140);
  expect(Math.abs((chooserBounds.x + chooserBounds.width / 2) - (zoneBounds.x + zoneBounds.width / 2))).toBeLessThan(2);
  const transfer = await page.evaluateHandle(() => {
    const value = new DataTransfer();
    value.items.add(new File(['Order Number,Status\n1,Cancelled'], 'production.csv', {type: 'text/csv'}));
    return value;
  });
  await dropzone.dispatchEvent('dragenter', {dataTransfer: transfer});
  await expect(dropzone).toHaveClass(/is-dragging/);
  await expect(dropzone.getByText('Drop your files here', {exact: true})).toBeVisible();
  await page.screenshot({path: 'test-results/import-dialog-large.png', fullPage: true});
  await dropzone.dispatchEvent('drop', {dataTransfer: transfer});
  await expect(dropzone).not.toHaveClass(/is-dragging/);
  await expect(dropzone.getByText('1 file selected', {exact: true})).toBeVisible();
  await expect(imports.getByRole('button', {name: 'Import and update reports', exact: true})).toBeEnabled();
});

test('New Orders uses all 25 production-report columns for table and clipboard',async({page})=>{
  const fixture=workspaceFixture(3);
  await page.addInitScript(()=>Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{window.copiedNewOrders=value;}}}));
  const row={eta_comments:'ETA: Hello Team.<br>Please be informed that we requested the abstractor for review.<br>We will complete this order ASAP.',order_number:'NEW-1',match_type:'sla_only',sla_status:'SearchFix',sla_category:'Today SLA',sla_expiration:'2026-11-11 14:30:00',product:'Update',state:'NJ',county:'Bergen',client:'TELSIX',production_report:{No:'',Date:'11/10/2026','Order Number':'NEW-1','TraceQ Id':'TRACE-1',State:'NJ',County:'Bergen',Client:'TELSIX','Online/Ground':'Online',Product:'Update',Status:'SearchFix',ETA:'11/12/2026',Comments:'Keep original comment',Assignee:'Owner',Searcher:'Searcher','Clarification Requested':'Yes',Shift:'Day','Process date':'',Typer:'Typer','Review/QC':'QC',Expense:0,'In-Time':'11/10/2026 12:30:00 PM','Out Time':'','SLA Expiration':'2026-11-11 14:30:00','Free site':'Yes',review:'Review'}};
  await page.route('**/api/**',async route=>{
    const name=new URL(route.request().url()).pathname;
    let body=fixture.response(name);
    if(name==='/api/sla-compare')body={has_production:true,previews:fixture.previews,orders:[row],metrics:{sla_only:1,total_sla:1,total_production:1,matched:0},transitions:[],sla_summary:{rows:[],totals:{}}};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'SLA Compare',exact:true}).click();
  await page.getByRole('button',{name:'✨ New Orders (1)',exact:true}).click();
  const table=page.getByRole('table',{name:'New Orders production report',exact:true});
  const headers=await table.locator('thead th span').allTextContents();
  expect(headers).toEqual(['No','Date','Order Number','TraceQ Id','State','County','Client','Online/Ground','Product','Status','ETA','Comments','Assignee','Searcher','Clarification Requested','Shift','Process date','Typer','Review/QC','Expense','In-Time','Out Time','SLA Expiration','Free site','review']);
  await expect(table.locator('tbody tr')).toHaveCount(1);
  await expect(table.locator('.eta-comment-cell')).toHaveText('ETA: Hello Team.\nPlease be informed that we requested the abstractor for review.\nWe will complete this order ASAP.');
  await expect(table.locator('thead th').first()).toHaveCSS('font-size','12.5px');
  await expect(table.locator('tbody td').nth(19)).toHaveText('0');
  await page.getByRole('button',{name:'Copy New Orders for Excel',exact:true}).click();
  const copied=await page.evaluate(()=>window.copiedNewOrders);
  const cells=copied.split('\t');
  expect(cells).toHaveLength(25);
  expect(cells[0]).toBe('');expect(cells[2]).toBe('NEW-1');expect(cells[10]).toBe('11/12/2026');
  expect(cells[11]).toBe('ETA: Hello Team. Please be informed that we requested the abstractor for review. We will complete this order ASAP.');expect(cells[17]).toBe('Typer');expect(cells[22]).toBe('2026-11-11 14:30:00');
  await expect(page.getByRole('link',{name:'Download Filtered Orders (Excel)',exact:true})).toHaveAttribute('href',/filter_type=sla_only/);
  await table.locator('.eta-comment-cell').scrollIntoViewIfNeeded();
  await page.screenshot({path:'test-results/new-orders-production-columns.png',animations:'disabled'});
});

test('Clear Report confirms, reports failures and stays cleared after reload', async ({page}) => {
  const fixture=workspaceFixture(1);
  let cleared=false, attempts=0;
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url());
    let body=fixture.response(url.pathname);
    if(url.pathname==='/api/sla-compare'){
      if(url.searchParams.get('clear')==='1'){
        expect(route.request().method()).toBe('POST');attempts++;
        if(attempts===1)return route.fulfill({status:500,json:{error:'Unable to clear test report'}});
        cleared=true;
      }
      body={has_production:!cleared,orders:[],preview_name:'preview1',selected_preview_id:1,
        previews:[{id:1,name:'preview1',row_count:1,created:'2026-11-10T10:00:00Z'}],
        source_files:cleared?'':'production.xlsx',metrics:{total_sla:1,total_production:cleared?0:1},
        transitions:[],sla_summary:{rows:[],totals:{}}};
    }
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'SLA Compare',exact:true}).click();
  await page.getByRole('button',{name:'Clear Report',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Clear comparison report'});
  await expect(dialog).toBeVisible();
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  expect(attempts).toBe(0);
  await page.getByRole('button',{name:'Clear Report',exact:true}).click();
  await dialog.getByRole('button',{name:'Clear comparison',exact:true}).click();
  await expect(dialog.getByRole('alert')).toHaveText('Unable to clear test report');
  await dialog.getByRole('button',{name:'Clear comparison',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Clear Report',exact:true})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Upload Production Report (Excel)',exact:true})).toBeVisible();
  await page.reload();
  await page.getByRole('button',{name:'SLA Compare',exact:true}).click();
  await expect(page.getByRole('button',{name:'Upload Production Report (Excel)',exact:true})).toBeVisible();
  expect(attempts).toBe(2);expect(errors).toEqual([]);
});
