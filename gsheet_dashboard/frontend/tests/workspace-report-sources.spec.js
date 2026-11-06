import {test, expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page) {
  const fixture=workspaceFixture(3);
  let mode='tracker';
  const uploads=[];
  await page.route('**/api/**',async route=>{
    const url=new URL(route.request().url()), name=url.pathname;
    let body=fixture.response(name);
    if(name==='/api/state')body={...body,sheet_url:'https://docs.google.com/spreadsheets/d/test-workbook/edit',report_workspace:{mode,row_count:3}};
    if(name==='/api/report-source'){mode=route.request().postDataJSON().mode;body={mode,publication:{synced:true}};}
    if(name==='/api/report-workspace')body={mode,row_count:3};
    if(name==='/api/sla-compare'){
      if(route.request().method()==='POST')uploads.push(route.request().postDataBuffer().toString());
      body={has_production:false,previews:[],orders:[],metrics:{}};
    }
    await route.fulfill({json:body});
  });
  await page.goto('/');
  return uploads;
}

test('daily and monthly reports require imported report mode',async({page})=>{
  await setup(page);
  for(const section of ['Daily Orders','Monthly Orders']){
    await page.getByRole('button',{name:section,exact:true}).click();
    await expect(page.getByText('Daily Orders and Monthly Orders are available in Import Excel report.',{exact:false})).toBeVisible();
    await expect(page.locator('.daily-orders')).toHaveCount(0);
  }
  await page.getByRole('button',{name:'Import Excel report',exact:true}).click();
  await expect(page.getByText('Daily Orders and Monthly Orders are available in Import Excel report.',{exact:false})).toHaveCount(0);
  await expect(page.getByRole('heading',{name:'Monthly production orders',exact:true})).toBeVisible();
});

test('every sidebar workspace has a link to the configured Google Sheet',async({page})=>{
  await setup(page);
  for(const section of ['Daily Orders','Monthly Orders','SLA Status','SLA Compare','Capacity Report','Changes','Captures']){
    await page.getByRole('button',{name:section,exact:true}).click();
    const link=page.locator('.workspace-context').getByRole('link',{name:'Google Sheet'});
    await expect(link).toHaveAttribute('href','https://docs.google.com/spreadsheets/d/test-workbook/edit');
    await expect(link).toHaveAttribute('target','_blank');
  }
});

test('SLA Compare accepts dropped report files and rejects other extensions',async({page})=>{
  const uploads=await setup(page);
  await page.getByRole('button',{name:'SLA Compare',exact:true}).click();
  await expect(page.getByText('No Production Report Uploaded')).toBeVisible();
  const workspace=page.getByRole('region',{name:'SLA Compare Workspace'});
  const transfer=await page.evaluateHandle(()=>{
    const value=new DataTransfer();
    value.items.add(new File(['Order Number,Status\n1,Cancelled'],'production.csv',{type:'text/csv'}));
    return value;
  });
  await workspace.dispatchEvent('dragenter',{dataTransfer:transfer});
  await expect(page.getByText('Drop production reports here to compare')).toBeVisible();
  await workspace.dispatchEvent('drop',{dataTransfer:transfer});
  await expect.poll(()=>uploads.length).toBe(1);
  expect(uploads[0]).toContain('production.csv');
  const invalid=await page.evaluateHandle(()=>{
    const value=new DataTransfer();value.items.add(new File(['text'],'invalid.txt'));return value;
  });
  await workspace.dispatchEvent('drop',{dataTransfer:invalid});
  await expect(page.getByRole('alert')).toContainText('Choose Excel');
  expect(uploads).toHaveLength(1);
});
