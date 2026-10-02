import React, {useEffect, useRef, useState} from 'react';
import {ArrowRight, Check, Command, Database, Download, FolderOpen, HardDrive, KeyRound, LoaderCircle, Monitor, Plug, Settings2, ShieldCheck, Upload, WifiOff, X} from 'lucide-react';

export class WorkspaceBoundary extends React.Component {
  state = {failed: false};
  static getDerivedStateFromError() { return {failed: true}; }
  render() {
    if (this.state.failed) return <div className="recovery-screen"><div className="brand-mark"><Monitor size={28}/></div><h1>Let’s reopen your workspace</h1><p>The interface encountered a problem. Your saved data is still on this computer.</p><button className="primary" onClick={()=>location.reload()}>Reload workspace</button></div>;
    return this.props.children;
  }
}

export function OfflineNotice({snapshot}) {
  return snapshot?.offline ? <div className="offline-notice" role="status"><WifiOff size={17}/><div><strong>Viewing a saved Google Sheets copy</strong><span>Last refreshed {new Date(snapshot.updated_at).toLocaleString()}. Reconnect to sync changes.</span></div></div> : null;
}

function Dialog({title, children, onClose, className=''}) {
  const ref=useRef();
  useEffect(()=>{const dialog=ref.current;dialog.showModal();return()=>dialog.close();},[]);
  return <dialog ref={ref} className={`studio-dialog ${className}`} onCancel={event=>{event.preventDefault();onClose();}} onClick={event=>{if(event.target===event.currentTarget)onClose();}}><div className="studio-dialog-heading"><div><span className="eyebrow">DATATRACE STUDIO</span><h2>{title}</h2></div><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={20}/></button></div>{children}</dialog>;
}

export function LocalWelcome({onImport}) {
  const desktop=!!window.desktop;
  return <section className="welcome-workspace">
    <div className="welcome-intro"><span className="welcome-tag"><span/>YOUR LOCAL WORKSPACE</span><h2>Clear work.<br/><span>Confident decisions.</span></h2><p>Keep your title production, daily performance, and saved captures in one focused workspace.</p><div className="welcome-actions"><button className="primary" onClick={()=>window.dispatchEvent(new Event('datatrace:settings'))}><Plug size={17}/>{desktop?'Connect your workspace':'Connection setup'}<ArrowRight size={16}/></button><button className="secondary" onClick={onImport}><Upload size={16}/>Import Excel or CSV</button></div><div className="local-assurance"><ShieldCheck size={16}/>Saved on this computer. Google Sheets when connected.</div></div>
    <div className="welcome-steps"><div className="welcome-steps-title"><Monitor size={20}/><strong>A workspace that works your way</strong></div>{[
      ['01','Connect once','Add your Google Sheet and TitleVision credentials in Connections.'],
      ['02','Capture with confidence','Run a fresh extraction or import an existing queue file.'],
      ['03','Keep everything in view','Review production, compare captures, and export your reports.'],
    ].map(([number,title,text])=><div className="welcome-step" key={number}><span>{number}</span><div><h3>{title}</h3><p>{text}</p></div></div>)}<div className="welcome-footnote"><HardDrive size={15}/>No hosting required <span>·</span> Google Sheets sync when online</div></div>
    <div className="capability-grid">{[[Database,'A reliable history','Your captures stay available across restarts.'],[WifiOff,'Useful offline','Read the last saved production report with its refresh time.'],[ShieldCheck,'Private by design','Desktop credentials are encrypted for your Windows account.']].map(([Icon,title,text])=><article key={title}><Icon size={22}/><h3>{title}</h3><p>{text}</p></article>)}</div>
  </section>;
}

