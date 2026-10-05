import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, Camera, Home, ListFilter, Settings2, ArrowDown, ArrowUp, ArrowDownToLine, ArrowLeftRight, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, Clock3, CloudUpload, Database, FileSpreadsheet, Filter, HardDrive, LoaderCircle, Maximize2, Minimize2, Play, Plus, Printer, Search, SlidersHorizontal, Table2, Trash2, Upload, X } from 'lucide-react';
import './style.css';
import './tokens.css';
import {OrdersWorkspace, ProductionOverview, OperationActivity, ThemeControl, VIEW_TITLES} from './StudioWorkspace';
import DismissibleNotice from './DismissibleNotice';
import {WorkspaceSidebar, WorkspaceContext, SheetSegments, CapturePicker, useSidebarState} from './WorkspaceShell';
import {MonthlyActivity} from './MonthlyMaintenance';
import {DesktopTools, LocalWelcome, OfflineNotice, WorkspaceBoundary} from './DesktopExperience';
import remainingProducts from '../../remaining_products.json';

import {EMPTY, DEFAULT_IGNORE, colors, str, label, normalized, badgeClass, STATUS_COLORS, statusColor, textColorForBg, api, saveBlob, csvDownload, matches, IconButton} from './workspaceUtils';
const OverviewDashboard = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.OverviewDashboard})));
const AdvancedChart = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.AdvancedChart})));
const SideDrawer = React.lazy(() => import('./WorkspaceViews').then(module => ({default: module.SideDrawer})));
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

function TriggerClock({schedule, clock}) {
  const [elapsed,setElapsed]=useState(()=>performance.now());
  useEffect(()=>{const timer=setInterval(()=>setElapsed(performance.now()),1000);return()=>clearInterval(timer);},[]);
  if (!clock?.synchronized || clock.epoch_ms == null) return <div className="trigger-clock"><span>Indian time (IST)</span><strong data-testid="indian-clock">Synchronizing Indian time…</strong><span>Scheduled runs wait for network time.</span></div>;
  const now=clock.epoch_ms+Math.max(0,elapsed-(clock.receivedAt??elapsed));
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
    <span>Indian time (IST) · Network synchronized</span>
    <strong data-testid="indian-clock">{indianDateTime.format(now)} IST</strong>
    <span data-testid="next-trigger">{schedule?.enabled&&next?
      `Next run: ${indianDateTime.format(next)} IST${next<now?' (pending)':''}`:'Schedule paused'}</span>
  </div>;
}

function StatusReport({rows}) {
  const counts=new Map();
  rows.forEach(row=>{const raw=str(row.Status).trim()||'(Blank)';const key=raw.toLowerCase();const entry=counts.get(key)||{name:raw,count:0};entry.count++;counts.set(key,entry);});
  return <section className="status-report"><div className="section-heading"><h2>Status Report</h2><span className="row-tally">{counts.size} statuses</span></div><div className="status-report-scroll"><table className="status-report-table"><thead><tr><th>Status</th><th>Orders</th><th>Share</th></tr></thead><tbody>{[...counts.values()].sort((a,b)=>b.count-a.count).map(item=>{const bg=statusColor(item.name);return <tr key={item.name} style={{backgroundColor:bg,color:textColorForBg(bg)}}><td>{item.name}</td><td>{item.count.toLocaleString()}</td><td>{rows.length?(item.count/rows.length*100).toFixed(1):'0.0'}%</td></tr>;})}</tbody></table></div></section>;
}


