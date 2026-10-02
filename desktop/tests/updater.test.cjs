const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {createUpdater} = require('../updater.cjs');

function fixture(options={}) {
  const updater = new EventEmitter(); let installs=0, checks=0, downloads=0, prepared=0;
  updater.checkForUpdates = async () => {checks++; updater.emit('update-available',{version:'2.3.0'});};
  updater.downloadUpdate = async () => {downloads++;updater.emit('download-progress',{percent:42});updater.emit('update-downloaded',{version:'2.3.0'});};
  updater.quitAndInstall = (silent, restart) => {assert.equal(silent,false);assert.equal(restart,true);installs++;};
  const states=[];
  const controller=createUpdater({updater,enabled:true,version:'2.2.0',notify:s=>states.push(s),prepareInstall:async()=>{prepared++;},...options});
  return {updater,controller,states,counts:()=>({checks,downloads,installs,prepared})};
}
test('checking and downloading never install; installation is explicit and prepared',async()=>{
  const f=fixture();assert.equal(f.updater.autoDownload,false);assert.equal(f.updater.autoInstallOnAppQuit,false);
  assert.equal(f.updater.allowDowngrade,false);assert.equal(f.updater.allowPrerelease,false);
  assert.equal((await f.controller.check()).status,'available');assert.equal(f.counts().downloads,0);
  assert.equal((await f.controller.download()).status,'downloaded');assert.equal(f.counts().installs,0);
  assert.ok(f.states.some(s=>s.percent===42));await f.controller.install();await f.controller.install();
  assert.deepEqual(f.counts(),{checks:1,downloads:1,installs:1,prepared:1});
});
test('active work blocks installation and allows retry without losing the download',async()=>{
  let busy=true;const f=fixture({prepareInstall:async()=>{if(busy)throw Error('A job is running.');}});
  await f.controller.check();await f.controller.download();
  assert.equal((await f.controller.install()).status,'downloaded');assert.equal(f.counts().installs,0);
  busy=false;await f.controller.install();assert.equal(f.counts().installs,1);
});
test('network, missing release, rate limits and verification failures are safe and retryable',async()=>{
  for(const message of ['ENOTFOUND secret-token','404 private-url','403 token','sha512 mismatch']){
    const f=fixture();const original=f.updater.checkForUpdates;
    f.updater.checkForUpdates=async()=>{throw Error(message);};
    const failed=await f.controller.check();assert.equal(failed.status,'error');assert.ok(!failed.message.includes('secret-token'));
    await f.controller.download();await f.controller.install();assert.equal(f.counts().installs,0);
    f.updater.checkForUpdates=original;assert.equal((await f.controller.check()).status,'available');
  }
});
test('concurrent clicks share the in-flight operation and cannot start installation early',async()=>{
  const f=fixture();let release;f.updater.checkForUpdates=()=>new Promise(resolve=>{release=()=>{f.updater.emit('update-available',{version:'2.3.0'});resolve();};});
  const checking=f.controller.check();assert.equal((await f.controller.check()).status,'checking');
  await f.controller.download();assert.equal(f.counts().downloads,0);release();await checking;
  let finish;f.updater.downloadUpdate=()=>new Promise(resolve=>{finish=()=>{f.updater.emit('update-downloaded',{version:'2.3.0'});resolve();};});
  const downloading=f.controller.download();assert.equal((await f.controller.check()).status,'downloading');
  await f.controller.install();assert.equal(f.counts().installs,0);finish();await downloading;
});
test('development mode never accesses the feed; up-to-date is a distinct result',async()=>{
  const f=fixture({enabled:false});await f.controller.check();await f.controller.download();await f.controller.install();
  assert.deepEqual(f.counts(),{checks:0,downloads:0,installs:0,prepared:0});assert.equal(f.controller.state().status,'unsupported');
  const g=fixture();g.updater.checkForUpdates=async()=>g.updater.emit('update-not-available');assert.equal((await g.controller.check()).status,'current');
});
test('download verification failure requires a fresh check and cannot install',async()=>{
  const f=fixture();await f.controller.check();f.updater.downloadUpdate=async()=>{throw Error('sha512 mismatch');};
  assert.equal((await f.controller.download()).status,'error');await f.controller.install();assert.equal(f.counts().installs,0);
  assert.match(f.controller.state().message,/verification failed/);
});
test('installer launch error restores the engine after shutdown',async()=>{
  let recovered=0;const f=fixture({recoverInstall:async()=>{recovered++;}});
  await f.controller.check();await f.controller.download();
  f.updater.quitAndInstall=()=>f.updater.emit('error',Error('installer failed'));
  await f.controller.install();await new Promise(resolve=>setImmediate(resolve));
  assert.equal(recovered,1);assert.equal(f.controller.state().status,'error');
});
