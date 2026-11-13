import {NEW_ORDER_COLUMNS, newOrderRecord, newOrdersTsv, plainComment} from './newOrderReport';
import {LoadingScreen, useActivity} from './LoadingExperience';
import React, {useState, useEffect, useMemo, useRef} from 'react';
import {
  ArrowLeftRight,
  ArrowDownToLine,
  Upload,
  RefreshCw,
  Search,
  CheckCircle2,
  Clock,
  FileSpreadsheet,
  Filter,
  X,
  FileCheck2,
  Sparkles,
  ChevronDown,
  ChevronUp,
  TableProperties,
  Layers,
  Pencil,
  Check,
  Plus
} from 'lucide-react';
import {api} from './workspaceUtils';
import {ColumnFilterButton, useColumnFilters} from './ColumnFilters';
import {Dialog} from './DesktopExperience';
import useComparisonEditing from './useComparisonEditing';

const STANDARD_PROD_STATUSES = [
  'Assign to ABS',
  'Attorney Approval',
  'Awaiting for Clarification',
  'Cancelled',
  'Completed and Delivered',
  'Home Builders',
  'Need To Add Subscription',
  'QC in Progress',
  'Responded',
  'Search In Progress',
  'SearchFix',
  'Site Down',
  'Typing in Progress',
  'Waiting for Effective Date'
];

const comparisonCategories = ['Future SLA', 'Negative SLA', 'Today SLA'];

function comparisonSummaryStatus(order) {
  if (order.match_type === 'prod_only') return null;
  if (String(order.sla_status).trim().toLowerCase() === 'home builders') return 'Home Builders';
  return ['status_moved', 'same_status'].includes(order.match_type) ? order.prod_status || '(Blank)' : null;
}

function recomputeSlaComparison(orders) {
  const summaryByStatus = {};
  let matchedCount = 0;
  let movedCount = 0;
  let sameCount = 0;
  let slaOnlyCount = 0;
  let prodOnlyCount = 0;
  const transitionMap = {};

  orders.forEach(o => {
    const mtype = o.match_type;
    if (mtype === 'status_moved' || mtype === 'same_status') {
      matchedCount++;
      if (mtype === 'status_moved') {
        movedCount++;
        const transKey = `${o.sla_status}➔${o.prod_status}`;
        if (!transitionMap[transKey]) {
          transitionMap[transKey] = {
            from_status: o.sla_status,
            to_status: o.prod_status,
            count: 0,
            label: `${o.sla_status} ➔ ${o.prod_status}`
          };
        }
        transitionMap[transKey].count++;
      } else {
        sameCount++;
      }

    } else if (mtype === 'sla_only') {
      slaOnlyCount++;
    } else if (mtype === 'prod_only') {
      prodOnlyCount++;
    }

    const st = comparisonSummaryStatus(o);
    if (st !== null) {
      if (!summaryByStatus[st]) {
        summaryByStatus[st] = {
          Status: st,
          'Future SLA': 0,
          'Negative SLA': 0,
          'Today SLA': 0,
          'Unknown SLA': 0,
          'Not in SLA Queue': 0,
          'Grand Total': 0
        };
      }
      const cat = mtype === 'prod_only' ? 'Not in SLA Queue' : o.sla_category;
      if (summaryByStatus[st][cat] !== undefined) {
        summaryByStatus[st][cat]++;
      } else {
        summaryByStatus[st]['Unknown SLA']++;
      }
      summaryByStatus[st]['Grand Total']++;
    }
  });

  const rows = Object.values(summaryByStatus).sort((a, b) =>
    String(a.Status).localeCompare(String(b.Status), undefined, { sensitivity: 'base' })
  );

  const totals = {
    Status: 'Grand Total',
    'Future SLA': rows.reduce((s, r) => s + (r['Future SLA'] || 0), 0),
    'Negative SLA': rows.reduce((s, r) => s + (r['Negative SLA'] || 0), 0),
    'Today SLA': rows.reduce((s, r) => s + (r['Today SLA'] || 0), 0),
    'Unknown SLA': rows.reduce((s, r) => s + (r['Unknown SLA'] || 0), 0),
    'Not in SLA Queue': rows.reduce((s, r) => s + (r['Not in SLA Queue'] || 0), 0),
    'Grand Total': rows.reduce((s, r) => s + (r['Grand Total'] || 0), 0)
  };

  const transitions = Object.values(transitionMap).sort((a, b) => {
    const fromComp = a.from_status.localeCompare(b.from_status, undefined, { sensitivity: 'base' });
    if (fromComp !== 0) return fromComp;
    return a.to_status.localeCompare(b.to_status, undefined, { sensitivity: 'base' });
  });

  return {
    sla_summary: {
      columns: ['Status', ...comparisonCategories, ...(totals['Unknown SLA']?['Unknown SLA']:[]), 'Grand Total'],
      rows,
      totals
    },
    transitions,
    metrics: {
      matched: matchedCount,
      status_moved: movedCount,
      same_status: sameCount,
      sla_only: slaOnlyCount,
      prod_only: prodOnlyCount
    }
  };
}

const FILTER_COLUMNS = [
  'Order Number',
  'Product',
  'State',
  'County',
  'Client',
  'SLA Status',
  'SLA Category',
  'ETA Comments',
  'Movement / Difference',
  'Production Status',
  'SLA Status Expiration',
  'Out Time',
  'Worker'
];

