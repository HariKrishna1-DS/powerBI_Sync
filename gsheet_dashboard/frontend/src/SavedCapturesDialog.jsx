import React, {useDeferredValue, useEffect, useMemo, useRef, useState} from 'react';
import {FileSpreadsheet, LoaderCircle, Maximize2, Minimize2, RotateCcw, Search, Trash2} from 'lucide-react';
import {Dialog} from './DesktopExperience';
import {IconButton} from './workspaceUtils';
import './savedCaptures.css';

const captureDate=value=>value?new Date(value).toLocaleString():'Date unavailable';

export default function SavedCapturesDialog({previews,selected,busy,onClose,onSelect,onDeleteMany,onReset}) {
  const [query,setQuery]=useState(''),[checked,setChecked]=useState(new Set()),[maximized,setMaximized]=useState(false);
  const [confirmation,setConfirmation]=useState(null),[working,setWorking]=useState(false),[error,setError]=useState('');
  const selectAll=useRef(null),deferred=useDeferredValue(query).trim().toLowerCase();
  const items=useMemo(()=>previews.filter(item=>`${item.name} ${captureDate(item.created)} ${item.source||''} ${item.row_count}`.toLowerCase().includes(deferred)),[previews,deferred]);
  const selectedIds=previews.filter(item=>checked.has(item.id)).map(item=>item.id);
  const allChecked=items.length>0&&items.every(item=>checked.has(item.id));
  useEffect(()=>{if(selectAll.current)selectAll.current.indeterminate=!allChecked&&items.some(item=>checked.has(item.id));},[allChecked,items,checked]);
  const blocked=busy||working;
  function toggle(id){setChecked(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next;});setConfirmation(null);}
  function toggleAll(){setChecked(current=>{const next=new Set(current);items.forEach(item=>allChecked?next.delete(item.id):next.add(item.id));return next;});setConfirmation(null);}
  async function confirm(){
    setWorking(true);setError('');
    try{
      if(confirmation.kind==='reset'){await onReset();setChecked(new Set());setQuery('');}
      else {await onDeleteMany(confirmation.ids);setChecked(current=>new Set([...current].filter(id=>!confirmation.ids.includes(id))));}
      setConfirmation(null);
    }catch(error){setError(error.message);}finally{setWorking(false);}
  }
  return <Dialog title="Saved captures" className={`capture-manager ${maximized?'capture-manager-maximized':''}`} onClose={()=>{if(!working)onClose();}}
    actions={<IconButton title={maximized?'Restore capture window':'Maximize saved captures'} onClick={()=>setMaximized(value=>!value)}>{maximized?<Minimize2 size={19}/>:<Maximize2 size={19}/>}</IconButton>}>
    <div className="capture-manager-body">
      <div className="capture-manager-summary"><div><strong>{previews.length.toLocaleString()} saved captures</strong><p>Browse your complete local preview history. Open a capture to see all its orders.</p></div><span>{previews.reduce((sum,item)=>sum+item.row_count,0).toLocaleString()} captured rows</span></div>
      <div className="capture-manager-toolbar"><label className="library-search"><Search size={17}/><input aria-label="Search all saved captures" placeholder="Search name, date, source or row count" value={query} onChange={event=>setQuery(event.target.value)}/></label><button className="secondary capture-delete" disabled={blocked||!selectedIds.length} onClick={()=>{setError('');setConfirmation({kind:'delete',ids:selectedIds});}}><Trash2 size={16}/>Delete selected ({selectedIds.length})</button></div>
      <div className="capture-selection-summary" role="status">{selectedIds.length} selected · Showing {items.length} of {previews.length}{selectedIds.length>0&&<button className="text-button" disabled={blocked} onClick={()=>{setChecked(new Set());setConfirmation(null);}}>Clear selection</button>}</div>
      {error&&<div className="notice error" role="alert">{error}</div>}
      {confirmation&&<section className="capture-confirmation" aria-label="Confirm capture removal">
        <strong>{confirmation.kind==='reset'?'Start a new local report?':`Delete ${confirmation.ids.length} selected ${confirmation.ids.length===1?'capture':'captures'}?`}</strong>
        <p>{confirmation.kind==='reset'?'Clear all local previews, imported reports and activity, pause scheduled runs, and restart numbering at preview1. Your Google Sheet and connection settings stay as they are.':'The selected previews and their CSV/Excel files will be removed from this computer.'} A recovery backup is saved first.</p>
        <div><button className="primary capture-delete" disabled={blocked} onClick={confirm}>{working?<><LoaderCircle size={16} className="spin"/>Removing…</>:confirmation.kind==='reset'?'Reset local workspace':'Delete captures'}</button><button className="secondary" disabled={working} onClick={()=>setConfirmation(null)}>Cancel</button></div>
      </section>}
      <div className="capture-manager-scroll" role="region" aria-label="All saved previews" tabIndex={0}><table className="capture-manager-table"><thead><tr><th><input ref={selectAll} type="checkbox" aria-label="Select all visible captures" checked={allChecked} disabled={blocked||!items.length} onChange={toggleAll}/></th><th>Capture</th><th>Saved</th><th>Source</th><th>Rows</th><th>Details</th></tr></thead><tbody>{items.map(item=><tr key={item.id} className={checked.has(item.id)?'capture-checked':selected===item.id?'capture-current':''}><td><input type="checkbox" aria-label={`Select ${item.name}`} checked={checked.has(item.id)} disabled={blocked} onChange={()=>toggle(item.id)}/></td><td><strong>{item.name}</strong>{item.id===previews[0]?.id&&<span className="capture-latest">Latest</span>}</td><td>{captureDate(item.created)}</td><td>{item.source||'Local capture'}</td><td>{item.row_count.toLocaleString()}</td><td><button className="secondary" disabled={working} aria-label={`Open ${item.name}`} onClick={()=>{onSelect(item.id);onClose();}}>Open</button></td></tr>)}</tbody></table>{!items.length&&<div className="capture-manager-empty"><FileSpreadsheet size={32}/><h3>{query?'No matching captures':'Your new preview history starts here'}</h3><p>{query?'Try a different name, date or source.':'Extract a queue or import a capture to save preview1.'}</p></div>}</div>
      <footer className="capture-manager-footer"><p>Saved on this computer · Recovery backups are available in Settings.</p><button className="text-button capture-delete" disabled={blocked} onClick={()=>{setError('');setConfirmation({kind:'reset'});}}><RotateCcw size={16}/>Start new report</button></footer>
    </div>
  </Dialog>;
}
