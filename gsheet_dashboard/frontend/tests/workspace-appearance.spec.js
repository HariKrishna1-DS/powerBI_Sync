import {test,expect} from '@playwright/test';
import {workspaceFixture} from './workspace-fixture.js';

for(const theme of ['light','dark'])test(`workspace appearance is consistent in ${theme} mode`,async({page})=>{
  const fixture=workspaceFixture(12),errors=[];
  fixture.rows[0].Status='Completed and Delivered';
  page.on('pageerror',error=>errors.push(error.message));
  await page.addInitScript(value=>localStorage.setItem('tv-tracker-theme',JSON.stringify(value)),theme);
  await page.route('**/api/**',async route=>{
    const name=new URL(route.request().url()).pathname;
    let body=fixture.response(name);
    if(name==='/api/state')body={...body,sheet_url:'https://docs.google.com/spreadsheets/d/example/edit',report_workspace:{mode:'excel',row_count:12}};
    if(name==='/api/daily-orders')body={mode:'excel',source:'Imported Excel',selected_date:'2026-10-05',rows:[{Date:'2026-10-05',Received:12,Completed:1,Clarification:0,Cancelled:0,'Vendor Pending':0,'In-House Pending':11,'SLA OnTime':0,Missing:0,columns:fixture.columns,rows:fixture.rows,sla_rows:[],Previews:[]}]};
    if(name==='/api/report-workspace')body={mode:'excel',row_count:12};
    if(name==='/api/capacity-report')body={month:'2026-10',source:'Imported Excel',capacity:700,extended_capacity:750,columns:['Date','Received','Completed','Clarification','Cancelled','Vendor Pending','In-House Pending','Capacity','Ext capacity'],monthly:[{Date:'2026-10',Received:12,Completed:3}],daily:[{Date:'2026-10-05',Received:12,Completed:3}]};
    if(name==='/api/sla-status')body={as_of:'2026-10-05',source:'Saved capture',columns:fixture.columns,rows:fixture.rows,previews:fixture.previews,summary:[{Status:'Search In Progress','Future SLA':4,'Negative SLA':4,'Today SLA':4,'Grand Total':12}],summary_columns:['Status','Future SLA','Negative SLA','Today SLA','Grand Total'],totals:{Status:'Grand Total','Future SLA':4,'Negative SLA':4,'Today SLA':4,'Grand Total':12},excluded_rows:[],excluded_count:0};
    if(name==='/api/sla-compare')body={has_production:false,orders:[],previews:fixture.previews,metrics:{}};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('data-theme',theme);
  for(const [title,view] of [['Daily Orders','daily'],['Monthly Orders','monthly'],['SLA Status','sla'],['SLA Compare','slaCompare'],['Capacity Report','capacity'],['Changes','changes'],['Captures','captures']]){
    await page.getByRole('button',{name:title,exact:true}).click();
    await expect(page.locator('.workspace')).toHaveAttribute('data-view',view);
    await expect(page.locator('.workspace-loading')).toHaveCount(0);
    await expect(page.locator('.page-heading h1')).toBeVisible();
    await expect(page.locator('.page-heading h1')).toHaveCSS('font-size','30px');
    await expect(page.locator('.topbar .secondary').first()).toHaveCSS('border-radius','10px');
    await expect(page.locator('.sidebar .nav-item[aria-current="page"]')).toHaveCount(1);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    if(view==='daily')await expect(page.locator('.completed-order-row td').first()).toHaveCSS('background-color','rgb(255, 255, 153)');
    await page.screenshot({path:`test-results/ui-${view}-${theme}.png`,animations:'disabled'});
  }
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Connections & settings'})).toBeVisible();
  await page.screenshot({path:`test-results/ui-settings-${theme}.png`,animations:'disabled'});
  await page.keyboard.press('Escape');
  await page.setViewportSize({width:800,height:900});
  await page.getByRole('button',{name:'Captures',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`test-results/ui-compact-${theme}.png`,animations:'disabled'});
  expect(errors).toEqual([]);
});
