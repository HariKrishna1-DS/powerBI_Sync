import {test,expect} from '@playwright/test';
import fs from 'node:fs/promises';

async function fixture(page,count=120){
  const rows=Array.from({length:count},(_,i)=>({'Order Number':`TV-${String(62000+i).padStart(6,'0')}`,Product:i%2?'Current Owner':'Full Title',Status:i%3?'Search In Progress':'Awaiting Clarification',Client:i%2?'West Coast':'North Star',Assignee:i%2?'Team B':'Team A'}));
  const preview={id:2,name:'preview2',created:'2026-10-02T05:12:00Z',source:'Sample workspace',row_count:count};
  await page.route('**/api/**',route=>{
    const path=new URL(route.request().url()).pathname;
    return route.fulfill({json:path==='/api/state'?{previews:[preview],pending_sync:0,job:{running:false,stage:'Ready'},schedule:{enabled:false,times:['09:00']}}:
      path==='/api/live-sheets'?{mode:'tracker',updated_at:'2026-10-02T05:12:00Z',sheets:{Overview:{columns:Object.keys(rows[0]),rows}}}:
      path==='/api/previews/2'?{...preview,columns:Object.keys(rows[0]),rows}:
      path==='/api/order-history'?{events:[{preview_id:2,preview_name:'preview2',created:preview.created,status:'Search In Progress'}]}:
      path==='/api/activity'?{operations:[{id:1,kind:'capture',status:'interrupted',started:preview.created,error_code:'interrupted'}]}:{rows:[]}});
  });
  await page.goto('/');
  return rows;
}

test('orders preserve full production data and show real detail/history',async({page})=>{
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await fixture(page);
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  await page.getByRole('button',{name:'Open order TV-062000',exact:true}).click();
  await expect(page.getByRole('complementary',{name:'Order details'})).toBeVisible();
  await expect(page.locator('.order-event')).toContainText('preview2');
  await page.getByRole('button',{name:'Close order details'}).click();
  await expect(page.getByRole('complementary',{name:'Order details'})).toHaveCount(0);
  await page.getByRole('button',{name:'Needs attention',exact:true}).click();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(40);
  await page.getByLabel('Product',{exact:true}).selectOption('Full Title');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(20);
  expect(errors).toEqual([]);
});

test('saved views restore filters and selected CSV exports exactly the visible records',async({page})=>{
  await fixture(page);
  await page.getByLabel('Search rows').fill('TV-062119');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'Save view',exact:true}).click();
  await page.getByLabel('View name').fill('My order');
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await page.getByLabel('Search rows').fill('');
  await page.getByLabel('Saved views').selectOption('My order');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  const downloaded=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV',exact:true}).click();
  const content=await fs.readFile(await (await downloaded).path(),'utf8');
  expect(content).toContain('TV-062119');expect(content).not.toContain('TV-062000');
});

test('theme persists and narrow layouts have no page overflow',async({page})=>{
  await fixture(page);
  await page.getByLabel('Appearance').selectOption('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.reload();
  await expect(page.getByLabel('Appearance')).toHaveValue('dark');
  for(const width of [1440,1024,800,640]){
    await page.setViewportSize({width,height:900});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }
  await page.getByRole('button',{name:'Open order TV-062000',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});

test('overview and durable activity are connected to workspace data',async({page})=>{
  await fixture(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Status summary'})).toBeVisible();
  await expect(page.locator('.metric').filter({hasText:'Production orders'}).locator('strong')).toHaveText('120');
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await expect(page.getByText('The app stopped during this operation.',{exact:false})).toBeVisible();
});

test('100000 production records remain paginated and search responds within the interactive budget',async({page},testInfo)=>{
  await fixture(page,100000);
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  const measurements=[];
  for(const query of ['TV-161999','TV-142817','TV-101234','TV-160017','TV-098762']){
    const start=performance.now();
    await page.getByLabel('Search rows').fill(query);
    await expect(page.getByRole('button',{name:`Open order ${query}`,exact:true})).toBeVisible();
    await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
    measurements.push(Math.round(performance.now()-start));
  }
  await testInfo.attach('search-measurements',{body:JSON.stringify({rows:100000,roundTripMilliseconds:measurements}),contentType:'application/json'});
  expect(Math.max(...measurements)).toBeLessThan(2000);
});

test('background capture discovery preserves an active order search',async({page})=>{
  await page.clock.install();
  const rows=await fixture(page);
  await page.getByLabel('Search rows').fill('TV-062119');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  const next={id:3,name:'preview3',created:'2026-10-02T06:12:00Z',row_count:120};
  await page.route('**/api/previews/3',route=>route.fulfill({json:{...next,columns:Object.keys(rows[0]),rows}}));
  await page.route('**/api/state*',route=>route.fulfill({json:{previews:[next,{...next,id:2,name:'preview2'}],job:{running:false,stage:'Ready'},schedule:{enabled:false,times:['09:00']}}}));
  await page.clock.fastForward(11000);
  await expect(page.getByRole('button',{name:/preview3 120 rows/})).toBeVisible();
  await expect(page.getByLabel('Search rows')).toHaveValue('TV-062119');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
});

test('CSV treats formula-like source fields as literal text',async({page})=>{
  const rows=await fixture(page,1);
  rows[0].Client='=HYPERLINK("https://example.invalid")';
  rows[0].Assignee='+1+1';
  await page.reload();
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  const download=page.waitForEvent('download');
  await page.getByRole('button',{name:'CSV',exact:true}).click();
  const content=await fs.readFile(await (await download).path(),'utf8');
  expect(content).toContain('"\'=HYPERLINK');
  expect(content).toContain('"\'+1+1"');
});
