import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDown, ArrowUp, ArrowDownToLine, ArrowLeftRight, BarChart3, Check, ChevronLeft, ChevronRight, Database, FileSpreadsheet, Filter, LoaderCircle, Play, Plus, Printer, Search, SlidersHorizontal, Table2, Upload, X } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Brush } from 'recharts';
import './style.css';

const EMPTY = {columns: [], rows: []};
const DEFAULT_IGNORE = ['Sync Timestamp', 'Queue Age Hours', 'Time Since Arrival', 'Task Time in Queue'];
const colors = ['#147d72', '#d79a32', '#596cc0', '#bb6179', '#4b9db4', '#849157'];
const str = value => value == null ? '' : String(value);
const label = value => str(value) || '(Blank)';
async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) { let body; try { body = await response.json(); } catch { body = {}; } throw Error(body.error || `Request failed (${response.status})`); }
  return response.json();
}
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function csvDownload(rows, columns, name) {
  const cell = value => '"' + str(value).replaceAll('"', '""') + '"';
  saveBlob(new Blob(['\ufeff' + [columns, ...rows.map(row => columns.map(c => row[c]))].map(row => row.map(cell).join(',')).join('\r\n')], {type: 'text/csv;charset=utf-8'}), name);
}
function matches(row, filters, except) {
  return Object.entries(filters).every(([column, filter]) => {
    if (column === except) return true;
    const value = str(row[column]);
    if (filter.values && !filter.values.includes(value)) return false;
    if (!filter.operator || filter.operator === 'none') return true;
    const query = filter.query || '';
    if (filter.operator === 'contains') return value.toLowerCase().includes(query.toLowerCase());
    if (filter.operator === 'excludes') return !value.toLowerCase().includes(query.toLowerCase());
    if (filter.operator === 'equals') return value === query;
    if (filter.operator === 'blank') return !value;
    if (filter.operator === 'notblank') return !!value;
    const parse = v => v.trim() === '' ? NaN : Number.isFinite(Number(v)) ? Number(v) : Date.parse(v);
    const a = parse(value), b = parse(query);
    if (!Number.isFinite(a) || !Number.isFinite(b)) return false;
    return filter.operator === 'gt' ? a > b : filter.operator === 'lt' ? a < b : a >= b && a <= parse(filter.end || '');
  });
}
function IconButton({title, children, ...props}) { return <button className="icon-button" title={title} aria-label={title} {...props}>{children}</button>; }

function FilterPanel({column, rows, filters, setFilters, close}) {
  const [search, setSearch] = useState('');
  const current = filters[column] || {};
  const unique = useMemo(() => {
    const counts = new Map();
    rows.filter(row => matches(row, filters, column)).forEach(row => {const v = str(row[column]); counts.set(v, (counts.get(v) || 0) + 1);});
    return [...counts].sort((a,b) => a[0].localeCompare(b[0], undefined, {numeric: true}));
  }, [column, rows, filters]);
  const visible = unique.filter(([v]) => label(v).toLowerCase().includes(search.toLowerCase()));
  function update(patch) {setFilters({...filters, [column]: {...current, ...patch}});}
  function toggle(value) {const chosen = current.values ?? unique.map(([v]) => v); update({values: chosen.includes(value) ? chosen.filter(v => v !== value) : [...chosen, value]});}
  return <aside className="filter-panel" aria-label="Column filters">
    <div className="panel-head"><div><span className="eyebrow">COLUMN FILTER</span><h3>{column}</h3></div><IconButton title="Close filter" onClick={close}><X size={18}/></IconButton></div>
    <label>Condition<select value={current.operator || 'none'} onChange={e => update({operator: e.target.value})}>
      <option value="none">Any value</option><option value="contains">Contains</option><option value="excludes">Does not contain</option><option value="equals">Equals</option><option value="blank">Is blank</option><option value="notblank">Is not blank</option><option value="gt">Greater than / after</option><option value="lt">Less than / before</option><option value="between">Between (inclusive)</option>
    </select></label>
    {current.operator && !['none','blank','notblank'].includes(current.operator) && <input aria-label="Filter value" placeholder="Value, number or YYYY-MM-DD" value={current.query || ''} onChange={e => update({query: e.target.value})}/>}
    {current.operator === 'between' && <input aria-label="Filter end value" placeholder="End value" value={current.end || ''} onChange={e => update({end: e.target.value})}/>}
    <div className="unique-title"><h4>Unique values <span>{unique.length}</span></h4><div className="inline"><IconButton title="Download unique values" onClick={() => csvDownload(unique.map(([v,count])=>({[column]:v,Count:count})),[column,'Count'],`${column}-values.csv`)}><ArrowDownToLine size={16}/></IconButton><IconButton title="Print unique values" onClick={()=>window.print()}><Printer size={16}/></IconButton></div></div>
    <input aria-label="Search unique values" placeholder="Search values" value={search} onChange={e=>setSearch(e.target.value)}/>
    <div className="selection-actions"><button onClick={()=>update({values:undefined})}>Select all</button><button onClick={()=>update({values:[]})}>Select none</button><button onClick={()=>{const next={...filters};delete next[column];setFilters(next);}}>Reset column</button></div>
    <div className="unique-values">{visible.map(([v,count])=><label key={v} className="check-row"><input type="checkbox" checked={!current.values || current.values.includes(v)} onChange={()=>toggle(v)}/><span>{label(v)}</span><small>{count.toLocaleString()}</small></label>)}{!visible.length && <p className="muted">No matching values.</p>}</div>
    <div className="print-values"><h2>{column} — Unique values</h2>{visible.map(([v,count])=><p key={v}>{label(v)}: {count}</p>)}</div>
  </aside>;
}

