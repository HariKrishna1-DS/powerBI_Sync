// Owner-authorized synthetic acceptance. Secrets travel only through child stdin.
const {app,safeStorage}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createVault}=require('./settings.cjs');
const {createCloudAuth}=require('./cloud-auth.cjs');
const root=path.resolve(__dirname,'..');
const profile=path.join(root,'.desktop-build','SupabasePilotProfile');
// A separate helper profile avoids locking the live application's Chromium cache
// and its single-instance socket. Windows safeStorage still uses this user's key.
const helperProfile=path.join(root,'.desktop-build','SupabaseAcceptanceHelper');
fs.mkdirSync(helperProfile,{recursive:true});
// Preserve the profile's encrypted OS crypt binding; copy only this app's
// protected Local State locally. No key or credential is printed or uploaded.
fs.copyFileSync(path.join(profile,'Local State'),path.join(helperProfile,'Local State'));
app.setPath('userData',helperProfile);
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');
app.whenReady().then(async()=>{
  const vault=createVault(path.join(profile,'settings.vault'),safeStorage);
  const settings=vault.read();
  const auth=createCloudAuth({read:()=>settings,write:()=>{throw Error('Refresh the pilot sign-in before running acceptance.');}});
  const accessToken=await auth.accessToken();
  const script=process.argv.includes('--features')?'live_feature_acceptance.py':process.argv.includes('--publication')?'live_publication_acceptance.py':'live_acceptance.py';
  const child=spawn(process.env.DATATRACE_PYTHON||'python',[path.join(root,'cloud_backend',script)],{
    cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],
    env:{...process.env,PYTHONPATH:[path.join(root,'.desktop-build','deps'),path.join(root,'gsheet_dashboard'),root].join(path.delimiter)}});
  child.stdin.end(JSON.stringify({config:settings.cloudConfig,accessToken}));
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  child.on('error',()=>{console.error('Cannot start the acceptance engine.');app.exit(1);});
  child.on('exit',code=>app.exit(code||0));
}).catch(error=>{console.error(error.message);app.exit(1);});
