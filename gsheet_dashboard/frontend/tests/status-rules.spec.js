import {test, expect} from '@playwright/test';

test('dropdown slicers and multiple status replacements sync together', async ({page}) => {
  test.setTimeout(120000);
  const rows = [
    {'Task Status':'Workflow Suspended', Client:'A', Product:'Full Title', 'Online/ Ground':'Online'},
    {'Task Status':'Available', Client:'B', Product:'Current Owner', 'Online/ Ground':'Ground'}
  ];
  const preview = {id:1, name:'preview1', created:'2026-09-25T00:00:00Z', source:'Test', row_count:2,
    columns:Object.keys(rows[0]), rows};
  let synced;
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/sync') {
      synced = route.request().postDataJSON();
      return route.fulfill({json:{accepted:true}});
    }
    return route.fulfill({json:path === '/api/state'
      ? {previews:[preview], job:{running:false,stage:'Ready'}, capabilities:{status_rules:true}, sheet_url:'https://docs.google.com'}
      : preview});
  });
  await page.goto('http://127.0.0.1:8511');
  await expect(page.locator('.metrics .metric')).toHaveCount(5);
  expect(await page.locator('.metrics .metric').evaluateAll(items => new Set(items.map(item => item.offsetTop)).size)).toBe(1);
  await expect(page.locator('.dropdown-slicer')).toHaveCount(3);
  const clients = page.locator('.dropdown-slicer').first();
  await expect(clients.getByRole('checkbox').first()).toBeHidden();
  await clients.locator('summary').click();
  await expect(clients.getByRole('checkbox').first()).toBeVisible();
  await clients.getByRole('checkbox').first().check();
  await expect(clients.locator('summary')).toContainText('1 selected');
  await clients.getByRole('button', {name:'All clients'}).click();
  await clients.locator('summary').click();
  await page.getByLabel('Status_1', {exact:true}).selectOption('Workflow Suspended');
  await page.getByLabel('Status_2', {exact:true}).selectOption('Awaiting for Clarification');
  await page.getByRole('button', {name:'Add status rule', exact:true}).click();
  await page.getByLabel('Status_1', {exact:true}).selectOption('Available');
  await page.getByLabel('Status_2', {exact:true}).selectOption('Search in Progress');
  await page.getByRole('button', {name:'Add status rule', exact:true}).click();
  await expect(page.locator('.status-rule')).toHaveCount(2);
  await expect(page.locator('.status-report-table')).toContainText('Awaiting for Clarification');
  await page.getByRole('button', {name:'Sync Filters', exact:true}).click();
  await expect.poll(()=>synced).toEqual({preview:1, status_rules:[
    {source:'Workflow Suspended',target:'Awaiting for Clarification'},
    {source:'Available',target:'Search in Progress'}
  ]});
  await page.reload();
  await expect(page.locator('.status-rule')).toHaveCount(2);
  await page.screenshot({path:'test-results/status-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({path:'test-results/status-mobile.png',fullPage:true});
  await page.getByRole('button', {name:'Remove Available rule'}).click();
  await expect(page.locator('.status-rule')).toHaveCount(1);
  expect(errors).toEqual([]);
});
