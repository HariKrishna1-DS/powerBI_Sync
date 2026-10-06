import React, {useEffect, useState} from 'react';
const LazyReportChart = React.lazy(() => import('./ReportChart'));
function ReportChart(props) { return <React.Suspense fallback={<p role="status">Loading chart…</p>}><LazyReportChart {...props}/></React.Suspense>; }
import {Download, ExternalLink, RefreshCw, Upload} from 'lucide-react';
import {api, saveBlob} from './workspaceUtils';
import {Dialog, OfflineNotice} from './DesktopExperience';
import './reportWorkspace.css';

const DAILY = ['Received', 'Completed', 'Clarification', 'Cancelled', 'Vendor Pending', 'In-House Pending', 'On time SLA', 'Missed SLA'];
const CAPACITY = ['Date', ...DAILY.slice(0, 6), 'Capacity', 'Ext capacity'];
const number = value => value == null ? '—' : Number(value).toLocaleString();

export async function downloadReports() {
  const response = await fetch('/api/reporting/export', {signal: AbortSignal.timeout(120000)});
  if (!response.ok) throw Error((await response.json()).error || 'Report export failed.');
  saveBlob(await response.blob(), 'Tv-Tracker-Reports.xlsx');
}

export function ReportSourceControls({running, preferences, onChanged}) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState([]);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const prefs = data?.preferences || preferences;
  async function refresh() { setData(await api('/api/reporting')); }
  useEffect(() => { refresh().catch(e => setError(e.message)); }, [preferences?.revision]);
  async function action(work) {
    setBusy(true); setError('');
    try { await work(); await refresh(); onChanged(); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  }
  function activate(source, importId) {
    return api('/api/reporting/source', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({source, import_id: importId})});
  }
  const blocked = busy || running || prefs?.publish_status === 'publishing';
  return <section className="report-source" aria-label="Report source controls">
    <div className="report-source-controls">
      <label>Report source<select aria-label="Report source" value={prefs?.source || 'tracker'} disabled={blocked} onChange={e => {
        const source = e.target.value;
        const imported = prefs?.import_id || data?.imports[0]?.id;
        if (source === 'import' && !imported) { setOpen(true); return; }
        action(() => activate(source, imported));
      }}><option value="tracker">Tracker report</option><option value="import">Import Excel report</option></select></label>
      {prefs?.source === 'import' && <label>Saved import<select aria-label="Saved Excel import" value={prefs.import_id || ''} disabled={blocked}
        onChange={e => action(() => activate('import', e.target.value))}>{data?.imports.map(item => <option key={item.id} value={item.id}>{item.files.map(file => file.name).join(', ')} · {number(item.count)} orders</option>)}</select></label>}
      <button className="secondary" disabled={blocked} onClick={() => { setPreview(null); setFiles([]); setOpen(true); }}><Upload size={16}/>Import Excel reports</button>
      <button className="secondary" disabled={blocked} onClick={() => action(() => api('/api/reporting/publish', {method: 'POST'}))}><RefreshCw size={16}/>Publish reports</button>
    </div>
    <p className="field-help" role="status">{prefs?.publish_status === 'publishing' ? 'Publishing the selected source to Google Sheets…' : prefs?.publish_status === 'published' ? 'This source is published to Google Sheets.' : prefs?.publish_status === 'failed' ? prefs.publish_error : 'Choose a report source. Source changes also publish its reports to Google Sheets.'}</p>
    <p className="field-help">The first upgraded computer to publish becomes this workbook’s designated writer. Other computers can read reports. Queue captures remain separate from imported reports.</p>
    {error && <p role="alert" className="notice error">{error}</p>}    <StorageControls blocked={blocked} onChanged={onChanged}/>
    {open && <Dialog title="Import Excel reports" onClose={() => { if (!busy) setOpen(false); }} className="report-import-dialog">
      <div className="report-import-body">
        <p>Select multiple production workbooks. Each order table needs Order Number, Product, Status and Date or In-Time. Use a values-only copy for formula workbooks.</p>
        <label>Excel workbooks<input aria-label="Excel report workbooks" type="file" accept=".xlsx" multiple disabled={busy}
          onChange={e => { setFiles([...e.target.files]); setPreview(null); }}/></label>
        <p>{files.length} workbooks selected. Up to 20 files and 100,000 rows; 20 MB total upload.</p>
        <button className="secondary" disabled={busy || !files.length} onClick={() => action(async () => {
          const body = new FormData(); files.forEach(file => body.append('files', file));
          setPreview(await api('/api/reporting/import', {method: 'POST', body}));
        })}>{busy ? 'Checking workbooks…' : 'Validate import'}</button>
        {preview && <section aria-label="Excel import summary" className="import-summary">
          <h3>{number(preview.count)} validated orders</h3>
          <p>{number(preview.duplicates_removed)} identical duplicates removed. Conflicting duplicates are rejected.</p>
          <ul>{preview.files.map((file, i) => <li key={i}>{file.name}: {number(file.accepted)} orders</li>)}</ul>
          {!!preview.skipped.length && <details><summary>Skipped summary sheets ({preview.skipped.length})</summary><ul>{preview.skipped.map((item, i) => <li key={i}>{item}</li>)}</ul></details>}
          <button className="primary" disabled={busy || running} onClick={() => action(async () => {
            await activate('import', preview.id); setOpen(false);
          })}>Use this import and publish reports</button>
        </section>}
        {error && <p role="alert" className="notice error">{error}</p>}
      </div>
    </Dialog>}
  </section>;
}


