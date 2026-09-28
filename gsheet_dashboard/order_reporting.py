"""Status automation and capture-level daily order reporting."""
from datetime import datetime

import pandas as pd

from datatrace_sync import apply_status_rules
from preview_store import compare
from reporting_dates import arrival_date, reporting_date

COMPLETED = 'Completed and Delivered'
AUTOMATIC_RULES = [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}]


def automatic_sync_frame(latest, previous=None, keys=None, ignore=None):
    day = reporting_date(latest)
    columns = list(latest['columns'])
    rows = list(latest['rows'])
    completed_orders = set()
    if previous is not None:
        comparison = compare(previous, latest, keys, ignore)
        if 'Order Number' not in latest['columns'] or 'Order Number' not in previous['columns']:
            raise ValueError('Order Number is required in both previews for automatic completion.')
        completed_orders = {str(row.get('Order Number', '')).strip()
                            for row in comparison['unmatched_rows']
                            if row['Comparison Status'] == 'Missing'} - {''}
        columns = list(dict.fromkeys(columns + previous['columns']))
        # Missing rows must remain in the uploaded reports to show their completion.
        present = {str(row.get('Order Number', '')).strip() for row in rows} - {''}
        rows += [row for row in previous['rows']
                 if str(row.get('Order Number', '')).strip() in completed_orders - present]
    frame = apply_status_rules(pd.DataFrame(rows, columns=columns).fillna(''), AUTOMATIC_RULES, reporting_date=day)
    if completed_orders:
        mask = frame['Order Number'].astype(str).str.strip().isin(completed_orders)
        for column in ('Task Status', 'Status'):
            if column in frame.columns:
                frame.loc[mask, column] = COMPLETED
        frame.loc[mask, 'Out Time'] = day
        if 'Is Available' in frame.columns:
            frame.loc[mask, 'Is Available'] = False
    frame.attrs['reporting_date'] = day
    frame.attrs['capture_date'] = datetime.fromisoformat(latest['created']).astimezone().date().isoformat()
    frame.attrs['original_capture'] = {'columns': list(latest['columns']), 'rows': latest['rows']}
    return frame, sorted(completed_orders)


def completion_history(store, latest_id):
    dates = {}
    previous = None
    for item in reversed(store.list()):
        if item['id'] > latest_id:
            continue
        preview = store.get(item['id'])
        if 'Order Number' not in preview['columns']:
            previous = None
            continue
        if not any(column in preview['columns'] for column in ('Task Status','Status')):
            previous = preview
            continue
        frame, _ = automatic_sync_frame(preview, previous)
        status = 'Task Status' if 'Task Status' in frame.columns else 'Status'
        for row in frame.to_dict('records'):
            if str(row.get(status, '')).strip().casefold() == COMPLETED.casefold():
                identity = str(row.get('Order Number', '')).strip()
                if identity:
                    dates.setdefault(identity, row['Out Time'])
        previous = preview
    return dates


def daily_orders(store):
    days = {}
    captures = sorted(store.list(), key=lambda item: (datetime.fromisoformat(item['created']), item['id']))
    for item in captures:
        preview = store.get(item['id'])
        day = reporting_date(preview)
        days.setdefault(day, []).append(preview)
    reports = []
    for day, previews in sorted(days.items(), reverse=True):
        orders, snapshots, columns = {}, [], []
        for preview in previews:
            columns = list(dict.fromkeys(columns + preview['columns']))
            current = {}
            for row in preview['rows']:
                identity = str(row.get('Order Number', '')).strip()
                if identity:
                    current[identity] = dict(row)
            snapshots.append(set(current))
            orders.update(current)
        unique = set(orders)
        missing = unique - snapshots[-1]
        arrivals = {identity: arrival_date(row) for identity, row in orders.items()}
        new = {identity for identity, date in arrivals.items() if date == day} if any(arrivals.values()) else unique - snapshots[0]
        unchanged = set.intersection(*snapshots)
        frame = apply_status_rules(pd.DataFrame(list(orders.values()), columns=columns).fillna(''), [], reporting_date=day)
        rows = frame.to_dict('records')
        for row in rows:
            if str(row.get('Order Number', '')).strip() in missing:
                for column in ('Task Status', 'Status'):
                    if column in row:
                        row[column] = COMPLETED
                if 'Is Available' in row:
                    row['Is Available'] = False
                row['Out Time'] = day
        reports.append({
            'Date': day, 'Previews': [p['name'] for p in previews],
            'Today Orders': len(unique), 'Missing (Completed Orders)': len(missing),
            'Newly Orders': len(new), 'Unchanged': len(unchanged),
            'columns': list(frame.columns), 'rows': rows,
            'missing_ids': sorted(missing), 'new_ids': sorted(new),
            'unchanged_ids': sorted(unchanged),
        })
    return reports
