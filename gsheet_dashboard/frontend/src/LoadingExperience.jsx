import React, {createContext, useContext, useEffect, useId, useMemo, useRef, useState} from 'react';
import {Activity, Check, ChevronDown, ChevronUp, LoaderCircle, AlertCircle, X, Clock3} from 'lucide-react';
import './loadingExperience.css';

const ActivityContext=createContext(null);
export function ActivityProvider({children}) {
  const [loads,setLoads]=useState({});
  const value=useMemo(()=>({loads,setLoads}),[loads]);
  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity(busy,title) {
  const context=useContext(ActivityContext), id=useId();
  const setLoads=context?.setLoads;
  useEffect(()=>{
    if(!busy)return;
    setLoads?.(current=>({...current,[id]:title}));
    return ()=>setLoads?.(current=>{const next={...current};delete next[id];return next;});
  },[busy,id,title,setLoads]);
}

export function LoadingScreen({title='Loading workspace…'}) {
  const context=useContext(ActivityContext), id=useId();
  const setLoads=context?.setLoads;
  useEffect(()=>{
    setLoads?.(current=>({...current,[id]:title}));
    return ()=>setLoads?.(current=>{const next={...current};delete next[id];return next;});
  },[id,title,setLoads]);
  return <div className="workspace-loading" role="status" aria-live="polite" aria-busy="true">
    <div className="workspace-loading-icon"><LoaderCircle size={27} className="spin"/></div>
    <strong>{title}</strong><span>Getting everything ready for you</span>
    <div className="loading-skeleton" aria-hidden="true"><i/><i/><i/></div>
  </div>;
}

const EXTRACTION_STEPS=['Connect to TitleVision','Sign in and open queue','Extract queue orders','Save capture locally'];
function extractionStep(job){
  const stage=String(job.stage||'').toLowerCase();
  if(/waiting for the current sheets/.test(stage))return 0;
  if(job.action==='sync'||/syncing|writing|verifying/.test(stage))return 4;
  if(job.result?.scrape==='success')return 3;
  if(/local storage|sav(e|ed|ing)|preparing.*(sync|storage)/.test(stage))return 3;
  if(/extracting|queue fetched|queue results|refreshing queue/.test(stage))return 2;
  if(/login|signing|configured queue/.test(stage))return 1;
  return 0;
}

export function ActivityPanel({busy,title,error,cancelled,pendingSync,job={},startingExtraction=false,extractionError='',onCancel,cancelling,connectionError}) {
  const context=useContext(ActivityContext);
  const loads=Object.values(context?.loads||{});
  const [expanded,setExpanded]=useState(false);
  const [extractionRun,setExtractionRun]=useState(null);
  const wasExtracting=useRef(false);
  const [started,setStarted]=useState(null),[elapsed,setElapsed]=useState(0);
  useEffect(()=>{if(job.action==='extract'&&job.run_id!=null)setExtractionRun(job.run_id);},[job.action,job.run_id]);
  const extraction=startingExtraction||!!extractionError||job.action==='extract'||extractionRun!==null&&extractionRun===job.run_id;
  const extracting=startingExtraction||extraction&&job.running;
  useEffect(()=>{
    if(extracting&&!wasExtracting.current){setExpanded(true);setStarted(Date.now());setElapsed(0);}
    wasExtracting.current=extracting;
  },[extracting]);
  useEffect(()=>{
    if(!extracting||!started)return;
    const tick=()=>setElapsed(Math.max(0,Math.floor((Date.now()-started)/1000)));
    tick();const timer=setInterval(tick,1000);return()=>clearInterval(timer);
  },[extracting,started]);
  const result=job.result||{};
  const failed=extraction&&(extractionError||!job.running&&!startingExtraction&&result.error);
  const stopped=extraction&&!extracting&&result.cancelled;
  const done=extraction&&!extracting&&!failed&&!stopped&&!!job.result;
  const showExtraction=extraction&&(extracting||failed||stopped||done);
  const active=extracting||busy||loads.length>0;
  const current=startingExtraction?0:extractionStep(job);
  const stage=startingExtraction?'Starting queue extraction…':job.stage||'Extracting queue…';
  const label=showExtraction?(failed?'Queue extraction needs attention':stopped?'Queue extraction cancelled':done?'Queue extraction complete':job.cancel_requested||cancelling?'Cancelling extraction…':stage):active?(busy?title:loads[0]):error?'Needs attention':cancelled?'Operation cancelled':'Workspace ready';
  const Icon=failed?AlertCircle:stopped?X:active?LoaderCircle:error&&!showExtraction?AlertCircle:Check;
  const rows=Number(result.rows)||0;
  const saved=!!(result.preview_name||result.saved_locally||result.preview_id);
  return <aside className={`workspace-activity ${expanded?'is-expanded':'is-collapsed'} ${active?'is-active':''} ${failed||error&&!active?'has-error':''}`} aria-label="Workspace activity">
    <button type="button" className="activity-toggle" onClick={()=>setExpanded(value=>!value)} aria-expanded={expanded} aria-controls="workspace-activity-details" title={expanded?'Minimize activity':'Expand activity'}>
      <span className="activity-status-icon"><Icon size={18} className={active&&!failed&&!stopped?'spin':''}/></span>
      <span className="activity-summary"><small>TV TRACKER · {showExtraction?'QUEUE EXTRACTION':'ACTIVITY'}</small><strong role="status">{label}</strong></span>
      {expanded?<ChevronDown size={17}/>:<ChevronUp size={17}/>}
    </button>
    {expanded&&<div id="workspace-activity-details" className="activity-details">
      {showExtraction?<>
        <div className="activity-detail-heading"><Activity size={15}/><strong>{extracting?'Extracting your queue':failed?'Extraction needs attention':stopped?'Extraction stopped':'Capture ready'}</strong>{started&&<span className="extraction-elapsed"><Clock3 size={12}/>{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')}</span>}</div>
        {failed?<p role="alert">{String(extractionError||result.error)}{saved&&<><br/>{result.preview_name||'Your capture'} is saved locally.</>}</p>:stopped?<p>{saved?'Your saved capture is retained.':'Existing captures are unchanged.'}</p>:done?<p>{result.preview_name||'New capture'} saved · {rows.toLocaleString()} rows{result.google_sheet==='success'?' · Google Sheets updated': ' · Saved locally'}</p>:<p className="extraction-live-stage" role="status">{stage}</p>}
        {(!extractionError||job.running)&&<ol className="extraction-steps" aria-label="Queue extraction steps">{EXTRACTION_STEPS.map((step,index)=>{
          const complete=done?(index<4||result.google_sheet==='success'):index<current;
          const running=extracting&&index===current;
          return <li key={step} className={complete?'is-complete':running?'is-current':'is-waiting'} aria-current={running?'step':undefined}><span className="extraction-step-icon">{complete?<Check size={12}/>:running?<LoaderCircle size={12} className="spin"/>:index+1}</span><span>{step}</span></li>;
        })}</ol>}
        {extracting&&rows>0&&<span className="activity-sync">{rows.toLocaleString()} rows extracted{result.preview_name?' · '+result.preview_name:''}</span>}
        {extracting&&connectionError&&<p className="extraction-connection" role="status">Reconnecting for progress updates…</p>}
        {extracting&&<div className="extraction-panel-footer"><span>Keep working while this runs.</span>{job.action==='extract'&&job.running&&<button type="button" className="text-button" onClick={onCancel} disabled={cancelling||job.cancel_requested}>{cancelling||job.cancel_requested?'Cancelling…':'Cancel extraction'}</button>}</div>}
      </>:<>
        <div className="activity-detail-heading"><Activity size={15}/><strong>{active?'Work in progress':'Workspace status'}</strong></div>
        <p>{active?'You can move between reports while background operations continue.':error?String(error):cancelled?'The operation stopped. You can start another when ready.':'You’re up to date. Your next operation will appear here.'}</p>
        {loads.length>0&&<ul>{[...new Set(loads)].map(value=><li key={value}>{value}</li>)}</ul>}
      </>}
      {pendingSync>0&&<span className="activity-sync">{pendingSync} pending sync</span>}
    </div>}
    {active&&<div className="activity-progress" aria-hidden="true"><span/></div>}
  </aside>;
}
