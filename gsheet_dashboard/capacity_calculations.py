"""Capacity workload by report date for Excel imports and completion day for trackers."""
from collections import defaultdict
from datetime import datetime, timedelta
import re

COUNTS = ['Received', 'Completed', 'Clarification', 'Cancelled', 'Vendor Pending', 'In-House Pending']
PENDING = ('Clarification', 'Vendor Pending', 'In-House Pending')


def completion_rows(periods, *, use_report_date=False):
    """Use the same retained order and source date for counts and drilldowns."""
    from monthly_production import local_datetime
    from tracker_sync import key
    orders = {}
    for period in periods:
        for row in period.get('rows', []):
            identity = key(row)
            if not identity:
                continue
            received = local_datetime(row.get('_received_at')) or local_datetime(row.get('In-Time')) or local_datetime(row.get('Date'))
            completed = local_datetime(row.get('Out Time')) or local_datetime(row.get('Completed Time'))
            month = str(row.get('_month') or '')
            rank = (month if re.fullmatch(r'\d{4}-\d{2}', month) else (received.strftime('%Y-%m') if received else ''),
                    received or datetime.min, completed or datetime.min)
            if identity not in orders or rank >= orders[identity][0]:
                orders[identity] = (rank, row, period['Date'], completed)
    result, missing_dates = defaultdict(list), 0
    for _, row, arrival_day, completed in orders.values():
        if order_status(row) not in ('completed and delivered', 'completed'):
            continue
        if use_report_date:
            date = arrival_day
        elif completed:
            date = completed.date().isoformat()
        else:
            missing_dates += 1
            date = arrival_day
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(date)):
            result[date].append(row)
    return result, missing_dates


def order_status(row):
    return ' '.join(str(row.get('Status') or row.get('Task Status') or '').casefold().split())


def capacity_date(value):
    """Weekend activity belongs to the preceding Friday, including month ends."""
    try:
        day = datetime.strptime(str(value), '%Y-%m-%d').date()
    except ValueError:
        return None
    return (day - timedelta(days=day.weekday()-4) if day.weekday() >= 5 else day).isoformat()


def capacity_periods(periods):
    days = {}
    for period in periods:
        date = capacity_date(period['Date'])
        if date is None:
            continue
        day = days.setdefault(date, dict(Date=date, rows=[], **{column: 0 for column in COUNTS}))
        for column in COUNTS:
            day[column] += int(period.get(column, 0) or 0)
        day['rows'].extend(dict(row, **{'Source received date': period['Date'], 'Capacity date': date})
                           for row in period.get('rows', []))
    return days


def capacity_completions(periods, *, use_report_date=False):
    completed, missing = completion_rows(periods, use_report_date=use_report_date)
    result = defaultdict(list)
    for source_date, rows in completed.items():
        date = capacity_date(source_date)
        if date:
            result[date].extend(dict(row, **{'Capacity date': date}) for row in rows)
    return result, missing


def pending_bucket(row):
    status = order_status(row)
    return ('Clarification' if status == 'awaiting for clarification' else
            'Vendor Pending' if status == 'assign to abs' else 'In-House Pending')


def capacity_ledger(reports, include_rows=False, *, use_report_date=False):
    """Count source statuses by report date for imports, completion time for trackers."""
    periods = reports.get('daily', [])
    days = capacity_periods(periods)
    has_rows = all(isinstance(period.get('rows'), list) for period in periods)
    missing_dates = 0
    completed = {}
    if has_rows:
        completed, missing_dates = capacity_completions(periods, use_report_date=use_report_date)
        for date in completed:
            days.setdefault(date, dict(Date=date, rows=[], **{column: 0 for column in COUNTS}))
    result = []
    for date in sorted(days):
        day = days[date]
        received = day.pop('rows')
        if has_rows:
            pending = [row for row in received if order_status(row) not in
                       ('completed and delivered', 'completed', 'cancelled', 'canceled')]
            day['Received'] = len(received)
            day['Completed'] = len(completed.get(date, []))
            day['Cancelled'] = sum(order_status(row) in ('cancelled', 'canceled') for row in received)
            for column in PENDING:
                day[column] = sum(pending_bucket(row) == column for row in pending)
            if include_rows:
                day['_received_rows'] = received
                day['_completed_rows'] = completed.get(date, [])
                day['_pending_rows'] = pending
        # Retain these response fields for older clients without adding carryover.
        day['Raw Received'] = day['Received']
        day['Rollover Received'] = 0
        result.append(day)
    return result, missing_dates


def capacity_days(reports, *, use_report_date=False):
    return capacity_ledger(reports, use_report_date=use_report_date)


def capacity_total(rows, label, columns=COUNTS):
    """All activity/status columns sum the selected dates without carryover."""
    return dict(Date=label, **{column: sum(int(row.get(column, 0) or 0) for row in rows)
                              for column in columns})


def capacity_details(reports, date, *, use_report_date=False):
    """Return the exact receipts, completions and status rows behind a date."""
    days, _ = capacity_ledger(reports, include_rows=True, use_report_date=use_report_date)
    index = next((i for i, day in enumerate(days) if day['Date'] == date), None)
    if index is None:
        raise ValueError('That date is no longer in the capacity report. Refresh the report and try again.')
    periods = reports.get('daily', [])
    if not all(isinstance(period.get('rows'), list) for period in periods):
        raise ValueError('Order details are unavailable for this report. Refresh the report and try again.')
    day = days[index]
    received, pending = day['_received_rows'], day['_pending_rows']
    groups = [
        {'key': 'received', 'label': 'Received', 'rows': received,
         'description': 'Orders received on this reporting date. Saturday and Sunday receipts are included on the preceding Friday.'},
        {'key': 'completed', 'label': 'Completed', 'rows': day['_completed_rows'],
         'description': ('Orders whose Status is Completed and Delivered, grouped by report Date; In-Time is used when the report Date is missing or invalid. '
                         if use_report_date else
                         'Completed orders use Out Time or Completed Time; missing completion dates use the received date. ')
                        + 'Saturday and Sunday activity is included on the preceding Friday.'},
        {'key': 'clarification', 'label': 'Clarification',
         'rows': [row for row in pending if pending_bucket(row) == 'Clarification']},
        {'key': 'cancelled', 'label': 'Cancelled',
         'rows': [row for row in received if order_status(row) in ('cancelled', 'canceled')]},
        {'key': 'vendor', 'label': 'Vendor Pending',
         'rows': [row for row in pending if pending_bucket(row) == 'Vendor Pending']},
        {'key': 'in_house', 'label': 'In-House Pending',
         'rows': [row for row in pending if pending_bucket(row) == 'In-House Pending']},
    ]
    columns = list(dict.fromkeys(['Source received date', 'Capacity date'] + [
        column for period in periods for column in period.get('columns', []) if not column.startswith('_')]))
    return {'date': date, 'previous_date': days[index-1]['Date'] if index else None,
            'next_date': days[index+1]['Date'] if index+1 < len(days) else None,
            'raw_received': day['Received'], 'rollover_received': 0,
            'counts': {column: day.get(column, 0) for column in COUNTS},
            'columns': columns, 'groups': groups}
