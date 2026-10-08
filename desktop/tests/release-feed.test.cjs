const {test} = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const semver = require('semver');
const {GitHubProvider} = require('electron-updater/out/providers/GitHubProvider');
const {createUpdater, PRODUCTION_UPDATE_FEED} = require('../updater.cjs');

for (const [installed, latest] of [['1.0.1','1.0.2'],['1.0.2','1.0.3']]) {
  test(`${installed} discovers and installs production ${latest} through Latest, ignoring an older testing series`,async()=>{
    const paths=[];
    const updater=new EventEmitter();let provider,info,downloads=0,installs=0,prepared=0;
    const executor={request:async options=>{
      paths.push(options.path);
      if(options.path.endsWith('.atom'))return `<feed><entry><title>Testing 2.8.1</title><link href="https://github.com/HariKrishna1-DS/powerBI_Sync/releases/tag/v2.8.1"/><content>Testing</content></entry><entry><title>Tv Tracker ${latest}</title><link href="https://github.com/HariKrishna1-DS/powerBI_Sync/releases/tag/v${latest}"/><content>Production</content></entry></feed>`;
      if(options.path.endsWith('/latest'))return JSON.stringify({tag_name:`v${latest}`});
      if(options.path.endsWith(`/v${latest}/latest.yml`))return `version: ${latest}
path: Tv-Tracker-${latest}-x64.exe
sha512: fixture-checksum
files:
  - url: Tv-Tracker-${latest}-x64.exe
    sha512: fixture-checksum
    size: 123
`;
      throw Error('Unexpected update request: '+options.path);
    }};
    updater.setFeedURL=options=>{assert.deepEqual(options,PRODUCTION_UPDATE_FEED);provider=new GitHubProvider(options,{allowPrerelease:false,currentVersion:semver.parse(installed),fullChangelog:false},{executor,platform:'win32',isUseMultipleRangeRequest:false});};
    updater.checkForUpdates=async()=>{info=await provider.getLatestVersion();updater.emit(semver.gt(info.version,installed)?'update-available':'update-not-available',info);};
    updater.downloadUpdate=async()=>{downloads++;const files=provider.resolveFiles(info);assert.equal(files[0].url.href,`https://github.com/HariKrishna1-DS/powerBI_Sync/releases/download/v${latest}/Tv-Tracker-${latest}-x64.exe`);updater.emit('update-downloaded',info);};
    updater.quitAndInstall=(silent,restart)=>{assert.equal(silent,true);assert.equal(restart,true);installs++;};
    const controller=createUpdater({updater,enabled:true,version:installed,prepareInstall:async()=>{prepared++;}});
    const available=await controller.check();assert.equal(available.status,'available');assert.equal(available.currentVersion,installed);assert.equal(available.version,latest);
    assert.equal(downloads,0);assert.equal(installs,0);assert.ok(paths.includes('/HariKrishna1-DS/powerBI_Sync/releases/latest'));assert.ok(!paths.some(p=>p.includes('/download/v2.8.1/')));
    assert.equal((await controller.download()).status,'downloaded');assert.equal(installs,0);await controller.install();assert.equal(installs,1);assert.equal(prepared,1);
    assert.equal(updater.allowPrerelease,false);assert.equal(updater.allowDowngrade,false);
  });
}