function App() {
  const [state,setState]=useState({previews:[],job:{running:false,stage:'Ready'}}), [selected,setSelected]=useState(null), [preview,setPreview]=useState(EMPTY), [view,setView]=useState('sheets');
  const [previous,setPrevious]=useState(''), [diff,setDiff]=useState(null), [keys,setKeys]=useState([]), [ignore,setIgnore]=useState(DEFAULT_IGNORE), [compareBusy,setCompareBusy]=useState(false), [compareError,setCompareError]=useState('');
  const [filters,setFilters]=useState({}), [filterColumn,setFilterColumn]=useState(null), [search,setSearch]=useState(''), [error,setError]=useState(''), [pending,setPending]=useState(false), [loading,setLoading]=useState(false), [uploading,setUploading]=useState(false);
  const [chartSelection,setChartSelection]=useState(null), [scheduleDraft,setScheduleDraft]=useState({enabled:false,times:['09:00'],newTime:'10:00'}), [savingSchedule,setSavingSchedule]=useState(false);
  const [selectedRemainingProducts, setSelectedRemainingProducts] = useState([]);
  const [savingProducts,setSavingProducts]=useState(false);
  const [liveSheets,setLiveSheets]=useState(null), [liveSheetError,setLiveSheetError]=useState('');
  const upload=useRef(), seen=useRef(null), scheduleLoaded=useRef(false), remainingLoaded=useRef(false), refreshRequest=useRef(null), jobRunning=useRef(false);
  const [compareAttempt,setCompareAttempt]=useState(0);
  const [sheetGroup,setSheetGroup]=useState('all'), [scheduleMessage,setScheduleMessage]=useState('');
  const [sidebarCollapsed,setSidebarCollapsed,sidebarReady,sidebarError]=useSidebarState();
  const mainScroll=useRef(null), viewScroll=useRef({});
  const navigate=next=>{if(next==='settings'){window.dispatchEvent(new Event('datatrace:settings'));return;} viewScroll.current[view]=mainScroll.current?.scrollTop||0;setView(next);};
  useEffect(()=>{if(mainScroll.current)mainScroll.current.scrollTop=viewScroll.current[view]||0;},[view]);
  const deferredSearch=useDeferredValue(search);
  const productionView=['sheets','overview'].includes(view);
  const searchIndex=useMemo(()=>new WeakMap(),[]);

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

  const handleProductSelectionChange = async (newSelection) => {
    if(savingProducts)return;
    setSavingProducts(true);
    try {await api('/api/remaining-products', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remaining_products: newSelection })
    });setSelectedRemainingProducts(newSelection);}
    catch(e){setError(`Product selection was not saved. ${e.message}`);}
    finally{setSavingProducts(false);}
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
    if(next.previews.length && next.previews[0].id!==seen.current){const priorLatest=seen.current;seen.current=next.previews[0].id;setSelected(current=>current===null||current===priorLatest?next.previews[0].id:current);setPrevious(current=>current||String(next.previews[1]?.id||''));}
    })();
    try{return await refreshRequest.current;}finally{refreshRequest.current=null;}
  }
  useEffect(()=>{let active=true,timer;const poll=async()=>{try{if(active)await refresh();}catch(e){if(active)setError(e.message);}finally{if(active)timer=setTimeout(poll,document.hidden?30000:jobRunning.current?1800:10000);}};poll();return()=>{active=false;clearTimeout(timer);};},[]);
  useEffect(()=>{if(!selected)return;let cancelled=false;setLoading(true);setPreview(EMPTY);setKeys([]);api(`/api/previews/${selected}`).then(data=>{if(!cancelled)setPreview(data);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[selected]);
  useEffect(()=>{
    if(!['sheets','overview'].includes(view))return;
    let active=true, busy=false;
    const refresh=async()=>{
      if(busy)return;
      busy=true;
      try{const data=await api('/api/live-sheets');if(active){setLiveSheets(data);setLiveSheetError('');}}
      catch(e){if(active){setLiveSheets(previous=>previous?{...previous,offline:true}:null);setLiveSheetError(e.message);}}
      finally{busy=false;}
    };
    refresh();const timer=setInterval(refresh,30000);
    return()=>{active=false;clearInterval(timer);};
  },[view,state.job.running]);
  useEffect(()=>{setFilters({});setFilterColumn(null);setSearch('');setChartSelection(null);},[view]);
  useEffect(()=>{if(!['sheets','overview'].includes(view)){setFilters({});setFilterColumn(null);setSearch('');setChartSelection(null);}},[previous,selected]);
  useEffect(()=>{
    setDiff(null);setCompareBusy(false);setCompareError('');
    if(view!=='changes'||!previous||!selected||Number(previous)===selected)return;
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
  const [syncAudit,setSyncAudit]=useState(null), [auditError,setAuditError]=useState('');
  useEffect(()=>{if(view!=='audit')return;let active=true;api('/api/sync-reports').then(data=>{if(active){setSyncAudit(data.report);setAuditError('');}}).catch(e=>{if(active)setAuditError(e.message);});return()=>{active=false;};},[view,state.job.running]);
  const auditTable=useMemo(()=>{
    const rows=[...(syncAudit?.changes||[]),...(syncAudit?.not_in_latest||[]).map(number=>({'Order Number':number,Action:'Not in latest preview'})),...(syncAudit?.ambiguous||[]).map(row=>({...row,Action:'Needs review'})),...(syncAudit?.default_conflicts||[]).map(row=>({'Order Number':row['Order Number'],Action:'Baseline conflict',Reason:row.Reason}))];
    return {columns:['Order Number','Action','Old Status','New Status','Reason'],rows};
  },[syncAudit]);
  const comparisonTable = diff?.record_columns ? {columns:diff.record_columns,rows:[...diff.matched_rows,...diff.unmatched_rows]} : EMPTY;
  const liveCurrent=!!liveSheets&&productionView;
  const allProduction=liveSheets?.sheets?.Overview||liveSheets?.sheets?.['All Products']||EMPTY;
  const sheetTables=useMemo(()=>({all:allProduction,
    full:liveSheets?.sheets?.['Full Title']||{columns:allProduction.columns,rows:allProduction.rows.filter(row=>['full title','full search'].includes(normalized(row.Product)))},
    remaining:liveSheets?.sheets?.['Remaining Products']||{columns:allProduction.columns,rows:allProduction.rows.filter(row=>!['full title','full search'].includes(normalized(row.Product))&&(!selectedRemainingProducts.length||selectedRemainingProducts.some(p=>normalized(p)===normalized(row.Product))))}
  }),[liveSheets,allProduction,selectedRemainingProducts]);
  const table = view==='captures' ? preview : view==='changes' ? comparisonTable : view==='audit' ? auditTable : view==='sheets'?sheetTables[sheetGroup]:allProduction;
  const liveFull=liveSheets?.sheets?.['Full Title'];
  const liveRemaining=liveSheets?.sheets?.['Remaining Products'];
  const filtered = useMemo(()=>{const query=deferredSearch.toLowerCase();return table.rows.filter(row=>{if(!matches(row,filters))return false;if(!query)return true;let indexed=searchIndex.get(row);if(!indexed){indexed=table.columns.map(c=>str(row[c]).toLowerCase()).join('\u0000');searchIndex.set(row,indexed);}return indexed.includes(query);});},[table,filters,deferredSearch,searchIndex]);
  const matchedComparison = view==='changes' ? filtered.filter(row=>['Unchanged','Matched - changed'].includes(row['Comparison Status'])) : [];
  const missingComparison = view==='changes' ? filtered.filter(row=>row['Comparison Status']==='Missing') : [];
  const chartRows = useMemo(()=>chartSelection?(chartSelection.rows||filtered.filter(row=>label(row[chartSelection.column])===chartSelection.value)):[],[chartSelection,filtered]);
  const productSplit = useMemo(()=>{
    if(['captures','changes','audit','daily','monthly'].includes(view) || !table.columns.includes('Product')) return null;
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
    if (view === 'changes') return [];
    if (view === 'captures') return loading || (selected && preview.id !== selected) ? [['Saved rows', '—', 'green'], ['Columns', '—', 'gray'], ['Source', loading ? 'Loading…' : 'Unavailable', 'gray']] : [['Saved rows', preview.rows.length.toLocaleString(), 'green'], ['Columns', preview.columns.length, 'gray'], ['Source', preview.source || 'Local file', 'gray']];
    if(view==='audit')return [['Sync log entries',filtered.length.toLocaleString(),'gray']];
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
  }, [view, filtered, table.columns, liveSheets, preview, loading, selected]);

  async function extract(){setPending(true);setError('');try{await api('/api/extract',{method:'POST'});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  const [exporting,setExporting]=useState(false);
  async function exportSheets(){
    setExporting(true);setError('');
    try{
      let response=await fetch('/api/export/google-sheets');
      if(response.status===409){
        const result=await response.json();
        if(!result.requires_short_names)throw Error(result.error||'Export failed');
        const proposed=Object.entries(result.proposed_names||{}).map(([from,to])=>`${from} → ${to}`).join('\n');
        if(!window.confirm(`Use these Excel tab names in the exported copy?\n\n${proposed}\n\nGoogle Sheets tab names stay unchanged.`))return;
        response=await fetch('/api/export/google-sheets?short_names=true');
      }
      if(!response.ok)throw Error((await response.json()).error||'Export failed');
      const filename=response.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1]||'Production_data.xlsx';
      saveBlob(await response.blob(),filename);
    }catch(e){setError(e.message);}finally{setExporting(false);}
  }
  async function syncSheets(){setPending(true);setError('');try{await api('/api/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview:selected,previous:previous?Number(previous):null,keys,ignore,remaining_products:selectedRemainingProducts.length>0?selectedRemainingProducts:null})});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function retryFailed(id){setPending(true);setError('');try{await api('/api/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview:id})});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function saveSchedule(enabled=true, times=scheduleDraft.times){
    setSavingSchedule(true);
    setScheduleMessage('');
    setError('');
    try{
      const saved=await api('/api/sync-schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled,times})});
      setScheduleDraft(prev=>({...prev,enabled:saved.enabled,times:saved.times||[saved.time]}));
      setScheduleMessage(saved.enabled?'Schedule saved. Times are in IST.':'Schedule paused.');
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
  return <div className={`workspace ${sidebarCollapsed?'sidebar-collapsed':''}`} data-view={view}>
    <a className="skip-link" href="#workspace-content">Skip to workspace</a>
    <WorkspaceSidebar state={state} selected={selected} view={view} onNavigate={navigate} collapsed={sidebarCollapsed} onToggle={()=>{if(sidebarReady)setSidebarCollapsed(!sidebarCollapsed).catch(()=>{});}} snapshot={liveSheets} busy={running} onDelete={deletePreview} onSelect={id=>{setSelected(id);navigate('captures');const index=state.previews.findIndex(p=>p.id===id);setPrevious(String(state.previews[index+1]?.id||''));}}/>
    <main ref={mainScroll}><header className="topbar"><div className="breadcrumb"><span>Workspace</span><ChevronRight size={13}/><strong>{VIEW_TITLES[view]}</strong></div><div className="inline"><DesktopTools onNavigate={navigate} onImport={()=>upload.current.click()} running={running}/><span className={`run-state ${running?'running':''}`}>{running&&<LoaderCircle size={14} className="spin"/>}{pending&&!state.job.running?'Starting…':state.job.stage}</span><button className="secondary" onClick={()=>upload.current.click()} disabled={uploading||(running&&state.job.action!=='sync')}><Upload size={16}/>{uploading?'Importing…':'Import file'}</button><button className="secondary" onClick={exportSheets} disabled={exporting||running} title="Download all Google Sheet tabs as Excel">{exporting?<LoaderCircle size={16} className="spin"/>:<ArrowDownToLine size={16}/>} {exporting?'Exporting...':'Export'}</button><input ref={upload} type="file" hidden accept=".csv,.xlsx" onChange={importFile}/></div></header>
      <div className="content" id="workspace-content" tabIndex={-1}><div className="page-heading"><div><span className="eyebrow">TITLE PRODUCTION</span><h1>{VIEW_TITLES[view]}</h1><p className="muted">{productionView?(view==='sheets'?'Keep every order in view.':'Your production, clearly organized.'):(preview.name?`${preview.name} · ${new Date(preview.created).toLocaleString()}`:'Your local production workspace')}</p></div><div className="page-actions"><button className="secondary" onClick={syncSheets} disabled={running||!selected||loading||compareBusy||!!compareError}>{state.job.action==='sync'&&running?<LoaderCircle size={17} className="spin"/>:<CloudUpload size={17}/>}<span>{state.job.action==='sync'&&running?'Syncing…':'Sync to Sheets'}</span></button><details className="sync-schedule"><summary><Clock3 size={16}/><span>AutoLogin Trigger</span><span className={`schedule-state ${state.schedule?.enabled?'enabled':''}`}>{state.schedule?.enabled?'On':'Paused'}</span></summary><div>
        <TriggerClock schedule={state.schedule} clock={state.clock}/>
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
        {scheduleMessage&&<p className="schedule-feedback" role="status"><Check size={14}/>{scheduleMessage}</p>}{state.schedule?.last_triggered_date&&<small>Last triggered {state.schedule.last_triggered_date}</small>}
      </div></details><button className="primary" onClick={extract} disabled={running}>{state.job.action==='extract'&&running?<LoaderCircle size={17} className="spin"/>:<Camera size={17}/>}<span>{state.job.action==='extract'&&running?'Extracting…':'Extract Queue'}</span></button></div></div>
      <WorkspaceContext view={view} production={productionView} preview={preview} snapshot={liveSheets} running={running} stage={pending&&!state.job.running?'Starting…':state.job.stage} pending={state.pending_sync} selected={selected}/>
      {sidebarError&&<div className="notice warning" role="alert">{sidebarError}</div>}
      {(state.failed_syncs||[]).map(failure=><div key={failure.preview_id} className="notice warning" role="alert"><strong>{failure.preview_name} retained locally.</strong> {failure.error}<button className="secondary" disabled={running} onClick={()=>retryFailed(failure.preview_id)}>Retry sync</button></div>)}
      {view==='audit'&&<div className="notice">Local sync activity · {syncAudit?.preview_name||'No sync report yet'}</div>}
      {view==='audit'&&auditError&&<div className="notice error">{auditError}</div>}
      {error&&<div className="notice error" role="alert">{error}<IconButton title="Dismiss error" onClick={()=>setError('')}><X size={16}/></IconButton></div>}
      {liveSheetError&&(!state.capabilities?.desktop||state.capabilities?.google_configured)&&productionView&&<div className="notice warning" role="status">Connect Google Sheets to load production reports. {liveSheetError}</div>}
      {productionView&&<OfflineNotice snapshot={liveSheets}/>}{liveCurrent&&!liveSheets.offline&&<DismissibleNotice key={`connected-${state.job.run_id}`} noticeId={`connected-${state.job.run_id}`} role="status"><Check size={14}/>Google Sheets connected · all retained tracker orders{liveSheets.updated_at&&<span> · Refreshed {new Date(liveSheets.updated_at).toLocaleTimeString()}</span>}</DismissibleNotice>}
      {result?.error&&<DismissibleNotice key={`error-${state.job.run_id}`} noticeId={`error-${state.job.run_id}`} className="notice warning" role="status">{result.preview_name&&<strong>{result.preview_name} saved. </strong>}{result.error}</DismissibleNotice>}
      {result&&!result.error&&!running&&<DismissibleNotice key={`result-${state.job.run_id}`} noticeId={`result-${state.job.run_id}`} className="notice success"><Check size={16}/>{result.action==='sync'?`${result.preview_name} synced · ${result.rows} rows · ${result.worksheets?.length||0} Google Sheets tabs updated`:`${result.preview_name} saved locally · ${result.rows} rows · Google Sheets sync pending`}</DismissibleNotice>}
      {result?.pass_report&&!running&&<DismissibleNotice key={`scan-${state.job.run_id}`} noticeId={`scan-${state.job.run_id}`} role="status">{result.pass_report.scanned} scanned · {result.pass_report.added} added · {result.pass_report.updated} updated · {result.pass_report.unchanged} unchanged · {result.pass_report.not_in_latest?.length||0} not in latest preview</DismissibleNotice>}
      {result?.pass_report&&!running&&((result.pass_report.ambiguous?.length||0)+(result.pass_report.unprocessed?.length||0)>0)&&<DismissibleNotice key={`review-${state.job.run_id}`} noticeId={`review-${state.job.run_id}`} className="notice warning" role="status">{(result.pass_report.ambiguous?.length||0)+(result.pass_report.unprocessed?.length||0)} review items · open Sync activity to review the saved local report.</DismissibleNotice>}
      {view==='audit'&&<><OperationActivity running={running}/><MonthlyActivity/></>}
      <React.Suspense fallback={<div className="loading" role="status"><LoaderCircle className="spin"/>Loading view…</div>}>{!state.previews.length && !liveSheets && !['monthly','audit'].includes(view) ? <LocalWelcome onImport={()=>upload.current.click()}/> : view==='overview'?<><ProductionOverview snapshot={liveSheets} state={state} onNavigate={navigate}/><OverviewDashboard rows={filtered} columns={table.columns} onSelect={setChartSelection} selectedProducts={selectedRemainingProducts} setSelectedProducts={handleProductSelectionChange} savingProducts={savingProducts}/><AdvancedChart rows={filtered} columns={table.columns} onSelect={setChartSelection}/><React.Suspense fallback={null}>{chartSelection&&<SideDrawer title={`${chartSelection.column}: ${chartSelection.value}`} rows={chartRows} columns={table.columns} onClose={()=>setChartSelection(null)}/>}</React.Suspense></>:view==='sheets'?<><SheetSegments value={sheetGroup} onChange={value=>{setSheetGroup(value);setFilterColumn(null);}} counts={Object.fromEntries(Object.entries(sheetTables).map(([key,value])=>[key,value.rows.length]))}/><div className={filterColumn?'data-layout with-filter':'data-layout'}><OrdersWorkspace snapshot={liveSheets} rows={filtered} columns={table.columns} search={search} setSearch={setSearch} filters={filters} setFilters={setFilters} openFilter={setFilterColumn} previews={state.previews}/>{filterColumn&&<FilterPanel key={filterColumn} column={filterColumn} rows={table.rows} filters={filters} setFilters={setFilters} close={()=>setFilterColumn(null)}/>}</div></>:<>
      {view==='captures'&&<CapturePicker previews={state.previews} selected={selected} onSelect={chooseLatest} onDelete={deletePreview} busy={running}/>}
      {view==='captures'&&preview.id&&<div className="notice" role="status">Raw saved capture · {preview.name}<a className="secondary" href={`/api/previews/${preview.id}/download/xlsx`}>Download Excel</a></div>}{view==='changes'&&<section className="compare-controls"><label>Previous preview<select aria-label="Previous preview" value={previous} onChange={e=>choosePrevious(e.target.value)}><option value="">Select a preview</option>{state.previews.filter(p=>p.id!==selected).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><ArrowLeftRight size={18}/><label>Latest preview<select aria-label="Latest preview" value={selected||''} onChange={e=>chooseLatest(e.target.value)}>{state.previews.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><span className="muted">Matched by Order Number (ignoring case and surrounding spaces)</span><details className="match-options"><summary>Ignored columns ({ignore.length})</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={ignore.includes(c)} onChange={()=>setIgnore(ignore.includes(c)?ignore.filter(k=>k!==c):[...ignore,c])}/>{c}</label>)}</div></details><button className="secondary" disabled={!diff||compareBusy} onClick={downloadChanges}><ArrowDownToLine size={16}/>Power BI changes.xlsx</button></section>}
      {view==='changes'&&compareError&&<div className="notice warning" role="alert">{compareError}<button className="secondary" onClick={()=>setCompareAttempt(value=>value+1)}>Retry comparison</button></div>}
      {view==='changes'&&!previous&&<div className="notice">Capture or import a second preview to compare changes.</div>}
      {view==='changes'&&diff&&<><p className="comparison-method">{diff.method}</p>{(diff.added_columns.length>0||diff.removed_columns.length>0)&&<div className="notice">Columns added: {diff.added_columns.join(', ')||'None'} · Columns removed: {diff.removed_columns.join(', ')||'None'}</div>}</>}
      {!['daily','monthly'].includes(view)&&<div className="metrics">{(view==='changes'?[['Matched',diff?.record_counts?.matched??'—','green'],['Missing Previews',diff?.record_counts?.missing??'—','red'],['Newly added',diff?.record_counts?.newly_added??'—','amber'],['Unchanged',diff?.record_counts?.unchanged??'—','gray']]:overviewMetrics).map(([title,value,color])=><div className={`metric ${color}`} key={title}><span>{title}</span><strong>{value}</strong></div>)}</div>}
      {!['daily','monthly'].includes(view)&&<div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search rows" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="Choose column filter" value={filterColumn||''} onChange={e=>setFilterColumn(e.target.value||null)}><option value="">Filter a column…</option>{table.columns.map(c=><option key={c}>{c}</option>)}</select>{Object.keys(filters).map(c=><button className="filter-chip" key={c} onClick={()=>setFilterColumn(c)}><Filter size={12}/>{c}</button>)}{Object.keys(filters).length>0&&<button className="text-button" onClick={()=>setFilters({})}>Clear filters</button>}<span className="row-tally">{filtered.length.toLocaleString()} / {table.rows.length.toLocaleString()} rows</span>{view!=='changes'&&preview.id&&<><button className="secondary" onClick={exportSheets} disabled={exporting||running}><ArrowDownToLine size={16}/>Production Excel</button><button className="secondary" onClick={()=>csvDownload(filtered,table.columns,`${view}.csv`)}>CSV</button></>}</div>}
      {(loading||(view==='changes'&&compareBusy))?<div className="loading"><LoaderCircle className="spin"/>Loading preview…</div>:<><div className={filterColumn?'data-layout with-filter':'data-layout'}><div className="data-main">{view==='sheets'&&<StatusReport rows={filtered}/>}
        {view==='daily'&&<DailyOrders preview={preview} running={running}/>}
        {view==='monthly'&&<MonthlyOrders preview={preview} running={running}/>}
        {['daily','monthly'].includes(view) ? null : productSplit ? <>
          <DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={'Production trackers'}/>
          <DataTable rows={liveFull?liveFull.rows.filter(row=>matches(row,filters)&&(!search||liveFull.columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase())))):productSplit.fullTitle} columns={liveFull?.columns||table.columns} filters={liveFull?{}:filters} openFilter={setFilterColumn} name={'Full Title'}/>
          <DataTable rows={liveRemaining?liveRemaining.rows.filter(row=>matches(row,filters)&&(!search||liveRemaining.columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase())))):productSplit.remaining} columns={liveRemaining?.columns||table.columns} filters={liveRemaining?{}:filters} openFilter={setFilterColumn} name={'Remaining Products'}/>
        </> : <>{view==='changes'&&diff?.order_append&&<section className="order-append"><div className="order-append-summary"><div><span>Previous last order</span><strong>{diff.order_append.anchor_order||'Not available'}</strong></div><div><span>First new order</span><strong>{diff.order_append.first_added_order||'—'}</strong></div><div><span>Latest new order</span><strong>{diff.order_append.latest_added_order||'—'}</strong></div><div><span>Orders added after it</span><strong>{diff.order_append.available?diff.order_append.count:'—'}</strong></div></div>{diff.order_append.available&&<DataTable rows={diff.order_append.rows} columns={diff.order_append.columns} filters={{}} openFilter={()=>{}} filterable={false} name={`Orders after ${diff.order_append.anchor_order}`}/>}</section>}{view==='changes'?<><DataTable rows={matchedComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`Matched orders · ${diff?.previous||'Previous'} and ${diff?.latest||'Latest'}`}/><DataTable rows={missingComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name="Missing Previews"/></>:<DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={view==='audit'?'Local sync activity':view==='captures'?'Saved capture':'Production trackers'}/>}</>}
      </div>{filterColumn&&<FilterPanel key={filterColumn} column={filterColumn} rows={table.rows} filters={filters} setFilters={setFilters} close={()=>setFilterColumn(null)}/>}</div></>}
      </>}
      </React.Suspense><footer className="page-footer"><span>Tv Tracker · Your local production workspace</span><span>{state.pending_sync>0?`${state.pending_sync} pending sync · `:''}{state.previews.length} saved captures · Local storage</span></footer></div>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<WorkspaceBoundary><React.Suspense fallback={<div className="loading"><LoaderCircle className="spin"/>Opening workspace…</div>}><App/></React.Suspense></WorkspaceBoundary>);

