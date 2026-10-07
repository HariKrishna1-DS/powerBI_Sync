import React, {useEffect, useState} from 'react';
import {Cloud, LoaderCircle, LogIn, LogOut, RefreshCw, ShieldCheck} from 'lucide-react';

export default function SharedWorkspace({running}) {
  const [state,setState]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const [url,setUrl]=useState('https://qontoybecrqpbjzoajqf.supabase.co'),[key,setKey]=useState('');
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[workspaces,setWorkspaces]=useState([]);
  const [selected,setSelected]=useState(''),[result,setResult]=useState(null),[loaded,setLoaded]=useState(false);
  const [plan,setPlan]=useState(null),[reviewed,setReviewed]=useState(false),[stopped,setStopped]=useState(false);
  const [memberId,setMemberId]=useState(''),[memberRole,setMemberRole]=useState('owner'),[accessConfirmed,setAccessConfirmed]=useState(false),[workerStopped,setWorkerStopped]=useState(false);
  const member=workspaces.find(w=>w.id===selected);
  useEffect(()=>{let active=true;setBusy(true);Promise.all([window.desktop.getCloudState(),window.desktop.getSettings()]).then(async([status,settings])=>{
    if(!active)return;setState(status);setUrl(status.projectUrl);setEmail(status.email||'');setKey(settings.cloudConfig?.publishableKey||'');
    if(status.signedIn){const rows=await window.desktop.getCloudWorkspaces();if(active){setWorkspaces(rows);setLoaded(true);}}
  }).catch(e=>{if(active)setError(e.message);}).finally(()=>{if(active)setBusy(false);});return()=>{active=false;};},[]);
  async function action(work){setBusy(true);setError('');setMessage('');try{await work();}catch(e){setError(e.message.replace(/^Error invoking remote method '[^']+': Error: /,''));}finally{setBusy(false);}}
  async function signIn(){await action(async()=>{const credentials={email,password};setPassword('');setLoaded(false);const status=await window.desktop.signInCloud(credentials);setState(status);setWorkspaces(await window.desktop.getCloudWorkspaces());setLoaded(true);setMessage('Signed in. Your permitted workspaces are listed below.');});}
  return <section className="settings-section">
    <div className="settings-section-heading"><div className="settings-section-icon"><Cloud size={20}/></div><div><h3>Shared workspace</h3><p>One shared database for your team</p></div><span className={`connection-pill ${state?.signedIn?'ready':''}`}>{state?.signedIn?'Signed in':state?.configured?'Sign-in needed':'Setup needed'}</span></div>
    <div className={`notice ${state?.workspace?'success':'warning'}`}>{state?.workspace?`Connected to ${state.workspace.name}. Captures upload to the shared database; the office worker publishes Google Sheets reports.`:'Migration setup: production capture and publishing still use the existing Google Sheets connection. Shared processing will be enabled after the office worker and migration checks pass.'}</div>
    {!state&&!error?<p role="status">Loading shared workspace settings…</p>:<>
      <details open={!state?.configured}><summary>Project connection</summary>
        <label>Supabase project URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} autoComplete="off" disabled={busy}/></label>
        <label>Publishable API key<input type="password" value={key} onChange={e=>setKey(e.target.value)} autoComplete="off" placeholder="sb_publishable_…" disabled={busy}/></label>
        <p className="field-help">Use only the publishable key. Your account controls workspace access; an administrator API key is not required.</p>
        <button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{setState(await window.desktop.configureCloud({url:url.trim(),publishableKey:key.trim()}));setWorkspaces([]);setMessage('Project connection saved securely. Sign in with your Tv Tracker workspace account.');})}>Save project connection</button>
      </details>
      {state?.configured&&!state.signedIn&&<div className="settings-section">
        <h3>Sign in to Tv Tracker</h3><p className="field-help">Use an account created in this project’s Authentication section. Your Supabase dashboard login is separate.</p>
        <div className="form-grid"><label>Workspace email<input type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} disabled={busy}/></label><label>Workspace password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} disabled={busy} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();if(!busy&&password)signIn();}}}/></label></div>
        <button type="button" className="primary" disabled={busy||running||!email||!password} onClick={signIn}>{busy?<LoaderCircle size={16} className="spin"/>:<LogIn size={16}/>}Sign in</button>
      </div>}
      {state?.signedIn&&<div className="settings-section"><h3>{state.email}</h3><p className="field-help"><ShieldCheck size={14}/>Session credentials are protected by Windows encryption.</p>
        <div className="settings-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>action(async()=>{setWorkspaces(await window.desktop.getCloudWorkspaces());setLoaded(true);setSelected('');setResult(null);setMessage('Workspace permissions refreshed.');})}><RefreshCw size={16}/>Refresh workspaces</button><button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{const status=await window.desktop.signOutCloud();setState(status);setWorkspaces([]);setSelected('');setResult(null);setLoaded(false);setMessage(status.remoteRevoked?'Signed out on this PC.': 'Signed out on this PC. The server could not confirm session revocation; other PCs were not signed out.');})}><LogOut size={16}/>Sign out on this PC</button></div>
        {state.workspace&&<button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{await window.desktop.disconnectCloudWorkspace();})}>Disconnect this PC · saved uploads are retained</button>}
        {!!workspaces.length&&<><label htmlFor="shared-workspace-selection">Workspace</label><select id="shared-workspace-selection" value={selected} onChange={e=>{setSelected(e.target.value);setResult(null);setPlan(null);setReviewed(false);setStopped(false);setWorkerStopped(false);setMemberId('');setAccessConfirmed(false);}} disabled={busy}><option value="">Choose a workspace</option>{workspaces.map(workspace=><option key={workspace.id} value={workspace.id}>{workspace.name} · {workspace.role==='owner'?'Admin / Manager':'Limited access'}</option>)}</select>
        <div className="settings-actions"><button type="button" className="secondary" disabled={busy||!selected||running} onClick={()=>action(async()=>{setResult(await window.desktop.runCloudAction({workspace:selected,action:'inspect'}));})}>Check shared data</button>
        {workspaces.find(w=>w.id===selected)?.role==='owner'&&workspaces.find(w=>w.id===selected)?.mode==='shadow'&&<button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{setResult(await window.desktop.runCloudAction({workspace:selected,action:'worker'}));})}>Run validation worker</button>}
        {member?.mode==='active'&&<button type="button" className="primary" disabled={busy||running} onClick={()=>action(async()=>{await window.desktop.joinCloudWorkspace({id:selected,officeWorker:false});setMessage('Connecting to shared workspace…');})}>Use this shared workspace</button>}
        {member?.mode==='active'&&member.role==='owner'&&<button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{await window.desktop.joinCloudWorkspace({id:selected,officeWorker:true});})}>Run office worker on this PC</button>}</div>
        {member?.role==='owner'&&<details className="settings-section"><summary>Team access</summary>
          <p className="field-help">Create or invite each admin/manager in Supabase Authentication first. Paste that user’s UUID here. Every admitted manager gets full app access, including capture, reports, configuration and team management. The registered office PC remains the single Sheets publisher.</p>
          <label>Registered user UUID<input value={memberId} onChange={e=>{setMemberId(e.target.value);setAccessConfirmed(false);}} autoComplete="off" disabled={busy}/></label>
          <label>Workspace permission<select value={memberRole} onChange={e=>{setMemberRole(e.target.value);setAccessConfirmed(false);}} disabled={busy}><option value="owner">Admin / Manager · full app access</option><option value="remove">Remove workspace access</option></select></label>
          <label className="check-row"><input type="checkbox" checked={accessConfirmed} onChange={e=>setAccessConfirmed(e.target.checked)} disabled={busy}/>I verified this user’s identity and the permission above.</label>
          <button className="secondary" type="button" disabled={busy||running||!accessConfirmed||!memberId.trim()} onClick={()=>action(async()=>{await window.desktop.setCloudMember({workspace:selected,user:memberId.trim(),role:memberRole==='remove'?null:memberRole});setAccessConfirmed(false);setMessage('Workspace access saved. The user can refresh workspaces after signing in.');})}>Save team access</button>
        </details>}
        {member?.role==='owner'&&member.mode==='active'&&<details className="settings-section"><summary>Recover office worker on a replacement PC</summary>
          <p className="field-help">Restore the latest portable workspace backup and configure Google Sheets first. Recovery keeps the registered worker identity and any restored pending job. It never cancels a job or starts another publisher automatically.</p>
          <label className="check-row"><input type="checkbox" checked={workerStopped} onChange={e=>setWorkerStopped(e.target.checked)} disabled={busy}/>The previous office worker is stopped and cannot restart.</label>
          <button className="secondary" type="button" disabled={busy||running||!workerStopped} onClick={()=>action(async()=>{await window.desktop.runCloudAction({workspace:selected,action:'recover-worker',legacy_stopped:workerStopped});setWorkerStopped(false);setMessage('Recovered worker identity verified. Use Run office worker on this PC to resume.');})}>Verify restored worker recovery</button>
        </details>}
        {member?.role==='owner'&&<details className="settings-section"><summary>Production migration · office PC</summary>
          <p className="field-help">Save this PC’s Google Sheets connection first. Review all production orders and the next preview number. Activation binds publishing to this PC and blocks older direct writers.</p>
          <div className="settings-actions">
            {member.mode==='shadow'&&<button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{setPlan(await window.desktop.runCloudAction({workspace:selected,action:'review'}));setReviewed(false);setStopped(false);setMessage('Migration snapshot encrypted and verified. Review the counts before activation.');})}>Review production baseline</button>}
            <button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{const saved=await window.desktop.runCloudAction({workspace:selected,action:'migration-status'});setPlan(saved.plan);setReviewed(false);setStopped(false);if(!saved.plan)setMessage('No saved migration review for this workspace on this PC.');})}>Resume saved review</button>
          </div>
          {plan&&<div role="region" aria-label="Migration review">
            <p>Snapshot {plan.created.slice(0,10)} · Next shared capture: preview{plan.next_sequence} · {plan.state==='active'?'Activated':'Awaiting review'}</p>
            <table className="migration-counts"><thead><tr><th>Production tracker</th><th>Orders</th></tr></thead><tbody>{plan.counts.map(item=><tr key={item.tab}><td>{item.tab}</td><td>{item.orders.toLocaleString()}</td></tr>)}</tbody></table>
            <p className="field-help">All columns are retained. Duplicate identities stop migration. Existing production rows are imported without recalculating their timing.</p>
            {plan.state!=='active'&&<><label className="check-row"><input type="checkbox" checked={reviewed} disabled={busy} onChange={e=>setReviewed(e.target.checked)}/>I reviewed these counts and the encrypted migration snapshot.</label>
            <label className="check-row"><input type="checkbox" checked={stopped} disabled={busy} onChange={e=>setStopped(e.target.checked)}/>All older captures and publishing jobs have stopped on every PC.</label>
            <button type="button" className="primary" disabled={busy||running||!reviewed||!stopped} onClick={()=>action(async()=>{setPlan(await window.desktop.runCloudAction({workspace:selected,action:'activate',plan:plan.id,reviewed,legacy_stopped:stopped}));setWorkspaces(await window.desktop.getCloudWorkspaces());setMessage('Shared workspace activated. Use Run office worker on this PC to start publishing.');})}>Activate reviewed workspace</button></>}
          </div>}
        </details>}</>}
        {result&&<p role="status">Revision {result.revision} · {result.orders.toLocaleString()} shared orders · {result.worker?`Worker: ${result.worker.state}`:'Data verified'}. {result.mode==='active'?`Sheets published revision: ${result.published_revision}.`:'Validation mode does not publish to Sheets.'}</p>}
        {loaded&&!workspaces.length&&<><p className="field-help">For the first office PC, create the shared workspace once. Other team members should wait for owner-granted access and then refresh.</p><button type="button" className="secondary" disabled={busy||running} onClick={()=>action(async()=>{const created=await window.desktop.createCloudWorkspace();setWorkspaces(await window.desktop.getCloudWorkspaces());setSelected(created.id);setMessage('Validation workspace is ready. Production data has not been imported.');})}>Create the first shared workspace</button></>}
      </div>}
    </>}
    {error&&<div className="notice error" role="alert">{error}</div>}{message&&<div className="notice success" role="status">{message}</div>}
  </section>;
}
