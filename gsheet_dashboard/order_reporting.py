"""Production reports derived exclusively from the two Google Sheets trackers."""
from collections import defaultdict
from datetime import datetime

import pandas as pd
from production_rules import order_key, timestamp, TRACKER_COLUMNS
from sla_comments import sla_entry, sla_status

COMPLETED = 'Completed and Delivered'
AUTOMATIC_RULES = [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}]


def automatic_sync_frame(latest, previous=None, keys=None, ignore=None, store=None, reports=None):
    # Raw queue statuses remain raw. Tracker reconciliation owns production status.
    frame = pd.DataFrame(latest['rows'], columns=latest['columns']).fillna('')
    frame.attrs['original_capture'] = dict(latest)
    frame.attrs['previous_capture'] = previous
    return frame, []


def completion_history(store, latest_id):
    return {}  # Disappearing from a queue cannot establish completion.


def _reports(sheet_rows, monthly=False):
    if sheet_rows is None:
        raise ValueError('Google Sheets tracker rows are required for production reporting.')
    groups = defaultdict(list)
    seen = set()
    completions = defaultdict(list)
    for source in sheet_rows:
        row = dict(source)
        key = order_key(row.get('Order Number'))
        if not key:
            continue
        if key in seen:
            raise ValueError('Duplicate Order Number in Google Sheets trackers.')
        seen.add(key)
        day = timestamp(row.get('Date')) or timestamp(row.get('In-Time'))
        label = day.strftime('%Y-%m' if monthly else '%Y-%m-%d') if day else 'Undated'
        groups[label].append(row)
        out = timestamp(row.get('Out Time'))
        status = sla_status(row.get('Free Site'))
        if out and status:
            completions[out.strftime('%Y-%m')].append(sla_entry(row, status))
    if monthly:
        for label in completions:
            groups.setdefault(label, [])
    reports = []
    for label, rows in sorted(groups.items(), reverse=True):
        completed = [row['Order Number'] for row in rows if str(row.get('Status', '')).strip().casefold() == 'completed and delivered']
        awaiting = sum(str(row.get('Status', '')).strip().casefold() == 'awaiting for clarification' for row in rows)
        report = {'Date': label, 'Today Orders': len(rows), 'Awaiting for Clarification': awaiting,
                  'Completed Orders': len(completed), 'Newly Orders': len(rows), 'Unchanged': 0,
                  'Previews': [], 'columns': TRACKER_COLUMNS, 'rows': rows,
                  'missing_ids': [], 'completed_ids': completed,
                  'new_ids': [row['Order Number'] for row in rows], 'unchanged_ids': [],
                  'source': 'Google Sheets'}
        if monthly:
            sla_rows = sorted(completions.get(label, []), key=lambda row: (row['completion_date'], row['Order Number']), reverse=True)
            report.update(Month=label, MonthLabel=datetime.strptime(label, '%Y-%m').strftime('%B %Y') if label != 'Undated' else label,
                          **{'Month Orders': len(rows), 'Days': sorted({(timestamp(r.get('Date')) or timestamp(r.get('In-Time'))).strftime('%Y-%m-%d') for r in rows if timestamp(r.get('Date')) or timestamp(r.get('In-Time'))}),
                             'SLA On Time': sum(r['Free Site'] == 'On Time' for r in sla_rows),
                             'SLA Missed': sum(r['Free Site'] == 'Missed' for r in sla_rows), 'sla_rows': sla_rows})
        reports.append(report)
    return reports


def daily_orders(store=None, preview_id=None, history=None, sheet_rows=None):
    return _reports(sheet_rows)


def monthly_orders(store=None, sheet_rows=None, history=None, corrections=None):
    return _reports(sheet_rows, monthly=True)