function Chart({rows, columns}) {
  const [type, setType] = useState('bar'), [group, setGroup] = useState(''), [width, setWidth] = useState(56);
  const field = columns.includes(group) ? group : columns.includes('Arrival Date') ? 'Arrival Date' : columns[0];
  const data = useMemo(()=>{const counts=new Map();rows.forEach(row=>{const name=label(row[field]);counts.set(name,(counts.get(name)||0)+1);});return [...counts].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true})).map(([name,count])=>({name,count}));},[rows,field]);
  const pie = type === 'pie' || type === 'donut';
  const Component = type === 'line' ? LineChart : type === 'area' ? AreaChart : BarChart;
  return <section className="chart-section">
    <div className="section-heading"><div><span className="eyebrow">QUEUE DISTRIBUTION</span><h2>Orders by {field || 'column'}</h2></div><div className="chart-controls"><label>Group by<select value={field || ''} onChange={e=>setGroup(e.target.value)}>{columns.map(c=><option key={c}>{c}</option>)}</select></label><label>Chart<select aria-label="Chart type" value={type} onChange={e=>setType(e.target.value)}><option value="bar">Bar</option><option value="line">Line</option><option value="area">Area</option><option value="horizontal">Horizontal bar</option><option value="pie">Pie</option><option value="donut">Donut</option></select></label><label className="zoom">Spacing<input aria-label="Chart spacing" type="range" min="32" max="120" value={width} onChange={e=>setWidth(Number(e.target.value))}/></label></div></div>
    {!rows.length ? <div className="chart-empty">No rows match the current filters.</div> : <div className="chart-scroll" tabIndex={0} aria-label="Scrollable chart"><div style={{minWidth:pie ? 560 : type==='horizontal' ? 680 : Math.max(680,data.length*width),height:type==='horizontal'?Math.max(340,data.length*32):350}}>
      <ResponsiveContainer width="100%" height="100%">{pie ? <PieChart><Pie isAnimationActive={false} data={data} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={125} innerRadius={type==='donut'?78:0}>{data.map((d,i)=><Cell key={d.name} fill={colors[i%colors.length]}/>)}</Pie><Tooltip/></PieChart> : <Component data={data} layout={type==='horizontal'?'vertical':'horizontal'} margin={{top:15,right:24,left:6,bottom:12}}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edee"/><XAxis type={type==='horizontal'?'number':'category'} dataKey={type==='horizontal'?undefined:'name'} tick={{fontSize:11,fill:'#647078'}} tickMargin={10}/><YAxis type={type==='horizontal'?'category':'number'} dataKey={type==='horizontal'?'name':undefined} width={type==='horizontal'?155:42} tick={{fontSize:11}} allowDecimals={false}/><Tooltip cursor={{fill:'#f0f5f3'}}/>{type==='line'?<Line isAnimationActive={false} type="monotone" dataKey="count" stroke="#147d72" strokeWidth={2} dot={false}/>:type==='area'?<Area isAnimationActive={false} dataKey="count" stroke="#147d72" fill="#d5ece7"/>:<Bar isAnimationActive={false} dataKey="count" fill="#147d72" maxBarSize={42} radius={[3,3,0,0]}/>}{type!=='horizontal' && data.length>8 && <Brush dataKey="name" height={22} stroke="#9bbfb7" travellerWidth={8}/>}</Component>}</ResponsiveContainer>
    </div></div>}
    {pie && <div className="legend-scroll">{data.map((d,i)=><span key={d.name}><i style={{background:colors[i%colors.length]}}/>{d.name} <b>{d.count}</b></span>)}</div>}
  </section>;
}

