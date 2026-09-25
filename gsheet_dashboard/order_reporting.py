"""Status automation and capture-level daily order reporting."""
from datetime import datetime

import pandas as pd

from datatrace_sync import apply_status_rules
from preview_store import compare

COMPLETED = 'Completed and Delivered'
AUTOMATIC_RULES = [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}]


def automatic_sync_frame(latest, previous=None, keys=None, ignore=None):
    columns = list(latest['columns'])
    rows = list(latest['rows'])
    completed_orders = set()
    if previous is not None:
        comparison = compare(previous, latest, keys, ignore)
        if 'Order Number' not in latest['columns'] or 'Order Number' not in previous['columns']:
            raise ValueError('Order Number is required in both previews for automatic completion.')
        completed_orders = {str(row.get('Order Number', '')).strip()
                            for row in comparison['unmatched_rows']} - {''}
        columns = list(dict.fromkeys(columns + previous['columns']))
        # Missing rows must remain in the uploaded reports to show their completion.
        present = {str(row.get('Order Number', '')).strip() for row in rows} - {''}
        rows += [row for row in previous['rows']
                 if str(row.get('Order Number', '')).strip() in completed_orders - present]
    frame = apply_status_rules(pd.DataFrame(rows, columns=columns).fillna(''), AUTOMATIC_RULES)
    if completed_orders:
        mask = frame['Order Number'].astype(str).str.strip().isin(completed_orders)
        for column in ('Task Status', 'Status'):
            if column in frame.columns:
                frame.loc[mask, column] = COMPLETED
        if 'Is Available' in frame.columns:
            frame.loc[mask, 'Is Available'] = False
    return frame, sorted(completed_orders)


def daily_orders(store):
    reports = []
    previous = None
    for item in reversed(store.list()):
        latest = store.get(item['id'])
        counts = compare(previous, latest)['record_counts'] if previous else None
        reports.append({
            'Date': datetime.fromisoformat(latest['created']).astimezone().date().isoformat(),
            'Captured': latest['created'], 'Preview': latest['name'],
            'Previous Preview': previous['name'] if previous else '',
            'Total Orders': len(latest['rows']),
            'Missing (Completed Orders)': counts['missing'] if counts else None,
            'Newly Added': counts['newly_added'] if counts else None,
            'Unchanged': counts['unchanged'] if counts else None,
            'preview_id': latest['id'], 'previous_id': previous['id'] if previous else None,
        })
        previous = latest
    return list(reversed(reports))
