import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';
import path from 'node:path';

async function setup(page, captureCount=3){
  const fixture=workspaceFixture();
  if(captureCount>3)fixture.previews.push(...Array.from({length:captureCount-3},(_,i)=>({id:29-i,name:`preview${29-i}`,created:'2026-09-29T12:00:00Z',row_count:240})));
  await page.route('**/api/**',route=>{const req=route.request();return route.fulfill({json:fixture.response(new URL(req.url()).pathname,req.postData()?req.postDataJSON():{})});});
  await page.goto('/');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(50);
  return fixture;
}

test('capture library searches, preserves selection and remains usable with a collapsed sidebar',async({page})=>{
  await setup(page);
  await page.getByLabel('Search saved captures').fill('September');
  await expect(page.locator('.preview-select')).toHaveCount(1);
  await page.locator('.preview-select').click();
  await expect(page.getByRole('heading',{name:'Capture library',exact:true})).toBeVisible();
  await expect(page.getByLabel('Selected capture',{exact:true})).toHaveValue('30');
  await page.getByRole('button',{name:'Collapse sidebar'}).click();
  await expect(page.locator('.workspace')).toHaveClass(/sidebar-collapsed/);
  await page.getByLabel('Find saved capture').fill('preview31');
  await page.getByLabel('Selected capture',{exact:true}).selectOption('31');
  await expect(page.locator('.context-preview')).toContainText('preview31');
  await page.reload();
  await expect(page.locator('.workspace')).toHaveClass(/sidebar-collapsed/);
  await expect(page.getByRole('button',{name:'Theme: System',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Expand sidebar'}).click();
  await expect(page.getByLabel('Search saved captures')).toBeVisible();
});

test('sheet segments use the correct sources and keep search and sorting available',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Full Title 120',exact:true}).click();
  await expect(page.locator('.metric').filter({hasText:'Visible orders'}).locator('strong')).toHaveText('120');
  await expect(page.locator('.orders-table')).not.toContainText('Current Owner');
  await page.getByLabel('Search rows').fill('TV-62000');
  await expect(page.locator('.orders-table tbody tr')).toHaveCount(1);
  await page.getByRole('button',{name:'All columns',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'County'})).toBeVisible();
  await page.getByRole('button',{name:'Order Number',exact:true}).click();
  await expect(page.getByRole('columnheader',{name:'Order Number'})).toHaveAttribute('aria-sort','ascending');
  await page.getByLabel('Search rows').fill('');
  await page.getByRole('button',{name:'Remaining Products 120',exact:true}).click();
  await expect(page.locator('.orders-table')).toContainText('Current Owner');
  await expect(page.locator('.orders-table')).not.toContainText('Full Title');
});

test('slow capture loading never presents a false zero row count or local-file source',async({page})=>{
  const fixture=await setup(page);
  let release;
  const held=new Promise(resolve=>{release=resolve;});
  await page.route('**/api/previews/31',async route=>{await held;await route.fulfill({json:fixture.response('/api/previews/31')});});
  await page.locator('.preview-select').filter({has:page.locator('strong',{hasText:/^preview31$/})}).click();
  await expect(page.locator('.metric').filter({hasText:'Saved rows'}).locator('strong')).toHaveText('—');
  await expect(page.locator('.metric').filter({hasText:'Source'}).locator('strong')).toHaveText('Loading…');
  release();
  await expect(page.locator('.metric').filter({hasText:'Saved rows'}).locator('strong')).toHaveText('228');
});

test('settings and appearance remain reachable in short desktop windows',async({page})=>{
  await page.setViewportSize({width:1280,height:620});
  await setup(page,35);
  const appearance=page.getByLabel('Appearance');
  await expect(appearance).toBeInViewport();
  await appearance.selectOption('dark');
  await expect(appearance).toHaveValue('dark');
  const settings=page.getByRole('button',{name:'Settings',exact:true});
  await expect(settings).toHaveCount(1);
  await settings.click();
  await expect(page.getByRole('heading',{name:'Connections & settings',exact:true})).toBeVisible();
});

for(const height of [900,720,620,500])test(`only saved captures scroll and remain usable at ${height}px height`,async({page})=>{
  await page.setViewportSize({width:1280,height});
  await setup(page,35);
  const sidebar=page.getByRole('complementary',{name:'Workspace sidebar'});
  const captures=page.getByRole('region',{name:'Saved captures',exact:true});
  const dimensions=await sidebar.evaluate(el=>({height:el.clientHeight,scroll:el.scrollHeight,overflow:getComputedStyle(el).overflowY}));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.height+1);
  expect(dimensions.overflow).toBe('hidden');
  const list=await captures.boundingBox();
  expect(list.height).toBeGreaterThanOrEqual(118);
  await expect(page.getByLabel('Appearance')).toBeInViewport();
  await expect(page.getByRole('button',{name:'Settings',exact:true})).toBeInViewport();
  const footer=await page.locator('.sidebar-footer').boundingBox();
  await captures.hover();
  await page.mouse.wheel(0,3000);
  await expect.poll(()=>captures.evaluate(el=>el.scrollTop)).toBeGreaterThan(100);
  expect((await page.locator('.sidebar-footer').boundingBox()).y).toBe(footer.y);
  await page.getByLabel('Search saved captures').fill('preview1');
  const target=page.locator('.preview-select').filter({has:page.locator('strong',{hasText:/^preview1$/})});
  await target.click();
  await expect(page.getByLabel('Selected capture',{exact:true})).toHaveValue('1');
  await expect(target).toHaveAttribute('aria-pressed','true');
  await expect(page.locator('.loading')).toHaveCount(0);
  if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`sidebar-${height}.png`)});
});

