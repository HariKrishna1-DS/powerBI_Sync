import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';

test('new captures advance the default comparison and preserve an explicit historical pair',async({page})=>{
  const fixture=workspaceFixture(24);
  await page.clock.install();
  await page.route('**/api/**',route=>route.fulfill({json:fixture.response(new URL(route.request().url()).pathname)}));
  await page.goto('/');
  await page.getByRole('button',{name:'Changes',exact:true}).click();
  await expect(page.getByLabel('Previous preview',{exact:true})).toHaveValue('31');
  fixture.previews.unshift({...fixture.previews[0],id:33,name:'preview33'});
  await page.clock.fastForward(11000);
  await expect(page.getByLabel('Latest preview',{exact:true})).toHaveValue('33');
  await expect(page.getByLabel('Previous preview',{exact:true})).toHaveValue('32');
  await page.getByLabel('Previous preview',{exact:true}).selectOption('30');
  fixture.previews.unshift({...fixture.previews[0],id:34,name:'preview34'});
  await page.clock.fastForward(11000);
  await expect(page.getByLabel('Latest preview',{exact:true})).toHaveValue('31');
  await expect(page.getByLabel('Previous preview',{exact:true})).toHaveValue('30');
});

test('navigation exposes headings and pending unverified captures have clear status',async({page})=>{
  const fixture=workspaceFixture(80);
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname, body=fixture.response(path);
    if(path==='/api/state')body.pending_sync=4;
    if(path.startsWith('/api/previews/'))body.metadata={kind:'portal',complete:false,expected_rows:null};
    return route.fulfill({json:body});
  });
  await page.goto('/');
  await expect(page.locator('.context-job')).toHaveClass(/is-pending/);
  await expect(page.getByText('4 local captures still awaiting publication',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Captures',exact:true}).click();
  await expect(page.getByText('This capture is saved locally, but the portal',{exact:false})).toBeVisible();
  await page.locator('main').evaluate(el=>el.scrollTop=600);
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect.poll(()=>page.locator('main').evaluate(el=>el.scrollTop)).toBe(0);
  await expect(page.getByRole('heading',{name:'Data Sheets',exact:true})).toBeVisible();
});
