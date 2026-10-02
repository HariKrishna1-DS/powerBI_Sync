import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowDown, ArrowUp, ArrowDownToLine, ArrowLeftRight, BarChart3, CalendarDays, Check, ChevronLeft, ChevronRight, Clock3, CloudUpload, Database, FileSpreadsheet, Filter, HardDrive, LoaderCircle, Maximize2, Minimize2, Play, Plus, Printer, Search, SlidersHorizontal, Table2, Trash2, Upload, X } from 'lucide-react';
import { ResponsiveContainer, LabelList, BarChart, Bar, LineChart, Line, AreaChart, Area, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Brush } from 'recharts';
import {OfflineNotice} from './DesktopExperience';
import remainingProducts from '../../remaining_products.json';

import {EMPTY, DEFAULT_IGNORE, colors, str, label, normalized, badgeClass, STATUS_COLORS, statusColor, textColorForBg, api, saveBlob, csvDownload, matches, IconButton} from './workspaceUtils';
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
}function OverviewDashboard({rows, columns, onSelect, selectedProducts, setSelectedProducts}) {
  const ogCol = columns.includes('Online/ Ground') ? 'Online/ Ground' : columns.includes('Online/Ground') ? 'Online/Ground' : null;
  const clientCol = columns.includes('Client') ? 'Client' : null;
  const prodCol = columns.includes('Product') ? 'Product' : null;
  const statusCol = columns.includes('Task Status') ? 'Task Status' : columns.includes('Status') ? 'Status' : null;

  // Slicer State
  const [selectedClients, setSelectedClients] = useState([]);
  const [selectedOg, setSelectedOg] = useState([]);
  const [localProducts, setLocalProducts] = useState([]);
  const activeSelectedProducts = selectedProducts !== undefined ? selectedProducts : localProducts;
  const updateSelectedProducts = setSelectedProducts !== undefined ? setSelectedProducts : setLocalProducts;
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
    rows.forEach(r => {
      const p = label(r[prodCol]);
      if (p && !['full title', 'full search'].includes(normalized(p))) {
        map.set(p, (map.get(p) || 0) + 1);
      }
    });
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
      if (activeSelectedProducts.length > 0 && prodCol) {
        if (!activeSelectedProducts.includes(label(r[prodCol]))) return false;
      }
      return true;
    });
  }, [rows, selectedClients, selectedOg, activeSelectedProducts, clientCol, ogCol, prodCol]);

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
              <summary>Remaining Products <span>{selectedProducts.length ? `${selectedProducts.length} selected` : 'All'}</span></summary>
              <div className="dropdown-slicer-options">
                <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                  <button className="text-button" onClick={()=>setSelectedProducts(allProducts.map(x=>x[0]))}>All products</button>
                  <button className="text-button" onClick={()=>setSelectedProducts([])}>Clear</button>
                </div>
                <label className="slicer-item" style={{ fontWeight: 600, borderBottom: '1px solid #e2e8f0', paddingBottom: 6, marginBottom: 6 }}>
                  <input
                    type="checkbox"
                    checked={allProducts.length > 0 && selectedProducts.length === allProducts.length}
                    onChange={e => setSelectedProducts(e.target.checked ? allProducts.map(x=>x[0]) : [])}
                  />
                  <span style={{ flex: 1 }}>All products</span>
                  <small style={{ color: '#94a3b8' }}>{allProducts.reduce((sum, p) => sum + p[1], 0)}</small>
                </label>
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
    <div className="table-scroll"><table><thead><tr>{columns.map(c=><th key={c}><div className="th-inner">{filterable?<button className={filters[c]?'column-button active-filter':'column-button'} title={`Filter ${c} and view unique values`} onClick={()=>openFilter(c)}>{c}<Filter size={13}/></button>:<span className="column-label">{c}</span>}<IconButton title={`Sort ${c}`} onClick={()=>setSort({column:c,desc:sort?.column===c?!sort.desc:false})}>{sort?.column===c&&sort.desc?<ArrowDown size={13}/>:<ArrowUp size={13}/>}</IconButton></div></th>)}</tr></thead><tbody>{sorted.slice(safePage*size,(safePage+1)*size).map((row,i)=><tr key={i}>{columns.map(c=><td key={c} title={str(row[c])}>{c==='Change'||c==='Comparison Status'?<span className={`badge ${badgeClass(row[c])}`}>{c==='Comparison Status'&&row[c]==='Missing'?'Missing Previews':str(row[c])}</span>:label(row[c])}</td>)}</tr>)}</tbody></table>{!rows.length&&<div className="table-empty">No matching rows</div>}</div>
    <footer className="table-footer"><span>{rows.length.toLocaleString()} rows</span><div className="inline"><label>Rows <select aria-label="Rows per page" value={size} onChange={e=>setSize(Number(e.target.value))}>{[25,50,100,250].map(n=><option key={n}>{n}</option>)}</select></label><IconButton title="Previous page" disabled={safePage===0} onClick={()=>setPage(safePage-1)}><ChevronLeft size={16}/></IconButton><span>{safePage+1} / {pages}</span><IconButton title="Next page" disabled={safePage+1===pages} onClick={()=>setPage(safePage+1)}><ChevronRight size={16}/></IconButton></div></footer>
  </section>;
}