function DataTable({rows, columns, filters, openFilter, name}) {
  const [page, setPage] = useState(0), [size, setSize] = useState(50), [sort, setSort] = useState(null);
  useEffect(()=>setPage(0),[rows,size]);
  const sorted = useMemo(()=>sort ? [...rows].sort((a,b)=>str(a[sort.column]).localeCompare(str(b[sort.column]),undefined,{numeric:true})*(sort.desc?-1:1)) : rows,[rows,sort]);
  const pages = Math.max(1,Math.ceil(rows.length/size)), safePage = Math.min(page,pages-1);
  return <section className="table-section"><div className="section-heading"><h2>{name}</h2><button className="secondary" disabled={!rows.length} onClick={()=>csvDownload(sorted,columns,`${name}-filtered.csv`)}><ArrowDownToLine size={16}/>Filtered CSV</button></div>
    <div className="table-scroll"><table><thead><tr>{columns.map(c=><th key={c}><div className="th-inner"><button className={filters[c]?'column-button active-filter':'column-button'} title={`Filter ${c} and view unique values`} onClick={()=>openFilter(c)}>{c}<Filter size={13}/></button><IconButton title={`Sort ${c}`} onClick={()=>setSort({column:c,desc:sort?.column===c?!sort.desc:false})}>{sort?.column===c&&sort.desc?<ArrowDown size={13}/>:<ArrowUp size={13}/>}</IconButton></div></th>)}</tr></thead><tbody>{sorted.slice(safePage*size,(safePage+1)*size).map((row,i)=><tr key={i}>{columns.map(c=><td key={c} title={str(row[c])}>{c==='Change'?<span className={`badge ${str(row[c]).toLowerCase()}`}>{str(row[c])}</span>:label(row[c])}</td>)}</tr>)}</tbody></table>{!rows.length&&<div className="table-empty">No matching rows</div>}</div>
    <footer className="table-footer"><span>{rows.length.toLocaleString()} rows</span><div className="inline"><label>Rows <select aria-label="Rows per page" value={size} onChange={e=>setSize(Number(e.target.value))}>{[25,50,100,250].map(n=><option key={n}>{n}</option>)}</select></label><IconButton title="Previous page" disabled={safePage===0} onClick={()=>setPage(safePage-1)}><ChevronLeft size={16}/></IconButton><span>{safePage+1} / {pages}</span><IconButton title="Next page" disabled={safePage+1===pages} onClick={()=>setPage(safePage+1)}><ChevronRight size={16}/></IconButton></div></footer>
  </section>;
}