function StorageControls({blocked, onChanged}) {  const [data, setData] = useState(null), [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);  async function refresh() { setData(await api('/api/reporting/storage')); }  async function archive() {    setBusy(true); setError('');    try { setResult(await api('/api/reporting/archive', {method: 'POST'})); await refresh(); onChanged(); }    catch (e) { setError(e.message); } finally { setBusy(false); }  }  return <details className="storage-controls" onToggle={event => { if (event.currentTarget.open) refresh().catch(e => setError(e.message)); }}>    <summary>Storage and recovery</summary>    {data && <><p>{number(data.captures)} active captures · {number(data.imports)} report imports · {(data.database_bytes / 1048576).toFixed(1)} MB database · {(data.backup_bytes / 1048576).toFixed(1)} MB recovery archives</p><p className="field-help">{data.policy}</p></>}    <p className="field-help">Older synced history moves into a verified full-workspace archive before removal from the active list. Local archives need this Windows account. Before archiving, use Settings to export a password-encrypted backup to a second drive for recovery on another PC.</p>    {!!data?.legacy_backup_count && <><p className="field-help">{data.legacy_backup_count} older recovery archives are not encrypted.</p><button className="secondary" disabled={blocked || busy} onClick={async()=>{setBusy(true);setError('');try{const value=await api('/api/reporting/protect-backups',{method:'POST'});await refresh();if(value.failed)throw Error(`${value.failed} archives could not be protected; their originals were retained.`);}catch(e){setError(e.message);}finally{setBusy(false);}}}>Protect older backups</button></>}    <button className="secondary" disabled={blocked || busy || !data} onClick={archive}>{busy ? 'Archiving…' : 'Archive older local history'}</button>    {result && <p role="status">{result.archived_captures} captures and {result.archived_imports} imports archived. {result.backup && <><a href={`/api/reporting/archive/${encodeURIComponent(result.backup)}`} download>Download recovery archive</a><br/>{result.recovery}</>}</p>}    {error && <p role="alert" className="notice error">{error}</p>}    <CloudHistoryControls blocked={blocked || busy}/>  </details>;}function CloudHistoryControls({blocked}) {  const [plan,setPlan]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[selected,setSelected]=useState('');  async function refresh(){setPlan(await api('/api/reporting/cloud-history'));}  async function act(fn){setBusy(true);setError('');setMessage('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}  return <section aria-label="Cloud history recovery"><h4>Google Sheets history</h4><p className="field-help">Preview older generated backup tabs before archiving. Active trackers and raw preview history remain in Sheets. Avoid archiving any backup tab used by your own formulas.</p>    <button className="secondary" disabled={blocked||busy} onClick={()=>act(refresh)}>Review cloud history</button>    {plan && <><p>{number(plan.allocated_cells)} allocated cells · {number(plan.reclaimable_cells)} cells can be archived.</p><p className="field-help">{plan.policy}</p>      {!!plan.tabs.length && <><details><summary>{plan.tabs.length} backup tabs selected</summary><ul>{plan.tabs.map(tab=><li key={tab.id}>{tab.title} · {tab.created}</li>)}</ul></details><p className="field-help">The selected tabs will be removed only after their recovery archive is saved and verified. Export a password-encrypted workspace backup afterward; it includes cloud recovery archives.</p><button className="secondary" disabled={blocked||busy} onClick={()=>act(async()=>{const result=await api('/api/reporting/cloud-history',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fingerprint:plan.fingerprint})});setMessage(`${result.archived_tabs} backup tabs archived. Export a protected workspace backup to another drive.`);await refresh();})}>Archive the listed backup tabs</button></>}      {!!plan.archives.length && <div className="report-source-controls"><label>Cloud recovery archive<select value={selected} onChange={e=>setSelected(e.target.value)}><option value="">Choose an archive</option>{plan.archives.map(name=><option key={name}>{name}</option>)}</select></label><button className="secondary" disabled={blocked||busy||!selected} onClick={()=>act(async()=>{const value=await api('/api/reporting/cloud-history/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({archive:selected})});setMessage(`${value.restored_tabs} backup tabs restored. Existing tabs were preserved.`);await refresh();})}>Restore missing backup tabs</button></div>}    </>}{message&&<p role="status">{message}</p>}{error&&<p role="alert" className="notice error">{error}</p>}  </section>;}function SummaryTable({rows, columns, onSelect, selected, links = {}}) {
  return <div className="table-scroll report-summary-table" tabIndex={0} role="region" aria-label="Report summary table"><table>
    <thead><tr>{columns.map(column => <th scope="col" key={column}>{column}</th>)}</tr></thead>
    <tbody>{rows.map(row => <tr key={row.Date} className={selected === row.Date ? 'selected-report-day' : String(row.Date).endsWith('YTD') ? 'report-total' : ''}>
      {columns.map(column => <td key={column}>{column === 'Date' ? links[row.Date]
        ? <a href={links[row.Date]} target="_blank" rel="noreferrer" onClick={() => onSelect?.(row.Date)}>{row.Date}<span className="sr-only"> — open this date in Google Sheets</span></a>
        : onSelect ? <button className="text-button" onClick={() => onSelect(row.Date)}>{row.Date}</button> : row.Date
        : number(row[column])}</td>)}
    </tr>)}</tbody>
  </table>{!rows.length && <p className="table-empty">No report data for this source.</p>}</div>;
}