function completionStatus(row) { return row; }

const DAILY_SERIES = [
  {name:'Today Orders',color:'#147d72'},
  {name:'Not in latest preview',color:'#bd6268'},
  {name:'Newly Orders',color:'#d79a32'},
  {name:'Unchanged',color:'#596cc0'},
  {name:'Awaiting for Clarification',color:STATUS_COLORS['awaiting for clarification']}
];

function PeriodOrdersChart({history, selected, onSelect, period, series, title, label: chartLabel}) {
  const [expanded,setExpanded]=useState(false);
  const sorted=useMemo(()=>[...history].sort((a,b)=>a[period].localeCompare(b[period])),[history,period]);
  const selectedIndex=Math.max(0,sorted.findIndex(item=>item[period]===selected));
  const start=Math.max(0,Math.min(selectedIndex-2,sorted.length-3));
  const data=sorted.slice(start,start+3);
  const formatPeriod=value=>{
    const date=new Date(period==='Date'?`${value}T12:00:00`:`${value}-01T12:00:00`);
    return Number.isNaN(date.getTime())?value:date.toLocaleDateString('en-US',period==='Date'?{month:'short',day:'numeric'}:{month:'short',year:'numeric'});
  };
  const renderChart=(large=false)=><>
    <div className="chart-period-controls">
      <button className="secondary" disabled={start===0} onClick={()=>onSelect(sorted[Math.max(0,start-1)][period])}><ChevronLeft size={15}/>Earlier</button>
      <span>{data.length?`${formatPeriod(data[0][period])} – ${formatPeriod(data.at(-1)[period])}`:''}</span>
      <button className="secondary" disabled={start+3>=sorted.length} onClick={()=>onSelect(sorted[Math.min(sorted.length-1,start+5)][period])}>Later<ChevronRight size={15}/></button>
    </div>
    <div className="daily-chart-legend">{series.map(item=><span key={item.name}><i style={{background:item.color}}/>{item.name}</span>)}</div>
    <div className="daily-chart-scroll"><div style={{height:large?460:340,minWidth:Math.max(620,data.length*series.length*48)}}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{top:32,right:24,bottom:12,left:4}} barGap={5} barCategoryGap="12%">
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e9edee"/>
          <XAxis dataKey={period} tick={{fontSize:12}} tickFormatter={formatPeriod} interval={0}/>
          <YAxis allowDecimals={false} tick={{fontSize:12}} width={52} domain={[0,max=>Math.max(5,Math.ceil(max*1.15))]}/>
          <Tooltip cursor={{fill:'#f0f5f3'}} formatter={(value,name,item)=>period==='Month'?`${Number(value).toLocaleString()} (${monthlyPercentage(item.payload,name)})`:Number(value).toLocaleString()}/>
          {series.map(item=><Bar key={item.name} dataKey={item.name} fill={item.color} radius={[3,3,0,0]} maxBarSize={40} minPointSize={value=>Number(value)>0?3:0} isAnimationActive={false} cursor="pointer" onClick={entry=>onSelect(entry[period]||entry.payload?.[period])}>
            {data.map(row=><Cell key={row[period]} fillOpacity={row[period]===selected?1:0.8}/>)}
            <LabelList dataKey={item.name} position="top" fill="#233b37" fontSize={11} fontWeight={600} formatter={value=>Number(value)>0?Number(value).toLocaleString():''}/>
          </Bar>)}
        </BarChart>
      </ResponsiveContainer>
    </div></div>
    <p className="chart-hint">Values appear above each bar. Zero values have no bar. Select a bar or use Earlier / Later to change the period.</p>
  </>;
  return <section className="daily-chart" aria-label={chartLabel}>
    <div className="card-head"><h3>{title}</h3><IconButton title={`Expand ${chartLabel.toLowerCase()}`} onClick={()=>setExpanded(true)}><Maximize2 size={16}/></IconButton></div>
    {data.length?renderChart():<div className="table-empty">No orders</div>}
    {expanded&&<MaximizedModal title={title} onClose={()=>setExpanded(false)}>{renderChart(true)}</MaximizedModal>}
  </section>;
}
function DailyOrdersChart({history, selectedDate, onSelect}) {
  return <PeriodOrdersChart history={history} selected={selectedDate} onSelect={onSelect} period="Date" series={DAILY_SERIES} title="Daily Orders by Date" label="Daily orders bar chart"/>;
}

