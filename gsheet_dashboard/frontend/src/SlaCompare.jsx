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

      const st = o.prod_status || '(Blank)';
      if (!summaryByStatus[st]) {
        summaryByStatus[st] = {
          Status: st,
          'Future SLA': 0,
          'Negative SLA': 0,
          'Today SLA': 0,
          'Unknown SLA': 0,
          'Grand Total': 0
        };
      }
      const cat = o.prod_sla_category || o.sla_category;
      if (summaryByStatus[st][cat] !== undefined) {
        summaryByStatus[st][cat]++;
      } else {
        summaryByStatus[st]['Unknown SLA']++;
      }
      summaryByStatus[st]['Grand Total']++;
    } else if (mtype === 'sla_only') {
      slaOnlyCount++;
    } else if (mtype === 'prod_only') {
      prodOnlyCount++;
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
    'Grand Total': rows.reduce((s, r) => s + (r['Grand Total'] || 0), 0)
  };

  const transitions = Object.values(transitionMap).sort((a, b) => {
    const fromComp = a.from_status.localeCompare(b.from_status, undefined, { sensitivity: 'base' });
    if (fromComp !== 0) return fromComp;
    return a.to_status.localeCompare(b.to_status, undefined, { sensitivity: 'base' });
  });

  return {
    sla_summary: {
      columns: ['Status', 'Future SLA', 'Negative SLA', 'Today SLA', 'Grand Total'],
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
  'Movement / Difference',
  'Production Status',
  'Prod SLA',
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
  const [showSummaryTable, setShowSummaryTable] = useState(true);
  const [search, setSearch] = useState('');
  const [uploading, setUploading] = useState(false);
  const [draggingFiles, setDraggingFiles] = useState(false);
  const uploadInProgress = useRef(false);
  const dragDepth = useRef(0);
  const [message, setMessage] = useState('');
  const [popModal, setPopModal] = useState(null);
  const [popSearch, setPopSearch] = useState('');
  const [editingOrderNumber, setEditingOrderNumber] = useState(null);
  const [editStatusValue, setEditStatusValue] = useState('');
  const [isCustomStatus, setIsCustomStatus] = useState(false);
  const [customStatusInput, setCustomStatusInput] = useState('');
  const [customStatuses, setCustomStatuses] = useState([]);
  const [savingStatus, setSavingStatus] = useState(false);
  const fileInputRef = useRef(null);
  const ordersTableRef = useRef(null);

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
          const isMoved = slaSt && cleanStatus &&
            slaSt.toLowerCase() !== cleanStatus.toLowerCase() &&
            cleanStatus !== 'Not in Production Report';
          return {
            ...item,
            prod_status: cleanStatus,
            status_changed: isMoved,
            match_type: isMoved ? 'status_moved' : 'same_status',
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
              const isMoved = slaSt && cleanStatus &&
                slaSt.toLowerCase() !== cleanStatus.toLowerCase() &&
                cleanStatus !== 'Not in Production Report';
              return {
                ...item,
                prod_status: cleanStatus,
                status_changed: isMoved,
                match_type: isMoved ? 'status_moved' : 'same_status',
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
    const isEditing = editingOrderNumber === order.order_number;
    if (isEditing) {
      return (
        <div className="status-edit-container">
          {!isCustomStatus ? (
            <div className="inline" style={{gap: 4, alignItems: 'center'}}>
              <select
                className="status-edit-select"
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
    setFilterType(type);
    setSelectedTransition(null);
    setSelectedSlaStatus(null);
    scrollToOrders();
  };

  const loadComparison = async (previewId = selectedPreview, useSample = false) => {
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

    // Search query
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(o =>
        (o.order_number && o.order_number.toLowerCase().includes(q)) ||
        (o.sla_status && o.sla_status.toLowerCase().includes(q)) ||
        (o.prod_status && o.prod_status.toLowerCase().includes(q)) ||
        (o.client && o.client.toLowerCase().includes(q)) ||
        (o.county && o.county.toLowerCase().includes(q)) ||
        (o.state && o.state.toLowerCase().includes(q)) ||
        (o.product && o.product.toLowerCase().includes(q)) ||
        (o.searcher && o.searcher.toLowerCase().includes(q)) ||
        (o.typer && o.typer.toLowerCase().includes(q))
      );
    }

    return list;
  }, [data, filterType, selectedSlaStatus, selectedTransition, search]);

  // 2. Prepare structured records for Excel-like column filtering
  const tableRecords = useMemo(() => {
    return baseFilteredOrders.map((o, idx) => ({
      _raw: o,
      _idx: idx,
      'Order Number': o.order_number,
      'Product': o.product,
      'State': o.state,
      'County': o.county,
      'Client': o.client,
      'SLA Status': o.sla_status,
      'SLA Category': o.sla_category,
      'Movement / Difference': o.change_label,
      'Production Status': o.prod_status,
      'Prod SLA': o.prod_sla,
      'Out Time': o.out_time,
      'Worker': [o.searcher, o.typer].filter(Boolean).join(' / ')
    }));
  }, [baseFilteredOrders]);

  // 3. Attach Excel-style column filter controls
  const columnFilterControls = useColumnFilters(tableRecords, FILTER_COLUMNS);
  const activeColFilterCount = Object.keys(columnFilterControls.filters).length;

  const metrics = data?.metrics || {};
  const slaSummary = data?.sla_summary || {rows: [], totals: {}};

  // Helper to open Pop Table modal for matrix cells (based on Production Report status)
  const openMatrixPop = (status, category) => {
    if (!data || !data.orders) return;
    // SLA summary is based on matched orders in the production report
    const matched = data.orders.filter(o => o.match_type === 'status_moved' || o.match_type === 'same_status');
    let subset = matched;
    if (status && status !== 'Grand Total') {
      subset = subset.filter(o => o.prod_status === status);
    }
    if (category && category !== 'Grand Total') {
      subset = subset.filter(o => (o.prod_sla_category || o.sla_category) === category);
    }
    const labelParts = [];
    if (status && status !== 'Grand Total') labelParts.push(status);
    else labelParts.push('All Production Statuses');

    if (category && category !== 'Grand Total') labelParts.push(category);
    else labelParts.push('All SLA Categories');

    setPopSearch('');
    setPopModal({
      title: `${labelParts.join(' · ')} (${subset.length.toLocaleString()} orders)`,
      prod_status: status === 'Grand Total' ? null : status,
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
    <section className="sla-compare-workspace" aria-label="SLA Compare Workspace"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={(event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = uploading || loading ? 'none' : 'copy';
      }}
      onDrop={handleDrop}
    >
      {/* Top Header & Actions */}
      <div className="section-heading">
        <div>
          <h2>SLA Compare · Side-by-Side Production Comparison</h2>
          <p className="muted">
            Matching {metrics.matched?.toLocaleString() || 0} orders by Order Number between SLA Status ({data?.preview_name || 'Queue'}) and Uploaded Production Report ({data?.source_files || 'None'}).
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
          <button
            type="button"
            className="primary"
            disabled={uploading || loading}
            onClick={() => fileInputRef.current?.click()}
            title="Upload your Production Report (.xlsx or .csv) to match against SLA Status"
          >
            <Upload size={16} />
            {uploading ? 'Processing…' : 'Upload Production Report'}
          </button>
          <button
            type="button"
            className="secondary"
            disabled={uploading || loading}
            onClick={() => loadComparison(selectedPreview, false)}
            title="Refresh current comparison"
          >
            <RefreshCw size={16} className={loading ? 'spin' : ''} />
            Refresh
          </button>
          {data?.has_production && (
            <button
              type="button"
              className="secondary"
              onClick={async () => {
                if (window.confirm('Clear the current comparison and uploaded Production Report?')) {
                  await api('/api/sla-compare?clear=1');
                  loadComparison();
                }
              }}
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
            aria-disabled={loading || !data}
            title="Export full comparison to styled Excel workbook"
          >
            <ArrowDownToLine size={16} />
            Download Excel
          </a>
        </div>
      </div>

      {/* Preview Selector Toolbar */}
      <div className="sla-compare-toolbar">
        <label className="sla-preview-picker">
          SLA Queue Preview
          <select
            aria-label="Select SLA Queue Preview"
            value={selectedPreview}
            disabled={loading || uploading}
            onChange={(e) => setSelectedPreview(e.target.value)}
          >
            {data?.previews?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {p.row_count.toLocaleString()} rows · {new Date(p.created).toLocaleDateString('en-US', {month: 'short', day: 'numeric'})}
                {p.id === data.previews[0]?.id ? ' (Latest)' : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="search-input">
          <Search size={15} />
          <input
            type="text"
            placeholder="Search order number, client, county, status…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button type="button" className="icon-button" onClick={() => setSearch('')}>
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Notices */}
      {message && <p className="notice success" role="status">{message}</p>}
      {error && <p className="notice warning" role="alert">{error}</p>}
      {data?.source_warning && <p className="notice warning" role="status">{data.source_warning}</p>}

      <p role="status" style={{
        padding: '12px 18px',
        border: `2px dashed ${draggingFiles ? 'var(--accent, #0d9488)' : 'var(--border, #cbd5e1)'}`,
        borderRadius: 12,
        background: draggingFiles ? 'var(--accent-subtle, #f0fdfa)' : 'var(--surface, #ffffff)',
        textAlign: 'center'
      }}>
        {uploading ? 'Processing production reports…' : loading ? 'Loading comparison…' : draggingFiles
          ? 'Drop production reports here to compare'
          : 'Drag and drop production reports anywhere in SLA Compare, or use Upload Production Report. Supports .xlsx, .xlsm and .csv files.'}
      </p>

      {!data?.has_production ? (
        <div className="sla-compare-empty-state" style={{
          textAlign: 'center',
          padding: '56px 24px',
          background: 'var(--surface, #ffffff)',
          border: '1px dashed var(--border, #cbd5e1)',
          borderRadius: '12px',
          margin: '24px 0',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px'
        }}>
          <div style={{
            width: '64px',
            height: '64px',
            borderRadius: '50%',
            background: 'var(--accent-subtle, #f0fdfa)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--accent, #0d9488)'
          }}>
            <FileSpreadsheet size={32} />
          </div>
          <h2 style={{fontSize: '20px', fontWeight: 600, margin: 0}}>No Production Report Uploaded</h2>
          <p style={{maxWidth: '540px', color: 'var(--muted, #64748b)', margin: 0, lineHeight: 1.5}}>
            Drag and drop your Production Report files here to compare order statuses, view the SLA Status Summary Matrix, and track moved or changed orders against the SLA Queue.
          </p>
          <button
            type="button"
            className="primary"
            style={{
              padding: '10px 22px',
              fontSize: '14px',
              fontWeight: 600,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              cursor: 'pointer'
            }}
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading || loading}
          >
            <Upload size={18} />
            {uploading ? 'Processing File…' : 'Upload Production Report (Excel)'}
          </button>
          <span style={{fontSize: '12px', color: 'var(--muted, #94a3b8)'}}>
            Supports Full Search, C-O & Update, or any production Excel workbook with Order Number and Status columns.
          </span>
        </div>
      ) : (
        <>
          {/* Summary KPI Cards in Ordered Sequence (1: Matched in Both, 2: Identical, 3: Moved, 4: New Orders) */}
          <div className="compare-kpis">
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
            <h3>SLA Status Summary Matrix (Based on Production Report)</h3>
            <span className="subheading-tag">Grouped by Production Status for matched orders · Click any number to view related orders Pop Table</span>
          </div>
          <div className="subheading-right inline">
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
            <table className="sla-matrix-table" aria-label="SLA Status Summary Table based on Production Report">
              <thead>
                <tr>
                  <th scope="col" style={{width: 260}}>Production Status</th>
                  <th scope="col" className="col-num" style={{width: 120}}>Future SLA</th>
                  <th scope="col" className="col-num" style={{width: 130}}>Negative SLA</th>
                  <th scope="col" className="col-num" style={{width: 120}}>Today SLA</th>
                  <th scope="col" className="col-num col-grand" style={{width: 140}}>Grand Total</th>
                </tr>
              </thead>
              <tbody>
                {slaSummary.rows.map((row) => {
                  const isSelected = selectedSlaStatus === row.Status;
                  return (
                    <tr key={row.Status} className={isSelected ? 'matrix-row-selected' : ''}>
                      <th scope="row">
                        <button
                          type="button"
                          className="status-click-btn"
                          onClick={() => openMatrixPop(row.Status, null)}
                          title={`Click to open Pop Table for all ${row.Status} orders`}
                        >
                          {row.Status}
                        </button>
                      </th>
                      <td className="col-num">
                        <button
                          type="button"
                          className="num-click-btn"
                          onClick={() => openMatrixPop(row.Status, 'Future SLA')}
                          title={`Click to open Pop Table for ${row['Future SLA'] || 0} Future SLA orders under ${row.Status}`}
                        >
                          {row['Future SLA'] || '—'}
                        </button>
                      </td>
                      <td className="col-num">
                        <button
                          type="button"
                          className="num-click-btn"
                          onClick={() => openMatrixPop(row.Status, 'Negative SLA')}
                          title={`Click to open Pop Table for ${row['Negative SLA'] || 0} Negative SLA orders under ${row.Status}`}
                        >
                          {row['Negative SLA'] || '—'}
                        </button>
                      </td>
                      <td className="col-num">
                        <button
                          type="button"
                          className="num-click-btn"
                          onClick={() => openMatrixPop(row.Status, 'Today SLA')}
                          title={`Click to open Pop Table for ${row['Today SLA'] || 0} Today SLA orders under ${row.Status}`}
                        >
                          {row['Today SLA'] || '—'}
                        </button>
                      </td>
                      <td className="col-num col-grand">
                        <button
                          type="button"
                          className="num-click-btn bold"
                          onClick={() => openMatrixPop(row.Status, null)}
                          title={`Click to open Pop Table for ${row['Grand Total'] || 0} orders under ${row.Status}`}
                        >
                          {row['Grand Total']}
                        </button>
                      </td>
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
                        title="Click to open Pop Table for all matched orders"
                      >
                        Grand Total
                      </button>
                    </th>
                    <td className="col-num">
                      <button
                        type="button"
                        className="num-click-btn bold"
                        onClick={() => openMatrixPop(null, 'Future SLA')}
                        title="Click to open Pop Table for all Future SLA orders"
                      >
                        {slaSummary.totals['Future SLA'] || 0}
                      </button>
                    </td>
                    <td className="col-num">
                      <button
                        type="button"
                        className="num-click-btn bold"
                        onClick={() => openMatrixPop(null, 'Negative SLA')}
                        title="Click to open Pop Table for all Negative SLA orders"
                      >
                        {slaSummary.totals['Negative SLA'] || 0}
                      </button>
                    </td>
                    <td className="col-num">
                      <button
                        type="button"
                        className="num-click-btn bold"
                        onClick={() => openMatrixPop(null, 'Today SLA')}
                        title="Click to open Pop Table for all Today SLA orders"
                      >
                        {slaSummary.totals['Today SLA'] || 0}
                      </button>
                    </td>
                    <td className="col-num col-grand">
                      <button
                        type="button"
                        className="num-click-btn bold"
                        onClick={() => openMatrixPop(null, null)}
                        title="Click to open Pop Table for all matched orders"
                      >
                        {slaSummary.totals['Grand Total'] || 0}
                      </button>
                    </td>
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
          <a
            className="secondary button-link"
            href={`/api/sla-compare/export?table=orders&filter_type=${encodeURIComponent(filterType)}${selectedSlaStatus ? `&sla_status=${encodeURIComponent(selectedSlaStatus)}` : ''}${selectedTransition ? `&from_status=${encodeURIComponent(selectedTransition.from_status)}&to_status=${encodeURIComponent(selectedTransition.to_status)}` : ''}${search ? `&q=${encodeURIComponent(search)}` : ''}`}
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
      <div className="table-scroll compare-table-wrap">
        <table className="side-by-side-table" aria-label="SLA vs Production Orders Comparison">
          <thead>
            {/* Top Multi-Header: SLA vs Production */}
            <tr className="super-header">
              <th colSpan={4} className="group-col info-group">Order Identity & Location</th>
              <th colSpan={2} className="group-col sla-group">◄ SLA Status (Active Queue)</th>
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
                  <span>Prod SLA / ETA</span>
                  <ColumnFilterButton column="Prod SLA" controls={columnFilterControls} />
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
                      <strong>{order.order_number}</strong>
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
                    <span className="timestamp-text">{order.prod_sla || '—'}</span>
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
                <td colSpan={11} className="table-empty">
                  {search || activeColFilterCount ? 'No orders match the current search or column filters.' : 'No orders found for this filter.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      </>)}

      {/* Pop Table Modal for Matrix and Movements */}
      {popModal && (
        <Dialog
          title={popModal.title}
          onClose={() => setPopModal(null)}
          className="detail-dialog compare-pop-dialog"
        >
          <div className="dialog-content">
            <div className="pop-modal-toolbar">
              <div className="pop-modal-info">
                <p className="muted" style={{margin: 0}}>
                  {popModalOrders.length.toLocaleString()} orders in this group · Matched between SLA Status and Production Report
                </p>
              </div>
              <div className="pop-modal-actions inline" style={{gap: 8}}>
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
                  href={`/api/sla-compare/export?table=orders${popModal.prod_status ? `&prod_status=${encodeURIComponent(popModal.prod_status)}` : ''}${popModal.status ? `&sla_status=${encodeURIComponent(popModal.status)}` : ''}${popModal.category ? `&category=${encodeURIComponent(popModal.category)}` : ''}${popModal.from_status ? `&from_status=${encodeURIComponent(popModal.from_status)}&to_status=${encodeURIComponent(popModal.to_status)}` : ''}`}
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
                    if (popModal.from_status && popModal.to_status) {
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
                    <th>Order Number</th>
                    <th>Product</th>
                    <th>State / County</th>
                    <th>Client</th>
                    <th>Movement / Difference</th>
                    <th>Production Status</th>
                    <th>Prod SLA / ETA</th>
                    <th>Out Time</th>
                    <th>Worker</th>
                  </tr>
                </thead>
                <tbody>
                  {popModalOrders.map((o, idx) => (
                    <tr key={`${o.order_number}-${idx}`} className={o.match_type === 'status_moved' ? 'row-status-moved' : ''}>
                      <td><strong>{o.order_number}</strong></td>
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
                      <td>{o.prod_sla || '—'}</td>
                      <td>{o.out_time || '—'}</td>
                      <td>{[o.searcher, o.typer].filter(Boolean).join(' / ') || '—'}</td>
                    </tr>
                  ))}
                  {!popModalOrders.length && (
                    <tr>
                      <td colSpan={9} className="table-empty">
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
