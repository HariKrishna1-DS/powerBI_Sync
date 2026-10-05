import React, {useEffect, useId, useMemo, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {ArrowDownToLine, ArrowUpDown, ArrowRight, Bookmark, Check, ChevronLeft, ChevronRight, Clock3, FileSearch, Filter, History, Inbox, LayoutDashboard, Monitor, Moon, Search, Sun, X} from 'lucide-react';
import {useWorkspacePreference} from './useWorkspacePreference';
import {api, csvDownload, str, normalized, badgeClass, IconButton} from './workspaceUtils';

export const VIEW_TITLES={overview:'Overview',sheets:'Data Sheets',captures:'Capture library',changes:'Changes',daily:'Daily Orders',monthly:'Monthly report',audit:'Activity'};
const orderCollator=new Intl.Collator(undefined,{numeric:true,sensitivity:'base'});
const relativeTime=value=>value?new Date(value).toLocaleString(): 'Not available';
const attention=row=>/clarification|hold|suspend|review|missing|rejected/i.test(str(row.Status));
function tone(value){const v=normalized(value);return /complete|delivered/.test(v)?'complete':/hold|suspend|clarification|missing|reject/.test(v)?'attention':/progress|available|review/.test(v)?'active':'neutral';}
export function StatusPill({value}){return <span className={`order-status ${tone(value)}`} data-status={badgeClass(value)}><i/>{str(value)||'Not set'}</span>;}

export function ThemeControl(){
  const [theme,setTheme,ready,error]=useWorkspacePreference('theme','tv-tracker-theme','system',value=>['light','dark','system'].includes(value));
  const [menuPosition,setMenuPosition]=useState(null);
  const trigger=useRef(null),menu=useRef(null),menuId=useId();
  const choices=[['system','System',Monitor],['light','Light',Sun],['dark','Dark',Moon]];
  const [,currentLabel,CurrentIcon]=choices.find(([value])=>value===theme);
  const closeMenu=()=>{setMenuPosition(null);if(trigger.current?.getClientRects().length)trigger.current.focus();};
  useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=theme==='system'?(media.matches?'dark':'light'):theme;};apply();media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply);},[theme]);
  useEffect(()=>{
    if(!menuPosition)return;
    menu.current?.querySelector('[aria-checked="true"]')?.focus();
    const dismiss=event=>{if(!menu.current?.contains(event.target)&&!trigger.current?.contains(event.target))setMenuPosition(null);};
    const reposition=()=>setMenuPosition(null);
    document.addEventListener('pointerdown',dismiss);
    window.addEventListener('resize',reposition);
    window.addEventListener('scroll',reposition,true);
    return()=>{document.removeEventListener('pointerdown',dismiss);window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);};
  },[menuPosition]);
  function toggleMenu(){
    if(menuPosition){closeMenu();return;}
    const rect=trigger.current.getBoundingClientRect();
    setMenuPosition({left:Math.max(12,Math.min(rect.right+10,innerWidth-196)),bottom:Math.max(12,innerHeight-rect.bottom)});
  }
  function menuKeys(event){
    if(event.key==='Escape'){event.preventDefault();closeMenu();return;}
    if(event.key==='Tab'){closeMenu();return;}
    if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key))return;
    event.preventDefault();
    const items=[...menu.current.querySelectorAll('[role="menuitemradio"]')];
    const index=items.indexOf(document.activeElement);
    items[event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();
  }
  return <div className="appearance-control"><label className="theme-control">Appearance<select aria-label="Appearance" disabled={!ready} value={theme} onChange={e=>{setTheme(e.target.value).catch(()=>{});}}>{choices.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><button ref={trigger} className="theme-icon-button" aria-label={`Theme: ${currentLabel}`} title={`Appearance: ${currentLabel}`} aria-haspopup="menu" aria-expanded={!!menuPosition} aria-controls={menuPosition?menuId:undefined} disabled={!ready} onClick={toggleMenu}><CurrentIcon size={19} aria-hidden="true"/></button>{menuPosition&&createPortal(<div ref={menu} id={menuId} className="appearance-menu" role="menu" aria-label="Appearance options" style={menuPosition} onKeyDown={menuKeys}><span className="appearance-menu-heading">Appearance</span>{choices.map(([value,label,Icon])=><button key={value} type="button" role="menuitemradio" aria-checked={theme===value} tabIndex={-1} onClick={()=>{setTheme(value).then(closeMenu).catch(()=>{});}}><Icon size={17} aria-hidden="true"/><span>{label}</span>{theme===value&&<Check size={15} aria-hidden="true"/>}</button>)}{error&&<p className="field-help" role="alert">{error}</p>}</div>,document.body)}{error&&!menuPosition&&<p className="field-help" role="alert">{error}</p>}</div>;
}