function DailyOrders({preview, running}) {
  const [history,setHistory]=useState([]), [error,setError]=useState(''), [date,setDate]=useState(''), [search,setSearch]=useState('');
  const [loading,setLoading]=useState(true), [snapshot,setSnapshot]=useState(null);
  useEffect(()=>{let active=true;setLoading(true);api(`/api/daily-orders${preview.id?`?preview_id=${preview.id}`:''}`).then(data=>{if(active){setHistory(data.rows);setSnapshot(data);setDate(data.selected_date||'');setSearch('');setError('');}}).catch(e=>{if(active){setHistory([]);setError(e.message);}}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[preview.id,running]);
  const selectedDay=history.find(day=>day.Date===date)||history[0];
  const columns=selectedDay?.columns||[];
  const rows=(selectedDay?.rows||[]).filter(row=>!search||columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase())));
  const groups=[
    ['Today Orders',rows],
    ['Not in latest preview',rows.filter(row=>selectedDay?.missing_ids.includes(str(row['Order Number']).trim()))],
    ['Newly Orders',rows.filter(row=>selectedDay?.new_ids.includes(str(row['Order Number']).trim()))],
    ['Unchanged',rows.filter(row=>selectedDay?.unchanged_ids.includes(str(row['Order Number']).trim()))],
    ['Awaiting for Clarification',rows.filter(row=>normalized(row['Task Status'] ?? row.Status)==='awaiting for clarification')]
  ];
  const names=['Today Orders','Not in latest preview','Newly Orders','Unchanged','Awaiting for Clarification'];
  return <section className="daily-orders"><OfflineNotice snapshot={snapshot}/>
    {error&&<div className="notice error">{error}</div>}
    {loading?<div className="loading"><LoaderCircle className="spin"/>Loading daily orders...</div>:<>
      <div className="section-heading"><h2>Daily production orders</h2><label>Date<select aria-label="Daily orders date" value={selectedDay?.Date||''} onChange={e=>{setDate(e.target.value);setSearch('');}}>{history.map(day=><option key={day.Date}>{day.Date}</option>)}</select></label></div>
      <div className="metrics">{names.map((name,index)=><div className={`metric ${['green','red','amber','gray','purple'][index]}`} key={name}><span>{name}</span><strong>{selectedDay?.[name]??0}</strong></div>)}</div>
      <DailyOrdersChart history={history} selectedDate={selectedDay?.Date} onSelect={value=>{if(value){setDate(value);setSearch('');}}}/>
      <div className="table-scroll"><table><thead><tr>{['Date','Previews',...names].map(name=><th key={name}>{name}</th>)}</tr></thead><tbody>{history.map(day=><tr key={day.Date}><td><button className="text-button" onClick={()=>{setDate(day.Date);setSearch('');}}>{day.Date}</button></td><td>{day.Previews.join(', ')}</td>{names.map(name=><td key={name}>{day[name]}</td>)}</tr>)}</tbody></table></div>
      <div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search daily orders" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div></div>
      {selectedDay?groups.map(([name,items])=><DataTable key={name} rows={items} columns={columns} filters={{}} openFilter={()=>{}} filterable={false} name={`${name} · ${items.length}`}/>):<div className="table-empty">No daily orders</div>}
    </>}
  </section>;
}