export function ProductionDailyReport({revision, running}) {
  const [data, setData] = useState(null), [date, setDate] = useState(''), [error, setError] = useState('');
  const [search, setSearch] = useState(''), [page, setPage] = useState(0);
  useEffect(() => { let active = true;
    api('/api/daily-orders').then(value => { if (active) { setData(value); setError(''); } }).catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [revision, running]);
  const history = data?.rows || [], day = history.find(row => row.Date === date) || history[0];
  const rows = (day?.rows || []).filter(row => !search || Object.values(row).some(value => String(value).toLowerCase().includes(search.toLowerCase())));
  const columns = day?.columns || [];
  const currentPage = Math.min(page, Math.max(0, Math.ceil(rows.length / 25) - 1));
  const select = value => { setDate(value); setPage(0); setSearch(''); };
  return <section className="production-daily-report">
    <OfflineNotice snapshot={data}/>{error && <p role="alert" className="notice error">{error}</p>}
    <div className="section-heading"><div><h2>Daily production orders</h2><p className="muted">{data?.source || 'Loading reports…'} · Orders grouped by received date</p></div>
      <label>Date<select aria-label="Daily orders date" value={day?.Date || ''} onChange={e => select(e.target.value)}>{history.map(row => <option key={row.Date}>{row.Date}</option>)}</select></label></div>
    <div className="report-metrics">{DAILY.map((name, i) => <article className="report-metric" data-tone={i} key={name}><span>{name}</span><strong>{number(day?.[name])}</strong></article>)}</div>
    <p className="field-help">Completed + Clarification + Cancelled + Vendor Pending + In-House Pending = Received. SLA counts include only completed orders with valid recorded timing.</p>
    {!!day?.['SLA Unclassified'] && <p role="status" className="notice warning">{number(day['SLA Unclassified'])} completed orders need verified timing; {number(day['Inferred Completions'])} are inferred from queue disappearance.</p>}
    <ReportChart rows={[...history].reverse().slice(-14)}/>
    <SummaryTable rows={history} columns={['Date', ...DAILY]} onSelect={select} selected={day?.Date} links={data?.sheet_links}/>
    <div className="report-detail-toolbar"><label>Find an order<input aria-label="Search daily orders" value={search} onChange={e => { setSearch(e.target.value); setPage(0); }} placeholder="Search order details"/></label>
      {data?.sheet_links?.[day?.Date] && <a className="secondary" href={data.sheet_links[day.Date]} target="_blank" rel="noreferrer"><ExternalLink size={16}/>Open this date in Sheets</a>}</div>
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Daily order details"><table><thead><tr>{columns.map(column => <th scope="col" key={column}>{column}</th>)}</tr></thead><tbody>{rows.slice(currentPage * 25, currentPage * 25 + 25).map((row, i) => <tr key={row['Order Number'] || i}>{columns.map(column => <td key={column}>{String(row[column] ?? '')}</td>)}</tr>)}</tbody></table></div>
    <div className="table-footer"><span>{number(rows.length)} orders</span><div className="inline"><button className="secondary" disabled={!currentPage} onClick={() => setPage(currentPage - 1)}>Previous</button><span>{currentPage + 1} / {Math.max(1, Math.ceil(rows.length / 25))}</span><button className="secondary" disabled={(currentPage + 1) * 25 >= rows.length} onClick={() => setPage(currentPage + 1)}>Next</button></div></div>
  </section>;
}

export function CapacityReport({revision, running, onChanged}) {
  const [data, setData] = useState(null), [error, setError] = useState(''), [date, setDate] = useState('default');
  const [capacity, setCapacity] = useState(''), [extended, setExtended] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; api('/api/reporting/capacity').then(value => { if (active) { setData(value); setError(''); } }).catch(e => { if (active) setError(e.message); }); return () => { active = false; }; }, [revision, running]);
  useEffect(() => { const row = data?.daily.find(item => item.Date === date);
    setCapacity(String(date === 'default' ? data?.preferences.default_capacity ?? '' : row?.Capacity ?? ''));
    setExtended(String(date === 'default' ? data?.preferences.default_extended ?? '' : row?.['Ext capacity'] ?? ''));
  }, [data, date]);
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('');
    try { await api('/api/reporting/capacity', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({date, capacity: capacity === '' ? null : Number(capacity), extended: extended === '' ? null : Number(extended)})}); onChanged(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <section className="capacity-report"><OfflineNotice snapshot={data}/>
    <div className="section-heading"><div><h2>Capacity Report</h2><p className="muted">{data?.source || 'Loading reports…'} · Actual orders and editable targets</p></div><button className="secondary" disabled={busy} onClick={() => { setBusy(true); downloadReports().catch(e => setError(e.message)).finally(() => setBusy(false)); }}><Download size={16}/>Download Excel</button></div>
    {error && <p role="alert" className="notice error">{error}</p>}
    <form className="capacity-targets" onSubmit={save}><label>Target applies to<select aria-label="Capacity target date" value={date} onChange={e => setDate(e.target.value)}><option value="default">Default reporting day</option>{data?.daily.map(row => <option key={row.Date}>{row.Date}</option>)}</select></label>
      <label>Capacity<input aria-label="Capacity" type="number" min="0" max="1000000" step="1" value={capacity} onChange={e => setCapacity(e.target.value)}/></label>
      <label>Extended capacity<input aria-label="Extended capacity" type="number" min="0" max="1000000" step="1" value={extended} onChange={e => setExtended(e.target.value)}/></label>
      <button className="primary" disabled={busy || running || !data || data?.preferences.publish_status === 'publishing'}>{busy ? 'Saving…' : 'Save targets and publish'}</button>
    </form>
    <p className="field-help">Targets are planning values, not measured output. Default targets apply to represented reporting days unless overridden. Monthly and calendar-year totals exclude days with no orders in this source.</p>
    <ReportChart rows={[...(data?.daily || [])].reverse().slice(-31)} capacity/>
    <h3>Monthly and year-to-date totals</h3><SummaryTable rows={[...(data?.monthly || []), ...(data?.ytd ? [data.ytd] : [])]} columns={CAPACITY}/>
    <h3>Daily capacity</h3><SummaryTable rows={data?.daily || []} columns={CAPACITY}/>
  </section>;
}
