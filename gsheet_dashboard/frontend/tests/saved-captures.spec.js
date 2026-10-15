import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture';

async function setup(page,count=42){
  const fixture=workspaceFixture();
  const captures=Array.from({length:count},(_,i)=>({id:count-i,name:`preview${count-i}`,created:'2026-10-15T10:00:00Z',source:'Queue import',row_count:240}));
  let current=[...captures],fresh=false,failed=false;
  const requests=[];
  await page.route('**/api/**',async route=>{
    const req=route.request(),path=new URL(req.url()).pathname,body=req.postData()?req.postDataJSON():{};
    if(path==='/api/previews/delete'||path==='/api/workspace/reset'){
      requests.push({path,body});
      if(failed)return route.fulfill({status:503,json:{error:'The recovery copy could not be saved. No captures were deleted.'}});
      const ids=path==='/api/workspace/reset'?current.map(p=>p.id):body.ids;
      current=current.filter(p=>!ids.includes(p.id));
      if(path==='/api/workspace/reset')fresh=true;
      return route.fulfill({json:{deleted:ids,recovery_backup:'before-delete-test.zip',reset:fresh,next_preview:1}});
    }
    if(path==='/api/state')return route.fulfill({json:{...fixture.response(path),previews:current,report_workspace:{mode:fresh?'excel':'tracker',fresh_start:fresh,enabled:!fresh}}});
    if(path.startsWith('/api/previews/'))return route.fulfill({json:{...current.find(p=>p.id===Number(path.split('/')[3])),columns:fixture.columns,rows:fixture.rows}});
    if(fresh&&path==='/api/live-sheets')return route.fulfill({json:{mode:'excel',sheets:{Overview:{rows:[],columns:[]}},reports:{}}});
    return route.fulfill({json:fixture.response(path,body)});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'View all saved captures',exact:true}).click();
  return {requests,fail:()=>{failed=true;}};
}

test('all captures can be maximized, searched and opened',async({page})=>{
  await setup(page);
  const dialog=page.getByRole('dialog',{name:'Saved captures',exact:true});
  await expect(dialog.locator('tbody tr')).toHaveCount(42);
  await dialog.getByRole('button',{name:'Maximize saved captures',exact:true}).click();
  await expect(dialog).toHaveClass(/capture-manager-maximized/);
  const bounds=await dialog.boundingBox();expect(bounds.width).toBeGreaterThan(1380);expect(bounds.height).toBeGreaterThan(950);
  await dialog.getByLabel('Search all saved captures').fill('preview1');
  await expect(dialog.locator('tbody tr')).toHaveCount(11);
  await dialog.getByRole('button',{name:'Open preview1',exact:true}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByLabel('Selected capture',{exact:true})).toHaveValue('1');
  await page.getByRole('button',{name:'Manage captures',exact:true}).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button',{name:'Manage captures',exact:true})).toBeFocused();
});

test('bulk selection survives filters and cancellation never deletes',async({page})=>{
  const {requests}=await setup(page,12);
  const dialog=page.getByRole('dialog',{name:'Saved captures',exact:true});
  await dialog.getByLabel('Select preview12',{exact:true}).check();
  await dialog.getByLabel('Search all saved captures').fill('preview1');
  await dialog.getByLabel('Select all visible captures',{exact:true}).check();
  await dialog.getByRole('button',{name:'Delete selected (4)',exact:true}).click();
  await dialog.getByRole('button',{name:'Cancel',exact:true}).click();
  expect(requests).toHaveLength(0);
  await dialog.getByRole('button',{name:'Delete selected (4)',exact:true}).click();
  await dialog.getByRole('button',{name:'Delete captures',exact:true}).click();
  await expect(dialog.getByText('8 saved captures',{exact:true})).toBeVisible();
  expect(requests[0].body.ids).toEqual([12,11,10,1]);
  await dialog.getByLabel('Search all saved captures').fill('');
  await expect(dialog.locator('tbody tr')).toHaveCount(8);
});

test('failed bulk backup retains captures and selection for retry',async({page})=>{
  const fixture=await setup(page,3);fixture.fail();
  const dialog=page.getByRole('dialog',{name:'Saved captures',exact:true});
  await dialog.getByLabel('Select all visible captures',{exact:true}).check();
  await dialog.getByRole('button',{name:'Delete selected (3)',exact:true}).click();
  await dialog.getByRole('button',{name:'Delete captures',exact:true}).click();
  await expect(dialog.getByRole('alert')).toContainText('No captures were deleted');
  await expect(dialog.locator('tbody tr')).toHaveCount(3);
  await expect(dialog.getByLabel('Select preview3',{exact:true})).toBeChecked();
});

test('reset clears previews and imported reports and displays a fresh empty workspace',async({page})=>{
  const {requests}=await setup(page,3);
  const dialog=page.getByRole('dialog',{name:'Saved captures',exact:true});
  await dialog.getByRole('button',{name:'Start new report',exact:true}).click();
  await expect(dialog).toContainText('Your Google Sheet and connection settings stay as they are');
  await dialog.getByRole('button',{name:'Reset local workspace',exact:true}).click();
  await expect(dialog.getByText('0 saved captures',{exact:true})).toBeVisible();
  await expect(dialog).toContainText('Your new preview history starts here');
  expect(requests[0].body.confirmation).toBe('RESET LOCAL WORKSPACE');
  await dialog.getByRole('button',{name:'Close dialog',exact:true}).click();
  await expect(page.getByText('New local report ready. The next capture will be preview1.',{exact:false})).toBeVisible();
  await expect(page.getByText('Clear work.',{exact:false})).toBeVisible();
});

test('capture manager fits a short desktop window in dark mode',async({page})=>{
  await page.setViewportSize({width:1280,height:620});
  await page.addInitScript(()=>localStorage.setItem('tv-tracker-theme','dark'));
  await setup(page);
  const dialog=page.getByRole('dialog',{name:'Saved captures',exact:true});
  await expect(dialog.getByRole('button',{name:'Start new report',exact:true})).toBeInViewport();
  await expect(dialog.getByRole('button',{name:'Close dialog',exact:true})).toBeInViewport();
  await dialog.getByRole('button',{name:'Maximize saved captures',exact:true}).click();
  await expect(dialog.getByRole('button',{name:'Start new report',exact:true})).toBeInViewport();
  if(process.env.TV_TRACKER_SCREENSHOTS)await page.screenshot({path:`${process.env.TV_TRACKER_SCREENSHOTS}/capture-manager-dark.png`});
});