const MONTHLY_SERIES = [
  {name:'Month Orders',color:'#147d72'},
  {name:'Completed Orders',color:'#bd6268'},
  {name:'Unchanged',color:'#596cc0'},
  {name:'Awaiting for Clarification',color:STATUS_COLORS['awaiting for clarification']},
  {name:'SLA On Time',color:'#30874b'},
  {name:'SLA Missed',color:'#d79a32'}
];

function monthlyPercentage(report, name) {
  const total=name.startsWith('SLA ')?(report?.['SLA On Time']||0)+(report?.['SLA Missed']||0):report?.['Month Orders'];
  return `${total?((report?.[name]||0)/total*100).toFixed(1):'0.0'}%`;
}

function MonthlyOrdersChart({history, selectedMonth, onSelect}) {
  return <PeriodOrdersChart history={history} selected={selectedMonth} onSelect={onSelect} period="Month" series={MONTHLY_SERIES} title="Monthly Orders by Month" label="Monthly orders bar chart"/>;
}

const SLA_COLUMNS=['Order Number','Product Group','Product','In Time','Out Time','SLA Expiration','Free Site'];
const slaRowKey=row=>JSON.stringify([row['Order Number'],row.completion_date]);

function SlaOrdersTable({rows, statusFilter, onStatusFilter, onSave, running}) {
  const [search,setSearch]=useState(''), [group,setGroup]=useState(''), [page,setPage]=useState(0);
  const [editing,setEditing]=useState(null), [draft,setDraft]=useState(''), [saving,setSaving]=useState(false);
  const [error,setError]=useState(''), [message,setMessage]=useState('');
  const [selected,setSelected]=useState({}), [bulkStatus,setBulkStatus]=useState('');
  const pageCheckbox=useRef(null);
  const filtered=rows.filter(row=>(!statusFilter||row['Free Site']===statusFilter)&&(!group||row['Product Group']===group)&&
    (!search||SLA_COLUMNS.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase()))));
  const pages=Math.max(1,Math.ceil(filtered.length/25)), currentPage=Math.min(page,pages-1);
  const pageRows=filtered.slice(currentPage*25,(currentPage+1)*25);
  const selectable=filtered.filter(row=>row['Order Number']);
  const selectablePage=pageRows.filter(row=>row['Order Number']);
  const selectedRows=Object.values(selected), selectedCount=selectedRows.length;
  const checkedPage=selectablePage.filter(row=>selected[slaRowKey(row)]).length;
  const allPage=selectablePage.length>0&&checkedPage===selectablePage.length;
  useEffect(()=>{setPage(0);setSelected({});setBulkStatus('');},[search,group,statusFilter]);
  useEffect(()=>{if(pageCheckbox.current)pageCheckbox.current.indeterminate=checkedPage>0&&!allPage;},[checkedPage,allPage]);
  const selectRows=(items,checked)=>{
    setEditing(null);setError('');setMessage('');
    setSelected(previous=>{const next={...previous};items.forEach(row=>{if(checked)next[slaRowKey(row)]=row;else delete next[slaRowKey(row)];});return next;});
  };
  const save=async(items,status)=>{
    setSaving(true);setError('');setMessage('');
    try{const result=await onSave(items,status);setMessage(result);setEditing(null);setSelected({});setBulkStatus('');}
    catch(e){setError(e.message);}
    finally{setSaving(false);}
  };
  return <section className="sla-orders" aria-label="SLA order details">
    <div className="section-heading"><div><h3>SLA order details</h3><p className="muted">Edit an order, or select several orders to update their SLA status together.</p></div></div>
    {message&&<div className="notice success" role="status"><Check size={16}/>{message}</div>}
    {error&&<div className="notice error" role="alert">{error}</div>}
    {editing&&<div className="sla-editor" role="group" aria-label={`Edit SLA for order ${editing['Order Number']}`}>
      <div><strong>Order {editing['Order Number']}</strong><p className="muted">{editing['Product Group']} · Out Time: {editing['Out Time']}</p></div>
      <label>Free Site (SLA status)<select aria-label="Edit Free Site" value={draft} disabled={saving} onChange={e=>setDraft(e.target.value)}><option>On Time</option><option>Missing</option></select></label>
      <button className="primary" onClick={()=>save(editing,draft)} disabled={saving||running||draft===editing['Free Site']}>{saving?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>} {saving?'Saving…':'Save SLA'}</button>
      <button className="secondary" disabled={saving} onClick={()=>{setEditing(null);setError('');}}>Cancel</button>
    </div>}
    {running&&<p className="muted">SLA editing requires a live connection and an idle workspace.</p>}
    <div className="filter-toolbar">
      <div className="search-input"><Search size={16}/><input aria-label="Search SLA orders" placeholder="Search order or product" value={search} disabled={saving} onChange={e=>setSearch(e.target.value)}/></div>
      <select aria-label="Filter SLA status" value={statusFilter} disabled={saving} onChange={e=>onStatusFilter(e.target.value)}><option value="">All SLA results</option><option value="On Time">SLA On Time</option><option value="Missing">SLA Missed</option></select>
      <select aria-label="Filter SLA product group" value={group} disabled={saving} onChange={e=>setGroup(e.target.value)}><option value="">All products</option><option>Full Title</option><option>Remaining Products</option></select>
      <span className="row-tally">{filtered.length} / {rows.length} orders</span>
    </div>
    {selectedCount>0&&<div className="sla-bulk-editor" role="group" aria-label="Update selected SLA orders">
      <div><strong>{selectedCount} orders selected</strong><p className="muted">Selections carry across pages. Changing filters clears the selection.</p>
        {selectedCount<selectable.length&&<button className="text-button" disabled={saving||running} onClick={()=>selectRows(selectable,true)}>Select all {selectable.length} matching orders</button>}
      </div>
      <label>Set selected orders to<select aria-label="Bulk SLA status" value={bulkStatus} disabled={saving} onChange={e=>setBulkStatus(e.target.value)}><option value="">Choose status</option><option>On Time</option><option>Missing</option></select></label>
      <button className="primary" disabled={saving||running||!bulkStatus} onClick={()=>save(selectedRows,bulkStatus)}>{saving?<LoaderCircle size={16} className="spin"/>:<Check size={16}/>} {saving?'Saving…':`Update ${selectedCount} selected`}</button>
      <button className="secondary" disabled={saving} onClick={()=>{setSelected({});setBulkStatus('');setError('');}}>Clear selection</button>
    </div>}
    <div className="table-scroll"><table aria-label="SLA orders"><thead><tr><th className="sla-check"><input ref={pageCheckbox} type="checkbox" aria-label="Select all orders on this page" checked={allPage} disabled={saving||running||!selectablePage.length} onChange={e=>selectRows(selectablePage,e.target.checked)}/></th>{SLA_COLUMNS.map(column=><th key={column}>{column==='Free Site'?'Free Site / SLA':column}</th>)}<th>Action</th></tr></thead>
      <tbody>{pageRows.map(row=><tr key={slaRowKey(row)} className={selected[slaRowKey(row)]?'sla-selected':''}>
        <td className="sla-check"><input type="checkbox" aria-label={`Select order ${row['Order Number']}`} checked={!!selected[slaRowKey(row)]} disabled={saving||running||!row['Order Number']} onChange={e=>selectRows([row],e.target.checked)}/></td>
        {SLA_COLUMNS.map(column=><td key={column} title={str(row[column])}>{column==='Free Site'?<span className={`sla-badge ${row[column]==='On Time'?'on-time':'missed'}`}>{row[column]}</span>:str(row[column])||'—'}</td>)}
        <td><button className="secondary" aria-label={`Edit SLA for order ${row['Order Number']}`} disabled={saving||running||!row['Order Number']} onClick={()=>{setSelected({});setBulkStatus('');setEditing(row);setDraft(row['Free Site']);setError('');setMessage('');}}>Edit</button></td>
      </tr>)}</tbody></table>{!filtered.length&&<div className="table-empty">No matching SLA orders</div>}</div>
    <div className="table-footer"><span>Page {currentPage+1} of {pages}</span><div className="inline"><button className="secondary" aria-label="Previous SLA page" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}><ChevronLeft size={16}/>Previous</button><button className="secondary" aria-label="Next SLA page" disabled={currentPage>=pages-1} onClick={()=>setPage(currentPage+1)}>Next<ChevronRight size={16}/></button></div></div>
  </section>;
}

