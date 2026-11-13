import React, {useEffect, useState} from 'react';
import {Copy, Pencil, Plus} from 'lucide-react';
import {api} from './workspaceUtils';
import {Dialog} from './DesktopExperience';
import SlaOrderEditor, {StatusPicker} from './SlaOrderEditor';

// Keep order editing on the same preview and use the same revision checks as SLA Status.
export default function useComparisonEditing({previewId, orders, summaryStatus, onRefresh}) {
  const [report, setReport] = useState(null);
  const [entry, setEntry] = useState(null);
  const [statusEditor, setStatusEditor] = useState(null);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const reportUrl = `/api/sla-status?preview_id=${encodeURIComponent(previewId)}`;
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setEntry(null); setStatusEditor(null); setError('');
    if (previewId) api(reportUrl, {signal: controller.signal}).then(setReport).catch(err => {
      if (err.name !== 'AbortError') setError(err.message);
    });
    return () => controller.abort();
  }, [previewId]);
  const ready = report?.report_scope === 'preview' && Number(report.preview_id) === Number(previewId);
  const rows = [...(report?.rows || []), ...(report?.excluded_rows || [])];
  const findRow = order => rows.find(row => String(row['Order Number']).trim().toLowerCase() === String(order.order_number).trim().toLowerCase());
  function openOrder(order, copy = false) {
    const row = findRow(order);
    if (!ready || !row) return;
    setError(''); setEntry({row, status: row.Status, copy});
  }
  function addOrder(status) {
    if (!ready) return;
    setError(''); setEntry({status});
  }
  function editStatus(status) {
    setName(status || ''); setError('');
    setStatusEditor({status, orders: orders.filter(order => summaryStatus(order) === status)});
  }
  async function refresh() {
    setReport(await api(reportUrl));
    await onRefresh();
  }
  async function saveStatus(event) {
    event.preventDefault();
    if (saving || !name.trim()) return;
    setSaving(true); setError('');
    try {
      if (!statusEditor.status || !statusEditor.orders.length) {
        await api('/api/sla-statuses', {method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({preview_id: Number(previewId), status: name.trim(), ...(statusEditor.status ? {previous: statusEditor.status} : {})})});
      } else {
        // These rows are grouped by production status, not by their queue status.
        for (const order of statusEditor.orders) {
          await api('/api/sla-compare/update-status', {method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({order_number: order.order_number, prod_status: name.trim()})});
        }
      }
      await refresh(); setStatusEditor(null);
    } catch (err) {
      setError(err.message);
      // A group can be partially saved; show the persisted result and allow a retry.
      await onRefresh().catch(() => {});
    } finally { setSaving(false); }
  }
  function statusActions(status) {
    return <span className="inline compare-status-actions">
      <button type="button" className="icon-button" aria-label={`Add order to status ${status}`} title="Add SLA order" disabled={!ready || saving} onClick={() => addOrder(status)}><Plus size={15}/></button>
      <button type="button" className="icon-button" aria-label={`Edit status ${status}`} title="Edit comparison status name" disabled={!ready || saving} onClick={() => editStatus(status)}><Pencil size={15}/></button>
    </span>;
  }
  function rowActions(order) {
    const editable = ready && !!findRow(order);
    return <div className="inline">
      <button type="button" className="icon-button" aria-label={`Edit details ${order.order_number}`} title={editable ? 'Edit SLA order details' : 'Order is not in the selected SLA preview'} disabled={!editable} onClick={() => openOrder(order)}><Pencil size={15}/></button>
      <button type="button" className="icon-button" aria-label={`Copy order ${order.order_number}`} title="Copy into a new SLA order" disabled={!editable} onClick={() => openOrder(order, true)}><Copy size={15}/></button>
    </div>;
  }
  const addStatusButton = <button type="button" className="icon-button" aria-label="Add manual SLA status" title="Add status" disabled={!ready || saving} onClick={() => editStatus(null)}><Plus size={16}/></button>;
  const dialogs = <>
    {error && !statusEditor && <p role="alert" className="notice warning">{error}</p>}
    {statusEditor && <Dialog className="sla-status-name-dialog" title={statusEditor.status ? 'Edit comparison status name' : 'Add SLA status'} onClose={() => {if (!saving) setStatusEditor(null);}}>
      <form className="dialog-content" onSubmit={saveStatus}>
        <p className="muted">{statusEditor.orders.length ? `Update the production status for ${statusEditor.orders.length} orders in ${statusEditor.status}. Their SLA queue statuses remain available for comparison.` : `Add or rename a status in ${report?.preview_name || 'the selected preview'}. Use + beside its name to add orders.`}</p>
        <StatusPicker label="Status name" inputLabel="Comparison status name" value={name} onChange={setName} disabled={saving} autoFocus options={[...new Set([statusEditor.status,...(report?.summary || []).map(row=>row.Status),...(report?.custom_statuses || []),...rows.map(row=>row.Status),...orders.flatMap(order=>[summaryStatus(order),order.sla_status,order.prod_status]),'Typing in Progress'])].filter(Boolean)}/>
        {error && <p role="alert" className="notice warning">{error}</p>}
        <div className="inline"><button type="submit" className="primary" disabled={saving || !name.trim()}>{saving ? 'Saving…' : 'Save status'}</button><button type="button" className="secondary" disabled={saving} onClick={() => setStatusEditor(null)}>Cancel</button></div>
      </form>
    </Dialog>}
    {entry && ready && <SlaOrderEditor report={report} entry={entry} onClose={() => setEntry(null)} onSaved={async () => {await refresh(); setEntry(null);}}/>}
  </>;
  return {ready, saving, openAddStatus: () => editStatus(null), openOrder, addOrder, rowActions, statusActions, addStatusButton, dialogs, customStatuses: report?.custom_statuses || []};
}
