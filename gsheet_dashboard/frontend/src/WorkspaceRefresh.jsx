import React, {useEffect,useState} from 'react';
import {Sun,Moon,Settings,Search,FileSpreadsheet,ArrowUpRight,Trash2,Database,CalendarDays,HardDrive} from 'lucide-react';
import {useWorkspacePreference} from './useWorkspacePreference';

export function NavbarPreferences(){
  const [theme,setTheme,ready,error]=useWorkspacePreference('theme','tv-tracker-theme','system',value=>['light','dark','system'].includes(value));
  const [systemDark,setSystemDark]=useState(()=>matchMedia('(prefers-color-scheme: dark)').matches);
  useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const change=()=>setSystemDark(media.matches);media.addEventListener('change',change);return()=>media.removeEventListener('change',change);},[]);
  const dark=theme==='dark'||theme==='system'&&systemDark;
  useEffect(()=>{document.documentElement.dataset.theme=dark?'dark':'light';},[dark]);
  return <div className="navbar-preferences" aria-label="Appearance and settings">
    <button type="button" role="switch" aria-label="Dark mode" aria-checked={dark} className="modern-theme-toggle" disabled={!ready} onClick={()=>setTheme(dark?'light':'dark').catch(()=>{})} title={dark?'Switch to light mode':'Switch to dark mode'}><Sun size={15}/><Moon size={15}/><span className={dark?'toggle-thumb is-dark':'toggle-thumb'}/></button>
    <button type="button" className="navbar-settings" aria-label="Settings" title="Connections & settings" onClick={()=>window.dispatchEvent(new Event('datatrace:settings'))}><Settings size={20}/></button>
    {error&&<span role="alert" className="preference-error">{error}</span>}
  </div>;
}

export function CaptureLibrary({previews,busy,onOpen,onDelete,onBatchDelete}){
  const [query,setQuery]=useState(''),[sort,setSort]=useState('newest'),[selection,setSelection]=useState([]);
  useEffect(()=>setSelection(current=>current.filter(id=>previews.some(p=>p.id===id))),[previews]);
  const date=value=>value?new Date(value).toLocaleString(undefined,{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}):'Date unavailable';
  const items=previews.filter(p=>`${p.name} ${date(p.created)} ${p.row_count}`.toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==='rows'?b.row_count-a.row_count:sort==='oldest'?new Date(a.created)-new Date(b.created):new Date(b.created)-new Date(a.created));
  const toggle=id=>setSelection(current=>current.includes(id)?current.filter(value=>value!==id):[...current,id]);
  return <section className="capture-library-page" aria-label="Saved capture library">
    <div className="library-overview"><div><span className="library-eyebrow">YOUR WORKSPACE ARCHIVE</span><h2>Every capture. One place.</h2><p>Browse saved snapshots, review orders, and export your data.</p></div><div className="library-total"><HardDrive size={21}/><strong>{previews.length}</strong><span>saved captures</span></div></div>
    <div className="library-controls"><label className="capture-search"><Search size={18}/><input aria-label="Search saved captures" placeholder="Search captures by name, date or rows…" value={query} onChange={e=>setQuery(e.target.value)}/></label><select aria-label="Sort captures" value={sort} onChange={e=>setSort(e.target.value)}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="rows">Most rows</option></select><label className="capture-select-all"><input type="checkbox" aria-label="Select all captures" checked={items.length>0&&items.every(p=>selection.includes(p.id))} onChange={e=>setSelection(e.target.checked?[...new Set([...selection,...items.map(p=>p.id)])]:selection.filter(id=>!items.some(p=>p.id===id)))}/>Select all</label>{selection.length>0&&<button className="secondary" disabled={busy} onClick={()=>onBatchDelete(selection)}><Trash2 size={15}/>Delete ({selection.length})</button>}</div>
    <p className="capture-result-count">{items.length} {items.length===1?'capture':'captures'}{query?' matching your search':''}</p>
    <div className="capture-card-grid">{items.map(p=><article className="capture-card" key={p.id}><div className="capture-card-top"><span className="capture-file-icon"><FileSpreadsheet size={24}/></span>{p.id===previews[0]?.id&&<span className="capture-latest">Latest capture</span>}<input type="checkbox" aria-label={`Select ${p.name}`} checked={selection.includes(p.id)} onChange={()=>toggle(p.id)}/></div><h3>{p.name}</h3><div className="capture-card-meta"><span><Database size={14}/>{p.row_count.toLocaleString()} rows</span><span><CalendarDays size={14}/>{date(p.created)}</span></div><div className="capture-card-actions"><button className="capture-open" onClick={()=>onOpen(p.id)}>Open capture<ArrowUpRight size={16}/></button><a href={`/api/previews/${p.id}/download/xlsx`} aria-label={`Download ${p.name}`} title="Download Excel"><FileSpreadsheet size={17}/></a><button disabled={busy} onClick={e=>onDelete(e,p.id)} aria-label={`Delete ${p.name}`} title="Delete capture"><Trash2 size={16}/></button></div></article>)}</div>
    {!items.length&&<div className="capture-empty"><HardDrive size={36}/><h3>{query?'No matching captures':'Your archive starts here'}</h3><p>{query?'Try a different name, date or row count.':'Extract a queue or import a file to save your first capture.'}</p>{query&&<button className="secondary" onClick={()=>setQuery('')}>Clear search</button>}</div>}
  </section>;
}