function MonthlyOrders({preview,running}) {
  const [history,setHistory]=useState([]), [error,setError]=useState(''), [month,setMonth]=useState(''), [search,setSearch]=useState('');
  const [loading,setLoading]=useState(true), [snapshot,setSnapshot]=useState(null);
  const [slaFilter,setSlaFilter]=useState(''), [refreshId,setRefreshId]=useState(0), [saving,setSaving]=useState(false);
  const savePending=useRef(false), reportVersion=useRef(0);
  useEffect(()=>{
    let active=true, busy=false;
    setLoading(true);
    const refresh=async()=>{
      if(busy||savePending.current)return;
      busy=true;
      const version=reportVersion.current;
      try{
        const data=await api('/api/monthly-orders');
        if(active&&version===reportVersion.current){setHistory(data.rows);setSnapshot(data);setError(data.sla_error||'');}
      }catch(e){if(active&&version===reportVersion.current){setHistory([]);setError(e.message);}}
      finally{busy=false;if(active)setLoading(false);}
    };
    refresh();
    const timer=setInterval(refresh,30000);
    return()=>{active=false;clearInterval(timer);};
  },[preview?.id,refreshId]);

  const saveSla=async(row,status)=>{
    savePending.current=true;setSaving(true);reportVersion.current++;
    try{
      const order=item=>({order_number:item['Order Number'],completion_date:item.completion_date,expected_status:item['Free Site']});
      const bulk=Array.isArray(row);
      const result=await api(bulk?'/api/sla-comments/bulk':'/api/sla-comments',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify(bulk?{orders:row.map(order),status}:{...order(row),status})});
      reportVersion.current++;setHistory(result.rows);setError('');
      return result.message;
    }finally{savePending.current=false;setSaving(false);}
  };

  const selectedMonth=history.find(m=>m.Month===month)||history[0];
  const columns=selectedMonth?.columns||[];
  const rows=(selectedMonth?.rows||[]).filter(row=>!search||columns.some(column=>str(row[column]).toLowerCase().includes(search.toLowerCase())));
  const groups=[
    ['Month Orders',rows],
    ['Completed Orders',rows.filter(row=>selectedMonth?.completed_ids.includes(str(row['Order Number']).trim()))],
    ['Awaiting for Clarification',rows.filter(row=>normalized(row['Task Status'] ?? row.Status)==='awaiting for clarification')]
  ];
  const names=MONTHLY_SERIES.map(series=>series.name);

  return <section className="daily-orders"><OfflineNotice snapshot={snapshot}/>
    {error&&<div className="notice error">{error}</div>}
    {loading?<div className="loading"><LoaderCircle className="spin"/>Loading monthly orders...</div>:<>
      <div className="section-heading"><h2>Monthly production orders</h2><label>Month<select aria-label="Monthly orders date" disabled={saving} value={selectedMonth?.Month||''} onChange={e=>{setMonth(e.target.value);setSearch('');}}>{history.map(m=><option key={m.Month} value={m.Month}>{m.MonthLabel || m.Month}</option>)}</select></label></div>
      <div className="metrics">{names.slice(0,3).map((name,index)=><div className={`metric ${['green','red','purple'][index]}`} key={name}><span>{name}</span><strong>{selectedMonth?.[name]??(error?'—':0)}</strong><small>{monthlyPercentage(selectedMonth,name)}</small></div>)}</div>
      <div className="section-heading"><h2>SLA COMMENTS</h2><button className="secondary" disabled={saving} onClick={()=>setRefreshId(value=>value+1)}>Refresh SLA</button></div>
      <div className="metrics sla-metrics">{names.slice(3).map(name=>{const value=name==='SLA On Time'?'On Time':'Missing';return <button className={`metric sla-metric ${value==='On Time'?'green':'amber'}`} key={name} disabled={saving} aria-pressed={slaFilter===value} onClick={()=>setSlaFilter(slaFilter===value?'':value)}><span>{name}</span><strong>{selectedMonth?.[name]??(error?'—':0)}</strong><small>{monthlyPercentage(selectedMonth,name)}</small></button>;})}</div>
      <SlaOrdersTable key={selectedMonth?.Month||'empty'} rows={selectedMonth?.sla_rows||[]} statusFilter={slaFilter} onStatusFilter={setSlaFilter} onSave={saveSla} running={running||snapshot?.offline}/>
      <MonthlyOrdersChart history={history} selectedMonth={selectedMonth?.Month} onSelect={value=>{if(value){setMonth(value);setSearch('');}}}/>
      <div className="table-scroll"><table><thead><tr>{['Month','Previews',...names].map(name=><th key={name}>{name}</th>)}</tr></thead><tbody>{history.map(m=><tr key={m.Month}><td><button className="text-button" onClick={()=>{setMonth(m.Month);setSearch('');}}>{m.MonthLabel || m.Month}</button></td><td>{m.Previews.join(', ')}</td>{names.map(name=><td key={name}>{`${m[name]??0} (${monthlyPercentage(m,name)})`}</td>)}</tr>)}</tbody></table></div>
      <div className="filter-toolbar"><div className="search-input"><Search size={16}/><input aria-label="Search monthly orders" placeholder="Search all columns" value={search} onChange={e=>setSearch(e.target.value)}/></div></div>
      {selectedMonth?groups.map(([name,items])=><DataTable key={name} rows={items} columns={columns} filters={{}} openFilter={()=>{}} filterable={false} name={`${name} · ${items.length}`}/>):<div className="table-empty">No monthly orders</div>}
    </>}
  </section>;
}


export {DataTable, FilterPanel, DailyOrders, MonthlyOrders};