test('chart drilldowns reflect active filters and native dialogs restore keyboard focus',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:'Clear chart filters',exact:true}).click();
  await page.getByRole('button',{name:'Chart filters',exact:true}).click();
  await page.locator('.dropdown-slicer summary').filter({hasText:'Client'}).click();
  await page.getByRole('checkbox',{name:'Northstar Title & Escrow 80'}).check();
  await page.getByRole('button',{name:'Online: 60 (75.0%)',exact:true}).click();
  const dialog=page.getByRole('dialog',{name:'Online/ Ground: Online',exact:true});
  await expect(dialog).toContainText('60 matching records');
  await expect(dialog.locator('tbody')).not.toContainText('Pacific Coast');
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Online: 60 (75.0%)',exact:true})).toBeFocused();
});

test('schedule confirms writes and does not claim success after failure',async({page})=>{
  await setup(page);
  await page.getByText('AutoLogin Trigger',{exact:true}).click();
  await page.route('**/api/sync-schedule',route=>route.fulfill({status:503,json:{error:'Schedule storage unavailable'}}));
  await page.getByRole('button',{name:'Save AutoLogin Trigger',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Schedule storage unavailable');
  await expect(page.getByText('Schedule saved. Times are in IST.',{exact:true})).toHaveCount(0);
  await page.route('**/api/sync-schedule',route=>route.fulfill({json:route.request().postDataJSON()}));
  await page.getByRole('button',{name:'Save AutoLogin Trigger',exact:true}).click();
  await expect(page.getByText('Schedule saved. Times are in IST.',{exact:true})).toBeVisible();
});

test('failed product preference save retains the last confirmed selection',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.route('**/api/remaining-products',route=>route.fulfill({status:503,json:{error:'Storage unavailable'}}));
  await page.getByRole('button',{name:'Clear chart filters',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Product selection was not saved');
  await expect(page.getByRole('button',{name:'Chart filters (2)',exact:true})).toBeVisible();
});

for(const theme of ['light','dark'])test(`all primary screens fit desktop and narrow windows in ${theme} mode`,async({page})=>{
  test.setTimeout(120000);
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await setup(page);
  await page.getByLabel('Appearance').selectOption(theme);
  for(const [width,height] of [[1280,800],[1440,900],[1920,1080],[640,900]]){
    await page.setViewportSize({width,height});
    for(const name of ['Overview','Data Sheets','Daily Orders','Monthly Orders','Changes','Captures','Activity']){
      await page.getByRole('button',{name,exact:true}).click();
      await expect(page.locator('#workspace-content h1')).toBeVisible();
      await expect(page.locator('.loading')).toHaveCount(0);
      const sizes=await page.locator('main').evaluate(el=>({client:el.clientWidth,scroll:el.scrollWidth}));
      expect(sizes.scroll,`${name} at ${width}`).toBeLessThanOrEqual(sizes.client+1);
      expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
      if(process.env.TV_TRACKER_SCREENSHOTS&&width===1440)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`${theme}-${name.toLowerCase().replaceAll(' ','-')}.png`)});
    }
    if(width<=760)await expect(page.getByRole('button',{name:`Theme: ${theme==='light'?'Light':'Dark'}`,exact:true})).toBeVisible();
    else await expect(page.getByLabel('Appearance',{exact:true})).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('collapsed appearance uses icons and a keyboard accessible menu that persists the selection',async({page})=>{
  await setup(page);
  await page.getByRole('button',{name:'Collapse sidebar',exact:true}).click();
  const trigger=page.getByRole('button',{name:'Theme: System',exact:true});
  await expect(trigger).toBeVisible();
  await expect(trigger.locator('svg')).toHaveCount(1);
  await expect(page.getByLabel('Appearance',{exact:true})).toBeHidden();
  await trigger.click();
  const menu=page.getByRole('menu',{name:'Appearance options',exact:true});
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('menuitemradio',{name:'System',exact:true})).toBeFocused();
  for(const name of ['System','Light','Dark'])await expect(menu.getByRole('menuitemradio',{name,exact:true}).locator('svg').first()).toBeVisible();
  await page.keyboard.press('End');
  await expect(menu.getByRole('menuitemradio',{name:'Dark',exact:true})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(menu).toHaveCount(0);
  const dark=page.getByRole('button',{name:'Theme: Dark',exact:true});
  await expect(dark).toBeFocused();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await dark.click();
  await expect(menu.getByRole('menuitemradio',{name:'Dark',exact:true})).toHaveAttribute('aria-checked','true');
  await page.keyboard.press('Escape');
  await expect(dark).toBeFocused();
  await page.reload();
  await expect(dark).toBeVisible();
  await page.setViewportSize({width:640,height:620});
  await dark.scrollIntoViewIfNeeded();
  await dark.click();
  const box=await menu.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x+box.width).toBeLessThanOrEqual(640);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y+box.height).toBeLessThanOrEqual(620);
  if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,'collapsed-appearance-menu.png')});
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(menu).toHaveCount(0);
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'Expand sidebar',exact:true}).click();
  await expect(page.getByLabel('Appearance',{exact:true})).toHaveValue('dark');
});