function Connections({onClose,running}) {
  const [form,setForm]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[error,setError]=useState(''),[tab,setTab]=useState('connections');
  useEffect(()=>{window.desktop?.getSettings().then(value=>setForm({...value,password:''})).catch(e=>setError(e.message));return()=>{window.desktop?.discardSettings().catch(()=>{});};},[]);
  const update=(key,value)=>setForm(current=>({...current,[key]:value}));
  async function action(fn) {setBusy(true);setError('');setMessage('');try{await fn();}catch(e){setError(e.message.replace(/^Error invoking remote method '[^']+': Error: /,''));}finally{setBusy(false);}}
  async function save(event) {event.preventDefault();await action(async()=>{await window.desktop.saveSettings(form);setMessage('Settings saved. Reopening your workspace…');});}
  async function checkConnection() {await action(async()=>{const response=await fetch('/api/desktop/check-connection',{method:'POST',signal:AbortSignal.timeout(30000)});const value=await response.json();if(!response.ok)throw Error(value.error);setMessage(`Connected. ${value.orders.toLocaleString()} production orders are available.`);});}
  return <Dialog title="Connections & settings" onClose={()=>{if(!busy)onClose();}} className="settings-dialog">
    {!window.desktop?<div className="settings-body"><div className="settings-callout"><Monitor size={22}/><div><h3>Open DataTrace Studio for desktop settings</h3><p>The installed application includes secure credential storage, local backups, and background scheduling. This browser window is the development interface.</p></div></div><p className="muted">For web development, use the project’s .env.example and sync_config.json. Saved passwords and keys are never displayed here.</p></div>:!form?<div className="settings-body">{error?<p role="alert">{error}</p>:<p className="loading"><LoaderCircle className="spin"/>Loading settings…</p>}</div>:<form onSubmit={save}>
      <div className="settings-tabs" role="tablist" aria-label="Settings sections"><button type="button" role="tab" aria-selected={tab==='connections'} onClick={()=>setTab('connections')}><Plug size={16}/>Connections</button><button type="button" role="tab" aria-selected={tab==='workspace'} onClick={()=>setTab('workspace')}><HardDrive size={16}/>Workspace</button></div>
      <div className="settings-body" role="tabpanel">
      {tab==='connections'?<>
        <div className="settings-section"><div className="settings-section-heading"><div className="settings-section-icon"><Database size={20}/></div><div><h3>Google Sheets</h3><p>Your production source of truth</p></div><span className={`connection-pill ${form.googleConfigured?'ready':''}`}>{form.googleConfigured?'Configured':'Setup needed'}</span></div>
          <label>Spreadsheet URL or ID<input autoFocus value={form.spreadsheetId} onChange={e=>update('spreadsheetId',e.target.value)} placeholder="https://docs.google.com/spreadsheets/d/…" autoComplete="off"/></label>
          <div className="form-grid"><label>Full Title tracker tab<input value={form.fullTrackerTitle} onChange={e=>update('fullTrackerTitle',e.target.value)} required maxLength={100}/></label><label>Remaining Products tracker tab<input value={form.remainingTrackerTitle} onChange={e=>update('remainingTrackerTitle',e.target.value)} required maxLength={100}/></label></div>
          <div className="credential-row"><div><strong>Service-account key</strong><p>{form.serviceAccountEmail||'Import the JSON key from your Google Cloud project.'}</p></div><button type="button" className="secondary" disabled={busy} onClick={()=>action(async()=>{const value=await window.desktop.importServiceAccount();if(value){update('serviceAccountEmail',value.email);setMessage('Key selected. Save settings to apply it.');}})}><KeyRound size={16}/>{form.serviceAccountEmail?'Replace key':'Import key'}</button></div>
          {form.serviceAccountEmail&&<p className="field-help">Share the spreadsheet with this service-account email as Editor.</p>}
          <button type="button" className="text-button" disabled={busy||running} onClick={checkConnection}>Test saved Google Sheets connection</button>
        </div>
        <div className="settings-section"><div className="settings-section-heading"><div className="settings-section-icon"><Plug size={20}/></div><div><h3>TitleVision</h3><p>Secure queue extraction</p></div><span className={`connection-pill ${form.passwordSet?'ready':''}`}>{form.passwordSet?'Credentials saved':'Setup needed'}</span></div>
          <div className="form-grid"><label>Username<input value={form.username} onChange={e=>update('username',e.target.value)} autoComplete="username"/></label><label>Password<input type="password" value={form.password} onChange={e=>update('password',e.target.value)} placeholder={form.passwordSet?'Saved securely · leave blank to keep':'Enter your password'} autoComplete="new-password"/></label></div>
          <label>Queue URL<input type="url" value={form.queueUrl} onChange={e=>update('queueUrl',e.target.value)} required/></label>
          <p className="field-help">Extraction uses installed Microsoft Edge or Google Chrome. Internet and any required portal access are needed.</p>
        </div>
      </>:<>
        <div className="settings-section"><h3>Local data & recovery</h3><p className="field-help">Captures, pending syncs, and saved reports stay in your Windows profile. Backups exclude passwords and private keys.</p><code className="data-path">{form.dataPath}</code><div className="settings-actions"><button type="button" className="secondary" onClick={()=>action(()=>window.desktop.openDataFolder())}><FolderOpen size={16}/>Open data folder</button><button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{const value=await window.desktop.backup();if(value.saved)setMessage(`Backup saved: ${value.path}`);})}><Download size={16}/>Create backup</button><button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{const value=await window.desktop.restoreBackup();if(value.restored)setMessage('Workspace restored. Reopening…');})}><Upload size={16}/>Restore backup</button></div></div>
        <div className="settings-section"><h3>App behavior</h3><label className="check-row"><input type="checkbox" checked={form.closeToTray} onChange={e=>update('closeToTray',e.target.checked)}/>Keep running in the system tray when the window closes</label><label className="check-row"><input type="checkbox" checked={form.startAtLogin} onChange={e=>update('startAtLogin',e.target.checked)}/>Start DataTrace Studio when I sign in to Windows</label><p className="field-help">Scheduled extractions run while the app is open or in the tray and the computer is awake. Use Workspace → Quit to stop the app.</p></div>
        <div className="settings-section"><h3>Extraction browser</h3><p className="field-help">{form.browserDetected?'A supported browser was detected.':'Install Microsoft Edge or Google Chrome, or select its executable.'}</p><div className="browser-choice"><input aria-label="Browser executable" value={form.browserPath} readOnly placeholder="Automatically detect Edge or Chrome"/><button type="button" className="secondary" onClick={()=>action(async()=>{const value=await window.desktop.chooseBrowser();if(value)update('browserPath',value);})}>Choose browser</button><button type="button" className="text-button" onClick={()=>update('browserPath','')}>Use automatic</button></div></div>
      </>}
      {error&&<div className="notice error" role="alert">{error}</div>}{message&&<div className="notice success" role="status"><Check size={16}/>{message}</div>}
      </div><div className="settings-footer"><span><ShieldCheck size={15}/>Protected with Windows encryption</span><button type="button" className="secondary" onClick={onClose} disabled={busy}>Cancel</button><button className="primary" disabled={busy||running}>{busy?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>}Save settings</button></div>
    </form>}
  </Dialog>;
}

