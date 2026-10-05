import {test, expect} from '@playwright/test';

test('slow state polling stays serial and sync posts without a state preflight', async ({page}) => {
  const preview={id:28,name:'preview28',created:'2026-10-01T04:20:00Z',source:'Test',
    columns:['Order Number','Task Name','Task Status','Product'],
    rows:[{'Order Number':'001','Task Name':'Search','Task Status':'Available','Product':'Full Title'}]};
  const job={running:false,stage:'Ready',result:null};
  let active=0, maxActive=0, syncPosts=0;
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/state'){
      active++;maxActive=Math.max(maxActive,active);
      await new Promise(resolve=>setTimeout(resolve,3000));
      active--;
      await route.fulfill({json:{previews:[{...preview,row_count:1}],job,schedule:{enabled:false,times:['09:00']},
        daily_completed_ids:[],capabilities:{automatic_statuses:true}}});
    }else if(path==='/api/sync'){
      syncPosts++;job.running=true;job.stage='Preparing Google Sheets sync';
      await route.fulfill({status:202,json:{accepted:true}});
    }else if(path==='/api/previews/28'){
      await route.fulfill({json:preview});
    }else if(path==='/api/live-sheets'){
      await route.fulfill({json:{preview_name:'preview28',sheets:{
        'All Products':preview,'Full Title':preview,'Remaining Products':{columns:preview.columns,rows:[]},
        'Status Report':{columns:['Status','Orders'],rows:[{Status:'Available',Orders:1}]}}}});
    }else await route.fulfill({json:{}});
  });
  await page.goto(process.env.DASHBOARD_TEST_URL || '/');
  const sync=page.getByRole('button',{name:'Retry preview28 sync',exact:true});
  await expect(sync).toBeEnabled({timeout:15000});
  await page.waitForTimeout(6500);
  expect(maxActive).toBe(1);
  await sync.click();
  await expect.poll(()=>syncPosts,{timeout:1000,intervals:[50]}).toBe(1);
  await expect(page.locator('.run-state')).toContainText(/Starting|Preparing Google Sheets sync/);
  await page.waitForTimeout(3500);
  expect(maxActive).toBe(1);
});