test('failed appearance saves keep the confirmed theme and the error menu inside a short window',async({page})=>{
  await page.setViewportSize({width:640,height:620});
  await setup(page);
  await page.evaluate(()=>{const save=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==='tv-tracker-theme')throw Error('Storage unavailable');return save.call(this,key,value);};});
  const trigger=page.getByRole('button',{name:'Theme: System',exact:true});
  await trigger.click();
  const menu=page.getByRole('menu',{name:'Appearance options',exact:true});
  await menu.getByRole('menuitemradio',{name:'Dark',exact:true}).click();
  await expect(menu.getByRole('alert')).toContainText('could not be saved');
  await expect(menu.getByRole('menuitemradio',{name:'System',exact:true})).toHaveAttribute('aria-checked','true');
  await expect(trigger).toHaveAttribute('aria-label','Theme: System');
  const box=await menu.boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y+box.height).toBeLessThanOrEqual(620);
});

for(const theme of ['light','dark'])test(`settings forms, footer and quick actions fit wide, short and narrow windows in ${theme} mode`,async({page})=>{
  test.setTimeout(90000);
  await page.addInitScript(theme=>{
    window.desktop={getPreferences:async()=>({theme}),savePreferences:async()=>{},onCommand:()=>()=>{},discardSettings:async()=>{},onUpdateState:()=>()=>{},getUpdateState:async()=>({status:'idle',currentVersion:'2.5.2',message:'Check for a new Windows release.'}),getSettings:async()=>({spreadsheetId:'https://docs.google.com/spreadsheets/d/example-production-sheet/edit',queueUrl:'https://tv.datatracetitle.com/Queues.aspx?qid=23656',fullTrackerTitle:'TV_Search_Production_Report_Full_Search',remainingTrackerTitle:'TV_Search_Production_Report_C-O_and_Update',username:'qc-fixture',passwordSet:true,serviceAccountEmail:'sheet-sync-bot@example-project.iam.gserviceaccount.com',googleConfigured:true,browserPath:'',browserDetected:true,closeToTray:true,startAtLogin:false,dataPath:'C:/Users/QC/AppData/Roaming/DataTrace Studio/workspace'})};
  },theme);
  await setup(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  const contrasts=await page.evaluate(()=>{
    const style=getComputedStyle(document.documentElement);
    const luminance=value=>{const channels=value.trim().slice(1).match(/../g).map(c=>parseInt(c,16)/255).map(c=>c<=0.04045?c/12.92:((c+0.055)/1.055)**2.4);return channels[0]*0.2126+channels[1]*0.7152+channels[2]*0.0722;};
    return ['--ink','--text','--muted'].flatMap(foreground=>['--canvas','--surface','--sidebar','--hover','--accent-soft'].map(background=>{const a=luminance(style.getPropertyValue(foreground)),b=luminance(style.getPropertyValue(background));return {foreground,background,ratio:(Math.max(a,b)+0.05)/(Math.min(a,b)+0.05)};}));
  });
  for(const contrast of contrasts)expect(contrast.ratio,`${contrast.foreground} on ${contrast.background}`).toBeGreaterThanOrEqual(4.5);
  for(const [width,height] of [[1440,900],[1280,620],[640,620]]){
    await page.setViewportSize({width,height});
    await page.getByRole('button',{name:'Settings',exact:true}).click();
    const dialog=page.getByRole('dialog',{name:'Connections & settings',exact:true});
    await expect(dialog.getByRole('tab',{name:'Connections',exact:true})).toBeVisible();
    for(const name of ['Connections','Workspace','Updates']){
      await dialog.getByRole('tab',{name,exact:true}).click();
      const box=await dialog.boundingBox();
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.x+box.width).toBeLessThanOrEqual(width);
      expect(box.y+box.height).toBeLessThanOrEqual(height);
      expect(await dialog.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
      await expect(dialog.getByRole('button',{name:'Save settings',exact:true})).toBeInViewport();
      await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeInViewport();
      const cancel=await dialog.getByRole('button',{name:'Cancel',exact:true}).boundingBox();
      const save=await dialog.getByRole('button',{name:'Save settings',exact:true}).boundingBox();
      expect(Math.abs(cancel.height-save.height)).toBeLessThanOrEqual(1);
      expect(Math.abs(cancel.y-save.y)).toBeLessThanOrEqual(1);
      if(name==='Connections'){
        for(const label of ['Spreadsheet URL or ID','Remaining Products tracker tab','Username','Password','Queue URL']){
          const input=dialog.getByLabel(label,{exact:true});
          await input.scrollIntoViewIfNeeded();
          await expect(input).toBeInViewport();
          const inputBox=await input.boundingBox();
          expect(inputBox.x).toBeGreaterThanOrEqual(box.x);
          expect(inputBox.x+inputBox.width).toBeLessThanOrEqual(box.x+box.width);
          const bodyBox=await dialog.locator('.settings-body').boundingBox();
          expect(inputBox.y,`${label} above settings body`).toBeGreaterThanOrEqual(bodyBox.y-1);
          expect(inputBox.y+inputBox.height,`${label} behind settings footer`).toBeLessThanOrEqual(bodyBox.y+bodyBox.height+1);
        }
      }
      if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`qc-${theme}-${width}-${height}-${name.toLowerCase()}.png`)});
    }
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole('button',{name:'Settings',exact:true})).toBeFocused();
    await page.getByRole('button',{name:'Quick actions',exact:true}).click();
    const quick=page.getByRole('dialog',{name:'Quick actions',exact:true});
    await expect(quick.getByLabel('Find an action')).toBeFocused();
    expect(await quick.evaluate(el=>el.scrollWidth<=el.clientWidth+1)).toBe(true);
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button',{name:'Quick actions',exact:true})).toBeFocused();
  }
});

