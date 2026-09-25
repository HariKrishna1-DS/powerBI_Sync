import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDown, ArrowUp, ArrowDownToLine, ArrowLeftRight, BarChart3, Check, ChevronLeft, ChevronRight, Clock3, CloudUpload, Database, FileSpreadsheet, Filter, LoaderCircle, Maximize2, Minimize2, Play, Plus, Printer, Search, SlidersHorizontal, Table2, Trash2, Upload, X } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Brush } from 'recharts';
import './style.css';

const EMPTY = {columns: [], rows: []};
const DEFAULT_IGNORE = ['Sync Timestamp', 'Queue Age Hours', 'Time Since Arrival', 'Task Time in Queue'];
const colors = ['#147d72', '#d79a32', '#596cc0', '#bb6179', '#4b9db4', '#849157'];
const str = value => value == null ? '' : String(value);
const label = value => str(value) || '(Blank)';
const normalized = value => str(value).trim().toLowerCase();
const badgeClass = value => normalized(value).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const STATUS_COLORS = {
  'available': '#d9ead3',
  'in progress': '#00b050',
  'qc in progress': '#f4b183',
  'ready to send': '#ffff00',
  'search in progress': '#ffffff',
  'typing in progress': '#00b050',
  'waiting for effective date': '#ffffff',
  'assign to abs': '#a6a6a6',
  'need to assign abs': '#a6a6a6',
  'awaiting for clarification': '#a66ad3',
  'cancelled': '#f4cccc',
  'completed and delivered': '#fff2cc',
  'task suspended': '#c9daf8',
  'workflow suspended': '#c9daf8'
};
function statusColor(value) {
  const key = normalized(value);
  if (STATUS_COLORS[key]) return STATUS_COLORS[key];
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) hash = (hash * 31 + key.charCodeAt(i)) % 360;
  return `hsl(${hash}, 58%, 78%)`;
}
function textColorForBg(color) {
  if (!color.startsWith('#')) return '#1f2937';
  const r = parseInt(color.slice(1, 3), 16), g = parseInt(color.slice(3, 5), 16), b = parseInt(color.slice(5, 7), 16);
  return (r * 299 + g * 587 + b * 114) / 1000 > 155 ? '#111827' : '#ffffff';
}
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

function SideDrawer({ title, rows, columns, onClose }) {
  if (!title) return null;
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="side-drawer" onClick={e => e.stopPropagation()}>
        <div className="drawer-header">
          <div>
            <h3>{title}</h3>
            <p>{rows.length.toLocaleString()} matching records</p>
          </div>
          <IconButton title="Close drawer" onClick={onClose}><X size={19}/></IconButton>
        </div>
        <div className="drawer-body">
          <DataTable rows={rows} columns={columns} filters={{}} openFilter={() => {}} filterable={false} name={title} onClose={onClose} />
        </div>
      </div>
    </div>
  );
}

