// Run with the packaged executable and ELECTRON_RUN_AS_NODE=1. Never logs into a portal.
const path=require('node:path');
const fs=require('node:fs');
const resources=path.join(path.dirname(process.execPath),'resources','extractor');
const puppeteer=require(path.join(resources,'node_modules','puppeteer-core'));
const {browserOptions}=require(path.join(resources,'browser_options.cjs'));
const browserPath=[process.env.PUPPETEER_EXECUTABLE_PATH,
  path.join(process.env['ProgramFiles(x86)']||'','Microsoft/Edge/Application/msedge.exe'),
  path.join(process.env.ProgramFiles||'','Google/Chrome/Application/chrome.exe'),
].find(file=>file&&fs.existsSync(file));
(async()=>{
  if(!browserPath)throw Error('Install Edge or Chrome before running the extraction smoke test.');
  const browser=await puppeteer.launch(browserOptions({...process.env,PUPPETEER_EXECUTABLE_PATH:browserPath,DATATRACE_HEADLESS:'true'}));
  try {
    const page=await browser.newPage();
    await page.setContent('<title>DataTrace extraction smoke test</title><main>Browser ready</main>');
    if(await page.title()!=='DataTrace extraction smoke test')throw Error('Browser page did not load.');
    console.log(JSON.stringify({passed:true,node:process.versions.node,browser:await browser.version(),source:'packaged Electron + packaged puppeteer-core',portalAccessed:false}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