for(const theme of ['light','dark'])test(`report controls and metric values align in ${theme} mode`,async({page})=>{
  await setup(page);
  await page.getByLabel('Appearance').selectOption(theme);
  for(const name of ['Overview','Daily Orders','Monthly Orders']){
    await page.getByRole('button',{name,exact:true}).click();
    await expect(page.locator('.loading')).toHaveCount(0);
    if(name==='Daily Orders'){
      const positions=await page.locator('.daily-orders>.metrics>.metric').evaluateAll(items=>items.map(item=>item.querySelector('strong').getBoundingClientRect().y-item.getBoundingClientRect().y));
      expect(Math.max(...positions)-Math.min(...positions)).toBeLessThanOrEqual(1);
      const paddings=await page.locator('.daily-orders>.metrics>.metric').evaluateAll(items=>items.map(item=>getComputedStyle(item).paddingLeft));
      expect(new Set(paddings).size).toBe(1);
    }
    if(name==='Monthly Orders'){
      const month=await page.getByLabel('Monthly orders date').boundingBox();
      const download=await page.getByRole('button',{name:'Download Excel',exact:true}).boundingBox();
      expect(download.x).toBeGreaterThan(month.x+month.width);
      expect(Math.abs(month.y+month.height-download.y-download.height)).toBeLessThanOrEqual(1);
    }
    if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:path.join(process.env.TV_TRACKER_SCREENSHOTS,`refined-${theme}-${name.toLowerCase().replaceAll(' ','-')}.png`)});
  }
});
