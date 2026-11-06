import React, {useDeferredValue, useMemo, useState} from 'react';
import {Activity, ArrowLeftRight, CalendarDays, Check, Clock3, Database, ExternalLink, RefreshCw, FileSpreadsheet, HardDrive, Home, PanelLeftClose, PanelLeftOpen, Search, Settings2, Table2, Trash2, X} from 'lucide-react';

import {IconButton} from './workspaceUtils';
import {useWorkspacePreference} from './useWorkspacePreference';

const destinations=[['sla','SLA Status',Clock3],['slaCompare','SLA Compare',ArrowLeftRight],['capacity','Capacity Report',FileSpreadsheet],['daily','Daily Orders',CalendarDays],['monthly','Monthly Orders',FileSpreadsheet],['changes','Changes',ArrowLeftRight]];
const dateLabel=value=>value?new Date(value).toLocaleDateString(undefined,{day:'numeric',month:'short'}):'Date unavailable';

export function WorkspaceSidebar({state,selected,view,onNavigate,onSelect,onDelete,onBatchDelete,busy,snapshot,collapsed,onToggle,onRefresh,refreshing}) {
  const nav=(id,title,Icon)=><button key={id} title={collapsed?title:undefined} aria-label={title} aria-current={(view===id||id==='captures'&&view==='captureDetail')?'page':undefined} className={`nav-item ${(view===id||id==='captures'&&view==='captureDetail')?'selected':''}`} onClick={()=>onNavigate(id)}><Icon size={19}/><span>{title}</span></button>;
  return <aside className="sidebar" aria-label="Workspace sidebar">
    <div className="brand"><div className="brand-mark"><Activity size={25}/></div><div className="brand-copy">Tv Tracker<span>Production workspace</span></div><IconButton title="Refresh all workspaces from Google Sheets" className="icon-button brand-refresh" onClick={onRefresh} disabled={busy||refreshing}><RefreshCw size={17} className={refreshing?'spin':''}/></IconButton></div>
    <div className="sidebar-section-label"><span>WORKSPACE</span><IconButton title={collapsed?'Expand sidebar':'Collapse sidebar'} onClick={onToggle}>{collapsed?<PanelLeftOpen size={17}/>:<PanelLeftClose size={17}/>}</IconButton></div>
    <nav aria-label="Workspace navigation">{destinations.map(([id,title,Icon])=>nav(id,title,Icon))}<div className="nav-subsection">{nav('captures','Captures',HardDrive)}</div></nav>

  </aside>;
}

export function useSidebarState(){
  return useWorkspacePreference('sidebarCollapsed','tv-tracker-sidebar-collapsed',false,value=>typeof value==='boolean');
}

export function WorkspaceContext({production,view,preview,snapshot,reportMode,running,stage,pending,selected,sheetUrl,onRefresh,refreshing}) {
  const report=['daily','monthly','capacity','sla','slaCompare'].includes(view);
  const updated=report||view==='audit'||view==='importChanges'?null:production?snapshot?.updated_at:preview?.created;
  let productionUrl;
  try{const url=new URL(sheetUrl);if(url.protocol==='https:'&&url.hostname==='docs.google.com'&&url.pathname.startsWith('/spreadsheets/d/')&&!url.username&&!url.password)productionUrl=url.href;}catch{}
  return <div className="workspace-context" aria-label="Workspace context">
    <a className="context-source source-link" href={productionUrl||'https://docs.google.com/spreadsheets/'} target="_blank" rel="noopener noreferrer" title={productionUrl?'Open the production Google Sheet in your browser':'Open Google Sheets (no production spreadsheet configured)'}><Database size={14}/>Google Sheet<ExternalLink size={12}/></a>
    <span className="context-preview"><FileSpreadsheet size={14}/>{view==='importChanges'?'Imported order edits':(production||report)&&reportMode==='excel'?'Excel report':selected?(preview.name||`preview${selected}`):'No capture selected'}</span>
    <span className="context-freshness"><Clock3 size={14}/>{updated?`${production?'Refreshed':'Captured'} ${new Date(updated).toLocaleString(undefined,{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}`:report?'Reporting period below':['audit','importChanges'].includes(view)?'Saved on this computer':'Freshness unavailable'}</span>
    <button className="text-button context-refresh" onClick={onRefresh} disabled={refreshing||running} aria-label="Refresh production data"><RefreshCw size={14} className={refreshing?'spin':''}/>{refreshing?'Refreshing…':'Refresh'}</button>
    <span className={`context-job ${running?'is-running':''}`} role="status">{running?<i className="job-pulse"/>:<Check size={14}/>}<span>{running?stage||'Working…':pending?`${pending} awaiting sync`:'Ready'}</span></span>
  </div>;
}

export function CapturePicker({previews,selected,onSelect,onDelete,busy}){
  const [query,setQuery]=useState('');
  const items=previews.filter(p=>`${p.name} ${dateLabel(p.created)} ${p.row_count}`.toLowerCase().includes(query.toLowerCase()));
  const chosen=previews.find(p=>p.id===selected);
  return <section className="capture-picker" aria-label="Choose a saved capture"><label className="library-search"><Search size={16}/><input aria-label="Find saved capture" placeholder="Search name, date or row count" value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Selected capture<select aria-label="Selected capture" value={selected||''} onChange={e=>onSelect(Number(e.target.value))}>{chosen&&!items.includes(chosen)&&<option value={chosen.id}>{chosen.name} (selected)</option>}{items.map(p=><option key={p.id} value={p.id}>{p.name} · {p.row_count.toLocaleString()} rows · {dateLabel(p.created)}{p.id===previews[0]?.id?' · Latest':''}</option>)}</select></label>{chosen&&<IconButton title="Delete selected capture" disabled={busy} onClick={e=>onDelete(e,chosen.id)}><Trash2 size={16}/></IconButton>}{!items.length&&<span role="status">No captures match your search.</span>}</section>;
}

export function SheetSegments({value,onChange,counts,imported=false}){
  return <div className="sheet-segments segmented" aria-label="Data sheet group">{[['all','All Products'],['full',imported?'Full Search file':'Full Title'],['remaining',imported?'C-O & Update file':'Remaining Products']].map(([id,title])=><button key={id} aria-pressed={value===id} onClick={()=>onChange(id)}>{title}<span>{counts[id]?.toLocaleString()??'—'}</span></button>)}</div>;
}
