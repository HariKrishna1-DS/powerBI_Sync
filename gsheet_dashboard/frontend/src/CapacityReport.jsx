import {FilterableTable} from './ColumnFilters';
import React, {useEffect,useState} from 'react';
import {ResponsiveContainer,ComposedChart,Bar,Line,XAxis,YAxis,CartesianGrid,Tooltip,Legend} from 'recharts';
import {api} from './workspaceUtils';
import {OfflineNotice} from './DesktopExperience';
import ReportOrderSearch from './ReportOrderSearch';
const DateOrdersDialog=React.lazy(()=>import('./DateOrdersDialog'));
const displayDate=value=>/^\d{4}-\d{2}-\d{2}$/.test(String(value))?`${value.slice(8,10)}-${value.slice(5,7)}-${value.slice(2,4)}`:/^\d{4}-\d{2}$/.test(String(value))?new Intl.DateTimeFormat('en',{month:'short',year:'2-digit',timeZone:'UTC'}).format(new Date(`${value}-01T00:00:00Z`)).replace(' ','-'):value;
const countGroups={'Received':'received','Completed':'completed','Clarification':'clarification','Cancelled':'cancelled','Vendor Pending':'vendor','In-House Pending':'in_house','Capacity':'received','Ext capacity':'received'};

export default function CapacityReport({revision,running}) {
  const [report,setReport]=useState(null),[capacity,setCapacity]=useState(700),[extended,setExtended]=useState(750),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [detailDate,setDetailDate]=useState(null),[detailMonth,setDetailMonth]=useState(null);
  const [countDetail,setCountDetail]=useState(null);
  async function refresh(){try{const value=await api('/api/capacity-report');setReport(value);setCapacity(value.capacity);setExtended(value.extended_capacity);setError('');}catch(e){setReport(previous=>previous?{...previous,offline:true}:null);setError(e.message);}}
  useEffect(()=>{refresh();const timer=setInterval(()=>{if(!document.hidden)refresh();},30000);return()=>clearInterval(timer);},[revision,running]);
  async function save(){setBusy(true);try{const value=await api('/api/report-capacity',{method:'POST',timeoutMs:180000,headers:{'Content-Type':'application/json'},body:JSON.stringify({capacity:Number(capacity),extended_capacity:Number(extended)})});await refresh();if(!value.publication.synced&&!value.publication.queued)setError(`Saved locally. Sheets update needs retry: ${value.publication.sync_error}`);}catch(e){setError(e.message);}finally{setBusy(false);}}
  const total=(label,rows)=>({Date:label,...Object.fromEntries((report?.columns||[]).slice(1).map(column=>[column,rows.reduce((sum,row)=>sum+Number(row[column]||0),0)]))});
  function showCount(row,column){
    const period=/^\d{4}-\d{2}-\d{2}$/.test(row.Date)?{date:row.Date}:/^\d{4}-\d{2}$/.test(row.Date)?{month:row.Date,aggregate:true}:row.Date==='Total'?{month:report.month,aggregate:true}:{year:report.month.slice(0,4),aggregate:true};
    setCountDetail({...period,initialGroup:countGroups[column],target:column.includes('capacity')||column==='Capacity'?`${column}: ${row[column]??0}. The table shows received orders against this target.`:''});
  }
  const table=(title,rows)=><section className="table-section"><h2>{title}</h2><div className="table-scroll"><FilterableTable><thead><tr>{report.columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map(row=><tr key={row.Date} className={row.Date.includes('Total')?`capacity-total ${row.Date==='Total'?'capacity-daily-total':''}`:row.Date===detailDate||row.Date===detailMonth?'daily-date-selected':undefined}>{report.columns.map(column=><td key={column}>{column==='Date'?/^\d{4}-\d{2}(-\d{2})?$/.test(row.Date)?<button type="button" className="text-button" aria-pressed={row.Date===detailDate||row.Date===detailMonth} onClick={()=>row.Date.length===7?setDetailMonth(row.Date):setDetailDate(row.Date)}>{displayDate(row.Date)}</button>:displayDate(row[column]):<button type="button" className="text-button" aria-label={`${displayDate(row.Date)}, ${column}: ${row[column]??0}`} onClick={()=>showCount(row,column)}>{row[column]??0}</button>}</td>)}</tr>)}</tbody></FilterableTable></div></section>;
  return <section className="daily-orders capacity-report"><div className="section-heading"><h2>PR Excel</h2><a className="secondary" href="/api/export/report?sheet=PR%20Excel" download>Download PR Excel</a></div><div className="monthly-actions"><label>Daily capacity<input type="number" min="0" step="1" value={capacity} onChange={e=>setCapacity(e.target.value)}/></label><label>Extended daily capacity<input type="number" min="0" step="1" value={extended} onChange={e=>setExtended(e.target.value)}/></label><button className="primary" disabled={busy||running} onClick={save}>{busy?'Saving…':'Save capacity'}</button></div>
    <p className="report-context">Capacity Report uses imported Excel orders. Saturday and Sunday receipts and completions are included on the preceding Friday.</p>
    {report?.import_required&&<p className="notice">Import Excel files to populate Capacity Report.</p>}
    <ReportOrderSearch name="Capacity Report" scope="capacity" revision={report} disabled={!report}/>
    {error&&<p className="notice warning" role="alert">{error}</p>}
    <OfflineNotice snapshot={report}/>
    {report?.completion_date_basis==='out_time'&&<p className="report-context">Completed counts use each Completed and Delivered order’s Out Time, including orders received in earlier months. A date can have completions even when no orders were received that day.{report.missing_completion_date_count>0&&` ${report.missing_completion_date_count} completed orders have a blank or invalid Out Time and are excluded from completed counts.`}</p>}
    {report&&<><p className="report-context">{report.source} · {report.scope_label||report.month}</p>{table('Monthly capacity',[...report.monthly,total(`${report.month.slice(0,4)} YTD Total`,report.monthly.filter(row=>row.Date.startsWith(report.month.slice(0,4))))])}{table('Daily capacity',[...report.daily,total('Total',report.daily)])}<section className="daily-chart" aria-label="Capacity report chart"><h2>Overall · {report.scope_label||report.month}</h2><div style={{height:360}}><ResponsiveContainer width="100%" height="100%"><ComposedChart data={report.daily}><CartesianGrid strokeDasharray="3 3"/><XAxis dataKey="Date"/><YAxis/><Tooltip/><Legend/><Bar dataKey="Received" fill="#315c9b" isAnimationActive={false}/><Bar dataKey="Completed" fill="#5ba4cf" isAnimationActive={false}/><Line dataKey="Capacity" stroke="#dc793b" dot={false} isAnimationActive={false}/><Line dataKey="Ext capacity" stroke="#8c93cf" dot={false} isAnimationActive={false}/></ComposedChart></ResponsiveContainer></div></section></>}
    {detailDate&&<React.Suspense fallback={null}><DateOrdersDialog key={detailDate} kind="capacity" date={detailDate} onClose={()=>setDetailDate(null)} onUpdated={refresh}/></React.Suspense>}
    {detailMonth&&<React.Suspense fallback={null}><DateOrdersDialog key={detailMonth} kind="capacity" month={detailMonth} onClose={()=>setDetailMonth(null)} onUpdated={refresh}/></React.Suspense>}
    {countDetail&&<React.Suspense fallback={null}><DateOrdersDialog kind="capacity" {...countDetail} onClose={()=>setCountDetail(null)} onUpdated={refresh}/></React.Suspense>}
  </section>;
}
