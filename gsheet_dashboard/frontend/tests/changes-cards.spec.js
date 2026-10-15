import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {workspaceFixture} from './workspace-fixture.js';

async function setup(page){
  const fixture=workspaceFixture(65),errors=[];
  const matched=fixture.rows.slice(0,61).map((row,index)=>({...row,'Comparison Status':index<40?'Unchanged':'Matched - changed'}));
  const missing=fixture.rows.slice(61,63).map(row=>({...row,'Comparison Status':'Missing'}));
  const added=fixture.rows.slice(63).map(row=>({...row,'Comparison Status':'Newly Added'}));
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
    const name=new URL(route.request().url()).pathname;
    if(name.startsWith('/api/')){
      let body=fixture.response(name);
      if(name==='/api/compare'){
        const request=route.request().postDataJSON(),empty=request.previous===30;
        body={previous:`preview${request.previous}`,latest:`preview${request.latest}`,method:'Matched by Order Number',
          record_columns:['Comparison Status',...fixture.columns],matched_rows:matched,
          unmatched_rows:empty?[]:[...missing,...added],
          record_counts:{matched:61,missing:empty?0:2,newly_added:empty?0:2,unchanged:40},
          added_columns:[],removed_columns:[]};
      }
      return route.fulfill({json:body});
    }
    const filename=path.join(process.cwd(),'dist',name==='/'?'index.html':name.slice(1));
    try{return route.fulfill({body:await readFile(filename),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});}
    catch{return route.fulfill({status:404,body:''});}
  });
  await page.goto('http://localhost:8510/');
  await page.getByRole('button',{name:'Changes',exact:true}).click();
  await expect(page.getByRole('button',{name:'Matched 61',exact:true})).toBeEnabled();
  return {fixture,errors,matched,missing,added};
}

test('each Changes card focuses its matching order table with daily-style controls',async({page})=>{
  const {matched,missing,added,errors}=await setup(page);
  for(const [key,name,rows] of [['matched','Matched',matched],['missing','Missing Previews',missing],['newly_added','Newly added',added],['unchanged','Unchanged',matched.slice(0,40)]]){
    const card=page.getByRole('button',{name:`${name} ${rows.length}`,exact:true});
    const section=page.locator(`#changes-orders-group-${key}`);
    await expect(card).toHaveAttribute('aria-controls',`changes-orders-group-${key}`);
    await card.click();
    await expect(section).toBeFocused();
    await expect(section.getByRole('heading',{name:`${name} · ${rows.length}`,exact:true})).toBeInViewport();
    await expect(section.locator('tbody tr')).toHaveCount(Math.min(rows.length,50));
    for(const row of rows.slice(0,50))await expect(section.getByRole('cell',{name:row['Order Number'],exact:true})).toBeVisible();
    await expect(section.getByRole('button',{name:'Filtered CSV',exact:true})).toBeEnabled();
    if(key==='matched'){
      await section.getByRole('button',{name:'Next page',exact:true}).click();
      await expect(section.locator('tbody tr')).toHaveCount(11);
      await expect(section.getByRole('cell',{name:matched[60]['Order Number'],exact:true})).toBeVisible();
    }
  }
  const unchanged=page.locator('#changes-orders-group-unchanged');
  await expect(unchanged).not.toContainText('Matched - changed');
  const addedTable=page.locator('#changes-orders-group-newly_added');
  await addedTable.getByRole('button',{name:'Sort Order Number',exact:true}).click();
  await addedTable.getByRole('button',{name:'Sort Order Number',exact:true}).click();
  await expect(addedTable.locator('tbody tr').first()).toContainText(added[1]['Order Number']);
  await page.getByRole('button',{name:'Newly added 2',exact:true}).focus();
  await page.keyboard.press('Enter');
  await expect(addedTable).toBeFocused();
  await page.emulateMedia({colorScheme:'dark'});
  await page.locator('.changes-metrics').screenshot({path:'test-results/changes-clickable-cards-dark.png'});
  expect(errors).toEqual([]);
});

test('Changes tables follow search and refresh when previews change, including zero counts',async({page})=>{
  const {added,errors}=await setup(page);
  await page.getByRole('textbox',{name:'Search rows',exact:true}).fill(added[0]['Order Number']);
  await expect(page.locator('#changes-orders-group-newly_added tbody tr')).toHaveCount(1);
  await expect(page.locator('#changes-orders-group-missing tbody tr')).toHaveCount(0);
  await expect(page.locator('#changes-orders-group-unchanged tbody tr')).toHaveCount(0);
  await page.getByRole('textbox',{name:'Search rows',exact:true}).fill('');
  await expect(page.locator('#changes-orders-group-newly_added tbody tr')).toHaveCount(2);
  await page.getByRole('combobox',{name:'Previous preview',exact:true}).selectOption('30');
  const card=page.getByRole('button',{name:'Newly added 0',exact:true});
  await expect(card).toBeEnabled();
  await card.click();
  await expect(page.locator('#changes-orders-group-newly_added')).toBeFocused();
  await expect(page.locator('#changes-orders-group-newly_added')).toContainText('No matching rows');
  await expect(page.locator('#changes-orders-group-missing tbody tr')).toHaveCount(0);
  expect(errors).toEqual([]);
});