export default function SlaCompare({state, reportMode}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedPreview, setSelectedPreview] = useState('');
  const [filterType, setFilterType] = useState('matched'); // Default to showing Matched in Both (Card 1)
  const [selectedTransition, setSelectedTransition] = useState(null);
  const [selectedSlaStatus, setSelectedSlaStatus] = useState(null);
  const [matrixFilter, setMatrixFilter] = useState(null);
  const [showSummaryTable, setShowSummaryTable] = useState(true);
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  useActivity(loading||uploading, uploading?'Processing production reports…':'Loading comparison…');
  const [draggingFiles, setDraggingFiles] = useState(false);
  const uploadInProgress = useRef(false);
  const dragDepth = useRef(0);
  const [message, setMessage] = useState('');
  const [popModal, setPopModal] = useState(null);
  const [popSearch, setPopSearch] = useState('');
  const [clearOpen, setClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [editingOrderNumber, setEditingOrderNumber] = useState(null);
  const [editStatusValue, setEditStatusValue] = useState('');
  const [isCustomStatus, setIsCustomStatus] = useState(false);
  const [customStatusInput, setCustomStatusInput] = useState('');
  const [customStatuses, setCustomStatuses] = useState([]);
  const [savingStatus, setSavingStatus] = useState(false);
  const [editingExpiration, setEditingExpiration] = useState(null);
  const [expirationValue, setExpirationValue] = useState('');
  const [expirationError, setExpirationError] = useState('');
  const [savingExpiration, setSavingExpiration] = useState(false);
  const fileInputRef = useRef(null);
  const ordersTableRef = useRef(null);
  const reportStartRef = useRef(null);
  const initialPositioned = useRef(false);
  const comparisonEditing = useComparisonEditing({
    previewId: data?.selected_preview_id,
    orders: data?.orders || [],
    summaryStatus: comparisonSummaryStatus,
    onRefresh: async () => {
      const updated = await api(`/api/sla-compare?preview_id=${encodeURIComponent(data.selected_preview_id)}`);
      setData(updated);
      setPopModal(null);
    }
  });
  useEffect(() => { initialPositioned.current = false; }, [reportMode]);
  useEffect(() => {
    if (loading || !data?.has_production || initialPositioned.current) return;
    const frame = requestAnimationFrame(() => {
      const target = reportStartRef.current;
      if (!target) return;
      const main = target.closest('main');
      if (main) {
        const headerHeight = main.querySelector('.topbar')?.getBoundingClientRect().height || 0;
        const top = main.scrollTop + target.getBoundingClientRect().top - main.getBoundingClientRect().top - headerHeight - 20;
        main.scrollTo({top: Math.max(0, top), behavior: 'instant'});
      } else target.scrollIntoView({block: 'start', behavior: 'instant'});
      initialPositioned.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, [loading, data, reportMode]);

  function startExpirationEdit(order) {
    setEditingExpiration(order.order_number);
    setExpirationValue(/^\d{4}-\d{2}-\d{2}[T ]/.test(order.sla_expiration || '')
      ? order.sla_expiration.replace(' ', 'T').slice(0, 16) : '');
    setExpirationError('');
  }

  async function saveExpiration(order) {
    if (!expirationValue || savingExpiration) return;
    setSavingExpiration(true);
    setExpirationError('');
    try {
      const response = await api('/api/sla-compare/expiration', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({preview_id: Number(data.selected_preview_id), order_number: order.order_number,
          expiration: expirationValue, expected_revision: order.sla_revision}),
      });
      setData(response.result);
      setPopModal(previous => previous ? {...previous, orders: previous.orders.map(item =>
        response.result.orders.find(updated => updated.order_number === item.order_number) || item)} : previous);
      setEditingExpiration(null);
    } catch (error) {
      setExpirationError(error.message || 'Could not save the SLA expiration.');
    } finally {
      setSavingExpiration(false);
    }
  }

  function renderExpirationCell(order) {
    if (editingExpiration === order.order_number) return <div className="sla-expiration-editor">
      <div className="inline">
        <input type="datetime-local" aria-label={`SLA expiration for ${order.order_number}`} value={expirationValue}
          disabled={savingExpiration} onChange={event => setExpirationValue(event.target.value)}
          onKeyDown={event => {if (event.key === 'Enter') {event.preventDefault();saveExpiration(order);}
            if (event.key === 'Escape') {event.stopPropagation();setEditingExpiration(null);}}} autoFocus/>
        <button type="button" className="icon-button" aria-label={`Save SLA expiration for ${order.order_number}`}
          disabled={savingExpiration || !expirationValue} onClick={() => saveExpiration(order)}><Check size={14}/></button>
        <button type="button" className="icon-button" aria-label="Cancel SLA expiration edit" disabled={savingExpiration}
          onClick={() => setEditingExpiration(null)}><X size={14}/></button>
      </div>
      {expirationError && <p className="notice warning" role="alert">{expirationError}</p>}
    </div>;
    const shown = /^\d{4}-\d{2}-\d{2}[T ]/.test(order.sla_expiration || '')
      ? order.sla_expiration.replace('T', ' ').slice(0, 16) : order.sla_expiration || '—';
    return <span className="inline sla-expiration-display"><span className="timestamp-text">{shown}</span>
      {order.match_type !== 'prod_only' && <button type="button" className="icon-button edit-pencil-btn"
        aria-label={`Edit SLA expiration for ${order.order_number}`} title="Edit SLA expiration date and time"
        disabled={savingExpiration} onClick={() => startExpirationEdit(order)}><Pencil size={12}/></button>}
    </span>;
  }

  const availableStatuses = useMemo(() => {
    const set = new Set(STANDARD_PROD_STATUSES);
    if (data?.orders) {
      data.orders.forEach(o => {
        if (o.prod_status && o.prod_status !== 'Not in Production Report' && o.prod_status !== '(Blank)') {
          set.add(o.prod_status);
        }
        if (o.sla_status && o.sla_status !== 'Not in SLA Queue' && o.sla_status !== '(Blank)') {
          set.add(o.sla_status);
        }
      });
    }
    customStatuses.forEach(s => {
      if (s && s.trim()) set.add(s.trim());
    });
    return Array.from(set).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base' })
    );
  }, [data, customStatuses]);

  const startEditStatus = (order) => {
    setEditingOrderNumber(order.order_number);
    setEditStatusValue(order.prod_status || '');
    setIsCustomStatus(false);
    setCustomStatusInput('');
  };

  const cancelEditStatus = () => {
    setEditingOrderNumber(null);
    setEditStatusValue('');
    setIsCustomStatus(false);
    setCustomStatusInput('');
  };

  const handleSaveStatus = async (order, targetStatus) => {
    const cleanStatus = (targetStatus || '').trim();
    if (!cleanStatus) return;

    setSavingStatus(true);
    try {
      if (!availableStatuses.includes(cleanStatus)) {
        setCustomStatuses(prev => [...prev, cleanStatus]);
      }

      // 1. Update data.orders locally for instant UI update
      const updatedOrders = (data?.orders || []).map(item => {
        if (item.order_number === order.order_number) {
          const slaSt = (item.sla_status || '').trim();
          const isMoved = slaSt && slaSt !== '(Blank)' && cleanStatus &&
            slaSt.toLowerCase() !== cleanStatus.toLowerCase() &&
            cleanStatus !== 'Not in Production Report';
          return {
            ...item,
            prod_status: cleanStatus,
            status_changed: isMoved,
            match_type: item.match_type === 'prod_only' ? 'prod_only' : isMoved ? 'status_moved' : 'same_status',
            change_label: isMoved ? `${slaSt} ➔ ${cleanStatus}` : 'Unchanged',
          };
        }
        return item;
      });

      // 2. Recompute Summary Matrix, metrics and transitions
      const recomputed = recomputeSlaComparison(updatedOrders);

      setData(prev => ({
        ...prev,
        orders: updatedOrders,
        sla_summary: recomputed.sla_summary,
        metrics: {
          ...prev.metrics,
          ...recomputed.metrics
        },
        transitions: recomputed.transitions
      }));

      // 3. Update popModal orders as well
      if (popModal && popModal.orders) {
        setPopModal(prevModal => ({
          ...prevModal,
          orders: (prevModal?.orders || []).map(item => {
            if (item.order_number === order.order_number) {
              const slaSt = (item.sla_status || '').trim();
              const isMoved = slaSt && slaSt !== '(Blank)' && cleanStatus &&
                slaSt.toLowerCase() !== cleanStatus.toLowerCase() &&
                cleanStatus !== 'Not in Production Report';
              return {
                ...item,
                prod_status: cleanStatus,
                status_changed: isMoved,
                match_type: item.match_type === 'prod_only' ? 'prod_only' : isMoved ? 'status_moved' : 'same_status',
                change_label: isMoved ? `${slaSt} ➔ ${cleanStatus}` : 'Unchanged',
              };
            }
            return item;
          })
        }));
      }

      cancelEditStatus();

      // 4. Save to backend endpoint
      await api('/api/sla-compare/update-status', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          order_number: order.order_number,
          prod_status: cleanStatus
        })
      });
    } catch (err) {
      console.error('Error saving status update:', err);
    } finally {
      setSavingStatus(false);
    }
  };

  const renderProdStatusCell = (order) => {
    if (order.match_type === 'sla_only' && order.sla_status === 'Home Builders') {
      return <span className="status-pill">Home Builders</span>;
    }
    const isEditing = editingOrderNumber === order.order_number;
    if (isEditing) {
      return (
        <div className="status-edit-container">
          {!isCustomStatus ? (
            <div className="inline" style={{gap: 4, alignItems: 'center'}}>
              <select
                className="status-edit-select" aria-label={`Production status for ${order.order_number}`} title={editStatusValue} disabled={savingStatus}
                value={editStatusValue}
                autoFocus
                onChange={(e) => {
                  if (e.target.value === '__ADD_NEW__') {
                    setIsCustomStatus(true);
                    setCustomStatusInput('');
                  } else {
                    setEditStatusValue(e.target.value);
                  }
                }}
              >
                <option value="" disabled>-- Select Status --</option>
                {availableStatuses.map(st => (
                  <option key={st} value={st}>{st}</option>
                ))}
                <option value="__ADD_NEW__">➕ Add New Status...</option>
              </select>
              <button
                type="button"
                className="icon-button save-status-btn"
                onClick={() => handleSaveStatus(order, editStatusValue)}
                disabled={savingStatus || !editStatusValue}
                title="Save Status"
              >
                <Check size={14} color="#16a34a" />
              </button>
              <button
                type="button"
                className="icon-button cancel-status-btn"
                onClick={cancelEditStatus}
                disabled={savingStatus}
                title="Cancel"
              >
                <X size={14} color="#dc2626" />
              </button>
            </div>
          ) : (
            <div className="inline" style={{gap: 4, alignItems: 'center'}}>
              <input
                type="text"
                className="status-edit-input"
                placeholder="Enter new status…"
                value={customStatusInput}
                autoFocus
                onChange={(e) => setCustomStatusInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveStatus(order, customStatusInput);
                  if (e.key === 'Escape') setIsCustomStatus(false);
                }}
              />
              <button
                type="button"
                className="icon-button save-status-btn"
                onClick={() => handleSaveStatus(order, customStatusInput)}
                disabled={savingStatus || !customStatusInput.trim()}
                title="Save New Status"
              >
                <Check size={14} color="#16a34a" />
              </button>
              <button
                type="button"
                className="icon-button cancel-status-btn"
                onClick={() => setIsCustomStatus(false)}
                disabled={savingStatus}
                title="Back to dropdown"
              >
                <X size={14} color="#dc2626" />
              </button>
            </div>
          )}
        </div>
      );
    }

    if (order.prod_status && order.prod_status !== 'Not in Production Report') {
      return (
        <div className="status-display-container inline" style={{gap: 6, alignItems: 'center'}}>
          <span className={`status-pill pill-${cleanStatusClass(order.prod_status)} ${order.match_type === 'status_moved' ? 'status-promoted' : ''}`}>
            {order.prod_status}
          </span>
          <button
            type="button"
            className="icon-button edit-pencil-btn"
            onClick={() => startEditStatus(order)}
            title="Edit Production Status"
            aria-label={`Edit Production Status for ${order.order_number}`}
          >
            <Pencil size={12} />
          </button>
        </div>
      );
    }

    return <span className="muted-dash">Not in Production Report</span>;
  };

  const scrollToOrders = () => {
    setTimeout(() => {
      ordersTableRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 60);
  };

  const handleKpiClick = (type) => {
    setMatrixFilter(null);
    setFilterType(type);
    setSelectedTransition(null);
    setSelectedSlaStatus(null);
    scrollToOrders();
  };

  const loadComparison = async (previewId = selectedPreview, useSample = false) => {
    setMatrixFilter(null);
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const params = new URLSearchParams();
      if (previewId) params.append('preview_id', previewId);
      if (useSample) params.append('sample', '1');
      const res = await api(`/api/sla-compare?${params.toString()}`);
      setData(res);
      if (res.selected_preview_id && !selectedPreview) {
        setSelectedPreview(String(res.selected_preview_id));
      }
      if (useSample) {
        setMessage('Loaded sample production report successfully.');
      }
    } catch (err) {
      setError(err.message || 'Failed to load SLA comparison');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadComparison();
  }, [selectedPreview, reportMode, state?.report_workspace?.data_revision]);

  const uploadFiles = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length || loading || uploadInProgress.current) return;
    if (files.some(file => !/\.(xlsx|xlsm|csv)$/i.test(file.name))) {
      setError('Choose Excel (.xlsx, .xlsm) or CSV (.csv) production reports.');
      setMessage('');
      return;
    }

    uploadInProgress.current = true;
    setUploading(true);
    setError('');
    setMessage('');

    const formData = new FormData();
    if (selectedPreview) formData.append('preview_id', selectedPreview);
    for (let i = 0; i < files.length; i++) {
      formData.append('files', files[i]);
    }

    try {
      const res = await fetch('/api/sla-compare', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.error || `Upload failed with HTTP ${res.status}`);
      }
      const json = await res.json();
      setData(json);
      setMessage(`Successfully compared with ${files.length} uploaded production file(s).`);
      setFilterType('status_moved');
      setSelectedSlaStatus(null);
      setSelectedTransition(null);
    } catch (err) {
      setError(err.message || 'Failed to upload production report');
    } finally {
      uploadInProgress.current = false;
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleFileUpload = (event) => {
    uploadFiles(event.target.files);
    event.target.value = '';
  };

  const handleDragEnter = (event) => {
    if (!Array.from(event.dataTransfer.types).includes('Files')) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDraggingFiles(true);
  };

  const handleDragLeave = (event) => {
    event.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (!dragDepth.current) setDraggingFiles(false);
  };

  const handleDrop = (event) => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current = 0;
    setDraggingFiles(false);
    uploadFiles(event.dataTransfer.files);
  };

  // 1. High-level filtering (tabs, transition pills, status card clicks, search text)
  const baseFilteredOrders = useMemo(() => {
    if (!data || !data.orders) return [];

    let list = data.orders;
    // The toolbar search looks across the full comparison, independently of
    // whichever KPI, matrix group, or status movement was previously selected.
    if (search.trim()) {
      const query = search.trim().toLowerCase();
      return list.filter(order => ['order_number', 'sla_status', 'prod_status', 'client',
        'county', 'state', 'product', 'searcher', 'typer'].some(field =>
        String(order[field] ?? '').toLowerCase().includes(query)));
    }
    if (matrixFilter) {
      list = list.filter(o => comparisonSummaryStatus(o) !== null && (!matrixFilter.status || comparisonSummaryStatus(o) === matrixFilter.status)
        && (!matrixFilter.category || o.sla_category === matrixFilter.category));
    }

    // Filter by match type
    if (filterType === 'status_moved') {
      list = list.filter(o => o.match_type === 'status_moved');
    } else if (filterType === 'matched') {
      list = list.filter(o => o.match_type === 'status_moved' || o.match_type === 'same_status');
    } else if (filterType === 'same_status') {
      list = list.filter(o => o.match_type === 'same_status');
    } else if (filterType === 'sla_only') {
      list = list.filter(o => o.match_type === 'sla_only');
    } else if (filterType === 'prod_only') {
      list = list.filter(o => o.match_type === 'prod_only');
    }

    // Filter by SLA Status if selected from the Summary Table
    if (selectedSlaStatus) {
      list = list.filter(o => o.sla_status === selectedSlaStatus);
    }

    // Filter by transition pill if selected
    if (selectedTransition) {
      list = list.filter(o => o.sla_status === selectedTransition.from_status && o.prod_status === selectedTransition.to_status);
    }

    return list;
  }, [data, filterType, selectedSlaStatus, selectedTransition, search, matrixFilter]);

  // 2. Prepare structured records for Excel-like column filtering
  const tableRecords = useMemo(() => {
    return baseFilteredOrders.map((o, idx) => ({
      ...newOrderRecord(o),
      _raw: o,
      _idx: idx,
      'Order Number': o.order_number,
      'Product': o.product,
      'State': o.state,
      'County': o.county,
      'Client': o.client,
      'SLA Status': o.sla_status,
      'SLA Category': o.sla_category,
      'ETA Comments': plainComment(o.eta_comments||''),
      'Movement / Difference': o.change_label,
      'Production Status': o.prod_status,
      'SLA Status Expiration': o.sla_expiration,
      'Out Time': o.out_time,
      'Worker': [o.searcher, o.typer].filter(Boolean).join(' / ')
    }));
  }, [baseFilteredOrders]);

  // 3. Attach Excel-style column filter controls
  const newOrderMode=filterType==='sla_only'&&!search.trim()&&!matrixFilter;
  const columnFilterControls = useColumnFilters(tableRecords, newOrderMode?NEW_ORDER_COLUMNS:FILTER_COLUMNS);
  const activeColFilterCount = Object.keys(columnFilterControls.filters).length;
  async function copyNewOrders() {
    const rows = columnFilterControls.rows.map(record => record._raw).filter(order => order.match_type === 'sla_only');
    const text = newOrdersTsv(rows);
    try {
      await navigator.clipboard.writeText(text);
      setMessage(`${rows.length} new orders copied for Excel: 25 production-report columns, from No through review. Paste into the No column; row numbers are left blank.`);
    } catch {
      setError('Unable to copy. Allow clipboard access and try Copy New Orders for Excel again.');
    }
  }
  const isSearching = Boolean(search.trim());

  const metrics = data?.metrics || {};
  const slaSummary = data?.sla_summary || {rows: [], totals: {}};
  const summaryRows = [...slaSummary.rows, ...comparisonEditing.customStatuses
    .filter(status => !slaSummary.rows.some(row => row.Status === status))
    .map(Status => ({Status, 'Grand Total': 0}))];
  const visibleComparisonCategories = [...comparisonCategories, ...(slaSummary.totals?.['Unknown SLA']?['Unknown SLA']:[])];

  // Helper to open Pop Table modal for matrix cells (based on Production Report status)
  const openMatrixPop = (status, category) => {
    if (!data || !data.orders) return;
    // Include every counted SLA Status order, even when absent from production.
    const matched = data.orders.filter(o => comparisonSummaryStatus(o) !== null);
    let subset = matched;
    if (status && status !== 'Grand Total') {
      subset = subset.filter(o => comparisonSummaryStatus(o) === status);
    }
    if (category && category !== 'Grand Total') {
      subset = subset.filter(o => (o.sla_category) === category);
    }
    const labelParts = [];
    if (status && status !== 'Grand Total') labelParts.push(status);
    else labelParts.push('All Production Statuses');

    if (category && category !== 'Grand Total') labelParts.push(category);
    else labelParts.push('All SLA Categories');

    setPopSearch('');
    setPopModal({
      title: `${labelParts.join(' · ')} (${subset.length.toLocaleString()} orders)`,
      summary_status: status === 'Grand Total' ? null : status,
      category: category === 'Grand Total' ? null : category,
      scope: 'matrix',
      orders: subset
    });
  };

  // Helper to open Pop Table modal for movements
  const openMovementPop = (transition) => {
    if (!data || !data.orders) return;
    const subset = data.orders.filter(o => o.sla_status === transition.from_status && o.prod_status === transition.to_status);
    setPopSearch('');
    setPopModal({
      title: `${transition.from_status} ➔ ${transition.to_status} (${subset.length.toLocaleString()} moved orders)`,
      from_status: transition.from_status,
      to_status: transition.to_status,
      scope: 'movement',
      orders: subset
    });
  };

  // Filtered orders inside the Pop Table modal
  const popModalOrders = useMemo(() => {
    if (!popModal || !popModal.orders) return [];
    if (!popSearch.trim()) return popModal.orders;
    const q = popSearch.trim().toLowerCase();
    return popModal.orders.filter(o =>
      (o.order_number && o.order_number.toLowerCase().includes(q)) ||
      (o.sla_status && o.sla_status.toLowerCase().includes(q)) ||
      (o.prod_status && o.prod_status.toLowerCase().includes(q)) ||
      (o.client && o.client.toLowerCase().includes(q)) ||
      (o.county && o.county.toLowerCase().includes(q)) ||
      (o.product && o.product.toLowerCase().includes(q)) ||
      (o.searcher && o.searcher.toLowerCase().includes(q)) ||
      (o.typer && o.typer.toLowerCase().includes(q))
    );
  }, [popModal, popSearch]);

  return (
    <section className={`sla-compare-workspace${isSearching ? ' is-searching' : ''}`} aria-label="SLA Compare Workspace"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = uploading || loading ? 'none' : 'copy';
      }}
      onDrop={handleDrop}
    >
      {/* Top Header & Actions */}
      <div className="section-heading compare-page-header">
        <div>
          <span className="compare-eyebrow">SLA WORKSPACE</span>
          <h2>Compare queue &amp; production</h2>
          <p className="muted" title={`Production report: ${data?.source_files || 'None'}`}>
            {data?.preview_name || 'SLA queue'} · {data?.has_production?`${metrics.matched?.toLocaleString() || 0} matched orders`:'Upload a report to get started'}
          </p>
        </div>
        <div className="inline">
          <input
            type="file"
            ref={fileInputRef}
            style={{display: 'none'}}
            multiple
            accept=".xlsx,.xlsm,.csv"
            onChange={handleFileUpload}
          />
          {data?.has_production && (
            <button
              type="button"
              className="secondary"
              disabled={loading || uploading || clearing}
              onClick={() => setClearOpen(true)}
              title="Clear the uploaded Production Report"
            >
              <X size={15} />
              Clear Report
            </button>
          )}
          <a
            className="secondary button-link"
            href="/api/sla-compare/export"
            download
            aria-disabled={loading || uploading || !data?.has_production}
            onClick={event=>{if(loading||uploading||!data?.has_production)event.preventDefault();}}
            title="Export full comparison to styled Excel workbook"
          >
            <ArrowDownToLine size={16} />
            Download Excel
          </a>
        </div>
      </div>

      {/* Preview Selector Toolbar */}
      <div className="sla-compare-toolbar compare-source-toolbar">
        <label className="sla-preview-picker">
          <span className="compare-control-label"><Layers size={15}/>SLA Queue Preview</span>
          <select
            aria-label="Select SLA Queue Preview"
            value={selectedPreview}
            disabled={loading || uploading}
            onChange={(e) => setSelectedPreview(e.target.value)}
          >
            {!data?.previews?.length&&<option value="">{loading?'Loading previews…':'No saved queue previews'}</option>}
            {data?.previews?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.row_count.toLocaleString()} rows · {new Date(p.created).toLocaleString('en-IN', {timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true})} IST
                {p.id === data.previews[0]?.id ? ' (Latest)' : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="search-input">
          <Search size={15} />
          <input
            type="text"
            aria-label="Search comparison orders"
            placeholder="Search order number, client, county, status…"
            value={search}
            onChange={(event) => {setSearch(event.target.value);columnFilterControls.clear();}}
          />
          {search && (
            <button type="button" className="icon-button" aria-label="Clear comparison search" onClick={() => setSearch('')}>
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {isSearching && <p className="comparison-search-status" role="status">
        Search results: {columnFilterControls.rows.length.toLocaleString()} matching order{columnFilterControls.rows.length === 1 ? '' : 's'} across the comparison.
      </p>}

      {/* Notices */}
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice warning" role="alert">{error}</p>}
      {data?.source_warning && <p className="notice warning" role="status">{data.source_warning}</p>}

      {(draggingFiles || uploading || loading) && <p role="status" className="compare-upload-hint">{uploading?'Processing production reports…':loading?'Loading comparison…':'Drop production reports here to compare'}</p>}

      {loading&&!data?<LoadingScreen title="Loading comparison…"/>:!data?.has_production ? (
        <div className={`sla-compare-empty-state compare-onboarding${draggingFiles?' is-dragging':''}`}>
          <div className="compare-upload-card">
            <span className="compare-upload-icon"><Upload size={28}/></span>
            <span className="compare-eyebrow">START A COMPARISON</span>
            <h2>No Production Report Uploaded</h2>
            <p>Drop your production report here to see how every order compares with your SLA queue.</p>
            <button type="button" className="primary" onClick={()=>fileInputRef.current?.click()} disabled={uploading||loading}>
              <Upload size={17}/>{uploading?'Processing File…':'Upload Production Report (Excel)'}
            </button>
            <div className="compare-file-types" aria-label="Supported report formats"><span>XLSX</span><span>XLSM</span><span>CSV</span><small>Multiple files supported</small></div>
            <span className="compare-required-columns">Include <strong>Order Number</strong> and <strong>Status</strong> columns.</span>
          </div>

        </div>
      ) : (
        <>
          {/* Summary KPI Cards in Ordered Sequence (1: Matched in Both, 2: Identical, 3: Moved, 4: New Orders) */}
          <div className="compare-kpis" ref={reportStartRef}>
            {/* Card 1: Matched in Both */}
            <button
              type="button"
              className={`compare-kpi matched ${filterType === 'matched' && !selectedSlaStatus ? 'active' : ''}`}
              onClick={() => handleKpiClick('matched')}
              title="Filter table to all matched orders in both reports and scroll down"
            >
              <div className="kpi-icon"><FileCheck2 size={20} /></div>
              <div className="kpi-info">
                <span className="kpi-label">Matched in Both</span>
                <strong className="kpi-val">{metrics.matched?.toLocaleString() || 0}</strong>
              </div>
              <span className="kpi-tag">{metrics.total_sla ? `${Math.round((metrics.matched / metrics.total_sla) * 100)}% of queue` : ''}</span>
            </button>

            {/* Card 2: Identical Status */}
            <button
              type="button"
              className={`compare-kpi same ${filterType === 'same_status' && !selectedSlaStatus ? 'active' : ''}`}
              onClick={() => handleKpiClick('same_status')}
              title="Filter table to orders with identical status and scroll down"
            >
              <div className="kpi-icon"><CheckCircle2 size={20} /></div>
              <div className="kpi-info">
                <span className="kpi-label">Identical Status</span>
                <strong className="kpi-val">{metrics.same_status?.toLocaleString() || 0}</strong>
              </div>
              <span className="kpi-tag">Unchanged</span>
            </button>

            {/* Card 3: Status Moved / Changed */}
            <button
              type="button"
              className={`compare-kpi moved ${filterType === 'status_moved' && !selectedSlaStatus ? 'active' : ''}`}
              onClick={() => handleKpiClick('status_moved')}
              title="Filter table to orders with moved/changed status and scroll down"
            >
              <div className="kpi-icon"><ArrowLeftRight size={20} /></div>
              <div className="kpi-info">
                <span className="kpi-label">Status Moved / Changed</span>
                <strong className="kpi-val highlight">{metrics.status_moved?.toLocaleString() || 0}</strong>
              </div>
              <span className="kpi-tag">Highlighted Diffs</span>
            </button>

            {/* Card 4: New Orders */}
            <button
              type="button"
              className={`compare-kpi sla-only ${filterType === 'sla_only' && !selectedSlaStatus ? 'active' : ''}`}
              onClick={() => handleKpiClick('sla_only')}
              title="Filter table to new orders present only in SLA queue and scroll down"
            >
              <div className="kpi-icon"><Clock size={20} /></div>
              <div className="kpi-info">
                <span className="kpi-label">New Orders</span>
                <strong className="kpi-val">{metrics.sla_only?.toLocaleString() || 0}</strong>
              </div>
              <span className="kpi-tag">In SLA / Not in Prod</span>
            </button>
          </div>

      {/* SLA STATUS SUMMARY TABLE (Based on Production Report) */}
      <div className="sla-summary-section">
        <div className="section-subheading">
          <div className="subheading-left">
            <TableProperties size={18} />
            <h3>SLA Status Summary Matrix</h3>
            <span className="subheading-tag">Grouped by Production Status for the selected SLA Status preview.</span>
          </div>
          <div className="subheading-right inline">
            <button type="button" className="primary compare-add-status" disabled={!comparisonEditing.ready || comparisonEditing.saving} onClick={comparisonEditing.openAddStatus}>
              <Plus size={17} />Add status
            </button>
            {selectedSlaStatus && (
              <span className="active-sla-filter-chip">
                Filtered by: <strong>{selectedSlaStatus}</strong>
                <button type="button" onClick={() => setSelectedSlaStatus(null)} title="Clear status filter">
                  <X size={13} />
                </button>
              </span>
            )}
            <a
              className="secondary button-link"
              href="/api/sla-compare/export?table=sla_summary"
              download
              title="Download SLA Status Summary matrix in Excel"
            >
              <ArrowDownToLine size={14} />
              Download Summary (Excel)
            </a>
            <button
              type="button"
              className="text-button toggle-summary-btn"
              onClick={() => setShowSummaryTable(!showSummaryTable)}
            >
              {showSummaryTable ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              {showSummaryTable ? 'Collapse Summary Table' : 'Expand Summary Table'}
            </button>
          </div>
        </div>

        {showSummaryTable && (
          <div className="table-scroll sla-matrix-wrap">
            <table className="sla-matrix-table" aria-label="SLA Status Summary Table">
              <thead>
                <tr>
                  <th scope="col" style={{width: 300}}><span className="sla-status-heading">Production Status {comparisonEditing.addStatusButton}</span></th>
                  {[...visibleComparisonCategories, 'Grand Total'].map(category => (
                    <th key={category} scope="col" className="col-num">{category}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summaryRows.map((row) => {
                  const isSelected = selectedSlaStatus === row.Status;
                  return (
                    <tr key={row.Status} className={isSelected ? 'matrix-row-selected' : ''}>
                      <th scope="row">
                        <div className="sla-status-label">
                        <button
                          type="button"
                          className="status-click-btn"
                          onClick={() => openMatrixPop(row.Status, null)}
                          title={`Click to open Pop Table for all ${row.Status} orders`}
                        >
                          {row.Status}
                        </button>
                        {comparisonEditing.statusActions(row.Status)}</div>
                      </th>
                      {[...visibleComparisonCategories, 'Grand Total'].map(category => (
                        <td key={category} className={`col-num ${category === 'Grand Total' ? 'col-grand' : ''}`}>
                          <button type="button" className="num-click-btn"
                            onClick={() => openMatrixPop(row.Status, category)}
                            title={`Open ${category} orders under ${row.Status}`}>
                            {row[category] || '—'}
                          </button>
                        </td>
                      ))}
                    </tr>
                  );
                })}
                {/* Totals Row */}
                {slaSummary.totals && (
                  <tr className="matrix-total-row">
                    <th scope="row">
                      <button
                        type="button"
                        className="num-click-btn bold"
                        onClick={() => openMatrixPop(null, null)}
                        title="Click to open Pop Table for all SLA Status orders"
                      >
                        Grand Total
                      </button>
                    </th>
                    {[...visibleComparisonCategories, 'Grand Total'].map(category => (
                      <td key={category} className={`col-num ${category === 'Grand Total' ? 'col-grand' : ''}`}>
                        <button type="button" className="num-click-btn bold"
                          onClick={() => openMatrixPop(null, category)}
                          title={`Click to open Pop Table for all ${category} orders`}>
                          {slaSummary.totals[category] || 0}
                        </button>
                      </td>
                    ))}
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Status Movements Section (Alphabetical Order Pills Layout) */}
      {data?.transitions && data.transitions.length > 0 && (
        <div className="status-transitions-bar">
          <div className="transitions-header inline" style={{justifyContent: 'space-between', width: '100%', marginBottom: 4}}>
            <span className="transitions-title">Status Movements ({metrics.status_moved || 0} orders moved in production):</span>
            <div className="inline" style={{gap: 8}}>
              {selectedTransition && (
                <button
                  type="button"
                  className="text-button clear-transition"
                  onClick={() => { setSelectedTransition(null); setSelectedSlaStatus(null); }}
                >
                  Clear filter ({selectedTransition.from_status} ➔ {selectedTransition.to_status})
                </button>
              )}
              <a
                className="secondary button-link"
                href="/api/sla-compare/export?table=movements"
                download
                title="Download status movements table in Excel"
              >
                <ArrowDownToLine size={13} />
                Download Movements (Excel)
              </a>
            </div>
          </div>

          <div className="transitions-pills">
            {data.transitions.map((t, idx) => {
              const isSelected = selectedTransition?.from_status === t.from_status && selectedTransition?.to_status === t.to_status;
              return (
                <button
                  type="button"
                  key={idx}
                  className={`transition-pill ${isSelected ? 'selected' : ''}`}
                  onClick={() => {
                    if (isSelected) {
                      setSelectedTransition(null);
                    } else {
                      setSelectedTransition(t);
                      setFilterType('status_moved');
                      setSelectedSlaStatus(null);
                      scrollToOrders();
                    }
                  }}
                  title={`Click to filter table by: ${t.from_status} moved to ${t.to_status} (${t.count} orders)`}
                >
                  <span className="pill-from">{t.from_status}</span>
                  <span className="pill-arrow">➔</span>
                  <span className="pill-to">{t.to_status}</span>
                  <span className="pill-count">{t.count}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Filter Tabs Navigation in Numbered Order (1: Matched, 2: Same, 3: Moved, 4: New Orders, 5: Prod Only) */}
      <div className="compare-filter-tabs" ref={ordersTableRef}>
        <div className="tabs-list">
          <button
            type="button"
            className={`tab-item ${filterType === 'matched' ? 'active' : ''}`}
            onClick={() => handleKpiClick('matched')}
          >
            🔗 All Matched ({metrics.matched || 0})
          </button>
          <button
            type="button"
            className={`tab-item ${filterType === 'same_status' ? 'active' : ''}`}
            onClick={() => handleKpiClick('same_status')}
          >
            ✅ Same Status ({metrics.same_status || 0})
          </button>
          <button
            type="button"
            className={`tab-item ${filterType === 'status_moved' && !selectedTransition && !selectedSlaStatus ? 'active' : ''}`}
            onClick={() => handleKpiClick('status_moved')}
          >
            🔄 Status Moved ({metrics.status_moved || 0})
          </button>
          <button
            type="button"
            className={`tab-item ${filterType === 'sla_only' ? 'active' : ''}`}
            onClick={() => handleKpiClick('sla_only')}
          >
            ✨ New Orders ({metrics.sla_only || 0})
          </button>
          <button
            type="button"
            className={`tab-item ${filterType === 'all' && !selectedSlaStatus ? 'active' : ''}`}
            onClick={() => handleKpiClick('all')}
          >
            All Orders ({data?.orders?.length || 0})
          </button>
        </div>
        <div className="inline" style={{gap: 12}}>
          <span className="filtered-tally">
            Showing {columnFilterControls.rows.length} of {tableRecords.length} orders
          </span>
          {filterType === 'sla_only' && <button type="button" className="secondary" onClick={copyNewOrders} disabled={!columnFilterControls.rows.some(record => record._raw.match_type === 'sla_only')} title="Copy rows without headers in production worksheet column order. Paste into the No column.">Copy New Orders for Excel</button>}
          <a
            className="secondary button-link"
            href={`/api/sla-compare/export?table=orders&filter_type=${encodeURIComponent(isSearching ? 'all' : matrixFilter ? 'summary' : filterType)}${!isSearching && matrixFilter?.status ? `&summary_status=${encodeURIComponent(matrixFilter.status)}` : ''}${!isSearching && matrixFilter?.category ? `&category=${encodeURIComponent(matrixFilter.category)}` : ''}${!isSearching && selectedSlaStatus ? `&sla_status=${encodeURIComponent(selectedSlaStatus)}` : ''}${!isSearching && selectedTransition ? `&from_status=${encodeURIComponent(selectedTransition.from_status)}&to_status=${encodeURIComponent(selectedTransition.to_status)}` : ''}${isSearching ? `&q=${encodeURIComponent(search.trim())}` : ''}`}
            download
            title="Download currently filtered comparison orders to Excel"
          >
            <ArrowDownToLine size={14} />
            Download Filtered Orders (Excel)
          </a>
        </div>
      </div>

      {/* Active Excel Column Filter Indicators */}
      {activeColFilterCount > 0 && (
        <div className="workspace-table-filter-status" style={{margin: '0 0 6px 0'}}>
          <span>
            {activeColFilterCount} Excel column filter{activeColFilterCount === 1 ? '' : 's'} active · {columnFilterControls.rows.length.toLocaleString()} of {columnFilterControls.sourceRows.length.toLocaleString()} matching orders
          </span>
          <button type="button" className="text-button" onClick={columnFilterControls.clear}>
            Clear Excel column filters
          </button>
        </div>
      )}

      {/* Side-by-Side Dual Comparison Table with Excel Column Filters */}
      {newOrderMode?<>
        <p className="report-context">Production report format · 25 columns · Copy rows into column A. No is left blank for your worksheet numbering.</p>
        <div className="table-scroll compare-table-wrap new-orders-report"><table className="side-by-side-table" aria-label="New Orders production report"><thead><tr>{NEW_ORDER_COLUMNS.map(column=><th key={column} scope="col"><div className="workspace-filter-heading"><span>{column}</span><ColumnFilterButton column={column} controls={columnFilterControls}/></div></th>)}</tr></thead><tbody>{columnFilterControls.rows.map(rec=><tr key={rec._raw.order_number}>{NEW_ORDER_COLUMNS.map(column=><td key={column} className={column==='Comments'?'eta-comment-cell':undefined}>{column==='SLA Expiration'?renderExpirationCell(rec._raw):String(newOrderRecord(rec._raw)[column])||'—'}</td>)}</tr>)}{!columnFilterControls.rows.length&&<tr><td colSpan={25} className="table-empty">No new orders match the current column filters.</td></tr>}</tbody></table></div>
      </>:<>
      <div className="table-scroll compare-table-wrap">
        <table className="side-by-side-table" aria-label="SLA vs Production Orders Comparison">
          <thead>
            {/* Top Multi-Header: SLA vs Production */}
            <tr className="super-header">
              <th colSpan={4} className="group-col info-group">Order Identity & Location</th>
              <th colSpan={3} className="group-col sla-group">◄ SLA Status (Active Queue)</th>
              <th className="group-col diff-group">Status Movement</th>
              <th colSpan={4} className="group-col prod-group">► Production Report (Uploaded)</th>
            </tr>
            {/* Column Headers with Excel-like ColumnFilterButtons */}
            <tr>
              <th scope="col" style={{width: 170}}>
                <div className="workspace-filter-heading">
                  <span>Order Number</span>
                  <ColumnFilterButton column="Order Number" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" style={{width: 140}}>
                <div className="workspace-filter-heading">
                  <span>Product</span>
                  <ColumnFilterButton column="Product" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" style={{width: 140}}>
                <div className="workspace-filter-heading">
                  <span>State / County</span>
                  <ColumnFilterButton column="State" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" style={{width: 120}}>
                <div className="workspace-filter-heading">
                  <span>Client</span>
                  <ColumnFilterButton column="Client" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="sla-head" style={{width: 180}}>
                <div className="workspace-filter-heading">
                  <span>SLA Status</span>
                  <ColumnFilterButton column="SLA Status" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="sla-head" style={{width: 130}}>
                <div className="workspace-filter-heading">
                  <span>SLA Category</span>
                  <ColumnFilterButton column="SLA Category" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="eta-comment-heading"><div className="workspace-filter-heading"><span>ETA Comments</span><ColumnFilterButton column="ETA Comments" controls={columnFilterControls}/></div></th>
              <th scope="col" className="diff-head" style={{width: 240}}>
                <div className="workspace-filter-heading">
                  <span>Movement / Difference</span>
                  <ColumnFilterButton column="Movement / Difference" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="prod-head" style={{width: 190}}>
                <div className="workspace-filter-heading">
                  <span>Production Status</span>
                  <ColumnFilterButton column="Production Status" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="prod-head" style={{width: 140}}>
                <div className="workspace-filter-heading">
                  <span>SLA Status Expiration</span>
                  <ColumnFilterButton column="SLA Status Expiration" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="prod-head" style={{width: 160}}>
                <div className="workspace-filter-heading">
                  <span>Out Time / Processed</span>
                  <ColumnFilterButton column="Out Time" controls={columnFilterControls} />
                </div>
              </th>
              <th scope="col" className="prod-head" style={{width: 150}}>
                <div className="workspace-filter-heading">
                  <span>Worker / Typer</span>
                  <ColumnFilterButton column="Worker" controls={columnFilterControls} />
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            {columnFilterControls.rows.map((rec) => {
              const order = rec._raw;
              const isMoved = order.match_type === 'status_moved';
              const isSame = order.match_type === 'same_status';
              const isSlaOnly = order.match_type === 'sla_only';
              const isProdOnly = order.match_type === 'prod_only';

              let rowClass = '';
              if (isMoved) rowClass = 'row-status-moved';
              else if (isSame) rowClass = 'row-same-status';
              else if (isSlaOnly) rowClass = 'row-sla-only';
              else if (isProdOnly) rowClass = 'row-prod-only';

              return (
                <tr key={`${order.order_number}-${rec._idx}`} className={rowClass}>
                  {/* Order Identity */}
                  <td>
                    <div className="order-num-cell">
                      {order.match_type !== 'prod_only' ? <button type="button" className="text-button" disabled={!comparisonEditing.ready} aria-label={`Edit SLA order ${order.order_number}`} onClick={() => comparisonEditing.openOrder(order)}><strong>{order.order_number}</strong></button> : <strong>{order.order_number}</strong>}
                      {isMoved && <span className="mini-badge badge-moved">MOVED</span>}
                      {isSame && <span className="mini-badge badge-same">MATCHED</span>}
                      {isSlaOnly && <span className="mini-badge badge-new">NEW ORDER</span>}
                      {isProdOnly && <span className="mini-badge badge-prod">PROD ONLY</span>}
                    </div>
                  </td>
                  <td><span className="cell-truncate">{order.product || '—'}</span></td>
                  <td>
                    <span className="location-tag">
                      {order.state && <strong>{order.state}</strong>}
                      {order.county && <small>{order.county}</small>}
                      {!order.state && !order.county && '—'}
                    </span>
                  </td>
                  <td><span className="cell-truncate">{order.client || '—'}</span></td>

                  {/* Left: SLA Status */}
                  <td className="sla-cell">
                    {order.sla_status && order.sla_status !== 'Not in SLA Queue' ? (
                      <span className={`status-pill pill-${cleanStatusClass(order.sla_status)}`}>
                        {order.sla_status}
                      </span>
                    ) : (
                      <span className="muted-dash">Not in SLA Queue</span>
                    )}
                  </td>
                  <td className="sla-cell">
                    {order.sla_category && order.sla_category !== '—' ? (
                      <span className={`category-pill pill-${cleanCategoryClass(order.sla_category)}`}>
                        {order.sla_category}
                      </span>
                    ) : (
                      <span className="muted-dash">—</span>
                    )}
                  </td>

                  <td className="eta-comment-cell">{plainComment(order.eta_comments)||'—'}</td>
                  {/* Middle: Movement Badge */}
                  <td className="diff-cell">
                    {isMoved ? (
                      <div className="movement-display">
                        <span className="move-from">{order.sla_status}</span>
                        <span className="move-arrow">➔</span>
                        <span className="move-to">{order.prod_status}</span>
                      </div>
                    ) : isSame ? (
                      <span className="same-indicator">✓ Match: {order.sla_status}</span>
                    ) : isSlaOnly ? (
                      <span className="sla-only-indicator">New Order (Pending in Queue)</span>
                    ) : (
                      <span className="prod-only-indicator">Production Only</span>
                    )}
                  </td>

                  {/* Right: Production Status */}
                  <td className="prod-cell">
                    {renderProdStatusCell(order)}
                  </td>
                  <td className="prod-cell">
                    {renderExpirationCell(order)}
                  </td>
                  <td className="prod-cell">
                    <span className="timestamp-text">{order.out_time || '—'}</span>
                  </td>
                  <td className="prod-cell">
                    <span className="worker-text">{[order.searcher, order.typer].filter(Boolean).join(' / ') || '—'}</span>
                  </td>
                </tr>
              );
            })}
            {!columnFilterControls.rows.length && (
              <tr>
                <td colSpan={12} className="table-empty">
                  {search || activeColFilterCount ? 'No orders match the current search or column filters.' : 'No orders found for this filter.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </>}
      </>)}

      {clearOpen && <Dialog title="Clear comparison report" onClose={() => {if (!clearing) setClearOpen(false);}}>
        <div className="dialog-content"><p>Clear the uploaded report from SLA Compare? Saved previews, imported reports in other workspaces, and original Excel files are retained.</p>
          {error && <p className="notice warning" role="alert">{error}</p>}
          <div className="inline"><button type="button" className="secondary" disabled={clearing} onClick={() => setClearOpen(false)}>Cancel</button>
            <button type="button" className="primary" disabled={clearing} onClick={async () => {
              setClearing(true); setError('');
              try {
                const params = new URLSearchParams({clear:'1'});
                if (selectedPreview) params.set('preview_id', selectedPreview);
                const result = await api(`/api/sla-compare?${params}`, {method:'POST'});
                setData(result); setSearch(''); setFilterType('matched'); setMatrixFilter(null);
                setSelectedTransition(null); setSelectedSlaStatus(null); setPopModal(null);
                columnFilterControls.clear(); setEditingOrderNumber(null); setEditingExpiration(null);
                if (fileInputRef.current) fileInputRef.current.value = '';
                setMessage('Comparison report cleared. Upload a production report to compare again.');
                setClearOpen(false);
              } catch (error) { setError(error.message || 'Could not clear the comparison report. Try again.'); }
              finally { setClearing(false); }
            }}>{clearing?'Clearing…':'Clear comparison'}</button></div>
        </div>
      </Dialog>}

      {/* Pop Table Modal for Matrix and Movements */}
      {popModal && (
        <Dialog
          title={popModal.title}
          onClose={() => setPopModal(null)}
          className="detail-dialog compare-pop-dialog orders-detail-dialog"
        >
          <div className="dialog-content">
            <div className="pop-modal-toolbar">
              <div className="pop-modal-info">
                <p className="muted" style={{margin: 0}}>
                  {popModalOrders.length.toLocaleString()} orders in this group · Categories from SLA Status
                </p>
              </div>
              <div className="pop-modal-actions inline" style={{gap: 8}}>
                <button type="button" className="secondary" disabled={!comparisonEditing.ready} onClick={() => comparisonEditing.addOrder(popModal.summary_status || popModal.status)}><Plus size={16}/>Add order</button>
                <div className="search-input">
                  <Search size={14} />
                  <input
                    type="text"
                    placeholder="Search in this popup table…"
                    value={popSearch}
                    onChange={(e) => setPopSearch(e.target.value)}
                  />
                  {popSearch && (
                    <button type="button" className="icon-button" onClick={() => setPopSearch('')}>
                      <X size={13} />
                    </button>
                  )}
                </div>
                <a
                  className="secondary button-link"
                  href={`/api/sla-compare/export?table=orders${popModal.scope === 'matrix' ? '&filter_type=summary' : ''}${popModal.summary_status ? `&summary_status=${encodeURIComponent(popModal.summary_status)}` : ''}${popModal.prod_status ? `&prod_status=${encodeURIComponent(popModal.prod_status)}` : ''}${popModal.status ? `&sla_status=${encodeURIComponent(popModal.status)}` : ''}${popModal.category ? `&category=${encodeURIComponent(popModal.category)}` : ''}${popModal.from_status ? `&from_status=${encodeURIComponent(popModal.from_status)}&to_status=${encodeURIComponent(popModal.to_status)}` : ''}`}
                  download
                  title="Download this exact popup table to Excel"
                >
                  <ArrowDownToLine size={14} />
                  Download (Excel)
                </a>
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    if (popModal.scope === 'matrix') {
                      setFilterType('all');
                      setSelectedTransition(null);
                      setSelectedSlaStatus(null);
                      setSearch('');
                      columnFilterControls.clear();
                      setMatrixFilter({status: popModal.summary_status, category: popModal.category});
                    } else if (popModal.from_status && popModal.to_status) {
                      setSelectedTransition({from_status: popModal.from_status, to_status: popModal.to_status});
                      setFilterType('status_moved');
                      setSelectedSlaStatus(null);
                    } else if (popModal.prod_status) {
                      setFilterType('matched');
                      setSearch(popModal.prod_status);
                    } else if (popModal.status) {
                      setSelectedSlaStatus(popModal.status);
                      setFilterType('all');
                      setSelectedTransition(null);
                    }
                    setPopModal(null);
                    scrollToOrders();
                  }}
                  title="Apply this group as filter to the main comparison table and scroll down"
                >
                  View in Main Table
                </button>
              </div>
            </div>

            <div className="pop-modal-table-scroll">
              <table className="side-by-side-table pop-orders-table">
                <thead>
                  <tr>
                    <th>Actions</th>
                    <th>Order Number</th>
                    <th>Product</th>
                    <th>State / County</th>
                    <th>Client</th>
                    <th>Movement / Difference</th>
                    <th>Production Status</th>
                    <th>SLA Status Expiration</th>
                    <th>Out Time</th>
                    <th>Worker</th>
                  </tr>
                </thead>
                <tbody>
                  {popModalOrders.map((o, idx) => (
                    <tr key={`${o.order_number}-${idx}`} className={o.match_type === 'status_moved' ? 'row-status-moved' : ''}>
                      <td>{comparisonEditing.rowActions(o)}</td>
                      <td>{o.match_type !== 'prod_only' ? <button type="button" className="text-button" disabled={!comparisonEditing.ready} onClick={() => comparisonEditing.openOrder(o)}><strong>{o.order_number}</strong></button> : <strong>{o.order_number}</strong>}</td>
                      <td>{o.product || '—'}</td>
                      <td>{[o.state, o.county].filter(Boolean).join(' / ') || '—'}</td>
                      <td>{o.client || '—'}</td>
                      <td>
                        {o.match_type === 'status_moved' ? (
                          <span style={{color: '#d97706', fontWeight: 650}}>{o.change_label}</span>
                        ) : (
                          o.change_label
                        )}
                      </td>
                      <td>
                        {renderProdStatusCell(o)}
                      </td>
                      <td>{renderExpirationCell(o)}</td>
                      <td>{o.out_time || '—'}</td>
                      <td>{[o.searcher, o.typer].filter(Boolean).join(' / ') || '—'}</td>
                    </tr>
                  ))}
                  {!popModalOrders.length && (
                    <tr>
                      <td colSpan={10} className="table-empty">
                        No orders match the current search in this group.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </Dialog>
      )}
      {comparisonEditing.dialogs}
    </section>
  );
}

// Helpers for CSS classes
function cleanStatusClass(status) {
  return String(status || '').toLowerCase().replace(/[^a-z0-9]/g, '');
}

function cleanCategoryClass(category) {
  if (!category) return 'unknown';
  if (category.includes('Today')) return 'today';
  if (category.includes('Negative')) return 'negative';
  if (category.includes('Future')) return 'future';
  return 'unknown';
}
