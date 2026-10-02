import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDown, ArrowUp, ArrowDownToLine, ArrowLeftRight, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, Clock3, CloudUpload, Database, FileSpreadsheet, Filter, HardDrive, LoaderCircle, Maximize2, Minimize2, Play, Plus, Printer, Search, SlidersHorizontal, Table2, Trash2, Upload, X } from 'lucide-react';
import './style.css';
import './desktop.css';
import {DesktopTools, LocalWelcome, OfflineNotice, WorkspaceBoundary} from './DesktopExperience';
import remainingProducts from '../../remaining_products.json';

import {EMPTY, DEFAULT_IGNORE, colors, str, label, normalized, badgeClass, STATUS_COLORS, statusColor, textColorForBg, api, saveBlob, csvDownload, matches, IconButton} from './workspaceUtils';
const OverviewDashboard = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.OverviewDashboard})));
const Chart = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.Chart})));
const DataTable = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.DataTable})));
const FilterPanel = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.FilterPanel})));
const DailyOrders = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.DailyOrders})));
const MonthlyOrders = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.MonthlyOrders})));
function formatTime12(time24) {
  if (!time24) return '';
  const [hStr, mStr] = time24.split(':');
  let h = parseInt(hStr, 10);
  const m = mStr || '00';
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12;
  if (h === 0) h = 12;
  return `${String(h).padStart(2, '0')}:${m} ${ampm}`;
}

const indianDateTime = new Intl.DateTimeFormat('en-IN', {
  timeZone:'Asia/Kolkata', day:'2-digit', month:'short', year:'numeric',
  hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:true
});

function TriggerClock({schedule}) {
  const [now,setNow]=useState(()=>Date.now());
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  const offset=330*60*1000;
  const day=new Date(now+offset).toISOString().slice(0,10);
  const midnight=Date.parse(`${day}T00:00:00+05:30`);
  const triggered=schedule?.last_triggered_date===day?(schedule.triggered_today||[]):[];
  const candidates=(schedule?.times||[]).map(time=>{
    const [hour,minute]=time.split(':').map(Number);
    const timestamp=midnight+(hour*60+minute)*60000;
    return triggered.includes(time)?timestamp+86400000:timestamp;
  });
  const next=candidates.length?Math.min(...candidates):null;
  return <div className="trigger-clock">
    <span>Indian time (IST)</span>
    <strong data-testid="indian-clock">{indianDateTime.format(now)} IST</strong>
    <span data-testid="next-trigger">{schedule?.enabled&&next?
      `Next run: ${indianDateTime.format(next)} IST${next<now?' (pending)':''}`:'Schedule paused'}</span>
  </div>;
}