export function ProductionOverview({snapshot,state,onNavigate}){
  const rows=snapshot?.sheets?.Overview?.rows||snapshot?.sheets?.['All Products']?.rows||[];
  const statuses=useMemo(()=>{const counts=new Map();for(const row of rows){const key=str(row.Status)||'Not set';counts.set(key,(counts.get(key)||0)+1);}return [...counts].sort((a,b)=>b[1]-a[1]);},[rows]);
  return <div className="production-overview">
    <section className="overview-welcome"><span className="eyebrow">YOUR PRODUCTION WORKSPACE</span><h2>A clear view of the work ahead.</h2><p>Review your production, resolve exceptions and keep every capture accounted for.</p><button className="text-button" onClick={()=>onNavigate('sheets')}>Explore orders <ArrowRight size={16}/></button></section>
    <div className="summary-strip"><div className="metric green"><span>Production orders</span><strong>{snapshot?rows.length.toLocaleString():'—'}</strong></div><div className="metric red"><span>Need attention</span><strong>{snapshot?rows.filter(attention).length.toLocaleString():'—'}</strong></div><div className="metric blue"><span>Saved captures</span><strong>{state.previews.length}</strong></div><div className="metric amber"><span>Pending sync</span><strong>{state.pending_sync||0}</strong></div></div>
    <div className="overview-columns"><section className="studio-section"><h2>Status summary</h2><p className="muted">All retained production orders</p>{statuses.length?statuses.map(([status,count])=><div className="status-summary-row" data-status={badgeClass(status)} key={status}><StatusPill value={status}/><span>{count.toLocaleString()}</span></div>):<p className="empty-copy">Connect Google Sheets to see production status.</p>}</section><section className="studio-section"><h2>Continue your work</h2>{[['captures','Capture history',`${state.previews.length} saved captures`],['daily','Daily report','Orders, completions and SLA'],['audit','Sync and activity',state.pending_sync?`${state.pending_sync} captures awaiting sync`:'Review recent operations']].map(([view,title,detail])=><button className="continue-row" key={view} onClick={()=>onNavigate(view)}><span><strong>{title}</strong><small>{detail}</small></span><ArrowRight size={17}/></button>)}<div className="freshness-note"><Clock3 size={16}/><span>Last production refresh<br/><strong>{relativeTime(snapshot?.updated_at)}</strong></span></div></section></div>
  </div>;
}

