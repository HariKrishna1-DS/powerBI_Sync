import {FilterableTable} from './ColumnFilters';
import React, {useEffect, useMemo, useRef, useState} from 'react';
import {ArrowDownToLine, LoaderCircle, RefreshCw, Pencil, Plus, Copy, Trash2, X} from 'lucide-react';
import {Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis} from 'recharts';
import {api,orderKey} from './workspaceUtils';
import {Dialog,OfflineNotice} from './DesktopExperience';
import {SideDrawer} from './WorkspaceViews';
import SlaOrderEditor from './SlaOrderEditor';
import ReportOrderSearch from './ReportOrderSearch';
import RepeatedSlaOrders from './RepeatedSlaOrders';

const categories=[['Future SLA','#81cbb5'],['Negative SLA','#ed8796'],['Today SLA','#e5bf68'],['Unknown SLA','#a8c5ed']];
const standardStatuses=['Completed and Delivered','QC in Progress','Typing in Progress','Search In Progress','SearchFix','Waiting for Effective Date','Attorney Approval','Home Builders','Assign to ABS','Awaiting for Clarification'];
export default function SlaStatus({revision,onUpdated,mode='tracker'}){
  const suggestedStatuses=standardStatuses.filter(status=>mode!=='tracker'||status!=='Completed and Delivered');
  const [report,setReport]=useState(null),[error,setError]=useState(''),[refresh,setRefresh]=useState(0),[loading,setLoading]=useState(true),[detail,setDetail]=useState(null);
  const [editing,setEditing]=useState(null),[replacement,setReplacement]=useState(''),[saving,setSaving]=useState(false),[editError,setEditError]=useState(''),[message,setMessage]=useState('');
  const [selectedPreview,setSelectedPreview]=useState(''),[publishing,setPublishing]=useState(false);
  const [editScope,setEditScope]=useState('group'),[orderSearch,setOrderSearch]=useState('');
  const [orderEditor,setOrderEditor]=useState(null),[newStatus,setNewStatus]=useState(null);
  const [deleting,setDeleting]=useState(null),[moveTo,setMoveTo]=useState(''),[deleteError,setDeleteError]=useState('');
  const editor=useRef(null),statusCreator=useRef(null),selectionGeneration=useRef(0),dateSelecting=useRef(false);
  useEffect(()=>{if(editing)editor.current?.scrollIntoView({block:'center'});},[editing?.status]);
  useEffect(()=>{if(newStatus!==null)statusCreator.current?.scrollIntoView({block:'center'});},[newStatus===null]);
  const previewId=mode==='tracker'?(selectedPreview||report?.preview_id):null;
  const reportUrl='/api/sla-status'+(mode==='tracker'&&selectedPreview?`?preview_id=${selectedPreview}`:'');
  const downloadUrl='/api/export/report?sheet=SLA%20Status'+(previewId?`&preview_id=${previewId}`:report?.report_date?`&date=${encodeURIComponent(report.report_date)}`:'');
  const editContext=context=>context.report_scope==='imported_date'?{mode:'excel',report_date:context.report_date}:{preview_id:context.preview_id};
  useEffect(()=>{selectionGeneration.current+=1;dateSelecting.current=false;setSelectedPreview('');setReport(null);setEditing(null);setDetail(null);setOrderEditor(null);setNewStatus(null);setDeleting(null);setMessage('');},[mode]);
  async function selectPreview(value){
    const followLatest=Number(value)===report?.previews?.[0]?.id;
    setSelectedPreview(value);setReport(null);setEditing(null);setDetail(null);setOrderEditor(null);setNewStatus(null);setDeleting(null);setMessage('');setPublishing(true);
    try{
      const result=await api('/api/sla-preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview_id:Number(value)}),timeoutMs:180000});
      setMessage(result.publication?.synced?`${result.preview_name} · SLA Status updated in Google Sheets.`:'Preview selected. SLA Status is saved locally.');
      if(result.publication?.sync_error)setError(result.publication.sync_error);
      if(followLatest)setSelectedPreview('');
      setRefresh(current=>current+1);
    }catch(error){setError(error.message);}finally{setPublishing(false);}
  }
  async function selectReportDate(value){
    const generation=++selectionGeneration.current;dateSelecting.current=true;
    setEditing(null);setDetail(null);setMessage('');setError('');setLoading(true);setPublishing(true);
    try{
      const result=await api('/api/sla-report-date',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date:value}),timeoutMs:180000});
      if(generation!==selectionGeneration.current)return;
      setReport(result);
      setMessage(result.publication?.synced?'Report date selected. SLA Status updated in Google Sheets.':'Report date selected locally.');
      if(result.publication?.sync_error)setError(result.publication.sync_error);
    }catch(error){if(generation===selectionGeneration.current)setError(error.message);}finally{if(generation===selectionGeneration.current){dateSelecting.current=false;setLoading(false);setPublishing(false);}}
  }
  function editStatus(status){
    const rows=[...report.rows,...report.excluded_rows].filter(row=>row.Status===status);
    setEditing({status,rows,orders:rows.map(orderKey),preview_id:report.preview_id,report_scope:report.report_scope,report_date:report.report_date});setEditScope('group');setOrderSearch('');
    setReplacement(status);setEditError('');setMessage('');
  }
  async function saveStatus(event){
    event.preventDefault();if(saving)return;
    setSaving(true);setEditError('');
    try{
      const empty=!editing.rows.length&&['preview','imported_date'].includes(editing.report_scope);
      const result=await api(empty?'/api/sla-statuses':'/api/order-status',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(empty?{previous:editing.status,status:replacement.trim(),...editContext(editing)}:{status:editing.status,replacement:replacement.trim(),order_numbers:editing.orders,edit_scope:editScope,
          ...(editing.report_scope==='preview'?{preview_id:editing.preview_id}:editing.report_scope==='imported_date'?{sla_report_date:editing.report_date}:{})}),timeoutMs:180000});
      setReport(await api(reportUrl));setEditing(null);setDetail(null);
      setMessage(`${empty?'Status renamed to':`${result.updated} orders updated to`} ${result.status}. ${report.report_scope==='preview'?(result.publication?.synced?'SLA Status updated in Google Sheets.':'Saved locally.'):'Google Sheets reports are updating.'}`);
      if(report.report_scope!=='preview')onUpdated?.();
    }catch(error){setEditError(error.message);}finally{setSaving(false);}
  }
  async function addStatus(event){
    event.preventDefault();setSaving(true);setEditError('');
    try{
      const result=await api('/api/sla-statuses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...editContext(report),status:newStatus.trim()}),timeoutMs:180000});
      setReport(await api(reportUrl));setNewStatus(null);setMessage(`${result.status} is ready. Click its name or + to add orders.`);
      if(report.report_scope==='imported_date')onUpdated?.();
    }catch(error){setEditError(error.message);}finally{setSaving(false);}
  }
  async function savedOrder(result){
    setReport(await api(reportUrl));setOrderEditor(null);
    setMessage(`${result.order_number} ${result.created?'added':'updated'} under ${result.status}. ${result.publication?.synced?'SLA Status updated in Google Sheets.':'Saved locally.'}`);
    if(report.report_scope==='imported_date')onUpdated?.();
  }
  function startStatus(){setNewStatus('');setEditError('');}
  function removeStatus(status){
    const orders=[...report.rows,...report.excluded_rows].filter(row=>row.Status===status).map(orderKey);
    setDeleting({status,orders,preview_id:report.preview_id,preview_name:report.preview_name,report_scope:report.report_scope,report_date:report.report_date});setMoveTo('');setDeleteError('');
  }
  async function deleteStatus(event){
    event.preventDefault();if(saving)return;setSaving(true);setDeleteError('');
    try{
      const result=await api('/api/sla-statuses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'delete',...editContext(deleting),status:deleting.status,order_numbers:deleting.orders,replacement:moveTo}),timeoutMs:180000});
      setReport(await api(reportUrl));setDeleting(null);setDetail(null);
      setMessage(`${result.status} deleted.${result.moved?` ${result.moved} orders moved to ${result.replacement}.`:''} ${result.publication?.synced?'SLA Status updated in Google Sheets.':'Saved locally.'}`);
    }catch(error){setDeleteError(error.message);}finally{setSaving(false);}
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
      if(busy||dateSelecting.current)return;
      busy=true;
      const generation=selectionGeneration.current;
      setLoading(true);
      try{const data=await api(reportUrl,{signal:controller.signal});if(!controller.signal.aborted&&generation===selectionGeneration.current){setReport(data);setError('');}}
      catch(error){if(error.name!=='AbortError'&&generation===selectionGeneration.current)setError(error.message);}
      finally{busy=false;if(!controller.signal.aborted&&generation===selectionGeneration.current)setLoading(false);}
    }
    load();const timer=setInterval(load,30000);
    return()=>{controller.abort();clearInterval(timer);};
  },[revision,refresh,selectedPreview,mode]);
  function show(status,category){
    setDetail({title:[status,category].filter(Boolean).join(' · ')||'All SLA orders',status,category});
  }
  const manual=(report?.report_scope==='preview'&&!!report.preview_id)||(report?.report_scope==='imported_date'&&!!report.report_date);
  const searchRows=useMemo(()=>report?[...report.rows,...report.excluded_rows]:[],[report]);
  const capturedCount=report?.captured_order_count??Math.max(0,(report?.rows.length||0)+(report?.excluded_count||0)-(report?.manual_order_count||0));
  const detailRows=!detail||!report?[]:detail.scope==='duplicates'?(report.duplicate_rows||[]).filter(row=>!detail.orderNumber||String(row['Order Number']).trim().toLowerCase()===detail.orderNumber.toLowerCase()):detail.scope==='current'?[...report.rows,...report.excluded_rows]:detail.scope==='excluded'?report.excluded_rows:report.rows.filter(row=>(!detail.status||row.Status===detail.status)&&(!detail.category||row['SLA Category']===detail.category));
  const detailColumns=detail?.scope==='duplicates'?['Capture row','SLA selection','Entry status','Entry condition','Counted status','Counted SLA','Applied status condition','Counted capture row','Selection reason',...(report?.columns||[])]:report?.columns;
  const editableDetail=manual&&detail?.scope!=='duplicates';
  const hasRepeated=report?.report_scope==='preview'&&!!(report.duplicate_row_count||report.missing_order_number_count);
  const showRepeated=orderNumber=>setDetail({title:orderNumber?`Repeated entries · ${orderNumber}`:'Repeated Order Numbers',scope:'duplicates',orderNumber});
  function rowActions(row){return <div className="inline"><button type="button" className="icon-button" aria-label={`Edit details ${row['Order Number']}`} title="Edit order details" onClick={()=>setOrderEditor({row,status:row.Status})}><Pencil size={15}/></button><button type="button" className="icon-button" aria-label={`Add order to ${row.Status}`} title="Add order to this status" onClick={()=>setOrderEditor({status:row.Status})}><Plus size={15}/></button><button type="button" className="icon-button" aria-label={`Copy order ${row['Order Number']}`} title="Copy into a new order" onClick={()=>setOrderEditor({row,status:row.Status,copy:true})}><Copy size={15}/></button></div>;}
  return <section className="sla-status-workspace">
    <div className="section-heading"><div><h2>SLA Status</h2>{report&&<p className="muted">{report.preview_name?`${report.preview_name} · ${capturedCount.toLocaleString()} unique orders · ${report.preview_row_count.toLocaleString()} captured rows`:report.source} · As of {report.as_of} ({report.date_basis==='arrival_time'?'Arrival Time date':'capture date'})</p>}</div><div className="inline">{manual&&<button className="secondary" disabled={saving||publishing||!!editing} onClick={startStatus}><Plus size={16}/>Add status</button>}<button className="secondary" disabled={loading||saving||publishing||!!editing} onClick={refreshStatus}><RefreshCw size={16}/>Refresh SLA Status</button><a className="secondary" href={downloadUrl} download aria-disabled={loading||saving||publishing||!report} onClick={event=>{if(loading||saving||publishing||!report)event.preventDefault();}}><ArrowDownToLine size={16}/>Download SLA Status</a></div></div>
    {mode==='tracker'&&<label className="sla-preview-picker">Preview<select aria-label="SLA preview" value={String(previewId||'')} disabled={loading||saving||publishing||!!editing||!report?.previews?.length} onChange={event=>selectPreview(event.target.value)}>
      {!report?.previews?.length&&<option value="">{loading?'Loading previews…':'No saved previews'}</option>}
      {report?.previews?.map(preview=><option key={preview.id} value={preview.id}>{preview.name} · {preview.row_count.toLocaleString()} captured rows{preview.id===report.preview_id?` · ${capturedCount.toLocaleString()} unique orders`:''} · {new Date(preview.created).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</option>)}
    </select></label>}
    {mode==='excel'&&<label className="sla-preview-picker">Report date<select aria-label="SLA report date" value={report?.report_date||''} disabled={loading||saving||publishing||!!editing||!report?.report_dates?.length} onChange={event=>selectReportDate(event.target.value)}>
      {!report?.report_dates?.length&&<option value="">{loading?'Loading dates…':'No report dates'}</option>}
      {report?.report_dates?.map((day,index)=><option key={day.date} value={day.date}>{day.date}{index===0&&day.date!=='Undated'?' (latest)':''} · {day.orders.toLocaleString()} orders</option>)}
    </select></label>}
    <div className={`sla-report-tools${hasRepeated?' has-repeated-orders':''}`}>
      <RepeatedSlaOrders report={report} onShow={showRepeated}/>
      <ReportOrderSearch name="SLA Status" rows={searchRows} columns={report?.columns||[]} disabled={!report}/>
    </div>
    {report?.report_scope==='imported_date'&&<p className="report-context">{report.date_order_count.toLocaleString()} orders {report.report_date==='Undated'?'without an arrival date':`received on ${report.report_date}`} out of {report.imported_order_count.toLocaleString()} imported orders. SLA categories are calculated as of {report.as_of}.{report.undated_order_count>0&&report.report_date!=='Undated'?` ${report.undated_order_count.toLocaleString()} orders without an arrival date are available under Undated.`:''}</p>}
    {report?.report_scope==='preview'&&<p className="report-context">{report.manual_order_count?`${report.captured_order_count} captured orders + ${report.manual_order_count} manually added order${report.manual_order_count===1?'':'s'} in ${report.preview_name}.`:`Only orders in ${report.preview_name} are included.`} <button className="text-button" onClick={()=>setDetail({title:'Current queue orders',scope:'current'})}>View current orders</button></p>}
    {report?.report_scope==='preview'&&<p className="report-context">Statuses follow the active queue conditions. Completed and Delivered is not used in extracted SLA Status.</p>}
    {report&&<p className="report-context sla-total-equation">Future SLA {report.totals['Future SLA'].toLocaleString()} + Negative SLA {report.totals['Negative SLA'].toLocaleString()} + Today SLA {report.totals['Today SLA'].toLocaleString()}{report.totals['Unknown SLA']?` + Unknown SLA ${report.totals['Unknown SLA'].toLocaleString()}`:''} = Grand Total {report.totals['Grand Total'].toLocaleString()}</p>}
    {report?.excluded_count>0&&<p className="report-context">{(report.rows.length+report.excluded_count).toLocaleString()} orders = {report.rows.length.toLocaleString()} in SLA totals + <button className="text-button" onClick={()=>setDetail({title:'Missing or invalid SLA expiration',scope:'excluded'})}>{report.excluded_count.toLocaleString()} orders have missing or invalid SLA expiration</button>.</p>}
    <p className="report-context">{report?.as_of?`Future SLA: due after ${report.as_of}. Negative SLA: due before ${report.as_of}. Today SLA: due on ${report.as_of}.`:'Future SLA: due after today. Negative SLA: overdue. Today SLA: due today.'}</p>
    <OfflineNotice snapshot={report}/>{(error||report?.sync_error)&&<p className="notice warning" role="alert">{error||report.sync_error}</p>}
    {loading&&!report?<div className="loading"><LoaderCircle className="spin"/>Loading SLA Status…</div>:report&&<>
      <div className="metrics">{[...categories.filter(([name])=>name in report.totals),['Grand Total','#a8c5ed']].map(([name],index)=><button type="button" className={`metric metric-action ${['green','red','gold','blue'][index%4]}`} key={name} onClick={()=>show(null,name==='Grand Total'?null:name)}><span>{name}</span><strong>{(report.totals[name]||0).toLocaleString()}</strong></button>)}</div>
      {message&&<p className="notice success" role="status">{message}</p>}
      {newStatus!==null&&<form ref={statusCreator} className="status-edit-form" aria-label="Create SLA status" onSubmit={addStatus}><h3>Add status</h3><label>Status name<input aria-label="Status name" autoFocus required maxLength={1000} value={newStatus} disabled={saving} onChange={event=>setNewStatus(event.target.value)}/></label><p>The status starts with zero orders. Open it to add an existing order or a new order.</p>{editError&&<p className="notice warning" role="alert">{editError}</p>}<div className="inline"><button type="submit" className="primary" disabled={saving||!newStatus.trim()}>{saving?'Saving…':'Create status'}</button><button type="button" className="secondary" disabled={saving} onClick={()=>setNewStatus(null)}>Cancel</button></div></form>}
      {editing&&<form ref={editor} className="status-edit-form" aria-label="Edit order status" onSubmit={saveStatus}>
        <div className="section-heading"><h3>Edit order status</h3><button type="button" className="icon-button" aria-label="Close status editor" disabled={saving} onClick={()=>setEditing(null)}><X size={16}/></button></div>
        <p>Update {editScope==='group'?'all ':''}{editing.orders.length} orders {report.preview_name?`in ${report.preview_name} `:''}currently marked <strong>{editing.status}</strong>. Choosing an existing status combines the orders under that status.</p>
        {editing.rows.length>0&&<label>Orders to update<select aria-label="Orders to update" value={editScope} disabled={saving} onChange={event=>{const scope=event.target.value;setEditScope(scope);setEditing({...editing,orders:scope==='group'?editing.rows.map(orderKey):[]});}}><option value="group">All orders in this status</option><option value="orders">Choose order numbers</option></select></label>}
        {editScope==='orders'&&<div className="sla-order-picker">
          <label>Find order number<input aria-label="Find order number" placeholder="Type an Order Number" value={orderSearch} disabled={saving} onChange={event=>setOrderSearch(event.target.value)}/></label>
          <div className="inline"><button type="button" className="text-button" disabled={saving} onClick={()=>setEditing({...editing,orders:editing.rows.map(orderKey)})}>Select all orders</button><button type="button" className="text-button" disabled={saving} onClick={()=>setEditing({...editing,orders:[]})}>Clear selection</button><span>{editing.orders.length} selected</span></div>
          <div className="sla-order-options" role="group" aria-label="Order numbers to update">{editing.rows.filter(row=>String(row['Order Number']).toLowerCase().includes(orderSearch.trim().toLowerCase())).map(row=><label className="sla-order-choice" key={orderKey(row)}><input type="checkbox" aria-label={`Select order ${row['Order Number']}${row['Source workbook']?` in ${row['Source workbook']}`:''}`} checked={editing.orders.includes(orderKey(row))} disabled={saving} onChange={event=>setEditing({...editing,orders:event.target.checked?[...editing.orders,orderKey(row)]:editing.orders.filter(key=>key!==orderKey(row))})}/><span>{row['Order Number']}<small>{[row.Product,row['Source workbook']].filter(Boolean).join(' · ')}</small></span></label>)}</div>
        </div>}
        <label>New status<input aria-label="New order status" list="sla-existing-statuses" value={replacement} disabled={saving} maxLength={1000} onChange={event=>setReplacement(event.target.value)} autoFocus required/></label>
        <datalist id="sla-existing-statuses">{[...new Set([...suggestedStatuses,...report.summary.map(row=>row.Status)])].map(status=><option key={status} value={status}/>)}</datalist>
        {editError&&<p role="alert" className="notice warning">{editError}</p>}
        <div className="inline"><button type="submit" className="primary" disabled={saving||(editing.rows.length>0&&!editing.orders.length)||!replacement.trim()||replacement.trim()===editing.status}>{saving?'Saving…':'Save status'}</button><button type="button" className="secondary" disabled={saving} onClick={()=>setEditing(null)}>Cancel</button></div>
      </form>}
      <div className="table-scroll"><FilterableTable aria-label="SLA status summary"><thead><tr>{report.summary_columns.map(column=><th key={column} scope="col">{column==='Status'?<span className="sla-status-heading">Status{manual&&<button type="button" className="icon-button" aria-label="Add manual SLA status" title="Add status" disabled={saving||publishing||!!editing} onClick={startStatus}><Plus size={16}/></button>}</span>:column}</th>)}</tr></thead><tbody>{[...report.summary,report.totals].map((row,index)=><tr key={index} className={index===report.summary.length?'sla-total':''}><th scope="row"><div className="sla-status-label"><button className="text-button" onClick={()=>show(index===report.summary.length?null:row.Status)}>{row.Status}</button>{index!==report.summary.length&&<span className="inline">{manual&&<button type="button" className="icon-button" aria-label={`Add order to status ${row.Status}`} disabled={saving} onClick={()=>setOrderEditor({status:row.Status})}><Plus size={15}/></button>}<button type="button" className="icon-button" aria-label={`Edit status ${row.Status}`} disabled={saving} onClick={()=>editStatus(row.Status)}><Pencil size={15}/></button>{manual&&report.custom_statuses?.includes(row.Status)&&<button type="button" className="icon-button" aria-label={`Delete status ${row.Status}`} title="Delete manual status" disabled={saving||publishing} onClick={()=>removeStatus(row.Status)}><Trash2 size={15}/></button>}</span>}</div></th>{report.summary_columns.slice(1).map(column=><td key={column}><button className="text-button" aria-label={`${row.Status}, ${column}: ${row[column]} orders`} onClick={()=>show(index===report.summary.length?null:row.Status,column==='Grand Total'?null:column)}>{row[column]||'—'}</button></td>)}</tr>)}</tbody></FilterableTable></div>
      {report.summary.length>0?<div className="chart-section" role="region" aria-label="SLA status bar chart"><div style={{height:Math.max(220,report.summary.length*40+70)}}><ResponsiveContainer width="100%" height="100%"><BarChart data={report.summary} layout="vertical" maxBarSize={24} margin={{top:12,right:24,left:10,bottom:12}}><CartesianGrid stroke="var(--chart-grid)" horizontal={false}/><XAxis type="number" allowDecimals={false}/><YAxis type="category" dataKey="Status" width={210} tick={{fontSize:12,fill:'var(--muted)'}}/><Tooltip/><Legend/>{categories.map(([name,color])=><Bar key={name} dataKey={name} stackId="sla" fill={color} isAnimationActive={false} onClick={entry=>show(entry.Status||entry.payload?.Status,name)} className="clickable-series"/>)}</BarChart></ResponsiveContainer></div></div>:<p className="table-empty">No queue orders available.</p>}
      {detail&&<SideDrawer key={detail.title} title={detail.title} rows={detailRows} columns={detailColumns} showOrderStatus onClose={()=>setDetail(null)} renderActions={editableDetail?rowActions:undefined} toolbar={editableDetail?<button type="button" className="secondary" onClick={()=>setOrderEditor({status:detail.status})}><Plus size={16}/>Add order</button>:undefined}/>}
      {orderEditor&&<SlaOrderEditor report={report} entry={orderEditor} onClose={()=>setOrderEditor(null)} onSaved={savedOrder}/>}
      {deleting&&<Dialog title="Delete manual SLA status" onClose={()=>{if(!saving)setDeleting(null);}} className="sla-delete-dialog"><form className="dialog-content" onSubmit={deleteStatus}><p>Remove <strong>{deleting.status}</strong> from {deleting.preview_name||deleting.report_date}.</p>{deleting.orders.length>0?<><p>Move its {deleting.orders.length} orders to another status. Every order will remain in the report and be counted once.</p><label>Move orders to<select aria-label="Move orders to" required value={moveTo} disabled={saving} onChange={event=>setMoveTo(event.target.value)}><option value="">Choose a status</option>{[...new Set([...report.summary.map(row=>row.Status),...suggestedStatuses])].filter(status=>status!==deleting.status).map(status=><option key={status} value={status}>{status}</option>)}</select></label></>:<p>This status has no orders.</p>}{deleteError&&<p role="alert" className="notice warning">{deleteError}</p>}<div className="inline"><button type="submit" className="primary" disabled={saving||(deleting.orders.length>0&&!moveTo)}><Trash2 size={16}/>{saving?'Deleting…':'Delete status'}</button><button type="button" className="secondary" disabled={saving} onClick={()=>setDeleting(null)}>Cancel</button></div></form></Dialog>}
    </>}
  </section>;
}
