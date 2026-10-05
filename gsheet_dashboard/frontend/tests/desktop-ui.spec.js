import {test, expect} from '@playwright/test';

const empty={previews:[],job:{running:false,stage:'Ready'},schedule:{enabled:false,times:['09:00']},capabilities:{desktop:true,google_configured:false}};
test('first run has a keyboard-accessible setup dialog and loads no charts',async({page})=>{
  const scripts=[];
  page.on('request',request=>{if(request.resourceType()==='script')scripts.push(request.url());});
  await page.addInitScript(()=>{window.desktop={getSettings:async()=>({spreadsheetId:'',queueUrl:'https://tv.datatracetitle.com/Queues.aspx',fullTrackerTitle:'Full',remainingTrackerTitle:'Remaining',username:'',passwordSet:false,serviceAccountEmail:'',googleConfigured:false,browserPath:'',browserDetected:true,closeToTray:true,startAtLogin:false}),onCommand:()=>()=>{},discardSettings:async()=>{}};});
  await page.route('**/api/**',route=>route.fulfill({status:route.request().url().endsWith('/api/state')?200:502,json:route.request().url().endsWith('/api/state')?empty:{error:'Connect Sheets'}}));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Clear work. Confident decisions.'})).toBeVisible();
  expect(scripts.some(url=>url.includes('/charts-'))).toBe(false);
  await page.keyboard.press('Control+k');
  await page.getByLabel('Find an action').fill('connections');
  await page.getByLabel('Find an action').press('Enter');
  await expect(page.getByRole('heading',{name:'Connections & settings'})).toBeVisible();
  await expect(page.getByLabel('Spreadsheet URL or ID')).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('heading',{name:'Connections & settings'})).toHaveCount(0);
});

test('cached production is explicitly marked offline',async({page})=>{
  const frame={columns:['Order Number','Product','Status'],rows:[{'Order Number':'CACHED-ONLY',Product:'Full Title',Status:'Search In Progress'}]};
  await page.route('**/api/**',route=>route.fulfill({json:route.request().url().endsWith('/api/state')?empty:{offline:true,updated_at:'2026-10-01T12:00:00Z',sheets:{Overview:frame,'Full Title':frame,'Remaining Products':{columns:frame.columns,rows:[]},Changes:{columns:[],rows:[]}}}}));
  await page.goto('/');
  await expect(page.getByText('Viewing a saved Google Sheets copy')).toBeVisible();
  await expect(page.getByText('Google Sheets connected',{exact:false})).toHaveCount(0);
  await page.getByRole('button',{name:'Orders',exact:true}).click();
  await expect(page.getByRole('button',{name:'Open order CACHED-ONLY',exact:true})).toBeVisible();
});

test('large local captures remain paginated and searchable',async({page},testInfo)=>{
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  const rows=Array.from({length:25000},(_,index)=>({'Order Number':`ORDER-${String(index).padStart(5,'0')}`,Product:'Full Title',Status:'Search In Progress'}));
  const preview={id:1,name:'preview1',source:'Test fixture',created:'2026-10-02T03:00:00Z',row_count:rows.length};
  await page.route('**/api/**',route=>{
    const routePath=new URL(route.request().url()).pathname;
    return route.fulfill({status:routePath==='/api/live-sheets'?502:200,json:routePath==='/api/state'?{...empty,previews:[preview]}:routePath==='/api/previews/1'?{...preview,columns:Object.keys(rows[0]),rows}:{error:'Offline'}});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Captures',exact:true}).click();
  await expect(page.getByRole('cell',{name:'ORDER-00000',exact:true})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(50);
  const started=Date.now();
  await page.getByRole('textbox',{name:'Search rows'}).fill('ORDER-24999');
  await expect(page.getByRole('cell',{name:'ORDER-24999',exact:true})).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(1);
  await testInfo.attach('search-performance',{body:JSON.stringify({rows:25000,searchMs:Date.now()-started}),contentType:'application/json'});
  expect(errors).toEqual([]);
  await page.setViewportSize({width:1024,height:768});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
});
