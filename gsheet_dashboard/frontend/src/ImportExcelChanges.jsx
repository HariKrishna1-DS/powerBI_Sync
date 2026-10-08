import React, {useDeferredValue,useEffect,useState} from 'react';
import {ChevronLeft,ChevronRight,LoaderCircle,RefreshCw,Search} from 'lucide-react';
import {api,str} from './workspaceUtils';
import {Dialog} from './DesktopExperience';

export default function ImportExcelChanges({revision,onRefresh,refreshing}) {
  const [history,setHistory]=useState(null),[error,setError]=useState(''),[action,setAction]=useState('');
  const [search,setSearch]=useState(''),[offset,setOffset]=useState(0),[detail,setDetail]=useState(null);
  const query=useDeferredValue(search);
  useEffect(()=>setOffset(0),[action,query]);
  useEffect(()=>{
    let active=true,busy=false;
    const controller=new AbortController();
    async function load(){
      if(busy)return;
      busy=true;
      try{
        const params=new URLSearchParams({action,search:query,offset:String(offset)});
        const value=await api(`/api/import-excel-changes?${params}`,{signal:controller.signal});
        if(active){setHistory(value);setError('');}
      }catch(e){if(active&&e.name!=='AbortError')setError(e.message);}
      finally{busy=false;}
    }
    load();const timer=setInterval(()=>{if(!document.hidden)load();},10000);
    return()=>{active=false;clearInterval(timer);controller.abort();};
  },[revision,action,query,offset]);
  const rows=history?.rows||[],limit=history?.limit||100,total=history?.total||0;
  const details=detail?[...new Set([...Object.keys(detail.Before||{}),...Object.keys(detail.After||{})])].filter(column=>column!=='No'&&!column.startsWith('_')):[];
  return <section className="import-changes-workspace">
    <div className="section-heading"><div><h2>Import Excel Changes</h2><p className="muted">Order edits detected in All Products, Full Search and Remaining Search.</p></div>
      <button className="secondary" disabled={refreshing} onClick={onRefresh}><RefreshCw size={16} className={refreshing?'spin':''}/>{refreshing?'Refreshing…':'Refresh from Sheets'}</button>
    </div>
    <p className="report-context">{history?.checked_at?`Last checked ${new Date(history.checked_at).toLocaleString()}`:'Refresh to check your imported order tabs.'} · Changes are checked automatically while Tv Tracker is running.</p>
    {history?.mode==='tracker'&&<p className="notice">Select Import Excel report to sync edits to imported orders. Saved change history remains available here.</p>}
    {(error||history?.sync_error)&&<p className="notice warning" role="alert">{error||history.sync_error}</p>}
    <div className="metrics">{[['Added','Orders added','green'],['Updated','Fields updated','blue'],['Removed','Orders removed','red']].map(([key,label,tone])=><div className={`metric ${tone}`} key={key}><span>{label}</span><strong>{(history?.counts?.[key]||0).toLocaleString()}</strong></div>)}</div>
    <div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search changed Order Number" placeholder="Search Order Number" value={search} onChange={e=>setSearch(e.target.value)}/></div><label>Changes<select aria-label="Filter imported changes" value={action} onChange={e=>setAction(e.target.value)}><option value="">All changes</option><option>Added</option><option>Updated</option><option>Removed</option></select></label><span className="row-tally">{total.toLocaleString()} changes</span></div>
    {!history&&!error?<p className="loading"><LoaderCircle size={18} className="spin"/>Loading changes…</p>:<div className="table-scroll"><table aria-label="Import Excel change history"><thead><tr><th>Detected at</th><th>Order Number</th><th>Change</th><th>Column</th><th>Previous → New</th><th>Source tab</th><th>Details</th></tr></thead>
      <tbody>{rows.map(row=><tr key={row.id}><td>{new Date(row['Changed At']).toLocaleString()}</td><td>{row['Order Number']}</td><td><span className={`badge ${row.Change.toLowerCase()}`}>{row.Change}</span></td><td>{row.Column}</td><td className="change-values"><span>{row['Previous Value']||'—'}</span><span aria-hidden="true"> → </span><strong>{row['New Value']||'—'}</strong></td><td>{row['Source Tabs']}</td><td><button className="text-button" aria-label={`View change ${row.id} for order ${row['Order Number']}`} onClick={()=>setDetail(row)}>View</button></td></tr>)}</tbody></table>
      {!rows.length&&<p className="table-empty">{search||action?'No changes match these filters.':'No Sheet changes recorded yet. Add, edit or remove an order in the imported tabs, then refresh.'}</p>}
    </div>}
    <div className="table-footer"><span>{total?`${offset+1}–${Math.min(offset+limit,total)} of ${total}`:'0 changes'}</span><div className="inline"><button className="secondary" aria-label="Previous imported changes" disabled={!offset} onClick={()=>setOffset(Math.max(0,offset-limit))}><ChevronLeft size={16}/>Previous</button><button className="secondary" aria-label="Next imported changes" disabled={offset+limit>=total} onClick={()=>setOffset(offset+limit)}>Next<ChevronRight size={16}/></button></div></div>
    {detail&&<Dialog title={`Order ${detail['Order Number']} · ${detail.Change}`} onClose={()=>setDetail(null)} className="detail-dialog"><div className="dialog-content"><p className="muted">{detail['Source Tabs']} · Detected {new Date(detail['Changed At']).toLocaleString()}</p><div className="table-scroll"><table><thead><tr><th>Column</th><th>Previous value</th><th>New value</th></tr></thead><tbody>{details.map(column=><tr key={column}><td>{column}</td><td>{str(detail.Before?.[column])||'—'}</td><td>{str(detail.After?.[column])||'—'}</td></tr>)}</tbody></table></div></div></Dialog>}
  </section>;
}