export function OrdersWorkspace({snapshot,rows,columns,search,setSearch,filters,setFilters,openFilter,previews}){
  const [group,setGroup]=useState('all'),[product,setProduct]=useState('all'),[page,setPage]=useState(0),[selected,setSelected]=useState(null),[sort,setSort]=useState({column:'',direction:1}),[viewName,setViewName]=useState(''),[saving,setSaving]=useState(false),[message,setMessage]=useState(''),[allColumns,setAllColumns]=useState(false);
  const [saved,setSaved,viewsReady,preferenceError]=useWorkspacePreference('orderViews','tv-tracker-order-views',[],value=>Array.isArray(value)&&value.length<=12&&value.every(v=>v&&typeof v.name==='string'&&typeof v.search==='string'));
  const [history,setHistory]=useState(null),[historyError,setHistoryError]=useState('');
  const all=snapshot?.sheets?.Overview?.rows||snapshot?.sheets?.['All Products']?.rows||[];
  const products=useMemo(()=>[...new Set(all.map(row=>str(row.Product)).filter(Boolean))].sort(),[all]);
  const visible=useMemo(()=>{const matching=rows.filter(row=>(group!=='attention'||attention(row))&&(product==='all'||str(row.Product)===product));return sort.column?matching.sort((a,b)=>orderCollator.compare(str(a[sort.column]),str(b[sort.column]))*sort.direction):matching;},[rows,group,product,sort]);
  const pages=Math.max(1,Math.ceil(visible.length/50)),safePage=Math.min(page,pages-1),pageRows=visible.slice(safePage*50,safePage*50+50);
  const current=selected?all.find(row=>str(row['Order Number'])===selected):null;
  useEffect(()=>setPage(0),[search,group,product,filters]);
  useEffect(()=>{setHistory(null);setHistoryError('');if(!selected)return;const controller=new AbortController();api(`/api/order-history?order=${encodeURIComponent(selected)}`,{signal:controller.signal}).then(data=>setHistory(Array.isArray(data.events)?data.events:[])).catch(e=>{if(e.name!=='AbortError')setHistoryError('Capture history is temporarily unavailable. Try reopening this order.');});return()=>controller.abort();},[selected]);
  const displayColumns=allColumns?columns:['Order Number','Product','Status',...['Received Date','Order Date','Date','Assignee','Client'].filter(c=>columns.includes(c)).slice(0,2)].filter(c=>columns.includes(c));
  async function saveView(){const name=viewName.trim();if(!name)return;const next=[{name,search,group,product,filters},...saved.filter(v=>v.name!==name)].slice(0,12);try{await setSaved(next);setSaving(false);setMessage(`Saved view ${name}.`);}catch{setMessage('This view could not be saved. Check local storage.');}}
  function applyView(name){const value=saved.find(v=>v.name===name);if(value){setSearch(value.search);setGroup(value.group==='attention'?'attention':'all');setProduct(typeof value.product==='string'?value.product:'all');setFilters(value.filters&&typeof value.filters==='object'?value.filters:{});}}
  return <div className={`orders-workspace ${current?'has-inspector':''}`}><section className="orders-main" aria-label="Production orders">
    <div className="orders-search"><Search size={19}/><input aria-label="Search rows" placeholder="Search orders, clients, products…" value={search} onChange={e=>setSearch(e.target.value)}/><kbd>Search</kbd></div>
    <div className="summary-strip"><div className="metric green"><span>Visible orders</span><strong>{visible.length.toLocaleString()}</strong></div><div className="metric red"><span>Need attention</span><strong>{all.filter(attention).length.toLocaleString()}</strong></div><div className="metric blue"><span>Latest capture rows</span><strong>{previews[0]?.row_count?.toLocaleString()??'—'}</strong></div></div>
    <div className="order-filters"><div className="segmented" aria-label="Order view"><button aria-pressed={group==='all'} onClick={()=>setGroup('all')}>All orders</button><button aria-pressed={group==='attention'} onClick={()=>setGroup('attention')}>Needs attention</button></div><select aria-label="Product" value={product} onChange={e=>setProduct(e.target.value)}><option value="all">All products</option>{products.map(v=><option key={v}>{v}</option>)}</select><select aria-label="Choose column filter" value="" onChange={e=>{if(e.target.value)openFilter(e.target.value);}}><option value="">Filter a column…</option>{columns.map(c=><option key={c}>{c}</option>)}</select></div>
    <div className="order-tools"><button className="text-button" aria-pressed={allColumns} onClick={()=>setAllColumns(value=>!value)}>{allColumns?'Compact columns':'All columns'}</button><select aria-label="Saved views" disabled={!viewsReady} value="" onChange={e=>applyView(e.target.value)}><option value="">Saved views</option>{saved.map(v=><option key={v.name}>{v.name}</option>)}</select><button className="text-button" disabled={!viewsReady} onClick={()=>setSaving(v=>!v)}><Bookmark size={14}/>Save view</button><button className="text-button" onClick={()=>csvDownload(visible,columns,'Tv-Tracker-orders.csv')}><ArrowDownToLine size={15}/>CSV</button>{Object.keys(filters).map(c=><button className="filter-chip" key={c} onClick={()=>openFilter(c)}><Filter size={12}/>{c}</button>)}{Object.keys(filters).length>0&&<button className="text-button" onClick={()=>setFilters({})}>Clear filters</button>}</div>
    {saving&&<form className="save-view" onSubmit={e=>{e.preventDefault();saveView();}}><input aria-label="View name" placeholder="Name this view" maxLength={50} value={viewName} onChange={e=>setViewName(e.target.value)} autoFocus/><button className="secondary" disabled={!viewName.trim()}>Save</button><button type="button" className="text-button" onClick={()=>setSaving(false)}>Cancel</button></form>}{message&&<p className="field-help" role="status">{message}</p>}{preferenceError&&<p className="field-help" role="alert">{preferenceError}</p>}
    <div className="orders-table-scroll"><table className="orders-table"><thead><tr>{displayColumns.map(c=><th key={c} scope="col" aria-sort={sort.column===c?(sort.direction===1?'ascending':'descending'):'none'}><button onClick={()=>setSort({column:c,direction:sort.column===c?-sort.direction:1})}>{c}<ArrowUpDown size={12}/></button></th>)}</tr></thead><tbody>{pageRows.map((row,index)=><tr key={`${str(row['Order Number'])}-${index}`} className={str(row['Order Number'])===selected?'selected':''}>{displayColumns.map(c=><td key={c}>{c==='Order Number'?<button className="order-link" aria-label={`Open order ${str(row[c])}`} onClick={()=>setSelected(str(row[c]))}>{str(row[c])||'Unknown order'}</button>:c==='Status'?<StatusPill value={row[c]}/>:str(row[c])||'—'}</td>)}</tr>)}</tbody></table>{!visible.length&&<div className="order-empty"><FileSearch size={28}/><h3>No matching orders</h3><p>Try a different search or clear your filters.</p><button className="secondary" onClick={()=>{setSearch('');setFilters({});setProduct('all');setGroup('all');}}>Reset filters</button></div>}</div>
    <div className="orders-pagination"><span>{visible.length?`${safePage*50+1}–${Math.min((safePage+1)*50,visible.length)} of ${visible.length.toLocaleString()}`:'0 orders'}</span><div className="inline"><IconButton title="Previous orders page" disabled={safePage===0} onClick={()=>setPage(safePage-1)}><ChevronLeft size={17}/></IconButton><span>Page {safePage+1} of {pages}</span><IconButton title="Next orders page" disabled={safePage>=pages-1} onClick={()=>setPage(safePage+1)}><ChevronRight size={17}/></IconButton></div></div>
  </section>{current&&<aside className="order-inspector" aria-label="Order details"><div className="inspector-heading"><span className="eyebrow">ORDER DETAILS</span><IconButton title="Close order details" onClick={()=>setSelected(null)}><X size={17}/></IconButton></div><h2>{selected}</h2><p>{str(current.Product)||'Product not set'}</p><StatusPill value={current.Status}/><dl>{columns.filter(c=>!['Order Number','Product','Status'].includes(c)&&str(current[c])).map(c=><React.Fragment key={c}><dt>{c}</dt><dd>{str(current[c])}</dd></React.Fragment>)}</dl><h3><History size={16}/>Capture history</h3><p className="field-help">Matches in the latest 100 local captures.</p>{historyError?<p className="field-help" role="status">{historyError}</p>:history===null?<p className="field-help" role="status">Loading history…</p>:history.length?history.map(event=><div className="order-event" key={event.preview_id}><i/><div><strong>{event.preview_name}</strong><span>{event.status||'Status not recorded'}</span><small>{relativeTime(event.created)}</small></div></div>):<p className="field-help">No match in the latest 100 local captures.</p>}<p className="field-help">Production refreshed {relativeTime(snapshot?.updated_at)}{snapshot?.offline?' · saved offline copy':''}</p></aside>}</div>;
}