function App() {
  const [state,setState]=useState({previews:[],job:{running:false,stage:'Ready'}}), [selected,setSelected]=useState(null), [preview,setPreview]=useState(EMPTY), [view,setView]=useState('overview');
  const [previous,setPrevious]=useState(''), [diff,setDiff]=useState(null), [keys,setKeys]=useState([]), [ignore,setIgnore]=useState(DEFAULT_IGNORE), [compareBusy,setCompareBusy]=useState(false), [compareError,setCompareError]=useState('');
  const [filters,setFilters]=useState({}), [filterColumn,setFilterColumn]=useState(null), [search,setSearch]=useState(''), [error,setError]=useState(''), [pending,setPending]=useState(false), [loading,setLoading]=useState(false), [uploading,setUploading]=useState(false);
  const [chartSelection,setChartSelection]=useState(null), [scheduleDraft,setScheduleDraft]=useState({enabled:false,times:['09:00'],newTime:'10:00'}), [savingSchedule,setSavingSchedule]=useState(false);
  const [selectedRemainingProducts, setSelectedRemainingProducts] = useState([]);
  const [liveSheets,setLiveSheets]=useState(null), [liveSheetError,setLiveSheetError]=useState('');
  const upload=useRef(), seen=useRef(null), scheduleLoaded=useRef(false), remainingLoaded=useRef(false), refreshRequest=useRef(null), jobRunning=useRef(false);
  const [compareAttempt,setCompareAttempt]=useState(0);

  function addTriggerTime() {
    const t = scheduleDraft.newTime?.trim();
    if (!t) return;
    const currentTimes = scheduleDraft.times || [];
    if (!currentTimes.includes(t)) {
      const updated = [...currentTimes, t].sort();
      setScheduleDraft(prev => ({ ...prev, times: updated }));
    }
  }

  function removeTriggerTime(timeToRemove) {
    const currentTimes = scheduleDraft.times || [];
    const updated = currentTimes.filter(t => t !== timeToRemove);
    setScheduleDraft(prev => ({ ...prev, times: updated }));
  }

  const handleProductSelectionChange = (newSelection) => {
    setSelectedRemainingProducts(newSelection);
    api('/api/remaining-products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remaining_products: newSelection })
    }).catch(console.error);
  };
  async function refresh() {
    if(refreshRequest.current)return refreshRequest.current;
    refreshRequest.current=(async()=>{
    const next=await api('/api/state');
    setState(next);jobRunning.current=next.job.running;
    if(next.schedule&&!scheduleLoaded.current){
      const times = next.schedule.times && next.schedule.times.length ? next.schedule.times : [next.schedule.time || '09:00'];
      setScheduleDraft(prev => ({ ...prev, enabled: !!next.schedule.enabled, times: times }));
      scheduleLoaded.current=true;
    }
    if(Array.isArray(next.remaining_products)&&!remainingLoaded.current){setSelectedRemainingProducts(next.remaining_products);remainingLoaded.current=true;}
    if(next.previews.length && next.previews[0].id!==seen.current){seen.current=next.previews[0].id;setSelected(next.previews[0].id);setPrevious(String(next.previews[1]?.id || ''));}
    })();
    try{return await refreshRequest.current;}finally{refreshRequest.current=null;}
  }
  useEffect(()=>{let active=true,timer;const poll=async()=>{try{if(active)await refresh();}catch(e){if(active)setError(e.message);}finally{if(active)timer=setTimeout(poll,document.hidden?30000:jobRunning.current?1800:10000);}};poll();return()=>{active=false;clearTimeout(timer);};},[]);
  useEffect(()=>{if(!selected)return;let cancelled=false;setLoading(true);setPreview(EMPTY);setFilters({});setFilterColumn(null);setSearch('');setKeys([]);api(`/api/previews/${selected}`).then(data=>{if(!cancelled)setPreview(data);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[selected]);
  useEffect(()=>{
    if(!['overview','sheets','changes'].includes(view))return;
    let active=true, busy=false;
    const refresh=async()=>{
      if(busy)return;
      busy=true;
      try{const data=await api('/api/live-sheets');if(active){setLiveSheets(data);setLiveSheetError('');}}
      catch(e){if(active){setLiveSheets(null);setLiveSheetError(e.message);}}
      finally{busy=false;}
    };
    refresh();const timer=setInterval(refresh,30000);
    return()=>{active=false;clearInterval(timer);};
  },[view,preview.name,state.job.running]);
  useEffect(()=>{setFilters({});setFilterColumn(null);setSearch('');setChartSelection(null);},[view,previous,selected]);
  useEffect(()=>{
    setDiff(null);setCompareBusy(false);setCompareError('');
    if(view!=='compare'||!previous||!selected||Number(previous)===selected)return;
    let cancelled=false;
    setCompareBusy(true);
    async function comparePreviews(){
      for(let attempt=0;attempt<3&&!cancelled;attempt++){
        try{
          const data=await api('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore})});
          if(!cancelled){setDiff(data);setCompareBusy(false);}
          return;
        }catch(e){
          if(cancelled)return;
          if(attempt===2||!(e instanceof TypeError)){setCompareError(e.message);setCompareBusy(false);return;}
          await new Promise(resolve=>setTimeout(resolve,1000));
        }
      }
    }
    comparePreviews();
    return()=>{cancelled=true;};
  },[previous,selected,keys,ignore,compareAttempt,view]);
  const comparisonTable = diff?.record_columns ? {columns:diff.record_columns,rows:[...diff.matched_rows,...diff.unmatched_rows]} : EMPTY;
  const liveCurrent=!!liveSheets&&['overview','sheets','changes'].includes(view);
  const table = view==='captures' ? preview : view==='compare' ? comparisonTable : view==='changes' ? (liveSheets?.sheets?.Changes||EMPTY) : (liveSheets?.sheets?.Overview||EMPTY);
  const liveFull=liveSheets?.sheets?.['Full Title'];
  const liveRemaining=liveSheets?.sheets?.['Remaining Products'];
  const filtered = useMemo(()=>table.rows.filter(row=>matches(row,filters)&&(!search||table.columns.some(c=>str(row[c]).toLowerCase().includes(search.toLowerCase())))),[table,filters,search]);
  const matchedComparison = view==='compare' ? filtered.filter(row=>['Unchanged','Matched - changed'].includes(row['Comparison Status'])) : [];
  const missingComparison = view==='compare' ? filtered.filter(row=>row['Comparison Status']==='Missing') : [];
  const chartRows = useMemo(()=>chartSelection?filtered.filter(row=>label(row[chartSelection.column])===chartSelection.value):[],[chartSelection,filtered]);
  const productSplit = useMemo(()=>{
    if(['captures','compare','daily','monthly'].includes(view) || !table.columns.includes('Product')) return null;
    let remainingRows = filtered.filter(row=>!['full title', 'full search'].includes(normalized(row.Product)));
    if (selectedRemainingProducts.length > 0) {
      const spSet = new Set(selectedRemainingProducts.map(p => p.toLowerCase()));
      remainingRows = remainingRows.filter(row => spSet.has(label(row.Product).toLowerCase()));
    }
    return {
      fullTitle: filtered.filter(row=>['full title', 'full search'].includes(normalized(row.Product))),
      remaining: remainingRows
    };
  },[filtered,table.columns,view,selectedRemainingProducts]);

  const overviewMetrics = useMemo(() => {
    if (view === 'compare') return [];
    if (view === 'captures') return [['Saved rows', preview.rows.length.toLocaleString(), 'green'], ['Columns', preview.columns.length, 'gray'], ['Source', preview.source || 'Local file', 'gray']];
    if(view==='changes')return [['Sync log entries',liveSheets?filtered.length.toLocaleString():'—','gray']];
    if(!liveSheets)return ['Visible orders','Online queue','Ground queue','Active clients','Full Title share'].map(title=>[title,'—','gray']);
    const ogC = table.columns.includes('Online/ Ground') ? 'Online/ Ground' : table.columns.includes('Online/Ground') ? 'Online/Ground' : null;
    const clC = table.columns.includes('Client') ? 'Client' : null;
    const prC = table.columns.includes('Product') ? 'Product' : null;

    const onN = ogC ? filtered.filter(r => str(r[ogC]).toLowerCase().includes('online')).length : 0;
    const grN = ogC ? filtered.filter(r => str(r[ogC]).toLowerCase().includes('ground')).length : 0;
    const clN = clC ? new Set(filtered.map(r => label(r[clC]))).size : 0;
    const ftN = prC ? filtered.filter(r => ['full title', 'full search'].includes(normalized(r[prC]))).length : 0;

    const tot = filtered.length || 1;
    return [
      ['Visible orders', filtered.length.toLocaleString(), 'green'],
      ['Online queue', `${onN.toLocaleString()} (${((onN/tot)*100).toFixed(1)}%)`, 'green'],
      ['Ground queue', `${grN.toLocaleString()} (${((grN/tot)*100).toFixed(1)}%)`, 'amber'],
      ['Active clients', clN.toLocaleString(), 'gray'],
      ['Full Title share', `${ftN.toLocaleString()} (${((ftN/tot)*100).toFixed(1)}%)`, 'gray']
    ];
  }, [view, filtered, table.columns, liveSheets]);

  async function extract(){setPending(true);setError('');try{await api('/api/extract',{method:'POST'});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  const [exporting,setExporting]=useState(false);
  async function exportSheets(){
    setExporting(true);setError('');
    try{
      const response=await fetch('/api/export/google-sheets');
      if(!response.ok)throw Error((await response.json()).error||'Export failed');
      const filename=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1]||'GoogleSheets.xlsx';
      saveBlob(await response.blob(),filename);
    }catch(e){setError(e.message);}finally{setExporting(false);}
  }
  async function syncSheets(){setPending(true);setError('');try{await api('/api/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview:selected,previous:previous?Number(previous):null,keys,ignore,remaining_products:selectedRemainingProducts.length>0?selectedRemainingProducts:null})});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function saveSchedule(enabled=true, times=scheduleDraft.times){
    setSavingSchedule(true);
    setError('');
    try{
      const saved=await api('/api/sync-schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,times})});
      setScheduleDraft(prev=>({...prev,enabled:saved.enabled,times:saved.times||[saved.time]}));
      await refresh();
    }catch(e){
      setError(e.message);
    }finally{
      setSavingSchedule(false);
    }
  }
  async function importFile(e){const file=e.target.files[0];if(!file)return;setUploading(true);setError('');try{const body=new FormData();body.append('file',file);await api('/api/import',{method:'POST',body});await refresh();}catch(e){setError(e.message);}finally{setUploading(false);e.target.value='';}}
  function choosePrevious(value){setPrevious(value);if(!value)return;const index=state.previews.findIndex(p=>p.id===Number(value));const newer=state.previews[index-1];if(newer)setSelected(newer.id);}
  function chooseLatest(value){const id=Number(value);setSelected(id);const index=state.previews.findIndex(p=>p.id===id);setPrevious(String(state.previews[index+1]?.id||''));}
  async function deletePreview(event,id){event.stopPropagation();const target=state.previews.find(p=>p.id===id);if(!window.confirm(`Delete ${target?.name||`preview${id}`} and its saved CSV/Excel files?`))return;setError('');try{await api(`/api/previews/${id}`,{method:'DELETE'});const next=await api('/api/state');setState(next);seen.current=next.previews[0]?.id??null;const nextSelected=id===selected?(next.previews[0]?.id??null):selected;setSelected(nextSelected);const index=next.previews.findIndex(p=>p.id===nextSelected);setPrevious(String(next.previews[index+1]?.id||''));if(!nextSelected){setPreview(EMPTY);setDiff(null);}}catch(e){setError(e.message);}}
  async function downloadChanges(){try{const response=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore,download:true})});if(!response.ok)throw Error((await response.json()).error);saveBlob(await response.blob(),`${diff.previous}-to-${diff.latest}-changes.xlsx`);}catch(e){setError(e.message);}}
  const running=state.job.running||pending, result=state.job.result;
  return <div className="workspace">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Activity size={23}/></div><div>DataTrace<span>STUDIO</span></div></div><div className="nav-label">WORKSPACE</div><nav>{[['overview','Overview',BarChart3],['sheets','Data sheets',Table2],['captures','Saved captures',HardDrive],['daily','Daily Orders',FileSpreadsheet],['monthly','Monthly report',CalendarDays],['changes','Changes',FileSpreadsheet],['compare','Compare previews',ArrowLeftRight]].map(([id,title,Icon])=><button className={view===id?'nav-item selected':'nav-item'} key={id} onClick={()=>setView(id)}><Icon size={18}/>{title}{id==='compare'&&diff&&<small>{diff.record_counts?diff.record_counts.missing+diff.record_counts.newly_added:diff.counts.added+diff.counts.removed}</small>}</button>)}</nav><div className="preview-heading"><span className="nav-label">SAVED PREVIEWS</span><span>{state.previews.length}</span></div><div className="preview-list">{state.previews.map(p=><div key={p.id} className={`preview-item ${selected===p.id?'selected':''}`}><button className="preview-select" onClick={()=>{setSelected(p.id);setView('captures');const index=state.previews.findIndex(x=>x.id===p.id);setPrevious(String(state.previews[index+1]?.id||''));}}><FileSpreadsheet size={17}/><div><strong>{p.name}</strong><small>{p.row_count.toLocaleString()} rows · {new Date(p.created).toLocaleDateString()}</small></div>{p.id===state.previews[0].id&&<i>Latest</i>}</button><IconButton title={`Delete ${p.name}`} disabled={state.job.running||pending} onClick={event=>deletePreview(event,p.id)}><Trash2 size={15}/></IconButton></div>)}{!state.previews.length&&<p className="no-previews">No saved previews</p>}</div><div className="sidebar-footer"><span className="status-dot"/>Running on your computer<a href={state.sheet_url} target="_blank" rel="noreferrer">Google Sheet ↗</a></div></aside>
    <main><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {view==='overview'?'Overview':view==='sheets'?'Data sheets':view==='captures'?'Saved captures':view==='daily'?'Daily Orders':view==='monthly'?'Monthly report':view==='changes'?'Changes':'Compare previews'}</div><div className="inline"><DesktopTools onNavigate={setView} onImport={()=>upload.current.click()} running={running}/><span className={`run-state ${running?'running':''}`}>{running&&<LoaderCircle size={14} className="spin"/>}{pending&&!state.job.running?'Starting…':state.job.stage}</span><button className="secondary" onClick={()=>upload.current.click()} disabled={uploading}><Upload size={16}/>{uploading?'Importing…':'Import file'}</button><button className="secondary" onClick={exportSheets} disabled={exporting||running} title="Download all Google Sheet tabs as Excel">{exporting?<LoaderCircle size={16} className="spin"/>:<ArrowDownToLine size={16}/>} {exporting?'Exporting...':'Export'}</button><input ref={upload} type="file" hidden accept=".csv,.xlsx" onChange={importFile}/></div></header>
      <div className="content"><div className="page-heading"><div><span className="eyebrow">DATATRACE QUEUE</span><h1>{view==='changes'?'Sync changes':view==='compare'?'Preview comparison':view==='sheets'?'Data sheets':view==='captures'?'Saved captures':view==='daily'?'Daily Orders':view==='monthly'?'Monthly report':'Queue overview'}</h1><p className="muted">{preview.name?`${preview.name} · ${new Date(preview.created).toLocaleString()} · ${preview.source}`:'No data captured yet'}</p></div><div className="page-actions"><button className="secondary" onClick={syncSheets} disabled={running||!selected||loading||compareBusy||!!compareError}>{state.job.action==='sync'&&running?<LoaderCircle size={17} className="spin"/>:<CloudUpload size={17}/>}<span>{state.job.action==='sync'&&running?'Syncing…':`Retry ${preview.name||'preview'} sync`}</span></button><details className="sync-schedule"><summary><Clock3 size={16}/>AutoLogin Trigger</summary><div>
        <TriggerClock schedule={state.schedule}/>
        <button className="secondary" disabled={savingSchedule||!state.schedule} onClick={()=>saveSchedule(!state.schedule?.enabled,state.schedule?.times||[state.schedule?.time||'09:00'])}>{state.schedule?.enabled?'Pause schedule':'Resume schedule'}</button>
        <div className="schedule-times-label">Scheduled times (IST):</div>
        <div className="schedule-times-list">
          {(scheduleDraft.times || []).map(t => (
            <div key={t} className="schedule-time-chip">
              <Clock3 size={13}/>
              <span>{formatTime12(t)}</span>
              <small className="time-24">({t})</small>
              <IconButton title={`Remove ${formatTime12(t)}`} onClick={() => removeTriggerTime(t)}><X size={13}/></IconButton>
            </div>
          ))}
        </div>
        <div className="schedule-add-row">
          <label>Indian Standard Time (UTC+05:30)<input aria-label="New trigger time" type="time" value={scheduleDraft.newTime || '10:00'} onChange={e => setScheduleDraft({ ...scheduleDraft, newTime: e.target.value })}/></label>
          <button type="button" className="add-time-btn" title="Add trigger time" onClick={addTriggerTime}><Plus size={15}/>Add</button>
        </div>
        <button className="primary" onClick={()=>saveSchedule()} disabled={savingSchedule||!scheduleDraft.times.length}>{savingSchedule?'Saving…':'Save AutoLogin Trigger'}</button>
        {state.schedule?.last_triggered_date&&<small>Last triggered {state.schedule.last_triggered_date}</small>}
      </div></details><button className="primary" onClick={extract} disabled={running}>{state.job.action==='extract'&&running?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}<span>{state.job.action==='extract'&&running?'Extracting queue…':'Run AutoLogin & Extract Queue'}</span></button></div></div>
      {view==='overview' && selected && <section className="automatic-statuses"><span className="eyebrow">AUTOMATIC STATUSES</span><div><span>Workflow Suspended</span><span aria-hidden="true">&#8594;</span><span className="status-rule-target" style={{background:statusColor('Awaiting for Clarification')}}>Awaiting for Clarification</span></div><div><span>Missing orders</span><span aria-hidden="true">&#8594;</span><span>Retained with existing status</span></div></section>}
      {error&&<div className="notice error" role="alert">{error}<IconButton title="Dismiss error" onClick={()=>setError('')}><X size={16}/></IconButton></div>}
      {liveSheetError&&(!state.capabilities?.desktop||state.capabilities?.google_configured)&&['overview','sheets','changes'].includes(view)&&<div className="notice warning" role="status">Connect Google Sheets to load production reports. {liveSheetError}</div>}
      <OfflineNotice snapshot={liveSheets}/>{liveCurrent&&!liveSheets.offline&&<div className="notice" role="status"><Check size={14}/>Google Sheets connected · all retained tracker orders{liveSheets.updated_at&&<span> · Refreshed {new Date(liveSheets.updated_at).toLocaleTimeString()}</span>}</div>}
      {result?.error&&<div className="notice warning" role="status">{result.preview_name&&<strong>{result.preview_name} saved. </strong>}{result.error}</div>}
      {result&&!result.error&&!running&&<div className="notice success"><Check size={16}/>{result.action==='sync'?`${result.preview_name} synced · ${result.rows} rows · ${result.worksheets?.length||0} Google Sheets tabs updated`:`${result.preview_name} saved locally · ${result.rows} rows · Google Sheets sync pending`}</div>}
      {result?.pass_report&&!running&&<div className="notice" role="status">{result.pass_report.scanned} scanned · {result.pass_report.added} added · {result.pass_report.updated} updated · {result.pass_report.unchanged} unchanged · {result.pass_report.not_in_latest?.length||0} not in latest preview</div>}
      {result?.pass_report&&!running&&((result.pass_report.ambiguous?.length||0)+(result.pass_report.unprocessed?.length||0)>0)&&<div className="notice warning" role="status">{(result.pass_report.ambiguous?.length||0)+(result.pass_report.unprocessed?.length||0)} review items · check Changes and the Needs review tab in Google Sheets.</div>}
      {!state.previews.length && !liveSheets ? <LocalWelcome onImport={()=>upload.current.click()}/> : <>
      {view==='captures'&&preview.id&&<div className="notice" role="status">Raw saved capture · {preview.name}<a className="secondary" href={`/api/previews/${preview.id}/download/xlsx`}>Download Excel</a></div>}{view==='compare'&&<section className="compare-controls"><label>Previous preview<select aria-label="Previous preview" value={previous} onChange={e=>choosePrevious(e.target.value)}><option value="">Select a preview</option>{state.previews.filter(p=>p.id!==selected).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><ArrowLeftRight size={18}/><label>Latest preview<select aria-label="Latest preview" value={selected||''} onChange={e=>chooseLatest(e.target.value)}>{state.previews.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><details className="match-options"><summary><SlidersHorizontal size={16}/>Matching columns {keys.length?`(${keys.length})`:'(Auto)'}</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={keys.includes(c)} onChange={()=>setKeys(keys.includes(c)?keys.filter(k=>k!==c):[...keys,c])}/>{c}</label>)}</div></details><details className="match-options"><summary>Ignored columns ({ignore.length})</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={ignore.includes(c)} onChange={()=>setIgnore(ignore.includes(c)?ignore.filter(k=>k!==c):[...ignore,c])}/>{c}</label>)}</div></details><button className="secondary" disabled={!diff||compareBusy} onClick={downloadChanges}><ArrowDownToLine size={16}/>Power BI changes.xlsx</button></section>}
      {view==='compare'&&compareError&&<div className="notice warning" role="alert">{compareError}<button className="secondary" onClick={()=>setCompareAttempt(value=>value+1)}>Retry comparison</button></div>}
      {view==='compare'&&!previous&&<div className="notice">Capture or import a second preview to compare changes.</div>}
      {view==='compare'&&diff&&<><p className="comparison-method">{diff.method}</p>{(diff.added_columns.length>0||diff.removed_columns.length>0)&&<div className="notice">Columns added: {diff.added_columns.join(', ')||'None'} · Columns removed: {diff.removed_columns.join(', ')||'None'}</div>}</>}
      {!['daily','monthly'].includes(view)&&<div className="metrics">{(view==='compare'?[['Matched',diff?.record_counts?.matched??'—','green'],['Missing Previews',diff?.record_counts?.missing??'—','red'],['Newly added',diff?.record_counts?.newly_added??'—','amber'],['Unchanged',diff?.record_counts?.unchanged??'—','gray']]:overviewMetrics).map(([title,value,color])=><div className={`metric ${color}`} key={title}><span>{title}</span><strong>{value}</strong></div>)}</div>}
      {!['daily','monthly'].includes(view)&&<div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search rows" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="Choose column filter" value={filterColumn||''} onChange={e=>setFilterColumn(e.target.value||null)}><option value="">Filter a column…</option>{table.columns.map(c=><option key={c}>{c}</option>)}</select>{Object.keys(filters).map(c=><button className="filter-chip" key={c} onClick={()=>setFilterColumn(c)}><Filter size={12}/>{c}</button>)}{Object.keys(filters).length>0&&<button className="text-button" onClick={()=>setFilters({})}>Clear filters</button>}<span className="row-tally">{filtered.length.toLocaleString()} / {table.rows.length.toLocaleString()} rows</span>{view!=='compare'&&preview.id&&<><a className="secondary" href='/api/export/google-sheets' title="Download Production_data.xlsx from Google Sheets"><ArrowDownToLine size={16}/>Excel</a><a className="secondary" href={`/api/previews/${preview.id}/download/csv`}>CSV</a></>}</div>}
      {(loading||(view==='compare'&&compareBusy))?<div className="loading"><LoaderCircle className="spin"/>Loading preview…</div>:<><div className={filterColumn?'data-layout with-filter':'data-layout'}><div className="data-main">{view==='overview'&&<><OverviewDashboard rows={filtered} columns={table.columns} onSelect={setChartSelection} selectedProducts={selectedRemainingProducts} setSelectedProducts={handleProductSelectionChange}/><Chart rows={filtered} columns={table.columns} onSelect={setChartSelection}/>{chartSelection&&<div className="chart-drilldown"><DataTable rows={chartRows} columns={table.columns} filters={{}} openFilter={()=>{}} filterable={false} onClose={()=>setChartSelection(null)} name={`${chartSelection.value} · ${chartRows.length} orders`}/></div>}</>}
        {view==='daily'&&<DailyOrders preview={preview}/>}
        {view==='monthly'&&<MonthlyOrders preview={preview} running={running}/>}
        {['overview','daily','monthly'].includes(view) ? null : productSplit ? <>
          <DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={'Production trackers'}/>
          <DataTable rows={liveFull?liveFull.rows.filter(row=>!search||liveFull.columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase()))):productSplit.fullTitle} columns={liveFull?.columns||table.columns} filters={liveFull?{}:filters} openFilter={setFilterColumn} name={'Full Title'}/>
          <DataTable rows={liveRemaining?liveRemaining.rows.filter(row=>!search||liveRemaining.columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase()))):productSplit.remaining} columns={liveRemaining?.columns||table.columns} filters={liveRemaining?{}:filters} openFilter={setFilterColumn} name={'Remaining Products'}/>
        </> : <>{view==='compare'&&diff?.order_append&&<section className="order-append"><div className="order-append-summary"><div><span>Previous last order</span><strong>{diff.order_append.anchor_order||'Not available'}</strong></div><div><span>First new order</span><strong>{diff.order_append.first_added_order||'—'}</strong></div><div><span>Latest new order</span><strong>{diff.order_append.latest_added_order||'—'}</strong></div><div><span>Orders added after it</span><strong>{diff.order_append.available?diff.order_append.count:'—'}</strong></div></div>{diff.order_append.available&&<DataTable rows={diff.order_append.rows} columns={diff.order_append.columns} filters={{}} openFilter={()=>{}} filterable={false} name={`Orders after ${diff.order_append.anchor_order}`}/>}</section>}{view==='compare'?<><DataTable rows={matchedComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`Matched orders · ${diff?.previous||'Previous'} and ${diff?.latest||'Latest'}`}/><DataTable rows={missingComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name="Missing Previews"/></>:<DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={view==='changes'?'Google Sheets sync log':view==='captures'?'Saved capture':'Production trackers'}/>}</>}
      </div>{filterColumn&&<FilterPanel key={filterColumn} column={filterColumn} rows={table.rows} filters={filters} setFilters={setFilters} close={()=>setFilterColumn(null)}/>}</div></>}
      </>}
      <footer className="page-footer"><span>DataTrace Studio · Your local production workspace</span><span>{state.pending_sync>0?`${state.pending_sync} pending sync · `:''}{state.previews.length} saved captures · Local storage</span></footer></div>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<WorkspaceBoundary><React.Suspense fallback={<div className="loading"><LoaderCircle className="spin"/>Opening workspace…</div>}><App/></React.Suspense></WorkspaceBoundary>);

