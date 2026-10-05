import {test, expect} from '@playwright/test';

test('data sheets reads all tracker rows even when an older preview is selected', async ({page}) => {
  const errors=[];
  page.on('pageerror', error=>errors.push(error.message));
  const captures=[{id:2,name:'preview2',created:'2026-10-02T03:30:00Z',source:'Capture',row_count:1},
                  {id:1,name:'preview1',created:'2026-10-01T03:30:00Z',source:'Capture',row_count:2}];
  const rows=[{'Order Number':'BASE','Product':'Full Title','Status':'Completed and Delivered'},
              {'Order Number':'A','Product':'Full Title','Status':'In Progress'},
              {'Order Number':'B','Product':'Current Owner','Status':'Search In Progress'}];
  const columns=['Order Number','Product','Status'];
  await page.route('**/api/**',async route=>{
    const path=new URL(route.request().url()).pathname;
    let body;
    if(path==='/api/state')body={previews:captures,job:{running:false,stage:'Ready'},schedule:{enabled:false,times:['09:00']},remaining_products:[]};
    else if(path.startsWith('/api/previews/'))body={...captures.find(p=>p.id===Number(path.split('/')[3])),columns,rows:[rows[2]]};
    else if(path==='/api/live-sheets')body={preview_name:'preview2',sheets:{'All Products':{columns,rows},'Full Title':{columns,rows:rows.slice(0,2)},'Remaining Products':{columns,rows:rows.slice(2)}}};
    else if(path==='/api/compare')body={record_columns:columns,matched_rows:[],unmatched_rows:[],added_columns:[],removed_columns:[],record_counts:{matched:0,missing:0,newly_added:0,unchanged:0},previous:'preview1',latest:'preview2'};
    else if(path==='/api/monthly-orders')body={rows:[],sla_error:null};
    else if(path==='/api/daily-orders')body={rows:[],selected_date:null};
    else body={};
    await route.fulfill({json:body});
  });
  await page.goto('/');
  await expect(page.locator('.metric').filter({hasText:'Visible orders'}).locator('strong')).toHaveText('3');
  await page.locator('.preview-select').filter({hasText:'preview1'}).click();
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.locator('.metric').filter({hasText:'Visible orders'}).locator('strong')).toHaveText('3');
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Status summary',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Data Sheets',exact:true}).click();
  await expect(page.getByText('Completed and Delivered').first()).toBeVisible();
  await page.getByRole('button',{name:'Daily Orders',exact:true}).click();
  await page.getByRole('button',{name:'Monthly report',exact:true}).click();
  expect(errors).toEqual([]);
});
