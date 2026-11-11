import React,{useEffect,useMemo,useState} from 'react';
import {api} from './workspaceUtils';
import {Dialog} from './DesktopExperience';
import {Search,CheckCircle2,Undo2,Pencil,Check,X,AlertTriangle} from 'lucide-react';
import {DataTable} from './WorkspaceViews';
import ReportOrderSearch from './ReportOrderSearch';
import './productionReport.css';
const statusChoices=['Assign to ABS','Attorney Approval','Awaiting for Clarification','Cancelled','Completed and Delivered','Home Builders','Need To Add Subscription','Need to assign ABS','QC in Progress','Responded','Search In Progress','SearchFix','Site Down','Typing in Progress','Waiting for Effective Date'];

function SuccessNotice({title,children}) {
  return <div className="production-success" role="status"><span className="production-success-icon" aria-hidden="true">✅</span><div className="production-success-content"><strong>{title}</strong>{children}</div></div>;
}

export default function ProductionReport({revision}) {
  const [folder,setFolder]=useState(''),[previews,setPreviews]=useState([]),[preview,setPreview]=useState('');
  const [detail,setDetail]=useState(null),[detailSearch,setDetailSearch]=useState('');
  const [restore,setRestore]=useState(null),[confirmRevert,setConfirmRevert]=useState(false),[message,setMessage]=useState('');
  const [statusOverrides,setStatusOverrides]=useState({}),[customOrder,setCustomOrder]=useState(null),[customStatus,setCustomStatus]=useState('');
  const [editingStatus,setEditingStatus]=useState(null),[statusDraft,setStatusDraft]=useState('');
  const [routes,setRoutes]=useState({}),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let alive=true;api('/api/production-report').then(data=>{if(alive){setFolder(value=>value||data.folder);setPreviews(data.previews);setRestore(data.revert||null);setPreview(value=>value||String(data.selected_preview_id||data.previews[0]?.id||''));}}).catch(error=>{if(alive)setError(error.message);});return()=>{alive=false;};},[revision]);
  async function run(action){
    setBusy(true);setError('');setMessage('');setDetail(null);setDetailSearch('');
    try{
      const data=await api(`/api/production-report/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,preview_id:Number(preview),routes,status_overrides:statusOverrides,fingerprint:result?.fingerprint,token:restore?.token}),timeoutMs:180000});
      setRestore(data.revert||null);
      if(action==='revert'){setResult(null);setStatusOverrides({});setConfirmRevert(false);setMessage(data.message);}
      else setResult(data);
    }
    catch(error){setError(error.message);if(action==='proceed')setResult(null);}
    finally{setBusy(false);}
  }
  const invalidate=()=>{setResult(null);setDetail(null);setRestore(null);setStatusOverrides({});setMessage('');};
  async function changeStatus(row,status){
    const overrides={...statusOverrides,[row['Order Number']]:status};
    setBusy(true);setError('');
    try{
      const data=await api('/api/production-report/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,preview_id:Number(preview),routes,status_overrides:overrides}),timeoutMs:180000});
      setStatusOverrides(overrides);setResult(data);setCustomOrder(null);setEditingStatus(null);
      const file=data.reports.find(file=>file.kind===detail.kind);
      setDetail(detail.statusChanges?{...file,orders:file.changed_orders||[],statusChanges:true}:file);
    }catch(error){setError(error.message);}finally{setBusy(false);}
  }
  function statusCell(row,column){
    if(column!=='Status')return undefined;
    const options=[...new Set([...statusChoices,...Object.values(statusOverrides),row.Status])].filter(Boolean).sort();
    if(editingStatus!==row['Order Number']||result.completed)return <div className="production-status-display"><span className="production-status-pill">{row.Status}</span>{!result.completed&&<button type="button" className="icon-button" aria-label={`Edit planned status for ${row['Order Number']}`} title="Edit status" disabled={busy} onClick={()=>{setEditingStatus(row['Order Number']);setStatusDraft(row.Status||'');setError('');}}><Pencil size={15}/></button>}</div>;
    return <div className="production-status-editor"><select autoFocus className="production-status-select" aria-label={`Planned status for ${row['Order Number']}`} title={statusDraft} value={statusDraft} disabled={busy} onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();event.preventDefault();setEditingStatus(null);}}} onChange={event=>{if(event.target.value==='__custom__'){setCustomOrder(row);setCustomStatus('');}else setStatusDraft(event.target.value);}}>{options.map(status=><option key={status} value={status}>{status}</option>)}<option value="__custom__">＋ Add New Status…</option></select><button type="button" className="icon-button production-status-confirm" aria-label={`Confirm planned status for ${row['Order Number']}`} title="Confirm status" disabled={busy||!statusDraft} onClick={()=>changeStatus(row,statusDraft)}><Check size={18}/></button><button type="button" className="icon-button production-status-cancel" aria-label={`Cancel status edit for ${row['Order Number']}`} title="Cancel edit" disabled={busy} onClick={()=>{setEditingStatus(null);setError('');}}><X size={18}/></button></div>;
  }
  const openOrders=file=>{setDetail(file);setDetailSearch('');setEditingStatus(null);};
  const detailTitle=detail?.kind==='full'?'Full Search':'C-O and Update';
  const detailRows=(detail?.orders||[]).filter(row=>!detailSearch.trim()||result.columns.some(column=>String(row[column]??'').toLowerCase().includes(detailSearch.trim().toLowerCase())));
  const searchableRows=useMemo(()=>(result?.rows||[]).map(({Destination,...row})=>row),[result]);
  return <section className="production-report">
    <div className="production-report-header"><div className="section-heading"><div><h2>Production Report</h2><p className="muted">Add missing preview orders to your two production workbooks.</p></div></div>
    <div className="production-report-search"><ReportOrderSearch name="Production Report" rows={searchableRows} columns={result?.columns||[]} disabled={!result||busy}/>{!result&&<p className="muted">Click Check folder &amp; orders below to load the selected preview for order-number search.</p>}</div>
    </div>
    <div className="production-report-controls">
      <label>Production report folder<input aria-label="Production report folder" placeholder={'C:\\Users\\Harikrishna\\Desktop\\PR'} value={folder} disabled={busy} onChange={event=>{setFolder(event.target.value);invalidate();}}/></label>
      <p className="muted">Paste the folder containing one C-O and Update workbook and one Full Search workbook. Local folders and accessible network paths are supported.</p>
      <label>Source preview<select aria-label="Production report preview" value={preview} disabled={busy} onChange={event=>{setPreview(event.target.value);invalidate();}}><option value="" disabled>Choose a saved preview</option>{previews.map(item=><option key={item.id} value={item.id}>{item.name} · {item.row_count} captured rows</option>)}</select></label>
      <p className="muted">Uses the selected preview’s SLA Status orders, including orders with unknown SLA. Existing order numbers in either workbook are skipped. Status Changed includes SLA Compare moved orders only when both statuses appear in the selected SLA Status report. Production-only statuses are excluded. Orders already Completed and Delivered or Need to Assign (including Need to assign ABS) in the destination Excel files are skipped for status updates. Proceed applies the SLA Status value to those orders in Excel.</p>
      <div className="production-main-actions"><button className="secondary action-check" disabled={busy||!folder.trim()||!preview} onClick={()=>run('check')}><Search size={18}/>{busy?'Working…':'Check folder & orders'}</button><button className="primary action-proceed" disabled={busy||!result||result.completed||!!result.unresolved.length} onClick={()=>run('proceed')}><CheckCircle2 size={19}/>Proceed — add orders & update statuses</button><button type="button" className="secondary action-revert" disabled={busy||!restore} onClick={()=>{setError("");setConfirmRevert(true);}} title="Restore the workbooks from before the latest Proceed"><Undo2 size={19}/>Revert Excel</button></div>
    </div>
    {error&&<div role="alert" className="production-revert-warning production-proceed-warning"><span className="production-revert-warning-icon" aria-hidden="true"><AlertTriangle size={26}/></span><div><strong>Action needed to continue</strong><p>{error}</p></div></div>}
    {customOrder&&<Dialog title="Add production status" className="production-add-status-dialog" onClose={()=>{if(!busy)setCustomOrder(null);}}><form className="dialog-content" onSubmit={event=>{event.preventDefault();changeStatus(customOrder,customStatus.trim());}}><p className="production-add-status-context">Add a status for <strong>{customOrder['Order Number']}</strong>.</p><label htmlFor="production-new-status">New status<input id="production-new-status" autoFocus required autoComplete="off" aria-label="New planned status" placeholder="e.g. Waiting for review" maxLength={256} value={customStatus} disabled={busy} onChange={event=>setCustomStatus(event.target.value)}/></label><p className="production-add-status-hint">This selects the status for your planned update. Click Proceed later to apply it to Excel.</p>{error&&<p className="notice warning" role="alert">{error}</p>}<div className="production-add-status-actions"><button type="button" className="secondary" disabled={busy} onClick={()=>setCustomOrder(null)}>Cancel</button><button type="submit" className="primary" disabled={busy||!customStatus.trim()}>{busy?'Saving…':'Use status'}</button></div></form></Dialog>}
    {message&&<SuccessNotice title="Excel reverted successfully"><p>{message}</p></SuccessNotice>}
    {result?.completed&&<SuccessNotice title="Excel updated successfully"><p>Missing orders were added and eligible statuses were updated. Your previous Excel files are backed up and can be restored with Revert Excel.</p><div className="inline">{result.downloads.map(file=><a className="secondary" key={file.url} href={file.url} download>Download {file.name}</a>)}</div></SuccessNotice>}
    {confirmRevert&&<Dialog title="Revert Excel" className="production-revert-dialog" onClose={()=>{if(!busy)setConfirmRevert(false);}}><div className="dialog-content"><p>Restore both production workbooks to their state before the latest Proceed? This removes orders added by that action and restores their previous statuses and data.</p><p>Close the Excel files first. If they were edited after Proceed, the restore will stop to protect those edits.</p>{error&&<div role="alert" className="production-revert-warning"><span className="production-revert-warning-icon" aria-hidden="true"><AlertTriangle size={26}/></span><div><strong>Action needed before restoring</strong><p>{error}</p></div></div>}<div className="inline"><button type="button" className="secondary" disabled={busy} onClick={()=>setConfirmRevert(false)}>Cancel</button><button type="button" className="primary" disabled={busy} onClick={()=>run('revert')}>{busy?'Reverting…':'Restore previous Excel'}</button></div></div></Dialog>}
    {result&&<>
      <div className="production-report-files">{result.reports.map(file=><article key={file.kind}><h3><button type="button" className="production-file-title" disabled={busy} onClick={()=>openOrders(file)} aria-haspopup="dialog">{file.kind==='full'?'Full Search':'C-O and Update'}</button></h3><p>{file.name}</p><p className="muted">Worksheet: {file.sheet}</p><div className="production-order-actions"><button type="button" className="production-order-count" disabled={busy} onClick={()=>openOrders(file)} aria-haspopup="dialog" aria-label={`${file.kind==='full'?'Full Search':'C-O and Update'}: ${file.missing} ${result.completed?'orders added':'Newly orders'}`}><strong>{file.missing} {result.completed?'orders added':'Newly orders'}</strong><span>View orders ↗</span></button><button type="button" className="production-order-count" disabled={busy} aria-haspopup="dialog" onClick={()=>openOrders({...file,orders:file.changed_orders||[],statusChanges:true})}><strong>{file.status_changed||0} Status Changed</strong><span>View orders</span></button></div><p>{file.existing} existing · {file.skipped} preview orders already present</p></article>)}</div>
      {!!result.unresolved.length&&<div className="production-report-controls"><h3>Choose destinations for unfamiliar products</h3><p>These products are not assigned uniquely by the existing files. Select their report, then check again.</p>{result.unresolved.map(product=><label key={product}>{product}<select aria-label={`Destination for ${product}`} value={routes[product]||''} onChange={event=>setRoutes({...routes,[product]:event.target.value})}><option value="">Choose report</option><option value="co">C-O and Update</option><option value="full">Full Search</option></select></label>)}<button className="secondary" disabled={busy} onClick={()=>run('check')}>Recheck destinations</button></div>}
      <p className="report-context">{result.preview_name} · Orders below use the Google Sheet column order. Destination workbooks retain their own headers and worksheet formatting.</p>
      <DataTable rows={result.rows} columns={result.columns} name="Preview orders in Google Sheet columns" filters={{}} openFilter={()=>{}} filterable={false}/>
    </>}
    {detail&&result&&<Dialog title={detailTitle+' — '+(detail.statusChanges?'status changes':result.completed?'orders added':'Newly orders')} onClose={()=>setDetail(null)} className="production-orders-dialog" initialFocus=".production-orders-search input"><div className="dialog-content"><p className="production-status-help">Click the pencil to edit a status, ✓ to confirm, or ✕ to cancel. Confirmed choices apply to Excel when you click Proceed. Saved preview statuses are unchanged.</p>{error&&<p className="notice warning" role="alert">{error}</p>}<p className="muted">{detail.name} · {result.preview_name} · {detail.orders?.length||0} {result.completed?'orders added':'orders to add'}</p><label className="search-input production-orders-search"><Search size={16}/><input aria-label="Search report orders" placeholder="Search order number, product, status or any column…" value={detailSearch} onChange={event=>setDetailSearch(event.target.value)}/></label><DataTable key={detail.kind} rows={detailRows} columns={detail.statusChanges?['Order Number','Product','PreviousStatus','Status','State','County','Client']:result.columns} renderCell={statusCell} name={detailTitle+' orders'} filters={{}} openFilter={()=>{}} filterable={false}/></div></Dialog>}
  </section>;
}
