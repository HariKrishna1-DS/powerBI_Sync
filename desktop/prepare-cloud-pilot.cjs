// Prepare an isolated profile for live acceptance. Never opens the user's main vault.
const {app,safeStorage}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {createVault,DEFAULTS}=require('./settings.cjs');
const {validateCloudConfig}=require('./cloud-auth.cjs');
const root=path.resolve(__dirname,'..','.desktop-build');
const profile=path.join(root,'SupabasePilotProfile');
app.setName('Tv Tracker');
app.setPath('userData',profile);
app.whenReady().then(()=>{
  const config=validateCloudConfig(JSON.parse(fs.readFileSync(path.join(root,'supabase-client.json'),'utf8')));
  const vault=createVault(path.join(profile,'settings.vault'),safeStorage);
  const existing=vault.read();
  vault.write({...DEFAULTS,...existing,cloudConfig:config,closeToTray:false,startAtLogin:false});
  console.log('Isolated Supabase pilot profile prepared with Windows encryption.');
  app.quit();
}).catch(()=>{console.error('The encrypted pilot profile could not be prepared.');app.exit(1);});
