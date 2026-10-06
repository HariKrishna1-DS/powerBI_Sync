// Owner-authorized synthetic acceptance. Secrets travel only through child stdin.
const {app,safeStorage}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {spawn}=require('node:child_process');
const {createVault}=require('./settings.cjs');
const {createCloudAuth}=require('./cloud-auth.cjs');
const root=path.resolve(__dirname,'..');
const profile=path.join(root,'.desktop-build','SupabasePilotProfile');
app.setPath('userData',profile);
app.whenReady().then(async()=>{
  const vault=createVault(path.join(profile,'settings.vault'),safeStorage);
  const settings=vault.read();
  const auth=createCloudAuth({read:()=>settings,write:()=>{throw Error('Refresh the pilot sign-in before running acceptance.');}});
  const accessToken=await auth.accessToken();
  const child=spawn(process.env.DATATRACE_PYTHON||'python',[path.join(root,'cloud_backend','live_acceptance.py')],{
    cwd:root,windowsHide:true,stdio:['pipe','pipe','pipe'],
    env:{...process.env,PYTHONPATH:[path.join(root,'.desktop-build','deps'),path.join(root,'gsheet_dashboard'),root].join(path.delimiter)}});
  child.stdin.end(JSON.stringify({config:settings.cloudConfig,accessToken}));
  child.stdout.pipe(process.stdout);
  child.stderr.pipe(process.stderr);
  child.on('error',()=>{console.error('Cannot start the acceptance engine.');app.exit(1);});
  child.on('exit',code=>app.exit(code||0));
}).catch(error=>{console.error(error.message);app.exit(1);});
