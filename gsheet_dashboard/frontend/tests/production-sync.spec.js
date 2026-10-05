import {test, expect} from '@playwright/test';

async function mockProduction(page, offline = false) {
  const preview = {id: 1, name: 'preview1', created: '2026-10-02T03:00:00Z', source: 'Test', row_count: 1};
  const rows = [
    {'Order Number': 'RETAINED', Product: 'Full Title', Status: 'Typing in Progress', 'Out Time': ''},
    {'Order Number': 'A', Product: 'Current Owner', Status: 'Search In Progress', 'Out Time': ''},
  ];
  const frame = items => ({columns: Object.keys(rows[0]), rows: items});
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/state') return route.fulfill({json: {previews: [preview], job: {running: false, stage: 'Ready'}, schedule: {enabled: false, times: ['09:00']}}});
    if (path === '/api/previews/1') return route.fulfill({json: {...preview, columns: ['Order Number', 'Task Status', 'Task Name', 'Product'],
      rows: [{'Order Number': 'RAW-ONLY', 'Task Status': 'Available', 'Task Name': 'CRSP2', Product: 'Full Title'}]}});
    if (path === '/api/sync-reports') return route.fulfill({json: {source: 'Local sync history', report: {preview_name: 'preview1', changes: [], not_in_latest: ['RETAINED']}}});
    if (path === '/api/live-sheets') {
      if (offline) return route.fulfill({status: 502, json: {error: 'Sheets is offline'}});
      return route.fulfill({json: {preview_name: 'preview1', source: 'Google Sheets', sheets: {
        Overview: frame(rows), 'Full Title': frame(rows.slice(0, 1)), 'Remaining Products': frame(rows.slice(1)),
        Changes: {columns: ['Preview', 'Type', 'Order Number'], rows: [{Preview: 'preview1', Type: 'Not in latest preview', 'Order Number': 'RETAINED'}]},
      }}});
    }
    return route.fulfill({json: {rows: []}});
  });
}

test('production views use retained Sheet orders and Sync activity reads local receipts', async ({page}) => {
  await mockProduction(page);
  await page.goto('/');
  await expect(page.getByRole('status').filter({hasText: 'Google Sheets connected'})).toBeVisible();
  const metric = page.locator('.metric').filter({hasText: 'Visible orders'});
  await expect(metric.locator('strong')).toHaveText('2');
  await page.getByRole('button', {name: 'Data Sheets', exact: true}).click();
  await expect(page.getByText('RETAINED', {exact: true}).first()).toBeVisible();
  await expect(page.getByText('Typing in Progress', {exact: true}).first()).toBeVisible();
  await expect(page.getByText('RAW-ONLY', {exact: true})).toHaveCount(0);
  await expect(page.getByText('Completed and Delivered', {exact: true})).toHaveCount(0);
  await page.getByRole('button', {name: 'Activity', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Activity', exact: true})).toBeVisible();
  await expect(page.getByText('Local sync activity · preview1')).toBeVisible();
  await expect(page.getByText('Not in latest preview', {exact: true})).toBeVisible();
  await page.getByRole('button', {name: 'Changes', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Changes',exact:true})).toBeVisible();
  await expect(page.getByText('Capture or import a second preview to compare changes.')).toBeVisible();
});

test('a failed Sheet connection does not show raw previews as production data', async ({page}) => {
  await mockProduction(page, true);
  await page.goto('/');
  await expect(page.getByRole('status').filter({hasText: 'Connect Google Sheets to load production reports'})).toBeVisible();
  await expect(page.locator('.metric').filter({hasText: 'Visible orders'}).locator('strong')).toHaveText('0');
  await page.getByRole('button', {name: 'Data Sheets', exact: true}).click();
  await expect(page.getByText('RAW-ONLY', {exact: true})).toHaveCount(0);
});
