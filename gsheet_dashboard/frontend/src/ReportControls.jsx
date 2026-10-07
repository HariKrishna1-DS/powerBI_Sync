import React, {useEffect, useState} from 'react';
import {Dialog} from './DesktopExperience';
import {api} from './workspaceUtils';

export default function ReportControls({mode, running, open, setOpen, onChanged, onBusy, workspaceState}) {
  const [settings,setSettings]=useState({}),[files,setFiles]=useState([]),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[replaceAll,setReplaceAll]=useState(false);
  useEffect(()=>{api('/api/report-workspace').then(setSettings).catch(e=>setMessage(e.message));},[open]);
  useEffect(()=>{if(workspaceState)setSettings(workspaceState);},[workspaceState]);
  useEffect(()=>{if(!open)return;const timer=setInterval(()=>api('/api/report-workspace').then(setSettings).catch(()=>{}),2000);return()=>clearInterval(timer);},[open]);
  useEffect(()=>{if(settings.publication_state==='synced')setMessage('Google Sheets reports updated.');if(settings.publication_state==='error')setMessage(`Report saved locally. Sheets update needs retry: ${settings.sync_error}`);},[settings.publication_state,settings.sync_error]);
  async function apply(path, options) {
    setBusy(true);onBusy?.(true);setMessage('');
    try {
      const result=await api(path,{...options,timeoutMs:180000});
      const next=await api('/api/report-workspace');setSettings(next);
      await onChanged(next);
      const publication=result.publication||result;
      const replaced=result.replaced_files?.length?`Replaced ${result.replaced_files.join(', ')}. `:'';
      setMessage(replaced+(publication.queued?'Report saved locally. Google Sheets update is queued.':publication.synced?'Reports saved and Google Sheets updated.':`Report saved locally. Google Sheets update needs retry: ${publication.sync_error||next.sync_error}`));
      setFiles([]);setReplaceAll(false);
    } catch(e) {setMessage(e.message);} finally {setBusy(false);onBusy?.(false);}
  }
  function choose(value) {
    if(value==='excel'&&!settings.row_count){setOpen(true);return;}
    apply('/api/report-source',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:value})});
  }
  function upload() {
    const body=new FormData();files.forEach(file=>body.append('files',file));body.append('replace_all',String(replaceAll));
    apply('/api/report-import',{method:'POST',body});
  }
  return <>
    <div className="report-mode" role="group" aria-label="Report source">
      <button disabled={busy} className={mode==='tracker'?'active':''} aria-pressed={mode==='tracker'} onClick={()=>choose('tracker')}>Tracker report</button>
      <button disabled={busy} className={mode==='excel'?'active':''} aria-pressed={mode==='excel'} onClick={()=>choose('excel')}>Import Excel report</button>
    </div>
    {(message||settings.sync_error||['pending','working'].includes(settings.publication_state))&&!open&&<button className="text-button" onClick={()=>setOpen(true)} title={message||settings.sync_error}>{settings.sync_error?'Sheets update pending':['pending','working'].includes(settings.publication_state)?'Sheets updating':'Report details'}</button>}
    {open&&<Dialog title="Import Excel reports" onClose={()=>{if(!busy)setOpen(false);}}>
      <div className="dialog-content">
        <p>Upload one or several workbooks. Every order worksheet and every status is included. Uploading the same filename again replaces its previous rows, including updated statuses and newly added orders. Other saved files are kept.</p>
        <label className="report-file-picker">Excel or CSV files<input type="file" multiple accept=".xlsx,.csv" disabled={busy} onChange={e=>{setFiles(Array.from(e.target.files||[]));e.target.value='';}}/></label>
        {!!files.length&&<ul className="report-upload-list">{files.map((file,index)=><li key={`${file.name}-${index}`}><span>{file.name}</span><button className="secondary" disabled={busy} onClick={()=>setFiles(current=>current.filter((_,i)=>i!==index))}>Remove selection</button></li>)}</ul>}
        {!!settings.row_count&&<label className="slicer-item report-replace-all"><input type="checkbox" checked={replaceAll} disabled={busy} onChange={e=>setReplaceAll(e.target.checked)}/>Replace all saved files with this upload</label>}
        <p>Importing selects the Excel report for all dashboards and publishes it to Google Sheets. Tracker report restores your tracker data. The Sheet includes seven report tabs; source/history tabs are kept hidden for recovery.</p>
        <div className="monthly-actions"><button className="primary" disabled={busy||!files.length} onClick={upload}>{busy?'Updating reports…':'Import and update reports'}</button><button className="secondary" disabled={busy} onClick={()=>apply('/api/report-publish',{method:'POST'})}>Publish current report</button></div>
        {settings.row_count>0&&<><div className="section-heading"><h3>Saved files: {settings.row_count.toLocaleString()} unique orders</h3><button className="secondary" disabled={busy} onClick={()=>apply('/api/report-remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({all:true})})}>Remove all files</button></div><p className="muted">Repeated uploads are allowed. For duplicate Order Numbers, the latest uploaded file wins. Removing all files leaves an empty Excel report. Select Tracker report to view tracker data.</p></>}
        {settings.imports?.map(file=><div className="report-saved-file" key={file.name}><div><strong>{file.name}</strong><p>{file.rows.toLocaleString()} rows / {file.worksheets} worksheets</p>{file.legacy&&<p className="muted">Upload the original files together once to manage this older batch as individual files.</p>}</div><button className="secondary" disabled={busy} onClick={()=>apply('/api/report-remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({file:file.name})})}>Remove file</button></div>)}
        {settings.files?.map((file,index)=><p className="muted" key={index}>{file.file} / {file.sheet}: {file.rows} rows{file.duplicates?` / ${file.duplicates} duplicate orders replaced`:''}</p>)}
        {!settings.row_count&&<p className="muted">No Excel files saved. Select files to create an Excel report.</p>}
        {message&&<p role="status" className="notice">{message}</p>}
      </div>
    </Dialog>}
  </>;
}