const PAGES=[['overview','Queue overview'],['sheets','Production data sheets'],['captures','Saved captures'],['daily','Daily Orders'],['monthly','Monthly report'],['changes','Sync changes'],['compare','Compare previews']];
export function DesktopTools({onNavigate,onImport,running}) {
  const [settings,setSettings]=useState(false),[commands,setCommands]=useState(false),[query,setQuery]=useState('');
  useEffect(()=>{
    const open=()=>setSettings(true);
    const keyboard=e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setQuery('');setCommands(value=>!value);}if((e.ctrlKey||e.metaKey)&&e.key===','){e.preventDefault();setSettings(true);}};
    const unsubscribe=window.desktop?.onCommand(command=>{if(command==='settings')open();if(command==='commands'){setQuery('');setCommands(true);}});
    window.addEventListener('datatrace:settings',open);window.addEventListener('keydown',keyboard);
    return()=>{unsubscribe?.();window.removeEventListener('datatrace:settings',open);window.removeEventListener('keydown',keyboard);};
  },[]);
  const options=[...PAGES.map(([id,label])=>({label,action:()=>onNavigate(id)})),{label:'Import Excel or CSV',action:onImport},{label:'Connections & settings',action:()=>setSettings(true)}].filter(item=>item.label.toLowerCase().includes(query.toLowerCase()));
  return <><button className="quick-command" aria-label="Quick actions" onClick={()=>{setQuery('');setCommands(true);}}><Command size={15}/><span>Quick actions</span><kbd>Ctrl K</kbd></button><button className="settings-button" aria-label="Connections & settings" title="Connections & settings (Ctrl+,)" onClick={()=>setSettings(true)}><Settings2 size={18}/></button>
    {settings&&<Connections onClose={()=>setSettings(false)} running={running}/>}
    {commands&&<Dialog title="Quick actions" onClose={()=>setCommands(false)} className="command-dialog"><div className="command-search"><Command size={19}/><input aria-label="Find an action" autoFocus placeholder="Where would you like to go?" value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&options[0]){e.preventDefault();setCommands(false);options[0].action();}}}/></div><div className="command-results">{options.map(item=><button key={item.label} onClick={()=>{setCommands(false);item.action();}}>{item.label}<ArrowRight size={15}/></button>)}{!options.length&&<p className="muted">No matching actions</p>}</div><div className="command-hint">Tab to move · Enter to open · Esc to close</div></Dialog>}
  </>;
}
