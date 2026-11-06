import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

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
