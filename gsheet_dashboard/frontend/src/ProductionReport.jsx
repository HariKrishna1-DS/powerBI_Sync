import React,{useEffect,useState} from 'react';
import {api} from './workspaceUtils';
import {Dialog} from './DesktopExperience';
import {Search} from 'lucide-react';
import {DataTable} from './WorkspaceViews';
import './productionReport.css';

export default function ProductionReport({revision}) {
  const [folder,setFolder]=useState(''),[previews,setPreviews]=useState([]),[preview,setPreview]=useState('');
  const [detail,setDetail]=useState(null),[detailSearch,setDetailSearch]=useState('');
  const [routes,setRoutes]=useState({}),[result,setResult]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
  useEffect(()=>{let alive=true;api('/api/production-report').then(data=>{if(alive){setFolder(value=>value||data.folder);setPreviews(data.previews);setPreview(value=>value||String(data.selected_preview_id||data.previews[0]?.id||''));}}).catch(error=>{if(alive)setError(error.message);});return()=>{alive=false;};},[revision]);
  async function run(action){
    setBusy(true);setError('');setDetail(null);setDetailSearch('');
    try{setResult(await api(`/api/production-report/${action}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder,preview_id:Number(preview),routes,fingerprint:result?.fingerprint}),timeoutMs:180000}));}
    catch(error){setError(error.message);if(action==='proceed')setResult(null);}
    finally{setBusy(false);}
  }
  const invalidate=()=>{setResult(null);setDetail(null);};
  const openOrders=file=>{setDetail(file);setDetailSearch('');};
  const detailTitle=detail?.kind==='full'?'Full Search':'C-O and Update';
  const detailRows=(detail?.orders||[]).filter(row=>!detailSearch.trim()||result.columns.some(column=>String(row[column]??'').toLowerCase().includes(detailSearch.trim().toLowerCase())));
  return <section className="production-report">
    <div className="section-heading"><div><h2>Production Report</h2><p className="muted">Add missing preview orders to your two production workbooks.</p></div></div>
    <div className="production-report-controls">
      <label>Production report folder<input aria-label="Production report folder" placeholder={'C:\\Users\\Harikrishna\\Desktop\\PR'} value={folder} disabled={busy} onChange={event=>{setFolder(event.target.value);invalidate();}}/></label>
      <p className="muted">Paste the folder containing one C-O and Update workbook and one Full Search workbook. Local folders and accessible network paths are supported.</p>
      <label>Source preview<select aria-label="Production report preview" value={preview} disabled={busy} onChange={event=>{setPreview(event.target.value);invalidate();}}><option value="" disabled>Choose a saved preview</option>{previews.map(item=><option key={item.id} value={item.id}>{item.name} · {item.row_count} captured rows</option>)}</select></label>
      <p className="muted">Uses the selected preview’s SLA Status orders, including orders with unknown SLA. Existing order numbers in either workbook are skipped. No existing statuses or cells are changed.</p>
      <div className="inline"><button className="secondary" disabled={busy||!folder.trim()||!preview} onClick={()=>run('check')}>{busy?'Working…':'Check folder & orders'}</button><button className="primary" disabled={busy||!result||result.completed||!!result.unresolved.length} onClick={()=>run('proceed')}>Proceed — add missing orders</button></div>
    </div>
    {error&&<p className="notice warning" role="alert">{error}</p>}
    {result&&<>
      <div className="production-report-files">{result.reports.map(file=><article key={file.kind}><h3><button type="button" className="production-file-title" disabled={busy} onClick={()=>openOrders(file)} aria-haspopup="dialog">{file.kind==='full'?'Full Search':'C-O and Update'}</button></h3><p>{file.name}</p><p className="muted">Worksheet: {file.sheet}</p><button type="button" className="production-order-count" disabled={busy} onClick={()=>openOrders(file)} aria-haspopup="dialog" aria-label={`${file.kind==='full'?'Full Search':'C-O and Update'}: ${file.missing} ${result.completed?'orders added':'missing orders'}`}><strong>{file.missing} {result.completed?'orders added':'missing orders'}</strong><span>View orders ↗</span></button><p>{file.existing} existing · {file.skipped} preview orders already present</p></article>)}</div>
      {!!result.unresolved.length&&<div className="production-report-controls"><h3>Choose destinations for unfamiliar products</h3><p>These products are not assigned uniquely by the existing files. Select their report, then check again.</p>{result.unresolved.map(product=><label key={product}>{product}<select aria-label={`Destination for ${product}`} value={routes[product]||''} onChange={event=>setRoutes({...routes,[product]:event.target.value})}><option value="">Choose report</option><option value="co">C-O and Update</option><option value="full">Full Search</option></select></label>)}<button className="secondary" disabled={busy} onClick={()=>run('check')}>Recheck destinations</button></div>}
      {result.completed&&<div className="notice success" role="status"><strong>Production workbooks updated.</strong><p>Previous data is retained. Backups are saved in the report folder’s .tv-tracker-backups directory.</p><div className="inline">{result.downloads.map(file=><a className="secondary" key={file.url} href={file.url} download>Download {file.name}</a>)}</div></div>}
      <p className="report-context">{result.preview_name} · Orders below use the Google Sheet column order. Destination workbooks retain their own headers and worksheet formatting.</p>
      <DataTable rows={result.rows} columns={result.columns} name="Preview orders in Google Sheet columns" filters={{}} openFilter={()=>{}} filterable={false}/>
    </>}
    {detail&&result&&<Dialog title={detailTitle+' — '+(result.completed?'orders added':'missing orders')} onClose={()=>setDetail(null)} className="production-orders-dialog" initialFocus=".production-orders-search input"><div className="dialog-content"><p className="muted">{detail.name} · {result.preview_name} · {detail.orders?.length||0} {result.completed?'orders added':'orders to add'}</p><label className="search-input production-orders-search"><Search size={16}/><input aria-label="Search report orders" placeholder="Search order number, product, status or any column…" value={detailSearch} onChange={event=>setDetailSearch(event.target.value)}/></label><DataTable key={detail.kind} rows={detailRows} columns={result.columns} name={detailTitle+' orders'} filters={{}} openFilter={()=>{}} filterable={false}/></div></Dialog>}
  </section>;
}
