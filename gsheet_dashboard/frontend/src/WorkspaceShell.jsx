import React, {useDeferredValue, useMemo, useState} from 'react';
import {Activity, ArrowLeftRight, CalendarDays, Check, Clock3, Database, ExternalLink, RefreshCw, FileSpreadsheet, HardDrive, Home, PanelLeftClose, PanelLeftOpen, Search, Settings2, Table2, Trash2, X} from 'lucide-react';
import {ThemeControl} from './StudioWorkspace';
import {IconButton} from './workspaceUtils';
import {useWorkspacePreference} from './useWorkspacePreference';

const destinations=[['daily','Daily Orders',CalendarDays],['monthly','Monthly Orders',FileSpreadsheet],['sla','SLA Status',Clock3],['slaCompare','SLA Compare',ArrowLeftRight],['capacity','Capacity Report',FileSpreadsheet],['changes','Changes',ArrowLeftRight]];
const dateLabel=value=>value?new Date(value).toLocaleDateString(undefined,{day:'numeric',month:'short'}):'Date unavailable';

export function WorkspaceSidebar({state,selected,view,onNavigate,onSelect,onDelete,onBatchDelete,busy,snapshot,collapsed,onToggle,onRefresh,refreshing}) {
  const [query,setQuery]=useState('');
  const [selectedCaptureIds,setSelectedCaptureIds]=useState(()=>new Set());
  const deferred=useDeferredValue(query);
  const captures=useMemo(()=>state.previews.filter(p=>`${p.name} ${dateLabel(p.created)} ${p.row_count}`.toLowerCase().includes(deferred.toLowerCase())),[state.previews,deferred]);

  const toggleSelect=(id,checked)=>{
    setSelectedCaptureIds(prev=>{
      const next=new Set(prev);
      if(checked)next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const toggleSelectAll=checked=>{
    if(checked){
      setSelectedCaptureIds(new Set(captures.map(p=>p.id)));
    }else{
      setSelectedCaptureIds(new Set());
    }
  };

  const isAllSelected=captures.length>0&&captures.every(p=>selectedCaptureIds.has(p.id));
  const someSelected=selectedCaptureIds.size>0;

  const nav=(id,title,Icon)=><button key={id} title={collapsed?title:undefined} aria-label={title} aria-current={view===id?'page':undefined} className={`nav-item ${view===id?'selected':''}`} onClick={()=>onNavigate(id)}><Icon size={19}/><span>{title}</span></button>;
  return <aside className="sidebar" aria-label="Workspace sidebar">
    <div className="brand"><div className="brand-mark"><Activity size={25}/></div><div className="brand-copy">Tv Tracker<span>Production workspace</span></div><IconButton title="Refresh all workspaces from Google Sheets" className="icon-button brand-refresh" onClick={onRefresh} disabled={busy||refreshing}><RefreshCw size={17} className={refreshing?'spin':''}/></IconButton></div>
    <div className="sidebar-section-label"><span>WORKSPACE</span><IconButton title={collapsed?'Expand sidebar':'Collapse sidebar'} onClick={onToggle}>{collapsed?<PanelLeftOpen size={17}/>:<PanelLeftClose size={17}/>}</IconButton></div>
    <nav aria-label="Workspace navigation">{destinations.map(([id,title,Icon])=>nav(id,title,Icon))}<div className="nav-subsection">{nav('captures','Captures',HardDrive)}</div></nav>
    <section className="capture-library" aria-label="Saved capture library">
      <div className="preview-heading" style={{display:'flex',alignItems:'center',justifyContent:'space-between',paddingRight:'4px'}}>
        <div style={{display:'flex',alignItems:'center',gap:'6px'}}>
          {captures.length>0&&(
            <input
              type="checkbox"
              aria-label="Select all captures"
              title="Select all captures"
              checked={isAllSelected}
              onChange={e=>toggleSelectAll(e.target.checked)}
              style={{cursor:'pointer',accentColor:'var(--accent,#0d9488)'}}
            />
          )}
          <span className="nav-label">SAVED CAPTURES</span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:'6px'}}>
          <span>{state.previews.length}</span>
          {someSelected&&(
            <button
              type="button"
              className="danger-button"
              style={{
                display:'inline-flex',
                alignItems:'center',
                gap:'4px',
                padding:'2px 7px',
                fontSize:'11px',
                fontWeight:600,
                background:'#e11d48',
                color:'#ffffff',
                border:'none',
                borderRadius:'4px',
                cursor:'pointer',
                lineHeight:'18px'
              }}
              title={`Delete ${selectedCaptureIds.size} selected captures`}
              disabled={busy}
              onClick={()=>{
                if(onBatchDelete){
                  onBatchDelete(Array.from(selectedCaptureIds));
                  setSelectedCaptureIds(new Set());
                }
              }}
            >
              <Trash2 size={12}/>
              <span>Delete ({selectedCaptureIds.size})</span>
            </button>
          )}
        </div>
      </div>
      <label className="library-search"><Search size={14}/><input aria-label="Search saved captures" placeholder="Find a capture…" value={query} onChange={e=>setQuery(e.target.value)}/>{query&&<IconButton title="Clear capture search" onClick={()=>setQuery('')}><X size={13}/></IconButton>}</label>
      <div className="preview-list" role="region" aria-label="Saved captures" tabIndex={0}>{captures.map(p=><div key={p.id} className={`preview-item ${selected===p.id?'selected':''}`} style={{display:'flex',alignItems:'center',gap:'4px'}}>
        <input
          type="checkbox"
          aria-label={`Select ${p.name}`}
          checked={selectedCaptureIds.has(p.id)}
          onChange={e=>toggleSelect(p.id,e.target.checked)}
          onClick={e=>e.stopPropagation()}
          style={{cursor:'pointer',accentColor:'var(--accent,#0d9488)',margin:'0 2px 0 6px'}}
        />
        <button className="preview-select" title={`${p.name} · ${p.row_count.toLocaleString()} rows · ${dateLabel(p.created)}`} aria-pressed={selected===p.id} onClick={()=>onSelect(p.id)}><FileSpreadsheet size={17}/><div><strong>{p.name}</strong><small>{p.row_count.toLocaleString()} rows · {dateLabel(p.created)}</small></div>{p.id===state.previews[0]?.id&&<i>Latest</i>}</button>
        <IconButton title={`Delete ${p.name}`} disabled={busy} onClick={event=>onDelete(event,p.id)}><Trash2 size={13}/></IconButton>
      </div>)}{!captures.length&&<p className="no-previews">{query?'No captures match your search.':'Your captures will appear here after an extraction or import.'}</p>}</div>
    </section>
    <div className="sidebar-footer">{nav('settings','Settings',Settings2)}<div className="sidebar-preferences"><ThemeControl/><span className={`connection-status ${snapshot?.offline?'offline':''}`}><i/>{snapshot?.offline?'Saved offline copy':snapshot?(snapshot.mode==='excel'?'Imported Excel':'Google Sheets connected'):'Local workspace'}</span>{state.sheet_url&&<a href={state.sheet_url} target="_blank" rel="noreferrer">Open Google Sheet ↗</a>}</div></div>
  </aside>;
}

export function useSidebarState(){
  return useWorkspacePreference('sidebarCollapsed','tv-tracker-sidebar-collapsed',false,value=>typeof value==='boolean');
}

export function WorkspaceContext({production,view,preview,snapshot,reportMode,running,stage,pending,selected,sheetUrl,onRefresh,refreshing}) {
  const report=['daily','monthly','capacity','sla','slaCompare'].includes(view);
  const source=view==='importChanges'?'Google Sheets change history':(production||report)&&reportMode==='excel'?'Imported Excel':production?(snapshot?.offline?'Saved Google Sheets copy':snapshot?(snapshot.mode==='excel'?'Imported Excel':'Live Google Sheets'):'Google Sheets unavailable'):report?'Production report':view==='audit'?'Local activity log':'Saved capture';
  const updated=report||view==='audit'||view==='importChanges'?null:production?snapshot?.updated_at:preview?.created;
  let productionUrl;
  try{const url=new URL(sheetUrl);if(url.protocol==='https:'&&url.hostname==='docs.google.com'&&url.pathname.startsWith('/spreadsheets/d/')&&!url.username&&!url.password)productionUrl=url.href;}catch{}
  const sourceContent=<><Database size={14}/>{source}</>;
  return <div className="workspace-context" aria-label="Workspace context">
    {production&&productionUrl?<a className={`context-source source-link ${snapshot?.offline?'stale':''}`} href={productionUrl} target="_blank" rel="noopener noreferrer" title="Open the production spreadsheet in your browser">{sourceContent}<ExternalLink size={12}/></a>:<span className={`context-source ${snapshot?.offline&&production?'stale':''}`}>{sourceContent}</span>}
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
