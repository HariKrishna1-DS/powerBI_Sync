import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';

test('quota pause preserves orders, explains automatic retry, and recovers without reconnecting', async ({page}) => {
  const fixture = workspaceFixture(12);
  let busy = true;
  await page.clock.install();
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body = fixture.response(path);
    if (path === '/api/state') body = {...body, capabilities: {desktop:true,google_configured:true},
      failed_syncs:busy?[{preview_id:32,preview_name:'preview32',automatic_retry:true,
        error:'Google Sheets is temporarily limiting requests. Your saved data is safe. Your connection settings do not need changing.'}]:[]};
    if (path === '/api/live-sheets') body = {...body, offline:busy,
      sync_error:busy?'Google Sheets is temporarily limiting requests. Your connection settings do not need changing.':null};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.getByText('Automatic retry queued')).toBeVisible();
  await expect(page.getByRole('button',{name:'Retry sync',exact:true})).toHaveCount(0);
  await expect(page.getByText('Viewing a saved Google Sheets copy')).toBeVisible();
  await expect(page.getByText('TV-62000',{exact:true}).first()).toBeVisible();
  await expect(page.getByText(/Enable the Google Sheets API|check credentials/i)).toHaveCount(0);
  await page.screenshot({path:'test-results/quota-paused.png',fullPage:false});
  busy=false;
  await page.clock.fastForward(31000);
  await expect(page.getByText('Automatic retry queued')).toHaveCount(0);
  await expect(page.getByRole('status').filter({hasText:'Reports read from Google Sheets'})).toBeVisible();
});

test('background refresh keeps cached rows usable and reports refresh completion', async ({page}) => {
  const fixture=workspaceFixture(12);
  let refreshing=true;
  await page.clock.install();
  await page.route('**/api/**', async route => {
    const path=new URL(route.request().url()).pathname;
    let body=fixture.response(path);
    if(path==='/api/live-sheets')body={...body,refreshing};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.getByText('Refreshing Google Sheets reports')).toBeVisible();
  await page.getByRole('button',{name:'Open order TV-62000',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'Order details'})).toBeVisible();
  refreshing=false;
  await page.clock.fastForward(2100);
  await expect(page.getByText('Refreshing Google Sheets reports')).toHaveCount(0);
});
