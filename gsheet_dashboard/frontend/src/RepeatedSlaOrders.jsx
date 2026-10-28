import React from 'react';

export default function RepeatedSlaOrders({report,onShow}) {
  if(report?.report_scope!=='preview'||(!report.duplicate_row_count&&!report.missing_order_number_count))return null;
  return <aside className="sla-repeated-orders" aria-label="Repeated orders and applied conditions">
    <h3>Repeated orders</h3>
    <p role="status">{report.preview_row_count.toLocaleString()} captured rows − {report.duplicate_row_count||0} repeated rows{report.missing_order_number_count?` − ${report.missing_order_number_count} rows without an Order Number`:''} = {report.captured_order_count.toLocaleString()} unique captured orders.</p>
    <p className="muted">Each Order Number is counted once using the condition shown below.</p>
    {!!report.duplicate_groups?.length&&<ul>{report.duplicate_groups.map(group=><li key={group.order_number}>
      <button type="button" className="sla-repeated-order" aria-label={`Show repeated entries for ${group.order_number}`} onClick={()=>onShow(group.order_number)}>
        <strong>{group.order_number}</strong>
        <span>{group.row_count} entries · Counted as <b>{group.status}</b>{group.sla_category?` · ${group.sla_category}`:' · SLA needs review'}</span>
        <small>Applied condition: {group.status_reason}. Capture row {group.selected_capture_row} is counted.</small>
        <small>{group.selection_reason}</small>
      </button>
    </li>)}</ul>}
    {report.duplicate_row_count>0&&<button type="button" className="text-button" onClick={()=>onShow()}>View {report.duplicate_order_count} repeated Order Numbers</button>}
  </aside>;
}
