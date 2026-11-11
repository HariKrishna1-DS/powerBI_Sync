import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

test('report titles and counts open only their missing orders in a popup',async({page})=>{
  const fixture=workspaceFixture(3);
  const full={'Order Number':'FULL-NEW',Product:'Full Title',Status:'Search In Progress'};
  const co={'Order Number':'CO-NEW',Product:'ClientReview',Status:'SearchFix'};
  let completed=false;
  await page.route('**/api/**',async route=>{
    const name=new URL(route.request().url()).pathname;
    let body=fixture.response(name);
    if(name==='/api/production-report')body={folder:'C:\\Reports',previews:fixture.previews,selected_preview_id:32};
    if(name==='/api/production-report/check'||name==='/api/production-report/proceed'){
      if(name.endsWith('proceed'))completed=true;
      body={preview_name:'preview32',fingerprint:'checked',columns:['Order Number','Product','Status'],rows:[full,co,{'Order Number':'ALREADY-PRESENT'}],unresolved:[],completed,downloads:[],reports:[{kind:'full',name:'Full Search.xlsx',sheet:'TV Orders',missing:1,existing:3,skipped:1,orders:[full]},{kind:'co',name:'C-O and Update.xlsx',sheet:'Sheet1',missing:1,existing:3,skipped:0,orders:[co]}]};
    }
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Production Report',exact:true}).click();
  await page.getByRole('button',{name:'Check folder & orders',exact:true}).click();
  await page.getByRole('button',{name:'Full Search: 1 missing orders',exact:true}).click();
  let dialog=page.getByRole('dialog',{name:'Full Search — missing orders'});
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('cell',{name:'FULL-NEW',exact:true})).toBeVisible();
  await expect(dialog.getByRole('cell',{name:'CO-NEW',exact:true})).toHaveCount(0);
  await expect(dialog.getByRole('cell',{name:'ALREADY-PRESENT',exact:true})).toHaveCount(0);
  await dialog.getByRole('textbox',{name:'Search report orders'}).fill('no match');
  await expect(dialog.getByText('No matching rows',{exact:true})).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('button',{name:'C-O and Update',exact:true}).click();
  dialog=page.getByRole('dialog',{name:'C-O and Update — missing orders'});
  await expect(dialog.getByRole('cell',{name:'CO-NEW',exact:true})).toBeVisible();
  await expect(dialog.getByRole('cell',{name:'FULL-NEW',exact:true})).toHaveCount(0);
  await page.screenshot({path:'test-results/production-report-popup.png',animations:'disabled'});
  await dialog.getByRole('button',{name:'Close dialog',exact:true}).click();
  await page.getByRole('button',{name:'Proceed — add missing orders',exact:true}).click();
  await page.getByRole('button',{name:'Full Search: 1 orders added',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Full Search — orders added'}).getByRole('cell',{name:'FULL-NEW',exact:true})).toBeVisible();
});