export function OperationActivity({running}){
  const [operations,setOperations]=useState([]),[error,setError]=useState('');
  useEffect(()=>{let active=true;api('/api/activity').then(data=>{if(active){setOperations(data.operations||[]);setError('');}}).catch(()=>{if(active)setError('Activity history is unavailable. Your captures remain in the workspace.');});return()=>{active=false;};},[running]);
  const labels={capture:'Queue capture',sync:'Google Sheets sync',scheduled_capture:'Scheduled capture'};
  const guidance={interrupted:'The app stopped during this operation. Check pending captures before retrying.',authentication:'Check the saved connection and account permissions.',connection:'Check the connection and retry when the service is available.',portal_results:'The portal did not provide a complete queue. Retry when it is available.',validation:'Review the sync details before retrying.',rate_limit:'The service limited requests. Wait before retrying.',operation_failed:'Review the latest error and retry after resolving it.'};
  return <section className="studio-section operation-history"><h2>Recent operations</h2><p className="muted">Local activity retained across restarts</p>{error&&<p role="status">{error}</p>}{operations.length?operations.slice(0,20).map(job=><article className="operation-row" key={job.id}><span className={`operation-dot ${job.status}`}/><div><strong>{labels[job.kind]||'Operation'}</strong><small>{relativeTime(job.started)}{job.preview_id?` · preview${job.preview_id}`:''}</small>{job.error_code&&<p>{guidance[job.error_code]||guidance.operation_failed}</p>}</div><span className="operation-state">{job.status}</span></article>):!error&&<p className="empty-copy">Your next capture or sync will appear here.</p>}</section>;
}