function MaximizedModal({ title, subtitle, children, onClose }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="maximized-modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>{title}</h3>
            {subtitle && <p style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{subtitle}</p>}
          </div>
          <IconButton title="Close modal" onClick={onClose}><X size={20}/></IconButton>
        </div>
        <div className="modal-body">
          {children}
        </div>
      </div>
    </div>
  );
}


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
}function OverviewDashboard({rows, columns, onSelect}) {
  const ogCol = columns.includes('Online/ Ground') ? 'Online/ Ground' : columns.includes('Online/Ground') ? 'Online/Ground' : null;
  const clientCol = columns.includes('Client') ? 'Client' : null;
  const prodCol = columns.includes('Product') ? 'Product' : null;
  const statusCol = columns.includes('Task Status') ? 'Task Status' : columns.includes('Status') ? 'Status' : null;

  // Slicer State
  const [selectedClients, setSelectedClients] = useState([]);
  const [selectedOg, setSelectedOg] = useState([]);
  const [selectedProducts, setSelectedProducts] = useState([]);
  const [showSlicers, setShowSlicers] = useState(true);

  // Maximize Modal State
  const [maximized, setMaximized] = useState(null);

  // Extract Slicer Options from base rows
  const allClients = useMemo(() => {
    if (!clientCol) return [];
    const map = new Map();
    rows.forEach(r => { const c = label(r[clientCol]); map.set(c, (map.get(c) || 0) + 1); });
    return [...map].sort((a,b) => b[1] - a[1]);
  }, [rows, clientCol]);

  const allOg = useMemo(() => {
    if (!ogCol) return [];
    const on = rows.filter(r => str(r[ogCol]).toLowerCase().includes('online')).length;
    const gr = rows.filter(r => str(r[ogCol]).toLowerCase().includes('ground')).length;
    return [['Online', on], ['Ground', gr]].filter(x => x[1] > 0);
  }, [rows, ogCol]);

  const allProducts = useMemo(() => {
    if (!prodCol) return [];
    const map = new Map();
    rows.forEach(r => { const p = label(r[prodCol]); map.set(p, (map.get(p) || 0) + 1); });
    return [...map].sort((a,b) => b[1] - a[1]);
  }, [rows, prodCol]);

  // Apply Slicers to filter rows
  const filteredRows = useMemo(() => {
    return rows.filter(r => {
      if (selectedClients.length > 0 && clientCol) {
        if (!selectedClients.includes(label(r[clientCol]))) return false;
      }
      if (selectedOg.length > 0 && ogCol) {
        const val = str(r[ogCol]).toLowerCase().includes('online') ? 'Online' : str(r[ogCol]).toLowerCase().includes('ground') ? 'Ground' : 'Other';
        if (!selectedOg.includes(val)) return false;
      }
      if (selectedProducts.length > 0 && prodCol) {
        if (!selectedProducts.includes(label(r[prodCol]))) return false;
      }
      return true;
    });
  }, [rows, selectedClients, selectedOg, selectedProducts, clientCol, ogCol, prodCol]);

  // Metrics calculation
  const onlineCount = useMemo(() => ogCol ? filteredRows.filter(r => str(r[ogCol]).toLowerCase().includes('online')).length : 0, [filteredRows, ogCol]);
  const groundCount = useMemo(() => ogCol ? filteredRows.filter(r => str(r[ogCol]).toLowerCase().includes('ground')).length : 0, [filteredRows, ogCol]);
  const onlinePct = filteredRows.length ? ((onlineCount / filteredRows.length) * 100).toFixed(1) : 0;
  const groundPct = filteredRows.length ? ((groundCount / filteredRows.length) * 100).toFixed(1) : 0;

  const clientCounts = useMemo(() => {
    if (!clientCol) return [];
    const map = new Map();
    filteredRows.forEach(r => { const c = label(r[clientCol]); map.set(c, (map.get(c) || 0) + 1); });
    return [...map].sort((a,b) => b[1] - a[1]);
  }, [filteredRows, clientCol]);

  const productCounts = useMemo(() => {
    if (!prodCol) return [];
    const map = new Map();
    filteredRows.forEach(r => { const p = label(r[prodCol]); map.set(p, (map.get(p) || 0) + 1); });
    return [...map].sort((a,b) => b[1] - a[1]);
  }, [filteredRows, prodCol]);

  const statusCounts = useMemo(() => {
    if (!statusCol) return [];
    const map = new Map();
    filteredRows.forEach(r => {
      const status = label(r[statusCol]);
      map.set(status, (map.get(status) || 0) + 1);
    });
    return [...map]
      .sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0], undefined, {numeric: true}))
      .map(([name, count]) => ({name, count, percent: filteredRows.length ? ((count / filteredRows.length) * 100).toFixed(1) : '0.0'}));
  }, [filteredRows, statusCol]);

  const fullTitleCount = useMemo(() => prodCol ? filteredRows.filter(r => normalized(r[prodCol]) === 'full title').length : 0, [filteredRows, prodCol]);
  const fullTitlePct = filteredRows.length ? ((fullTitleCount / filteredRows.length) * 100).toFixed(1) : 0;

  const ogPieData = [
    { name: 'Online', count: onlineCount, color: '#147d72' },
    { name: 'Ground', count: groundCount, color: '#d79a32' }
  ].filter(d => d.count > 0);

  const topClientsData = useMemo(() => clientCounts.slice(0, 10).map(([name, count]) => ({ name, count })), [clientCounts]);
  const topProductsData = useMemo(() => productCounts.slice(0, 10).map(([name, count]) => ({ name, count })), [productCounts]);

  const clientOgData = useMemo(() => {
    if (!clientCol || !ogCol) return [];
    const top6 = clientCounts.slice(0, 6).map(x => x[0]);
    return top6.map(cName => {
      const cRows = filteredRows.filter(r => label(r[clientCol]) === cName);
      const on = cRows.filter(r => str(r[ogCol]).toLowerCase().includes('online')).length;
      const gr = cRows.filter(r => str(r[ogCol]).toLowerCase().includes('ground')).length;
      return { name: cName, Online: on, Ground: gr };
    });
  }, [filteredRows, clientCol, ogCol, clientCounts]);

  const toggleSlicerItem = (list, setList, val) => {
    if (list.includes(val)) setList(list.filter(x => x !== val));
    else setList([...list, val]);
  };

  const clearAllSlicers = () => {
    setSelectedClients([]);
    setSelectedOg([]);
    setSelectedProducts([]);
  };

  const activeSlicerCount = selectedClients.length + selectedOg.length + selectedProducts.length;

  const renderChartContent = (chartId, isModal = false) => {
    const height = isModal ? 460 : chartId === 'pie' ? 250 : 280;
    switch (chartId) {
      case 'pie':
        return (
          <>
            <div style={{ height }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie className="clickable-series" isAnimationActive={false} data={ogPieData} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={isModal ? 140 : 85} innerRadius={isModal ? 80 : 50} onClick={entry => ogCol && onSelect({ column: ogCol, value: entry.name })}>
                    {ogPieData.map(d => <Cell key={d.name} fill={d.color} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="legend-pills">
              {ogPieData.map(d => (
                <span key={d.name} className="pill" onClick={() => ogCol && onSelect({ column: ogCol, value: d.name })}>
                  <i style={{ background: d.color }} /> {d.name}: <b>{d.count.toLocaleString()}</b> ({filteredRows.length ? ((d.count/filteredRows.length)*100).toFixed(1) : 0}%)
                </span>
              ))}
            </div>
          </>
        );
      case 'clients':
        return (
          <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topClientsData} layout="vertical" margin={{ top: 10, right: 25, left: 5, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e9edee" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" width={isModal ? 150 : 110} tick={{ fontSize: 11 }} />
                <Tooltip cursor={{ fill: '#f0f5f3' }} />
                <Bar className="clickable-series" isAnimationActive={false} dataKey="count" fill="#2563eb" radius={[0, 4, 4, 0]} onClick={entry => clientCol && onSelect({ column: clientCol, value: entry.name || entry.payload?.name })} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      case 'products':
        return (
          <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={topProductsData} margin={{ top: 10, right: 15, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edee" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip cursor={{ fill: '#f0f5f3' }} />
                <Bar className="clickable-series" isAnimationActive={false} dataKey="count" fill="#7c3aed" radius={[4, 4, 0, 0]} onClick={entry => prodCol && onSelect({ column: prodCol, value: entry.name || entry.payload?.name })} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      case 'clientOg':
        return (
          <div style={{ height }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={clientOgData} margin={{ top: 10, right: 15, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edee" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                <Tooltip cursor={{ fill: '#f0f5f3' }} />
                <Bar className="clickable-series" isAnimationActive={false} dataKey="Online" fill="#147d72" radius={[3, 3, 0, 0]} onClick={entry => clientCol && onSelect({ column: clientCol, value: entry.name || entry.payload?.name })} />
                <Bar className="clickable-series" isAnimationActive={false} dataKey="Ground" fill="#d79a32" radius={[3, 3, 0, 0]} onClick={entry => clientCol && onSelect({ column: clientCol, value: entry.name || entry.payload?.name })} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <section className="overview-dashboard">
      <div className="section-heading">
        <div>
          <span className="eyebrow">COLUMN ANALYTICS DASHBOARD</span>
          <h2>Online/Ground, Client & Product Breakdown</h2>
        </div>
        <div className="inline">
          <button className="secondary" onClick={() => setShowSlicers(!showSlicers)}>
            <SlidersHorizontal size={15} /> Filter Slicers {activeSlicerCount > 0 ? `(${activeSlicerCount})` : ''}
          </button>
          {activeSlicerCount > 0 && (
            <button className="text-button" onClick={clearAllSlicers}>
              Clear Slicers
            </button>
          )}
        </div>
      </div>

      {showSlicers && (
        <div className="slicer-panel">
          <div className="slicer-panel-head">
            <h4><Filter size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} /> Power BI Slicers</h4>
            {activeSlicerCount > 0 && <small style={{ color: '#147d72', fontWeight: 600 }}>{filteredRows.length.toLocaleString()} matching rows</small>}
          </div>
          <div className="slicer-grid">
            <details className="dropdown-slicer">
              <summary>Client <span>{selectedClients.length ? `${selectedClients.length} selected` : 'All'}</span></summary>
              <div className="dropdown-slicer-options"><button className="text-button" onClick={()=>setSelectedClients([])}>All clients</button>
              {allClients.map(([name, count]) => (
                <label key={name} className="slicer-item">
                  <input type="checkbox" checked={selectedClients.includes(name)} onChange={() => toggleSlicerItem(selectedClients, setSelectedClients, name)} />
                  <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
                  <small style={{ color: '#94a3b8' }}>{count}</small>
                </label>
              ))}
              </div>
            </details>

            <details className="dropdown-slicer">
              <summary>Online / Ground <span>{selectedOg.length ? selectedOg.join(', ') : 'All'}</span></summary>
              <div className="dropdown-slicer-options"><button className="text-button" onClick={()=>setSelectedOg([])}>All queues</button>
              {allOg.map(([name, count]) => (
                <label key={name} className="slicer-item">
                  <input type="checkbox" checked={selectedOg.includes(name)} onChange={() => toggleSlicerItem(selectedOg, setSelectedOg, name)} />
                  <span style={{ flex: 1 }}>{name}</span>
                  <small style={{ color: '#94a3b8' }}>{count}</small>
                </label>
              ))}
              </div>
            </details>

            <details className="dropdown-slicer">
              <summary>Product Category <span>{selectedProducts.length ? `${selectedProducts.length} selected` : 'All'}</span></summary>
              <div className="dropdown-slicer-options"><button className="text-button" onClick={()=>setSelectedProducts([])}>All products</button>
              {allProducts.map(([name, count]) => (
                <label key={name} className="slicer-item">
                  <input type="checkbox" checked={selectedProducts.includes(name)} onChange={() => toggleSlicerItem(selectedProducts, setSelectedProducts, name)} />
                  <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{name}</span>
                  <small style={{ color: '#94a3b8' }}>{count}</small>
                </label>
              ))}
              </div>
            </details>
          </div>
        </div>
      )}

      {statusCol && (
        <section className="status-report">
          <div className="section-heading">
            <div>
              <span className="eyebrow">AI - STATUS REPORT</span>
              <h2>Status Report</h2>
            </div>
            <span className="row-tally">{statusCounts.length.toLocaleString()} statuses</span>
          </div>
          <div className="status-report-scroll">
            <table className="status-report-table">
              <thead><tr><th>Status</th><th>Orders</th><th>Share</th></tr></thead>
              <tbody>{statusCounts.map(item => {
                const bg = statusColor(item.name);
                return <tr key={item.name} style={{backgroundColor:bg,color:textColorForBg(bg)}}><td>{item.name}</td><td>{item.count.toLocaleString()}</td><td>{item.percent}%</td></tr>;
              })}</tbody>
            </table>
            {!statusCounts.length && <div className="table-empty">No status values match the current filters.</div>}
          </div>
        </section>
      )}

      <div className="dashboard-grid">
        <div className="dashboard-card">
          <div className="card-head">
            <div>
              <h3>Online vs Ground Share</h3>
              <small>{onlinePct}% Online · {groundPct}% Ground</small>
            </div>
            <div className="card-actions">
              <button className="card-icon-btn" title="Maximize chart" onClick={() => setMaximized({ id: 'pie', title: 'Online vs Ground Share', subtitle: `${onlinePct}% Online · ${groundPct}% Ground` })}>
                <Maximize2 size={15} />
              </button>
            </div>
          </div>
          {renderChartContent('pie')}
        </div>

        <div className="dashboard-card">
          <div className="card-head">
            <div>
              <h3>Top Clients by Queue Volume</h3>
              <small>{clientCounts.length} active clients</small>
            </div>
            <div className="card-actions">
              <button className="card-icon-btn" title="Maximize chart" onClick={() => setMaximized({ id: 'clients', title: 'Top Clients by Queue Volume', subtitle: `${clientCounts.length} active clients` })}>
                <Maximize2 size={15} />
              </button>
            </div>
          </div>
          {renderChartContent('clients')}
        </div>

        <div className="dashboard-card">
          <div className="card-head">
            <div>
              <h3>Product Category Breakdown</h3>
              <small>{fullTitlePct}% Full Title share</small>
            </div>
            <div className="card-actions">
              <button className="card-icon-btn" title="Maximize chart" onClick={() => setMaximized({ id: 'products', title: 'Product Category Breakdown', subtitle: `${fullTitlePct}% Full Title share` })}>
                <Maximize2 size={15} />
              </button>
            </div>
          </div>
          {renderChartContent('products')}
        </div>

        <div className="dashboard-card">
          <div className="card-head">
            <div>
              <h3>Online vs Ground per Client</h3>
              <small>Delivery breakdown for top clients</small>
            </div>
            <div className="card-actions">
              <button className="card-icon-btn" title="Maximize chart" onClick={() => setMaximized({ id: 'clientOg', title: 'Online vs Ground per Client', subtitle: 'Delivery breakdown for top clients' })}>
                <Maximize2 size={15} />
              </button>
            </div>
          </div>
          {renderChartContent('clientOg')}
        </div>
      </div>

      {maximized && (
        <MaximizedModal title={maximized.title} subtitle={maximized.subtitle} onClose={() => setMaximized(null)}>
          {renderChartContent(maximized.id, true)}
        </MaximizedModal>
      )}
    </section>
  );
}


function Chart({rows, columns, onSelect}) {
  const [type, setType] = useState('bar'), [group, setGroup] = useState(''), [width, setWidth] = useState(56);
  const field = columns.includes(group) ? group : columns.includes('Arrival Date') ? 'Arrival Date' : columns[0];
  const data = useMemo(()=>{const counts=new Map();rows.forEach(row=>{const name=label(row[field]);counts.set(name,(counts.get(name)||0)+1);});return [...counts].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true})).map(([name,count])=>({name,count}));},[rows,field]);
  const pie = type === 'pie' || type === 'donut';
  const Component = type === 'line' ? LineChart : type === 'area' ? AreaChart : BarChart;
  return <section className="chart-section">
    <div className="section-heading"><div><span className="eyebrow">QUEUE DISTRIBUTION</span><h2>Orders by {field || 'column'}</h2></div><div className="chart-controls"><label>Group by<select value={field || ''} onChange={e=>{setGroup(e.target.value);onSelect(null);}}>{columns.map(c=><option key={c}>{c}</option>)}</select></label><label>Chart<select aria-label="Chart type" value={type} onChange={e=>setType(e.target.value)}><option value="bar">Bar</option><option value="line">Line</option><option value="area">Area</option><option value="horizontal">Horizontal bar</option><option value="pie">Pie</option><option value="donut">Donut</option></select></label><label className="zoom">Spacing<input aria-label="Chart spacing" type="range" min="32" max="120" value={width} onChange={e=>setWidth(Number(e.target.value))}/></label></div></div>
    {!rows.length ? <div className="chart-empty">No rows match the current filters.</div> : <div className="chart-scroll" tabIndex={0} aria-label="Scrollable chart"><div style={{minWidth:pie ? 560 : type==='horizontal' ? 680 : Math.max(680,data.length*width),height:type==='horizontal'?Math.max(340,data.length*32):350}}>
      <ResponsiveContainer width="100%" height="100%">{pie ? <PieChart><Pie className="clickable-series" isAnimationActive={false} data={data} dataKey="count" nameKey="name" cx="50%" cy="50%" outerRadius={125} innerRadius={type==='donut'?78:0} onClick={entry=>onSelect({column:field,value:entry.name})}>{data.map((d,i)=><Cell key={d.name} fill={colors[i%colors.length]}/>)}</Pie><Tooltip/></PieChart> : <Component data={data} layout={type==='horizontal'?'vertical':'horizontal'} margin={{top:15,right:24,left:6,bottom:12}}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edee"/><XAxis type={type==='horizontal'?'number':'category'} dataKey={type==='horizontal'?undefined:'name'} tick={{fontSize:11,fill:'#647078'}} tickMargin={10}/><YAxis type={type==='horizontal'?'category':'number'} dataKey={type==='horizontal'?'name':undefined} width={type==='horizontal'?155:42} tick={{fontSize:11}} allowDecimals={false}/><Tooltip cursor={{fill:'#f0f5f3'}}/>{type==='line'?<Line isAnimationActive={false} type="monotone" dataKey="count" stroke="#147d72" strokeWidth={2} dot={false}/>:type==='area'?<Area isAnimationActive={false} dataKey="count" stroke="#147d72" fill="#d5ece7"/>:<Bar className="clickable-series" isAnimationActive={false} dataKey="count" fill="#147d72" maxBarSize={42} radius={[3,3,0,0]} onClick={entry=>onSelect({column:field,value:entry.name||entry.payload?.name})}/>}{type!=='horizontal' && data.length>8 && <Brush dataKey="name" height={22} stroke="#9bbfb7" travellerWidth={8}/>}</Component>}</ResponsiveContainer>
    </div></div>}
    {pie && <div className="legend-scroll">{data.map((d,i)=><span key={d.name}><i style={{background:colors[i%colors.length]}}/>{d.name} <b>{d.count}</b></span>)}</div>}
  </section>;
}

function DataTable({rows, columns, filters, openFilter, name, filterable=true, onClose}) {
  const [page, setPage] = useState(0), [size, setSize] = useState(50), [sort, setSort] = useState(null);
  useEffect(()=>setPage(0),[rows,size]);
  const sorted = useMemo(()=>sort ? [...rows].sort((a,b)=>str(a[sort.column]).localeCompare(str(b[sort.column]),undefined,{numeric:true})*(sort.desc?-1:1)) : rows,[rows,sort]);
  const pages = Math.max(1,Math.ceil(rows.length/size)), safePage = Math.min(page,pages-1);
  return <section className="table-section"><div className="section-heading"><h2>{name}</h2><div className="inline"><button className="secondary" disabled={!rows.length} onClick={()=>csvDownload(sorted,columns,`${name}-filtered.csv`)}><ArrowDownToLine size={16}/>Filtered CSV</button>{onClose&&<IconButton title="Close chart details" onClick={onClose}><X size={17}/></IconButton>}</div></div>
    <div className="table-scroll"><table><thead><tr>{columns.map(c=><th key={c}><div className="th-inner">{filterable?<button className={filters[c]?'column-button active-filter':'column-button'} title={`Filter ${c} and view unique values`} onClick={()=>openFilter(c)}>{c}<Filter size={13}/></button>:<span className="column-label">{c}</span>}<IconButton title={`Sort ${c}`} onClick={()=>setSort({column:c,desc:sort?.column===c?!sort.desc:false})}>{sort?.column===c&&sort.desc?<ArrowDown size={13}/>:<ArrowUp size={13}/>}</IconButton></div></th>)}</tr></thead><tbody>{sorted.slice(safePage*size,(safePage+1)*size).map((row,i)=><tr key={i}>{columns.map(c=><td key={c} title={str(row[c])}>{c==='Change'||c==='Comparison Status'?<span className={`badge ${badgeClass(row[c])}`}>{c==='Comparison Status'&&row[c]==='Missing'?'Missing (Completed Orders)':str(row[c])}</span>:label(row[c])}</td>)}</tr>)}</tbody></table>{!rows.length&&<div className="table-empty">No matching rows</div>}</div>
    <footer className="table-footer"><span>{rows.length.toLocaleString()} rows</span><div className="inline"><label>Rows <select aria-label="Rows per page" value={size} onChange={e=>setSize(Number(e.target.value))}>{[25,50,100,250].map(n=><option key={n}>{n}</option>)}</select></label><IconButton title="Previous page" disabled={safePage===0} onClick={()=>setPage(safePage-1)}><ChevronLeft size={16}/></IconButton><span>{safePage+1} / {pages}</span><IconButton title="Next page" disabled={safePage+1===pages} onClick={()=>setPage(safePage+1)}><ChevronRight size={16}/></IconButton></div></footer>
  </section>;
}

function DailyOrders({preview, diff, onChoose}) {
  const [history,setHistory]=useState([]);
  const [error,setError]=useState('');
  const [date,setDate]=useState('');
  useEffect(()=>{let active=true;api('/api/daily-orders').then(data=>{if(active){setHistory(data.rows);setError('');}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[preview.id]);
  const dates=[...new Set(history.map(row=>row.Date))];
  const missing=(diff?.unmatched_rows||[]).filter(row=>row['Comparison Status']==='Missing');
  const unchanged=(diff?.matched_rows||[]).filter(row=>row['Comparison Status']==='Unchanged');
  const columns=diff?.record_columns||preview.columns;
  return <section className="daily-orders">
    <div className="section-heading"><h2>Daily capture history</h2><label>Date<select aria-label="Daily orders date" value={date} onChange={e=>setDate(e.target.value)}><option value="">All dates</option>{dates.map(day=><option key={day}>{day}</option>)}</select></label></div>
    {error&&<div className="notice error">{error}</div>}
    <div className="table-scroll"><table><thead><tr>{['Date','Capture','Previous','Total orders','Missing (Completed Orders)','Newly added','Unchanged'].map(name=><th key={name}>{name}</th>)}</tr></thead><tbody>{history.filter(row=>!date||row.Date===date).map(row=><tr key={row.preview_id}><td>{row.Date}</td><td><button className="text-button" onClick={()=>onChoose(row.preview_id,row.previous_id)}>{row.Preview}</button><small> {new Date(row.Captured).toLocaleTimeString()}</small></td><td>{row['Previous Preview']||'—'}</td><td>{row['Total Orders']}</td><td>{row['Missing (Completed Orders)']??'—'}</td><td>{row['Newly Added']??'—'}</td><td>{row.Unchanged??'—'}</td></tr>)}</tbody></table></div>
    {diff&&<><DataTable rows={missing} columns={columns} filters={{}} openFilter={()=>{}} filterable={false} name={`Missing (Completed Orders) · ${missing.length}`}/><DataTable rows={unchanged} columns={columns} filters={{}} openFilter={()=>{}} filterable={false} name={`Unchanged orders · ${unchanged.length}`}/></>}
  </section>;
}

function App() {
  const [state,setState]=useState({previews:[],job:{running:false,stage:'Ready'}}), [selected,setSelected]=useState(null), [preview,setPreview]=useState(EMPTY), [view,setView]=useState('overview');
  const [previous,setPrevious]=useState(''), [diff,setDiff]=useState(null), [keys,setKeys]=useState([]), [ignore,setIgnore]=useState(DEFAULT_IGNORE), [compareBusy,setCompareBusy]=useState(false), [compareError,setCompareError]=useState('');
  const [filters,setFilters]=useState({}), [filterColumn,setFilterColumn]=useState(null), [search,setSearch]=useState(''), [error,setError]=useState(''), [pending,setPending]=useState(false), [loading,setLoading]=useState(false), [uploading,setUploading]=useState(false);
  const [chartSelection,setChartSelection]=useState(null), [scheduleDraft,setScheduleDraft]=useState({enabled:false,time:'09:00'}), [savingSchedule,setSavingSchedule]=useState(false);
  const upload=useRef(), seen=useRef(null), scheduleLoaded=useRef(false);
  async function refresh() {const next=await api('/api/state');setState(next);if(next.schedule&&!scheduleLoaded.current){setScheduleDraft({enabled:next.schedule.enabled,time:next.schedule.time});scheduleLoaded.current=true;}if(next.previews.length && next.previews[0].id!==seen.current){seen.current=next.previews[0].id;setSelected(next.previews[0].id);setPrevious(String(next.previews[1]?.id || ''));}}
  useEffect(()=>{let active=true;const poll=async()=>{try{if(active)await refresh();}catch(e){if(active)setError(e.message);}};poll();const timer=setInterval(poll,1800);return()=>{active=false;clearInterval(timer);};},[]);
  useEffect(()=>{if(!selected)return;let cancelled=false;setLoading(true);setPreview(EMPTY);setFilters({});setFilterColumn(null);setSearch('');setKeys([]);api(`/api/previews/${selected}`).then(data=>{if(!cancelled)setPreview(data);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});return()=>{cancelled=true;};},[selected]);
  useEffect(()=>{setFilters({});setFilterColumn(null);setSearch('');setChartSelection(null);},[view,previous,selected]);
  useEffect(()=>{setDiff(null);setCompareBusy(false);setCompareError('');if(!previous||!selected||Number(previous)===selected)return;let cancelled=false;setCompareBusy(true);api('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore})}).then(data=>{if(!cancelled)setDiff(data);}).catch(e=>{if(!cancelled)setCompareError(e.message);}).finally(()=>{if(!cancelled)setCompareBusy(false);});return()=>{cancelled=true;};},[previous,selected,keys,ignore]);
  const comparisonTable = diff?.record_columns ? {columns:diff.record_columns,rows:[...diff.matched_rows,...diff.unmatched_rows]} : EMPTY;
  const completedOrderIds = useMemo(()=>new Set((diff?.unmatched_rows || []).map(row=>str(row['Order Number']).trim()).filter(Boolean)),[diff]);
  const mappedPreview = useMemo(()=>({...preview, rows:preview.rows.map(row=>{
    const next = {...row};
    for (const column of ['Task Status','Status']) if (column in next) {
      if (completedOrderIds.has(str(row['Order Number']).trim())) next[column] = 'Completed and Delivered';
      else if (normalized(row[column])==='workflow suspended') next[column] = 'Awaiting for Clarification';
    }
    if ('Is Available' in next) next['Is Available'] = normalized(next['Task Status'] ?? next.Status)==='available';
    return next;
  })}),[preview,completedOrderIds]);
  const table = view==='changes' ? comparisonTable : mappedPreview;
  const filtered = useMemo(()=>table.rows.filter(row=>matches(row,filters)&&(!search||table.columns.some(c=>str(row[c]).toLowerCase().includes(search.toLowerCase())))),[table,filters,search]);
  const matchedComparison = view==='changes' ? filtered.filter(row=>['Unchanged','Matched - changed'].includes(row['Comparison Status'])) : [];
  const unmatchedComparison = view==='changes' ? filtered.filter(row=>['Missing','Newly Added'].includes(row['Comparison Status'])) : [];
  const chartRows = useMemo(()=>chartSelection?filtered.filter(row=>label(row[chartSelection.column])===chartSelection.value):[],[chartSelection,filtered]);
  const productSplit = useMemo(()=>{
    if(['changes','daily'].includes(view) || !table.columns.includes('Product')) return null;
    return {
      fullTitle: filtered.filter(row=>normalized(row.Product)==='full title'),
      remaining: filtered.filter(row=>normalized(row.Product)!=='full title')
    };
  },[filtered,table.columns,view]);

  const overviewMetrics = useMemo(() => {
    if (view === 'changes') return [];
    const ogC = table.columns.includes('Online/ Ground') ? 'Online/ Ground' : table.columns.includes('Online/Ground') ? 'Online/Ground' : null;
    const clC = table.columns.includes('Client') ? 'Client' : null;
    const prC = table.columns.includes('Product') ? 'Product' : null;

    const onN = ogC ? filtered.filter(r => str(r[ogC]).toLowerCase().includes('online')).length : 0;
    const grN = ogC ? filtered.filter(r => str(r[ogC]).toLowerCase().includes('ground')).length : 0;
    const clN = clC ? new Set(filtered.map(r => label(r[clC]))).size : 0;
    const ftN = prC ? filtered.filter(r => normalized(r[prC]) === 'full title').length : 0;

    const tot = filtered.length || 1;
    return [
      ['Visible orders', filtered.length.toLocaleString(), 'green'],
      ['Online queue', `${onN.toLocaleString()} (${((onN/tot)*100).toFixed(1)}%)`, 'green'],
      ['Ground queue', `${grN.toLocaleString()} (${((grN/tot)*100).toFixed(1)}%)`, 'amber'],
      ['Active clients', clN.toLocaleString(), 'gray'],
      ['Full Title share', `${ftN.toLocaleString()} (${((ftN/tot)*100).toFixed(1)}%)`, 'gray']
    ];
  }, [view, filtered, table.columns]);

  async function extract(){setPending(true);setError('');try{await api('/api/extract',{method:'POST'});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function syncSheets(){setPending(true);setError('');try{const backend=await api('/api/state');if(!backend.capabilities?.automatic_statuses)throw Error('Restart or redeploy the dashboard backend to enable automatic statuses.');await api('/api/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preview:selected,previous:previous?Number(previous):null,keys,ignore})});await refresh();}catch(e){setError(e.message);}finally{setPending(false);}}
  async function saveSchedule(){setSavingSchedule(true);setError('');try{const saved=await api('/api/sync-schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(scheduleDraft)});setScheduleDraft({enabled:saved.enabled,time:saved.time});await refresh();}catch(e){setError(e.message);}finally{setSavingSchedule(false);}}
  async function importFile(e){const file=e.target.files[0];if(!file)return;setUploading(true);setError('');try{const body=new FormData();body.append('file',file);await api('/api/import',{method:'POST',body});await refresh();}catch(e){setError(e.message);}finally{setUploading(false);e.target.value='';}}
  function choosePrevious(value){setPrevious(value);if(!value)return;const index=state.previews.findIndex(p=>p.id===Number(value));const newer=state.previews[index-1];if(newer)setSelected(newer.id);}
  function chooseLatest(value){const id=Number(value);setSelected(id);const index=state.previews.findIndex(p=>p.id===id);setPrevious(String(state.previews[index+1]?.id||''));}
  async function deletePreview(event,id){event.stopPropagation();const target=state.previews.find(p=>p.id===id);if(!window.confirm(`Delete ${target?.name||`preview${id}`} and its saved CSV/Excel files?`))return;setError('');try{await api(`/api/previews/${id}`,{method:'DELETE'});const next=await api('/api/state');setState(next);seen.current=next.previews[0]?.id??null;const nextSelected=id===selected?(next.previews[0]?.id??null):selected;setSelected(nextSelected);const index=next.previews.findIndex(p=>p.id===nextSelected);setPrevious(String(next.previews[index+1]?.id||''));if(!nextSelected){setPreview(EMPTY);setDiff(null);}}catch(e){setError(e.message);}}
  async function downloadChanges(){try{const response=await fetch('/api/compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({previous:Number(previous),latest:selected,keys,ignore,download:true})});if(!response.ok)throw Error((await response.json()).error);saveBlob(await response.blob(),`${diff.previous}-to-${diff.latest}-changes.xlsx`);}catch(e){setError(e.message);}}
  const running=state.job.running||pending, result=state.job.result;
  return <div className="workspace">
    <aside className="sidebar"><div className="brand"><div className="brand-mark"><Activity size={23}/></div><div>DataTrace<span>WORKSPACE</span></div></div><div className="nav-label">WORKSPACE</div><nav>{[['overview','Overview',BarChart3],['sheets','Data sheets',Table2],['daily','Daily Orders',FileSpreadsheet],['changes','Changes',ArrowLeftRight]].map(([id,title,Icon])=><button className={view===id?'nav-item selected':'nav-item'} key={id} onClick={()=>setView(id)}><Icon size={18}/>{title}{id==='changes'&&diff&&<small>{diff.record_counts?diff.record_counts.missing+diff.record_counts.newly_added:diff.counts.added+diff.counts.removed}</small>}</button>)}</nav><div className="preview-heading"><span className="nav-label">SAVED PREVIEWS</span><span>{state.previews.length}</span></div><div className="preview-list">{state.previews.map(p=><div key={p.id} className={`preview-item ${selected===p.id?'selected':''}`}><button className="preview-select" onClick={()=>{setSelected(p.id);const index=state.previews.findIndex(x=>x.id===p.id);setPrevious(String(state.previews[index+1]?.id||''));}}><FileSpreadsheet size={17}/><div><strong>{p.name}</strong><small>{p.row_count.toLocaleString()} rows · {new Date(p.created).toLocaleDateString()}</small></div>{p.id===state.previews[0].id&&<i>Latest</i>}</button><IconButton title={`Delete ${p.name}`} onClick={event=>deletePreview(event,p.id)}><Trash2 size={15}/></IconButton></div>)}{!state.previews.length&&<p className="no-previews">No saved previews</p>}</div><div className="sidebar-footer"><span className="status-dot"/>Local workspace<a href={state.sheet_url} target="_blank" rel="noreferrer">Google Sheet ↗</a></div></aside>
    <main><header className="topbar"><div className="breadcrumb">Workspace <span>/</span> {view==='overview'?'Overview':view==='sheets'?'Data sheets':view==='daily'?'Daily Orders':'Changes'}</div><div className="inline"><span className={`run-state ${running?'running':''}`}>{running&&<LoaderCircle size={14} className="spin"/>}{state.job.stage}</span><button className="secondary" onClick={()=>upload.current.click()} disabled={uploading}><Upload size={16}/>{uploading?'Importing…':'Import file'}</button><input ref={upload} type="file" hidden accept=".csv,.xlsx" onChange={importFile}/></div></header>
      <div className="content"><div className="page-heading"><div><span className="eyebrow">DATATRACE QUEUE</span><h1>{view==='changes'?'Preview comparison':view==='sheets'?'Data sheets':view==='daily'?'Daily Orders':'Queue overview'}</h1><p className="muted">{preview.name?`${preview.name} · ${new Date(preview.created).toLocaleString()} · ${preview.source}`:'No data captured yet'}</p></div><div className="page-actions"><button className="secondary" onClick={syncSheets} disabled={running||!selected||loading||compareBusy||!!compareError}>{state.job.action==='sync'&&running?<LoaderCircle size={17} className="spin"/>:<CloudUpload size={17}/>}<span>{state.job.action==='sync'&&running?'Syncing…':`Sync ${preview.name||'preview'} to Sheets`}</span></button><details className="sync-schedule"><summary><Clock3 size={16}/>Sync trigger</summary><div><label className="check-row"><input type="checkbox" checked={scheduleDraft.enabled} onChange={e=>setScheduleDraft({...scheduleDraft,enabled:e.target.checked})}/>Daily sync enabled</label><label>Local time<input aria-label="Daily sync time" type="time" value={scheduleDraft.time} onChange={e=>setScheduleDraft({...scheduleDraft,time:e.target.value})}/></label><button className="primary" onClick={saveSchedule} disabled={savingSchedule}>{savingSchedule?'Saving…':'Save trigger'}</button>{state.schedule?.last_triggered_date&&<small>Last triggered {state.schedule.last_triggered_date}</small>}</div></details><button className="primary" onClick={extract} disabled={running}>{state.job.action==='extract'&&running?<LoaderCircle size={17} className="spin"/>:<Play size={17}/>}<span>{state.job.action==='extract'&&running?'Extracting queue…':'Run AutoLogin & Extract Queue'}</span></button></div></div>
      {view==='overview' && selected && <section className="automatic-statuses"><span className="eyebrow">AUTOMATIC STATUSES</span><div><span>Workflow Suspended</span><span aria-hidden="true">&#8594;</span><span className="status-rule-target" style={{background:statusColor('Awaiting for Clarification')}}>Awaiting for Clarification</span></div><div><span>Missing + Newly Added</span><span aria-hidden="true">&#8594;</span><span className="status-rule-target" style={{background:statusColor('Completed and Delivered')}}>Completed and Delivered</span></div></section>}
      {error&&<div className="notice error" role="alert">{error}<IconButton title="Dismiss error" onClick={()=>setError('')}><X size={16}/></IconButton></div>}
      {result?.error&&<div className="notice warning" role="status">{result.preview_name&&<strong>{result.preview_name} saved. </strong>}{result.error}</div>}
      {result&&!result.error&&!running&&<div className="notice success"><Check size={16}/>{result.action==='sync'?`${result.preview_name} synced · ${result.rows} rows · ${result.worksheets?.length||0} Google Sheets tabs updated`:`${result.preview_name} saved locally · ${result.rows} rows · Google Sheets not changed`}</div>}
      {!state.previews.length ? <div className="empty-state"><div className="empty-icon"><Database size={40} strokeWidth={1.3}/></div><h2>No queue data yet</h2><p>Your saved previews will appear here.</p><button className="secondary" onClick={()=>upload.current.click()}><Plus size={17}/>Import Excel or CSV</button></div> : <>
      {['changes','daily'].includes(view)&&<section className="compare-controls"><label>Previous preview<select aria-label="Previous preview" value={previous} onChange={e=>choosePrevious(e.target.value)}><option value="">Select a preview</option>{state.previews.filter(p=>p.id!==selected).map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><ArrowLeftRight size={18}/><label>Latest preview<select aria-label="Latest preview" value={selected||''} onChange={e=>chooseLatest(e.target.value)}>{state.previews.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><details className="match-options"><summary><SlidersHorizontal size={16}/>Matching columns {keys.length?`(${keys.length})`:'(Auto)'}</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={keys.includes(c)} onChange={()=>setKeys(keys.includes(c)?keys.filter(k=>k!==c):[...keys,c])}/>{c}</label>)}</div></details><details className="match-options"><summary>Ignored columns ({ignore.length})</summary><div>{preview.columns.map(c=><label className="check-row" key={c}><input type="checkbox" checked={ignore.includes(c)} onChange={()=>setIgnore(ignore.includes(c)?ignore.filter(k=>k!==c):[...ignore,c])}/>{c}</label>)}</div></details><button className="secondary" disabled={!diff||compareBusy} onClick={downloadChanges}><ArrowDownToLine size={16}/>Power BI changes.xlsx</button></section>}
      {['changes','daily'].includes(view)&&compareError&&<div className="notice warning">{compareError}</div>}
      {['changes','daily'].includes(view)&&!previous&&<div className="notice">Capture or import a second preview to compare changes.</div>}
      {view==='changes'&&diff&&<><p className="comparison-method">{diff.method}</p>{(diff.added_columns.length>0||diff.removed_columns.length>0)&&<div className="notice">Columns added: {diff.added_columns.join(', ')||'None'} · Columns removed: {diff.removed_columns.join(', ')||'None'}</div>}</>}
      <div className="metrics">{(view==='changes'?[['Matched',diff?.record_counts?.matched??'—','green'],['Missing (Completed Orders)',diff?.record_counts?.missing??'—','red'],['Newly added',diff?.record_counts?.newly_added??'—','amber'],['Unchanged',diff?.record_counts?.unchanged??'—','gray']]:view==='daily'?[['Daily orders',preview.rows.length,'green'],['Missing (Completed Orders)',diff?.record_counts?.missing??'—','red'],['Newly added',diff?.record_counts?.newly_added??'—','amber'],['Unchanged',diff?.record_counts?.unchanged??'—','gray']]:overviewMetrics).map(([title,value,color])=><div className={`metric ${color}`} key={title}><span>{title}</span><strong>{value}</strong></div>)}</div>
      <div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search rows" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div><select aria-label="Choose column filter" value={filterColumn||''} onChange={e=>setFilterColumn(e.target.value||null)}><option value="">Filter a column…</option>{table.columns.map(c=><option key={c}>{c}</option>)}</select>{Object.keys(filters).map(c=><button className="filter-chip" key={c} onClick={()=>setFilterColumn(c)}><Filter size={12}/>{c}</button>)}{Object.keys(filters).length>0&&<button className="text-button" onClick={()=>setFilters({})}>Clear filters</button>}<span className="row-tally">{filtered.length.toLocaleString()} / {table.rows.length.toLocaleString()} rows</span>{view!=='changes'&&preview.id&&<><a className="secondary" href={`/api/previews/${preview.id}/download/xlsx`}><ArrowDownToLine size={16}/>Excel</a><a className="secondary" href={`/api/previews/${preview.id}/download/csv`}>CSV</a></>}</div>
      {(loading||(['changes','daily'].includes(view)&&compareBusy))?<div className="loading"><LoaderCircle className="spin"/>Loading preview…</div>:<><div className={filterColumn?'data-layout with-filter':'data-layout'}><div className="data-main">{view==='overview'&&<><OverviewDashboard rows={filtered} columns={table.columns} onSelect={setChartSelection}/><Chart rows={filtered} columns={table.columns} onSelect={setChartSelection}/>{chartSelection&&<div className="chart-drilldown"><DataTable rows={chartRows} columns={table.columns} filters={{}} openFilter={()=>{}} filterable={false} onClose={()=>setChartSelection(null)} name={`${chartSelection.value} · ${chartRows.length} orders`}/></div>}</>}
        {view==='daily'&&<DailyOrders preview={preview} diff={diff} onChoose={(id,previousId)=>{setSelected(id);setPrevious(String(previousId||''));}}/>}
        {productSplit ? <>
          <DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`${preview.name||'Queue'} - All Products`}/>
          <DataTable rows={productSplit.fullTitle} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`${preview.name||'Queue'} - Full Title`}/>
          <DataTable rows={productSplit.remaining} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`${preview.name||'Queue'} - Remaining Products`}/>
        </> : <>{view==='changes'&&diff?.order_append&&<section className="order-append"><div className="order-append-summary"><div><span>Previous last order</span><strong>{diff.order_append.anchor_order||'Not available'}</strong></div><div><span>First new order</span><strong>{diff.order_append.first_added_order||'—'}</strong></div><div><span>Latest new order</span><strong>{diff.order_append.latest_added_order||'—'}</strong></div><div><span>Orders added after it</span><strong>{diff.order_append.available?diff.order_append.count:'—'}</strong></div></div>{diff.order_append.available&&<DataTable rows={diff.order_append.rows} columns={diff.order_append.columns} filters={{}} openFilter={()=>{}} filterable={false} name={`Orders after ${diff.order_append.anchor_order}`}/>}</section>}{view==='changes'?<><DataTable rows={matchedComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={`Matched orders · ${diff?.previous||'Previous'} and ${diff?.latest||'Latest'}`}/><DataTable rows={unmatchedComparison} columns={table.columns} filters={filters} openFilter={setFilterColumn} name="Missing (Completed Orders) and newly added orders"/></>:<DataTable rows={filtered} columns={table.columns} filters={filters} openFilter={setFilterColumn} name={preview.name||'Queue'}/>}</>}
      </div>{filterColumn&&<FilterPanel key={filterColumn} column={filterColumn} rows={table.rows} filters={filters} setFilters={setFilters} close={()=>setFilterColumn(null)}/>}</div></>}
      </>}
      <footer className="page-footer"><span>DataTrace Workspace</span><span>{state.previews.length} saved previews · Local storage</span></footer></div>
    </main>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);

