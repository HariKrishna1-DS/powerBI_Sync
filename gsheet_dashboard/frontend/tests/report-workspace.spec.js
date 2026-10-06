import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';
import AxeBuilder from '@axe-core/playwright';

async function setup(page) {
  const fixture = workspaceFixture(24);
  let preferences = {source: 'tracker', import_id: null, revision: 0, publish_status: 'published', default_capacity: 700, default_extended: 750};
  const daily = {Date: '2026-10-05', Received: 24, Completed: 10, Clarification: 3, Cancelled: 1, 'Vendor Pending': 2, 'In-House Pending': 8,
    'On time SLA': 8, 'Missed SLA': 1, 'SLA Unclassified': 1, 'Inferred Completions': 1, rows: fixture.rows, columns: fixture.columns};
  const requests = [];
  await page.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), path = url.pathname;
    requests.push(path);
    const data = fixture.response(path);
    if (path === '/api/state') Object.assign(data, {capabilities: {report_sources: true}, report_preferences: preferences});
    if (path === '/api/reporting') return route.fulfill({json: {preferences, imports: [{id: 'import-one', count: 2, files: [{name: 'a.xlsx'}]}]}});
    if (path === '/api/reporting/import') return route.fulfill({json: {id: 'import-one', count: 2, duplicates_removed: 1, files: [{name: 'a.xlsx', accepted: 1}, {name: 'b.xlsx', accepted: 1}], skipped: []}});
    if (path === '/api/reporting/source') { preferences = {...preferences, ...req.postDataJSON(), revision: preferences.revision + 1}; return route.fulfill({json: {preferences}}); }
    if (path === '/api/reporting/publish') return route.fulfill({json: {preferences}});
    if (path === '/api/live-sheets') Object.assign(data, {source_mode: preferences.source, source: preferences.source === 'import' ? 'Imported Excel' : 'Google Sheets'});
    if (path === '/api/daily-orders') return route.fulfill({json: {rows: [daily], source: 'Google Sheets', sheet_links: {'2026-10-05': 'https://docs.google.com/spreadsheets/d/fixture/edit#gid=123&range=A2:I2'}}});
    if (path === '/api/reporting/capacity') {
      if (req.method() === 'POST') { preferences = {...preferences, revision: preferences.revision + 1}; return route.fulfill({json: {saved: true}}); }
      return route.fulfill({json: {source: 'Google Sheets', preferences, daily: [{...daily, Capacity: 700, 'Ext capacity': 750}], monthly: [{...daily, Date: '2026-10', Capacity: 700, 'Ext capacity': 750}], ytd: {...daily, Date: '2026 YTD', Capacity: 700, 'Ext capacity': 750}}});
    }
    return route.fulfill({json: data});
  });
  await page.goto('/');
  await expect(page.getByLabel('Report source', {exact: true})).toBeVisible();
  return requests;
}

test('daily report exposes PDF buckets, uncertainty and exact Sheets date link', async ({page}) => {
  await setup(page);
  await page.getByRole('button', {name: 'Daily Orders', exact: true}).click();
  await expect(page.getByRole('heading', {name: 'Daily production orders'})).toBeVisible();
  await expect(page.locator('.report-metric')).toHaveCount(8);
  await expect(page.locator('.report-metric').filter({hasText: 'Vendor Pending'})).toContainText('2');
  await expect(page.getByText(/1 completed orders need verified timing/)).toBeVisible();
  await expect(page.getByRole('link', {name: 'Open this date in Sheets'})).toHaveAttribute('href', /gid=123&range=A2:I2$/);
  await page.getByLabel('Search daily orders').fill('TV-62001');
  await expect(page.getByRole('region', {name: 'Daily order details'}).locator('tbody tr')).toHaveCount(1);
});

test('multiple workbook import is reviewed before source activation', async ({page}) => {
  const requests = await setup(page);
  await page.getByRole('button', {name: 'Import Excel reports', exact: true}).click();
  await page.getByLabel('Excel report workbooks').setInputFiles([
    {name: 'a.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('fixture-a')},
    {name: 'b.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('fixture-b')},
  ]);
  await page.getByRole('button', {name: 'Validate import'}).click();
  await expect(page.getByRole('heading', {name: '2 validated orders'})).toBeVisible();
  expect(requests).not.toContain('/api/reporting/source');
  await page.getByRole('button', {name: 'Use this import and publish reports'}).click();
  await expect(page.getByLabel('Report source', {exact: true})).toHaveValue('import');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(requests).not.toContain('/api/import');
});

test('capacity report provides targets and PDF totals with responsive controls', async ({page}) => {
  await setup(page);
  await page.getByRole('button', {name: 'Capacity Report', exact: true}).click();
  await expect(page.getByLabel('Capacity', {exact: true})).toHaveValue('700');
  await expect(page.getByLabel('Extended capacity')).toHaveValue('750');
  await expect(page.getByText('2026 YTD', {exact: true})).toBeVisible();
  await page.getByLabel('Capacity', {exact: true}).fill('800');
  await page.getByLabel('Extended capacity').fill('900');
  await page.getByRole('button', {name: 'Save targets and publish'}).click();
  for (const theme of ['light', 'dark']) {
    await page.setViewportSize({width: 1440, height: 1000});
    await page.getByLabel('Appearance', {exact: true}).selectOption(theme);
    for (const width of [1440, 980, 760, 390]) {
      await page.setViewportSize({width, height: 800});
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width === 1440 || width === 390) await page.screenshot({path: `test-results/capacity-${theme}-${width}.png`, fullPage: true});
    }
  }
});

test('import dialog keyboard close restores access to the source controls', async ({page}) => {
  await setup(page);
  await page.getByRole('button', {name: 'Import Excel reports', exact: true}).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', {name: 'Import Excel reports', exact: true})).toBeFocused();
});

for (const theme of ['light', 'dark']) {
  test(`WCAG automated checks across workspace screens and import dialog (${theme})`, async ({page}, testInfo) => {
    test.setTimeout(180000);
    await setup(page);
    await page.getByLabel('Appearance', {exact: true}).selectOption(theme);
    const findings = [];
    async function audit(screen) {
      const results = await new AxeBuilder({page}).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']).analyze();
      for (const violation of results.violations) findings.push({screen, id: violation.id, impact: violation.impact,
        nodes: violation.nodes.map(node => ({target: node.target, summary: node.failureSummary}))});
      await testInfo.attach(`accessibility-${screen}`, {body: JSON.stringify(findings, null, 2), contentType: 'application/json'});
    }
    for (const screen of ['Overview', 'Data Sheets', 'Daily Orders', 'Capacity Report', 'Monthly report', 'Changes', 'Captures', 'Activity', 'Settings']) {
      await page.getByRole('button', {name: screen, exact: true}).click();
      await audit(screen);
      if (screen === 'Settings') await page.keyboard.press('Escape');
    }
    await page.getByRole('button', {name: 'Daily Orders', exact: true}).click();
    await page.getByRole('button', {name: 'Import Excel reports', exact: true}).click();
    await audit('Import dialog');
    await testInfo.attach('accessibility-findings', {body: JSON.stringify(findings, null, 2), contentType: 'application/json'});
    expect(findings).toEqual([]);
  });
}
