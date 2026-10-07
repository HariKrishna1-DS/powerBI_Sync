import React from 'react';
const EMPTY = {columns: [], rows: []};
const DEFAULT_IGNORE = ['Sync Timestamp', 'Queue Age Hours', 'Time Since Arrival', 'Task Time in Queue'];
const colors = ['#147d72', '#d79a32', '#596cc0', '#bb6179', '#4b9db4', '#849157'];
const str = value => value == null ? '' : String(value);
const label = value => str(value) || '(Blank)';
const normalized = value => str(value).trim().toLowerCase();
const badgeClass = value => normalized(value).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
const isSharedReport = snapshot => snapshot?.report_preferences?.shared === true || snapshot?.source === 'Shared workspace';
const productionSource = snapshot => isSharedReport(snapshot) ? 'Shared workspace' : snapshot?.source_mode === 'import' ? 'Imported Excel reports' : 'Google Sheets production';
function captureResultMessage(result, shared) {
  const rows = Number.isInteger(result.rows) ? ` · ${result.rows.toLocaleString()} rows` : '';
  if (shared) return `${result.preview_name}${rows} · ${result.cloud_state === 'accepted' ? 'Accepted by the shared workspace; awaiting verified publication.' : 'Saved locally; shared upload pending.'}`;
  return result.action === 'sync' ? `${result.preview_name} synced${rows} · ${result.worksheets?.length || 0} Google Sheets tabs updated` : `${result.preview_name} saved locally${rows} · Google Sheets sync pending`;
}
import STATUS_COLORS from '../../status_colors.json';

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
  const timeout = AbortSignal.timeout(30000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  const response = await fetch(url, {...options, signal});
  if (!response.ok) { let body; try { body = await response.json(); } catch { body = {}; } const error = Error(body.error || `Request failed (${response.status})`); error.details = body; throw error; }
  const body = await response.json();
  if (body.clock) body.clock.receivedAt = performance.now();
  return body;
}
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function csvDownload(rows, columns, name) {
  // Spreadsheet applications execute formula-looking text even in quoted CSV cells.
  const cell = value => {const raw=str(value);return '"'+(/^[\s]*[=+@-]|^[\t\r\n]/.test(raw)?"'":'')+raw.replaceAll('"','""')+'"';};
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


export {EMPTY, DEFAULT_IGNORE, colors, str, label, normalized, badgeClass, isSharedReport, productionSource, captureResultMessage, STATUS_COLORS, statusColor, textColorForBg, api, saveBlob, csvDownload, matches, IconButton};