function App() {
  const [state,setState]=useState({previews:[],job:{running:false,stage:'Ready'}}), [selected,setSelected]=useState(null), [preview,setPreview]=useState(EMPTY), [view,setView]=useState('overview');
  const [previous,setPrevious]=useState(''), [diff,setDiff]=useState(null), [keys,setKeys]=useState([]), [ignore,setIgnore]=useState(DEFAULT_IGNORE), [compareBusy,setCompareBusy]=useState(false), [compareError,setCompareError]=useState('');
  const [filters,setFilters]=useState({}), [filterColumn,setFilterColumn]=useState(null), [search,setSearch]=useState(''), [error,setError]=useState(''), [pending,setPending]=useState(false), [loading,setLoading]=useState(false), [uploading,setUploading]=useState(false);
  const upload=useRef(), seen=useRef(null);
  async function refresh() {const next=await api('/api/state');setState(next);if(next.previews.length && next.previews[0].id!==seen.current){seen.current=next.previews[0].id;setSelected(next.previews[0].id);setPrevious(String(next.previews[1]?.id || ''));}}
  useEffect(()=>{let active=true;const poll=async()=>{try{if(active)await refresh();}catch(e){if(active)setError(e.message);}};poll();const timer=setInterval(poll,1800);return()=>{active=false;clearInterval(timer);};},[]);
  useEffect(()=>{if(!selected)return;let cancelled=false;setLoading(true);setPreview(EMPTY);setFilters({});setFilterColumn(null);setSearch('');setKeys([]);api(`/api/previews/${selected}`).then(data=>{if(!cancelled)setPreview(data);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[selected]);
  useEffect(()=>{setFilters({});setFilterColumn(null);setSearch('');},[view,previous]);
  useEffect(()=>{setDiff(null);setCompareBusy(false);setCompareError('');if(!previous||!selected||Number(previous)===selected)return;let cancelled=false;setCompareBusy(true);api('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore})}).then(data=>{if(!cancelled)setDiff(data);}).catch(e=>{if(!cancelled)setCompareError(e.message);}).finally(()=>{if(!cancelled)setCompareBusy(false);});return()=>{cancelled=true;};},[previous,selected,keys,ignore]);
  const table = view==='changes' ? diff || EMPTY : preview;
  const filtered = useMemo(()=>table.rows.filter(row=>matches(row,filters)&&(!search||table.columns.some(c=>str(row[c]).toLowerCase().includes(search.toLowerCase())))),[table,filters,search]);
  async function extract(){setPending(true);setError('');try{await api('/api/extract',{method:'POST'});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function importFile(e){const file=e.target.files[0];if(!file)return;setUploading(true);setError('');try{const body=new FormData();body.append('file',file);await api('/api/import',{method:'POST',body});await refresh();}catch(e){setError(e.message);}finally{setUploading(false);e.target.value='';}}
  async function downloadChanges(){try{const response=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore,download:true})});if(!response.ok)throw Error((await response.json()).error);saveBlob(await response.blob(),`${diff.previous}-to-${diff.latest}-changes.xlsx`);}catch(e){setError(e.message);}}
  const running=state.job.running||pending, result=state.job.result;
  return <div className="workspace">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Activity size={23}/></div><div>DataTrace<span>WORKSPACE</span></div></div><div className="nav-label">WORKSPACE</div><nav>{[['overview','Overview',BarChart3],['sheets','Data sheets',Table2],['changes','Changes',ArrowLeftRight]].map(([id,title,Icon])=><button className={view===id?'nav-item selected':'nav-item'} key={id} onClick={()=>setView(id)}><Icon size={18}/>{title}{id==='changes'&&diff&&<small>{diff.counts.added+diff.counts.removed+diff.counts.modified}</small>}</button>)}</nav><div className="preview-heading"><span className="nav-label">SAVED PREVIEWS</span><span>{state.previews.length}</span></div><div className="preview-list">{state.previews.map(p=><button key={p.id} className={`preview-item ${selected===p.id?'selected':''}`} onClick={()=>{setSelected(p.id);const index=state.previews.findIndex(x=>x.id===p.id);setPrevious(String(state.previews[index+1]?.id||''));}}><FileSpreadsheet size={17}/><div><strong>{p.name}</strong><small>{p.row_count.toLocaleString()} rows · {new Date(p.created).toLocaleDateString()}</small></div>{p.id===state.previews[0].id&&<i>Latest</i>}</button>)}{!state.previews.length&&<p className="no-previews">No saved previews</p>}</div><div className="sidebar-footer"><span className="status-dot"/>Local workspace<a href={state.sheet_url} target="_blank" rel="noreferrer">Google Sheet ↗</a></div></aside>
    <main><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {view==='overview'?'Overview':view==='sheets'?'Data sheets':'Changes'}</div><div className="inline"><span className={`run-state ${running?'running':''}`}>{running&&<LoaderCircle size={14} className="spin"/>}{state.job.stage}</span><button className="secondary" onClick={()=>upload.current.click()} disabled={uploading}><Upload size={16}/>{uploading?'Importing…':'Import file'}</button><input ref={upload} type="file" hidden accept=".csv,.xlsx" onChange={importFile}/></div></header>
      <div className="content"><div className="page-heading"><div><span className="eyebrow">DATATRACE QUEUE</span><h1>{view==='changes'?'Preview comparison':view==='sheets'?'Data sheets':'Queue overview'}</h1><p className="muted">{preview.name?`${preview.name} · ${new Date(preview.created).toLocaleString()} · ${preview.source}`:'No data captured yet'}</p></div><button className="primary" onClick={extract} disabled={running}>{running?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}<span>{running?'Extracting queue…':'Run AutoLogin & Extract Queue'}</span></button></div>
      {error&&<div className="notice error" role="alert">{error}<IconButton title="Dismiss error" onClick={()=>setError('')}><X size={16}/></IconButton></div>}
      {result?.error&&<div className="notice warning" role="status">{result.preview_name&&<strong>{result.preview_name} saved. </strong>}{result.error}</div>}
      {result&&!result.error&&!running&&<div className="notice success"><Check size={16}/>{result.preview_name} saved · {result.rows} rows · Google Sheets synced</div>}
      {!state.previews.length ? <div className="empty-state"><div className="empty-icon"><Database size={40} strokeWidth={1.3}/></div><h2>No queue data yet</h2><p>Your saved previews will appear here.</p><button className="secondary" onClick={()=>upload.current.click()}><Plus size={17}/>Import Excel or CSV</button></div> : <>
      {view==='changes'&&<section className="compare-controls"><label>Previous preview<select aria-label="Previous preview" value={previous} onChange={e=>setPrevious(e.target.value)}><option value="">Select a preview</option>{state.previews.filter(p=>p.id!==selected).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><ArrowLeftRight size={18}/><label>Latest preview<select aria-label="Latest preview" value={selected||''} onChange={e=>setSelected(Number(e.target.value))}>{state.previews.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><details className="match-options"><summary><SlidersHorizontal size={16}/>Matching columns {keys.length?`(${keys.length})`:'(Auto)'}</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={keys.includes(c)} onChange={()=>setKeys(keys.includes(c)?keys.filter(k=>k!==c):[...keys,c])}/>{c}</label>)}</div></details><details className="match-options"><summary>Ignored columns ({ignore.length})</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={ignore.includes(c)} onChange={()=>setIgnore(ignore.includes(c)?ignore.filter(k=>k!==c):[...ignore,c])}/>{c}</label>)}</div></details><button className="secondary" disabled={!diff||compareBusy} onClick={downloadChanges}><ArrowDownToLine size={16}/>Power BI changes.xlsx</button></section>}
      {view==='changes'&&compareError&&<div className="notice warning">{compareError}</div>}
      {view==='changes'&&!previous&&<div className="notice">Capture or import a second preview to compare changes.</div>}
      {view==='changes'&&diff&&<><p className="comparison-method">{diff.method}</p>{(diff.added_columns.length>0||diff.removed_columns.length>0)&&<div className="notice">Columns added: {diff.added_columns.join(', ')||'None'} · Columns removed: {diff.removed_columns.join(', ')||'None'}</div>}</>}
      <div className="metrics">{(view==='changes'?[['Added',diff?.counts.added??'—','green'],['Removed',diff?.counts.removed??'—','red'],['Modified',diff?.counts.modified??'—','amber'],['Unchanged',diff?.counts.unchanged??'—','gray']]:[['Visible orders',filtered.length.toLocaleString(),'green'],['Available',filtered.filter(r=>str(r['Task Status']).toLowerCase()==='available').length,'gray'],['Suspended',filtered.filter(r=>str(r['Task Status']).toLowerCase().includes('suspended')).length,'amber'],['Saved previews',state.previews.length,'gray']]).map(([title,value,color])=><div className={`metric ${color}`} key={title}><span>{title}</span><strong>{value}</strong></div>)}</div>
      <div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search rows" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="Choose column filter" value={filterColumn||''} onChange={e=>setFilterColumn(e.target.value||null)}><option value="">Filter a column…</option>{table.columns.map(c=><option key={c}>{c}</option>)}</select>{Object.keys(filters).map(c=><button className="filter-chip" key={c} onClick={()=>setFilterColumn(c)}><Filter size={12}/>{c}</button>)}{Object.keys(filters).length>0&&<button className="text-button" onClick={()=>setFilters({})}>Clear filters</button>}<span className="row-tally">{filtered.length.toLocaleString()} / {table.rows.length.toLocaleString()} rows</span>{view!=='changes'&&preview.id&&<><a className="secondary" href={`/api/previews/${preview.id}/download/xlsx`}><ArrowDownToLine size={16}/>Excel</a><a className="secondary" href={`/api/previews/${preview.id}/download/csv`}>CSV</a></>}</div>
      {(loading||(view==='changes'&&compareBusy))?<div className="loading"><LoaderCircle className="spin"/>Loading preview…</div>:<><div className={filterColumn?'data-layout with-filter':'data-layout'}><div className="data-main">{view==='overview'&&<Chart rows={filtered} columns={table.columns}/>}<DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={view==='changes'?'DataTraceChanges':preview.name||'Queue'}/></div>{filterColumn&&<FilterPanel key={filterColumn} column={filterColumn} rows={table.rows} filters={filters} setFilters={setFilters} close={()=>setFilterColumn(null)}/>}</div></>}
      </>}
      <footer className="page-footer"><span>DataTrace Workspace</span><span>{state.previews.length} saved previews · Local storage</span></footer></div>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
