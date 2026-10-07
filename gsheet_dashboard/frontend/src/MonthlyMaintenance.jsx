import React, {useEffect, useState} from 'react';
import {LoaderCircle, ArrowDownToLine, X} from 'lucide-react';
import {api, saveBlob} from './workspaceUtils';
const operationName=kind=>({setup:'Monthly setup',import:'Workbook import',rollover:'Month rollover',open_month:'New month tabs'}[kind]||'Monthly operation');

export function MonthlyDownload({month, disabled}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  async function download(){
    setBusy(true);setError('');
    try{
      const response=await fetch(`/api/export/report?month=${encodeURIComponent(month)}`,{signal:AbortSignal.timeout(120000)});
      if(!response.ok){const body=await response.json();throw Error(body.error||'The monthly export failed.');}
      const filename=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1]||`TV_Search_Production_Report_${month}.xlsx`;
      saveBlob(await response.blob(),filename);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <div className="monthly-download"><button className="secondary" disabled={busy||disabled||!/^\d{4}-\d{2}$/.test(month||'')} onClick={download}>{busy?<LoaderCircle size={16} className="spin"/>:<ArrowDownToLine size={16}/>} {busy?'Generating Excel…':'Download Excel'}</button>{error&&<p role="alert">{error}</p>}</div>;
}

export function MonthlyMaintenance({month, running, onChanged}) {
  const [files,setFiles]=useState({}),[plan,setPlan]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[history,setHistory]=useState([]),[message,setMessage]=useState('');
  const workingMonth=/^\d{4}-\d{2}$/.test(month||'')&&month>'2026-09'?month:'2026-10';
  const fields=plan?.kind==='rollover'?['moved']:plan?.kind==='setup'?['renamed','added']:['read','added','updated','unchanged','skipped'];
  const shortTitle=value=>(value||'').replace('TV_Search_Production_Report_','').replaceAll('_',' ');
  async function refresh(){try{const data=await api('/api/monthly-maintenance');setHistory(data.operations||[]);}catch(e){setError(e.message);}}
  useEffect(()=>{refresh();const timer=setInterval(refresh,30000);return()=>clearInterval(timer);},[]);
  async function preview(kind){
    setBusy(true);setError('');setMessage('');setPlan(null);
    try{
      let options;
      if(kind==='import'){
        const body=new FormData();body.append('kind',kind);body.append('month',workingMonth);
        Object.entries(files).forEach(([field,file])=>{if(file)body.append(field,file);});
        options={method:'POST',body};
      }else options={method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind,month:workingMonth})};
      setPlan(await api('/api/monthly-maintenance/preview',{...options,signal:AbortSignal.timeout(120000)}));
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function confirm(){
    setBusy(true);setError('');
    try{
      const result=await api('/api/monthly-maintenance/apply',{method:'POST',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(120000),body:JSON.stringify({id:plan.id,confirmed:true})});
      setMessage(`Completed. ${result.moves?.length||0} orders moved. Affected existing tabs were backed up.`);
      setPlan(null);await refresh();onChanged();
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  return <details className="monthly-maintenance"><summary>Monthly setup, import and rollover</summary>
    <p className="muted">New orders stay in their arrival month. Rollover moves unfinished orders to the next month. September 2026 stays archived.</p>
    <div className="monthly-actions"><button className="secondary" disabled={busy||running} onClick={()=>preview('setup')}>Set up monthly tabs</button><button className="secondary" disabled={busy||running||!month||month<='2026-09'} onClick={()=>preview('rollover')}>Run month rollover</button><span className="muted">Working month: {workingMonth}</span></div>
    <div className="monthly-imports"><label>Full Search workbook<input type="file" accept=".xlsx" disabled={busy} onChange={e=>setFiles({...files,full_search:e.target.files[0]})}/></label><label>C-O and Update workbook<input type="file" accept=".xlsx" disabled={busy} onChange={e=>setFiles({...files,co_update:e.target.files[0]})}/></label><button className="secondary" disabled={busy||running||!Object.values(files).some(Boolean)} onClick={()=>preview('import')}>Preview workbook import</button></div>
    {busy&&<p role="status"><LoaderCircle size={16} className="spin"/> Preparing or verifying the operation…</p>}
    {error&&<p className="notice error" role="alert">{error}</p>}{message&&<p className="notice success" role="status">{message}</p>}
    {plan&&<section className="monthly-preview" aria-label="Monthly operation preview"><h3>{plan.kind==='rollover'?'Rollover dry run':plan.kind==='import'?'Import preview':'Monthly setup preview'}</h3>
      <p>Review these counts before confirming. Existing tabs are copied as backups before changes. A changed or expired preview must be refreshed.</p>
      {plan.kind==='rollover'&&<p><strong>{(plan.counts||[]).reduce((total,item)=>total+(item.moved||0),0)} orders would move.</strong> No orders have moved yet.</p>}
      <div className="table-scroll"><table><thead><tr><th>Source / target</th>{fields.map(field=><th key={field}>{field[0].toUpperCase()+field.slice(1)}</th>)}</tr></thead><tbody>{(plan.counts||[]).map((c,i)=><tr key={i}><td>{c.source&&<span title={c.source}>{shortTitle(c.source)}<br/></span>}<span title={c.target}>{c.target?`To: ${shortTitle(c.target)}`:Object.keys(c.targets||{}).map(shortTitle).join(', ')}</span></td>{fields.map(k=><td key={k}>{c[k]??'—'}</td>)}</tr>)}</tbody></table></div>
      {!plan.counts?.length&&<p>No eligible changes were found.</p>}
      {!!plan.reviews?.length&&<details><summary>{plan.reviews.length} review items</summary><ul className="monthly-review-list">{plan.reviews.slice(0,100).map((r,i)=><li key={i}>{r['Order Number']||`Row ${r.row||'unknown'}`}: {r.Reason}</li>)}</ul>{plan.reviews.length>100&&<p>Showing 100. Download the report for all items.</p>}</details>}
      <div className="monthly-actions"><button className="primary" disabled={busy||running||!plan.counts?.length} onClick={confirm}>Confirm {plan.kind==='rollover'?'rollover':plan.kind==='import'?'import':'monthly setup'}</button><button className="secondary" disabled={busy} onClick={()=>setPlan(null)}><X size={14}/>Cancel preview</button><button className="secondary" onClick={()=>saveBlob(new Blob([JSON.stringify(plan,null,2)],{type:'application/json'}),'monthly-preview.json')}>Download report</button></div>
    </section>}
    {history.some(item=>item.automatic&&item.status==='preview')&&<div className="notice">Month-end rollover is ready to review. Select the completed month and run its rollover preview.</div>}
    {history.filter(item=>item.status==='preview').slice(0,3).map(item=><p key={item.id}><button className="text-button" disabled={busy||running} onClick={()=>{setPlan(item);setError('');}}>Resume saved preview: {operationName(item.kind)} · {new Date(item.created*1000).toLocaleString()}</button></p>)}
  </details>;
}

export function MonthlyActivity(){
  const [items,setItems]=useState([]),[error,setError]=useState('');
  useEffect(()=>{let active=true;api('/api/monthly-maintenance').then(data=>{if(active)setItems(data.operations||[]);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
  return <section className="studio-section"><h2>Monthly production activity</h2>{error&&<p role="alert">{error}</p>}{!items.length&&!error&&<p className="muted">Imports and rollover reports will appear here.</p>}{items.map(item=><details key={item.id}><summary>{operationName(item.kind)} · {item.status} · {new Date(item.created*1000).toLocaleString()} · {item.moves?.length||0} moves</summary><button className="secondary" onClick={()=>saveBlob(new Blob([JSON.stringify(item,null,2)],{type:'application/json'}),'monthly-activity.json')}>Download full report</button><div className="monthly-review-list">{(item.moves||[]).map((move,i)=><p key={i}><strong>{move['Order Number']}</strong> · {move.from} → {move.to} · {move.reason}</p>)}</div></details>)}</section>;
}
