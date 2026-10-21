import React,{useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Copy,Search} from 'lucide-react';
import {Dialog} from './DesktopExperience';
import {api} from './workspaceUtils';

const fieldsList=['Borrower','SLA Expiration','Orig','Online/Ground','Client','Product','State','County','Municipality','Parcel ID','Task Name','Task Status','Last User','ETA','ETA Comments','Comment','Skill Grade'];
function rowFields(row={},imported=false){
  const aliases={'SLA Expiration':['SLA Expiration*'],'Online/Ground':['Online/ Ground'],State:['St']};
  return Object.fromEntries((imported?[...fieldsList,'Out Time']:fieldsList).map(name=>[name,String(row[name]??aliases[name]?.map(alias=>row[alias]).find(value=>value!=null)??'')]));
}
function FullComment({name,value,onChange}){
  const input=useRef(null);
  useLayoutEffect(()=>{
    const node=input.current;if(!node)return;
    const fit=()=>{if(node.clientWidth){node.style.height='auto';node.style.height=`${node.scrollHeight+2}px`;}};
    // Child effects can run before the native dialog becomes visible.
    // Refit when it opens or its width changes, without overriding manual height changes.
    let width=0;
    const observer=new ResizeObserver(entries=>{const next=entries[0].contentRect.width;if(next!==width){width=next;fit();}});
    observer.observe(node);fit();return()=>observer.disconnect();
  },[value]);
  return <textarea ref={input} aria-label={name} rows={4} value={value} maxLength={10000} onChange={onChange}/>;
}
export default function SlaOrderEditor({report,entry,onClose,onSaved}){
  const editing=!!entry.row&&!entry.copy;
  const imported=report.report_scope==='imported_date',editableNames=imported?[...fieldsList,'Out Time']:fieldsList;
  const contextLabel=report.preview_name||`Imported report · ${report.report_date}`;
  const [source,setSource]=useState(entry.row?.['Source workbook']||'');
  const [number,setNumber]=useState(editing?entry.row['Order Number']:''),[status,setStatus]=useState(entry.status||entry.row?.Status||report.summary[0]?.Status||'Search In Progress');
  const [fields,setFields]=useState(rowFields(entry.row,imported)),[lookup,setLookup]=useState(null),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[copied,setCopied]=useState(false);
  const requestId=useRef(0);
  async function check(value=number){
    if(!value.trim())return;
    const id=++requestId.current;setBusy(true);setError('');setLookup(null);
    try{
      const scope=imported?{mode:'excel',date:report.report_date,source_workbook:source}:{preview_id:report.preview_id};
      const result=await api(`/api/sla-order?${new URLSearchParams({...scope,order_number:value.trim()})}`);
      if(id!==requestId.current)return;
      setLookup({...result,number:value.trim()});
      if(result.exists)setFields(rowFields(result.fields,imported));
    }catch(error){if(id===requestId.current)setError(error.message);}
    finally{if(id===requestId.current)setBusy(false);}
  }
  useEffect(()=>{if(editing)check(entry.row['Order Number']);return()=>{requestId.current++;};},[]);
  const checked=lookup&&lookup.number.toLowerCase()===number.trim().toLowerCase();
  async function save(event){
    event.preventDefault();if(saving||!checked)return;setSaving(true);setError('');
    try{
      const scope=imported?{mode:'excel',report_date:report.report_date,source_workbook:lookup.source_workbook||source}:{preview_id:report.preview_id};
      const result=await api('/api/sla-order',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...scope,order_number:number.trim(),status,fields,expected_revision:lookup.revision}),timeoutMs:180000});
      await onSaved(result);
    }catch(error){setError(error.message);}finally{setSaving(false);}
  }
  async function copyDetails(){
    try{await navigator.clipboard.writeText(['Order Number\tStatus\t'+editableNames.join('\t'),[number,status,...editableNames.map(name=>fields[name]||'')].map(value=>String(value).replace(/[\t\r\n]+/g,' ')).join('\t')].join('\n'));setCopied(true);}
    catch{setError('Clipboard access is unavailable. You can select and copy the field values.');}
  }
  return <Dialog title={editing?'Edit SLA order':entry.copy?'Copy SLA order':'Add SLA order'} onClose={()=>{if(!saving)onClose();}} className="sla-order-dialog">
    <form className="dialog-content" onSubmit={save}>
      <p className="muted">{contextLabel}{entry.copy?' · Enter a different Order Number for the copy':''}. Existing orders move to the chosen status and are counted once.</p>
      {imported&&<label>Workbook<select aria-label="SLA source workbook" value={source} disabled={editing||saving||busy} onChange={event=>{requestId.current++;setSource(event.target.value);setLookup(null);setBusy(false);setError('');}}><option value="">Find across imported workbooks</option>{[...new Set([...(report.source_workbooks||[]),'Manual SLA orders'])].map(name=><option key={name} value={name}>{name}</option>)}</select></label>}
      <div className="sla-order-lookup"><label>Order Number<input aria-label="SLA Order Number" value={number} readOnly={editing} disabled={saving} required maxLength={1000} onChange={event=>{requestId.current++;setBusy(false);setNumber(event.target.value);setLookup(null);setError('');}} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();if(!busy&&!saving)check();}}} autoFocus={!editing}/></label><button type="button" className="secondary" onClick={()=>check()} disabled={!number.trim()||busy||saving}><Search size={16}/>{busy?'Looking up…':'Look up order'}</button></div>
      {checked&&<p className="notice success" role="status">{lookup.exists?`Order found${lookup.row?.['Queue Presence']==='Manual addition'?' in manual additions':` in ${imported?lookup.row?.['Source workbook']||contextLabel:report.preview_name}`}. Its details are loaded.${lookup.row?.Status&&lookup.row.Status!==status?` Saving moves it from ${lookup.row.Status} to ${status}.`:''}`:'New order. Enter its details and SLA expiration to add it.'}</p>}
      <label className="sla-target-status">Status<input aria-label="SLA order status" value={status} list="sla-order-statuses" required maxLength={1000} disabled={saving} onChange={event=>setStatus(event.target.value)}/></label>
      <datalist id="sla-order-statuses">{[...new Set([...report.summary.map(row=>row.Status),'Typing in Progress','Completed and Delivered'])].map(name=><option key={name} value={name}/>)}</datalist>
      {checked&&lookup.exists&&lookup.row?.['Status Reason']&&<div className="sla-rule-result" role="region" aria-label="Current SLA result"><strong>Current status: {lookup.row.Status}</strong><p>{lookup.row['Status Reason']}</p></div>}
      <fieldset disabled={!checked||saving||busy} className="sla-order-fields"><legend>Order details</legend><div className="form-grid">{editableNames.map(name=><label key={name} className={name==='Comment'||name==='ETA Comments'?'sla-comment-field':undefined}>{name}{name==='SLA Expiration'?<><input aria-label={name} type="datetime-local" required value={(fields[name]||'').replace(' ','T').slice(0,16)} onChange={event=>setFields({...fields,[name]:event.target.value})}/><small>India time · determines Future, Negative, or Today SLA.</small></>:name==='Comment'||name==='ETA Comments'?<FullComment name={name} value={fields[name]} onChange={event=>setFields({...fields,[name]:event.target.value})}/>:<input aria-label={name} value={fields[name]} maxLength={10000} onChange={event=>setFields({...fields,[name]:event.target.value})}/>}</label>)}</div></fieldset>
      {error&&<p className="notice warning" role="alert">{error}</p>}
      <div className="sla-order-footer inline"><button type="submit" className="primary" disabled={!checked||busy||saving||!status.trim()}>{saving?'Saving…':lookup?.exists?'Save order':'Add order'}</button><button type="button" className="secondary" disabled={saving} onClick={copyDetails}><Copy size={16}/>{copied?'Copied':'Copy details'}</button><button type="button" className="secondary" disabled={saving} onClick={onClose}>Cancel</button></div>
    </form>
  </Dialog>;
}
