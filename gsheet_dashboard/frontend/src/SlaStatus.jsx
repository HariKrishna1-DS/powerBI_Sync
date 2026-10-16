import React, {useEffect, useState} from 'react';
import {ArrowDownToLine, LoaderCircle, RefreshCw, Pencil, X} from 'lucide-react';
import {Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {api,orderKey} from './workspaceUtils';
import {OfflineNotice} from './DesktopExperience';
import {SideDrawer} from './WorkspaceViews';

const categories=[['Future SLA','#81cbb5'],['Negative SLA','#ed8796'],['Today SLA','#e5bf68']];
export default function SlaStatus({revision,onUpdated,mode='tracker'}){
  const [report,setReport]=useState(null),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[loading,setLoading]=useState(true),[detail,setDetail]=useState(null);
  const [editing,setEditing]=useState(null),[replacement,setReplacement]=useState(''),[saving,setSaving]=useState(false),[editError,setEditError]=useState(''),[message,setMessage]=useState('');
  const [selectedPreview,setSelectedPreview]=useState(''),[publishing,setPublishing]=useState(false);
  const previewId=mode==='tracker'?(selectedPreview||report?.preview_id):null;
  const reportUrl='/api/sla-status'+(mode==='tracker'&&selectedPreview?`?preview_id=${selectedPreview}`:'');
  const downloadUrl='/api/export/report?sheet=SLA%20Status'+(previewId?`&preview_id=${previewId}`:'');
  useEffect(()=>{setSelectedPreview('');setReport(null);setEditing(null);setDetail(null);setMessage('');},[mode]);
  async function selectPreview(value){
    const followLatest=Number(value)===report?.previews?.[0]?.id;
    setSelectedPreview(value);setReport(null);setEditing(null);setDetail(null);setMessage('');setPublishing(true);
    try{
      const result=await api('/api/sla-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview_id:Number(value)}),timeoutMs:180000});
      setMessage(result.publication?.synced?`${result.preview_name} · SLA Status updated in Google Sheets.`:'Preview selected. SLA Status is saved locally.');
      if(result.publication?.sync_error)setError(result.publication.sync_error);
      if(followLatest)setSelectedPreview('');
      setRefresh(current=>current+1);
    }catch(error){setError(error.message);}finally{setPublishing(false);}
  }
  function editStatus(status){
    const rows=[...report.rows,...report.excluded_rows].filter(row=>row.Status===status);
    setEditing({status,orders:rows.map(orderKey)});
    setReplacement(status);setEditError('');setMessage('');
  }
  async function saveStatus(event){
    event.preventDefault();if(saving)return;
    setSaving(true);setEditError('');
    try{
      const result=await api('/api/order-status',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({status:editing.status,replacement:replacement.trim(),order_numbers:editing.orders,
          ...(report.report_scope==='preview'?{preview_id:report.preview_id}:{})}),timeoutMs:180000});
      setReport(await api(reportUrl));setEditing(null);setDetail(null);
      setMessage(`${result.updated} orders updated to ${result.status}. ${report.report_scope==='preview'?(result.publication?.synced?'SLA Status updated in Google Sheets.':'Saved locally.'):'Google Sheets reports are updating.'}`);
      if(report.report_scope!=='preview')onUpdated?.();
    }catch(error){setEditError(error.message);}finally{setSaving(false);}
  }
  async function refreshStatus(){
    setLoading(true);setError('');
    try{
      if(mode==='tracker'&&previewId){
        const result=await api('/api/sla-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview_id:Number(previewId)}),timeoutMs:180000});
        setMessage(result.publication?.synced?`${result.preview_name} · SLA Status updated in Google Sheets.`:'SLA Status refreshed locally.');
      }else if(mode!=='tracker')await api('/api/report-refresh',{method:'POST',timeoutMs:180000});
      setRefresh(value=>value+1);
    }
    catch(error){setError(error.message);setLoading(false);}
  }
  useEffect(()=>{
    const controller=new AbortController();
    let busy=false;
    async function load(){
      if(busy)return;
      busy=true;
      setLoading(true);
      try{const data=await api(reportUrl,{signal:controller.signal});if(!controller.signal.aborted){setReport(data);setError('');}}
      catch(error){if(error.name!=='AbortError')setError(error.message);}
      finally{busy=false;if(!controller.signal.aborted)setLoading(false);}
    }
    load();const timer=setInterval(load,30000);
    return()=>{controller.abort();clearInterval(timer);};
  },[revision,refresh,selectedPreview,mode]);
  function show(status,category){
    const rows=report.rows.filter(row=>(!status||row.Status===status)&&(!category||row['SLA Category']===category));
    setDetail({title:[status,category].filter(Boolean).join(' · ')||'All SLA orders',rows});
  }
  return <section className="sla-status-workspace">
    <div className="section-heading"><div><h2>SLA Status</h2>{report&&<p className="muted">{report.preview_name?`${report.preview_name} · ${report.preview_row_count.toLocaleString()} captured orders`:report.source} · As of {report.as_of} (India time)</p>}</div><div className="inline"><button className="secondary" disabled={loading||saving||publishing} onClick={refreshStatus}><RefreshCw size={16}/>Refresh SLA Status</button><a className="secondary" href={downloadUrl} download><ArrowDownToLine size={16}/>Download SLA Status</a></div></div>
    {mode==='tracker'&&<label className="sla-preview-picker">Preview<select aria-label="SLA preview" value={String(previewId||'')} disabled={loading||saving||publishing||!report?.previews?.length} onChange={event=>selectPreview(event.target.value)}>
      {!report?.previews?.length&&<option value="">{loading?'Loading previews…':'No saved previews'}</option>}
      {report?.previews?.map(preview=><option key={preview.id} value={preview.id}>{preview.name} · {preview.row_count.toLocaleString()} orders · {new Date(preview.created).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</option>)}
    </select></label>}
    <p className="report-context">Future SLA: due after today. Negative SLA: overdue. Today SLA: due today.</p>
    <OfflineNotice snapshot={report}/>{(error||report?.sync_error)&&<p className="notice warning" role="alert">{error||report.sync_error}</p>}
    {loading&&!report?<div className="loading"><LoaderCircle className="spin"/>Loading SLA Status…</div>:report&&<>
      <div className="metrics">{[...categories,['Grand Total','#a8c5ed']].map(([name],index)=><button type="button" className={`metric metric-action ${['green','red','gold','blue'][index]}`} key={name} onClick={()=>show(null,name==='Grand Total'?null:name)}><span>{name}</span><strong>{report.totals[name].toLocaleString()}</strong></button>)}</div>
      {message&&<p className="notice success" role="status">{message}</p>}
      {editing&&<form className="status-edit-form" aria-label="Edit order status" onSubmit={saveStatus}>
        <div className="section-heading"><h3>Edit order status</h3><button type="button" className="icon-button" aria-label="Close status editor" disabled={saving} onClick={()=>setEditing(null)}><X size={16}/></button></div>
        <p>Update all {editing.orders.length} orders {report.preview_name?`in ${report.preview_name} `:''}currently marked <strong>{editing.status}</strong>. Choosing an existing status combines the orders under that status.</p>
        <label>New status<input aria-label="New order status" list="sla-existing-statuses" value={replacement} disabled={saving} maxLength={1000} onChange={event=>setReplacement(event.target.value)} autoFocus required/></label>
        <datalist id="sla-existing-statuses">{report.summary.map(row=><option key={row.Status} value={row.Status}/>)}</datalist>
        {editError&&<p role="alert" className="notice warning">{editError}</p>}
        <div className="inline"><button type="submit" className="primary" disabled={saving||!replacement.trim()||replacement.trim()===editing.status}>{saving?'Saving…':'Save status'}</button><button type="button" className="secondary" disabled={saving} onClick={()=>setEditing(null)}>Cancel</button></div>
      </form>}
      <div className="table-scroll"><table aria-label="SLA status summary"><thead><tr>{report.summary_columns.map(column=><th key={column} scope="col">{column}</th>)}</tr></thead><tbody>{[...report.summary,report.totals].map((row,index)=><tr key={index} className={index===report.summary.length?'sla-total':''}><th scope="row"><div className="sla-status-label"><button className="text-button" onClick={()=>show(index===report.summary.length?null:row.Status)}>{row.Status}</button>{index!==report.summary.length&&<button type="button" className="icon-button" aria-label={`Edit status ${row.Status}`} disabled={saving} onClick={()=>editStatus(row.Status)}><Pencil size={15}/></button>}</div></th>{report.summary_columns.slice(1).map(column=><td key={column}><button className="text-button" aria-label={`${row.Status}, ${column}: ${row[column]} orders`} onClick={()=>show(index===report.summary.length?null:row.Status,column==='Grand Total'?null:column)}>{row[column]||'—'}</button></td>)}</tr>)}</tbody></table></div>
      {report.summary.length>0?<div className="chart-section" role="region" aria-label="SLA status bar chart"><div style={{height:Math.max(220,report.summary.length*40+70)}}><ResponsiveContainer width="100%" height="100%"><BarChart data={report.summary} layout="vertical" maxBarSize={24} margin={{top:12,right:24,left:10,bottom:12}}><CartesianGrid stroke="var(--chart-grid)" horizontal={false}/><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="Status" width={210} tick={{fontSize:12,fill:'var(--muted)'}}/><Tooltip/><Legend/>{categories.map(([name,color])=><Bar key={name} dataKey={name} stackId="sla" fill={color} isAnimationActive={false} onClick={entry=>show(entry.Status||entry.payload?.Status,name)} className="clickable-series"/>)}</BarChart></ResponsiveContainer></div></div>:<p className="table-empty">No orders with a valid SLA expiration.</p>}
      {report.excluded_count>0&&<p className="report-context"><button className="text-button" onClick={()=>setDetail({title:'Missing or invalid SLA expiration',rows:report.excluded_rows})}>{report.excluded_count.toLocaleString()} orders have missing or invalid SLA expiration</button> and are excluded from the SLA totals.</p>}
      {detail&&<SideDrawer key={detail.title} {...detail} columns={report.columns} onClose={()=>setDetail(null)}/>}
    </>}
  </section>;
}
