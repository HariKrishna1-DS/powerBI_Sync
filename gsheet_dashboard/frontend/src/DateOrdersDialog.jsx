import {FilterableTable} from './ColumnFilters';
import React, {useDeferredValue,useEffect,useMemo,useRef,useState} from 'react';
import {LoaderCircle,Search} from 'lucide-react';
import {Dialog,OfflineNotice} from './DesktopExperience';
import {DataTable} from './WorkspaceViews';
import {api,str} from './workspaceUtils';

const countGroups={'Received':'received','Completed':'completed','Clarification':'clarification','Cancelled':'cancelled','Vendor Pending':'vendor','In-House Pending':'in_house','Capacity':'received','Ext capacity':'received'};

export const reportDateLabel=value=>/^\d{4}-\d{2}-\d{2}$/.test(str(value))?`${value.slice(8,10)}-${value.slice(5,7)}-${value.slice(2,4)}`:str(value);

export default function DateOrdersDialog({kind,date='',month='',year='',aggregate=false,initialGroup='received',target='',onClose,onUpdated}) {
  const [details,setDetails]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[reload,setReload]=useState(0);
  const [group,setGroup]=useState(initialGroup),[search,setSearch]=useState(''),[editing,setEditing]=useState(null),[draft,setDraft]=useState({});
  const [busy,setBusy]=useState(false),[editError,setEditError]=useState(''),[message,setMessage]=useState('');
  const [selectedDate,setSelectedDate]=useState(date);
  const dateList=useRef(null);
  const monthLabel=month?new Intl.DateTimeFormat('en',{month:'long',year:'numeric',timeZone:'UTC'}).format(new Date(`${month}-01T00:00:00Z`)):'';
  const query=useDeferredValue(search).toLowerCase();
  useEffect(()=>{
    const controller=new AbortController();
    setLoading(true);setError('');
    api(`/api/${kind==='capacity'?'capacity-report':'daily-orders'}/details?${new URLSearchParams({date:selectedDate,...(month?{month}:{}),...(year?{year}:{}),...(aggregate&&!selectedDate?{aggregate:'true'}:{})})}`,{signal:controller.signal})
      .then(value=>{setDetails(value);setError('');})
      .catch(error=>{if(error.name!=='AbortError'){setDetails(null);setError(error.message);}})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[kind,selectedDate,month,year,aggregate,reload]);
  useEffect(()=>{
    const list=dateList.current,selected=list?.querySelector('[aria-pressed="true"]');
    if(!selected)return;
    const bounds=list.getBoundingClientRect(),row=selected.closest('tr').getBoundingClientRect();
    const header=list.querySelector('thead').getBoundingClientRect().height;
    if(row.bottom>bounds.bottom||row.top<bounds.top+header)list.scrollTop+=row.top-bounds.top-header;
  },[details?.date,editing,month]);
  const selected=details?.groups.find(item=>item.key===group)||details?.groups[0];
  const columns=useMemo(()=>{
    const names=new Set(group==='changes'?['Changed At','Order Number','Column','Previous Value','New Value','Source Tabs']:['Order Number',...(details?.columns.includes('Source workbook')?['Source workbook']:[]),'Status','Out Time','Date','Product']);
    for(const column of details?.columns||[])names.add(column);
    for(const row of selected?.rows||[])for(const column of Object.keys(row))if(!column.startsWith('_'))names.add(column);
    return [...names].filter(column=>!column.startsWith('_'));
  },[details,selected,group,kind]);
  const rows=useMemo(()=>(selected?.rows||[]).filter(row=>!query||columns.some(column=>str(row[column]).toLowerCase().includes(query))),[selected,columns,query]);
  async function edit(row){
    if(busy)return;
    setBusy(true);setEditError('');
    try{
      const value=await api(`/api/order-details?${new URLSearchParams({order:row['Order Number'],month:details.mode==='excel'?'':row._month||'',mode:details.mode,source_workbook:row['Source workbook']||'',record_key:row._record_key||'',...(kind==='capacity'?{context:'capacity'}:{})})}`);
      setEditing({...value,reportDate:details.date||row['Capacity date']||'Undated'});setDraft(Object.fromEntries(value.editable_columns.map(column=>[column,str(value.order[column])])));
    }catch(error){setEditError(error.message);}finally{setBusy(false);}
  }
  const changes=editing?Object.fromEntries(editing.editable_columns.filter(column=>draft[column]!==str(editing.order[column])).map(column=>[column,draft[column]])):{};
  async function save(event){
    event.preventDefault();if(busy||!Object.keys(changes).length)return;
    setBusy(true);setEditError('');
    try{
      const result=await api('/api/order-details',{method:'POST',headers:{'Content-Type':'application/json'},timeoutMs:180000,
        body:JSON.stringify({order_number:editing.order['Order Number'],month:editing.month,mode:editing.mode,version:editing.version,source_workbook:editing.source_workbook||'',record_key:editing.record_key||'',report_date:editing.reportDate,changes,...(kind==='capacity'?{context:'capacity'}:{})})});
      setMessage(`Order ${result.order_number} saved. ${result.publication?.queued?'Google Sheets reports are updating.':result.publication?.synced?'Google Sheets reports updated.':'The change is saved locally; check report details for the Sheets update.'}`);
      setSelectedDate(details.date);setEditing(null);setReload(value=>value+1);onUpdated?.();
    }catch(error){setEditError(error.message);}finally{setBusy(false);}
  }
  function chooseDate(day,column='Received'){setSelectedDate(day);setGroup(countGroups[column]||'received');setSearch('');setEditError('');setMessage('');}
  function close(){if(!busy)onClose();}
  return <Dialog title={`${kind==='capacity'?'Capacity orders':'Daily orders'} · ${monthLabel||(year?`${year} YTD`:reportDateLabel(date))}`} onClose={close} className="detail-dialog date-orders-dialog">
    <div className="dialog-content"><OfflineNotice snapshot={details}/>
      {message&&<p className="notice success" role="status">{message}</p>}
      {target&&<p className="report-context">{target}</p>}
      {error&&<div className="notice warning" role="alert">{error}<button type="button" className="secondary" onClick={()=>setReload(value=>value+1)}>Retry details</button></div>}
      {editError&&<p className="notice warning" role="alert">{editError}</p>}
        {!editing&&month&&details&&<section className="capacity-month-days" aria-busy={loading} aria-label={`Daily capacity for ${monthLabel}`}>
          <h3>Daily dates · {monthLabel}</h3>{aggregate&&<button type="button" className="text-button" onClick={()=>chooseDate('')} aria-pressed={!selectedDate}>All orders · {monthLabel}</button>}
          <p className="report-context">Select a date to view and edit its orders below. Saturday and Sunday receipts and completions are included on the preceding Friday.</p>
          {details.daily?.length?<div ref={dateList} className="table-scroll"><FilterableTable><thead><tr>{details.capacity_columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{details.daily.map(day=><tr key={day.Date} className={details.date===day.Date?'daily-date-selected':undefined}>{details.capacity_columns.map(column=><td key={column}>{column==='Date'?<button type="button" className="text-button" aria-pressed={details.date===day.Date} disabled={busy} onClick={()=>chooseDate(day.Date)}>{reportDateLabel(day.Date)}</button>:<button type="button" className="text-button" aria-label={`${reportDateLabel(day.Date)}, ${column}: ${day[column]??0}`} disabled={busy} onClick={()=>chooseDate(day.Date,column)}>{day[column]??0}</button>}</td>)}</tr>)}</tbody></FilterableTable></div>:<p className="muted">No capacity activity is available for this month.</p>}
          {details.date&&<h3 className="capacity-selected-date">Orders · {reportDateLabel(details.date)}</h3>}
        </section>}
      {editing?<form className="date-order-editor" aria-label="Edit order details" onSubmit={save}>
        <div className="section-heading"><h3>Edit order {editing.order['Order Number']}</h3><button type="button" className="secondary" disabled={busy} onClick={()=>{setEditing(null);setEditError('');}}>Back to orders</button></div>
        {editing.source_workbook&&<p className="report-context">Source workbook: {editing.source_workbook}</p>}
        <p className="muted">Edit this order’s report source. Imported received dates use Date first, then In-Time; tracker dates use In-Time first. {kind==='capacity'&&details?.mode==='excel'?'Completed and Delivered orders use Out Time, with Saturday and Sunday counted on the preceding Friday.':'Completion dates use Out Time first, then Completed Time.'} Use MM/DD/YYYY or YYYY-MM-DD with an optional time.</p>
        <div className="date-editor-fields">{editing.editable_columns.map(column=><label key={column}>{column}<input aria-label={`Edit ${column}`} value={draft[column]} disabled={busy} maxLength={10000} required={['Status','Task Status'].includes(column)} onChange={event=>setDraft(current=>({...current,[column]:event.target.value}))}/></label>)}</div>
        <div className="date-editor-actions"><button className="primary" disabled={busy||!Object.keys(changes).length}>{busy?<><LoaderCircle size={16} className="spin"/>Saving…</>:'Save order changes'}</button><button type="button" className="secondary" disabled={busy} onClick={()=>{setEditing(null);setEditError('');}}>Cancel</button></div>
      </form>:loading?<p className="loading"><LoaderCircle className="spin"/>Loading date orders…</p>:details&&<>
        <p className="muted">{details.source} · {selected?.rows.length.toLocaleString()||0} matching records</p>
        {kind==='capacity'&&<p className="report-context">Received: {details.raw_received} orders {details.date?'on this reporting date':'in this reporting period'}. Status groups contain this period’s received orders; Completed uses recorded completion dates, including prior-month orders.</p>}
        <div className="date-detail-groups" role="group" aria-label="Order groups">{details.groups.map(item=><button type="button" className={item.key===selected?.key?'active':''} key={item.key} aria-pressed={item.key===selected?.key} onClick={()=>{setGroup(item.key);setSearch('');setEditError('');}}><span>{item.label}</span><strong>{item.rows.length.toLocaleString()}</strong></button>)}</div>
        {selected?.description&&<p className="report-context">{selected.description}</p>}
        <div className="search-input"><Search size={16}/><input aria-label="Search detail records" placeholder="Search all details" value={search} onChange={event=>setSearch(event.target.value)}/></div>
        <DataTable key={selected?.key} rows={rows} columns={columns} filters={{}} openFilter={()=>{}} filterable={false} name={selected?.label||'Orders'} onEdit={edit} editDisabled={busy}/>
      </>}
    </div>
  </Dialog>;
}
