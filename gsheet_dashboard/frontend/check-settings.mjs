import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';

const browser = await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
try {
  const page = await browser.newPage({viewport:{width:1366,height:1000}});
  const failures=[];
  page.on('pageerror',error=>failures.push(error.message));
  await page.goto('http://127.0.0.1:8510/',{waitUntil:'domcontentloaded'});
  await page.getByRole('button',{name:'Quick actions',exact:true}).waitFor();
  await page.evaluate(()=>window.dispatchEvent(new Event('datatrace:settings')));
  const dialog=page.getByRole('dialog',{name:'Connections & settings'});
  await dialog.getByLabel('Spreadsheet URL or ID').waitFor();
  await dialog.getByLabel('Username',{exact:true}).fill('');
  assert.equal(await dialog.getByLabel('Password',{exact:true}).inputValue(),'');
  await dialog.getByLabel('Service-account JSON key').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{}')});
  await dialog.getByRole('alert').filter({hasText:'Choose a Google service-account JSON key.'}).waitFor();
  await page.screenshot({path:'../scratch/settings-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await dialog.getByRole('button',{name:'Save settings',exact:true}).scrollIntoViewIfNeeded();
  const bounds=await dialog.boundingBox();
  assert(bounds.x>=0 && bounds.x+bounds.width<=391,'Dialog should fit mobile width');
  assert.equal(await dialog.evaluate(element=>element.scrollWidth>element.clientWidth),false,'No horizontal overflow');
  await page.screenshot({path:'../scratch/settings-mobile.png',fullPage:true});
  assert.deepEqual(failures,[]);
  console.log('Settings form rendered on desktop/mobile; key validation and masked password passed.');
} finally {
  await browser.close();
}
