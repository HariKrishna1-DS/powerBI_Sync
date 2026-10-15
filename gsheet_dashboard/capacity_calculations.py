"""Capacity workload by received day and actual completion day."""
from collections import defaultdict
from datetime import datetime, timedelta
import re

COUNTS = ['Received', 'Completed', 'Clarification', 'Cancelled', 'Vendor Pending', 'In-House Pending']


def completion_rows(periods):
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
        if completed:
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


def capacity_completions(periods):
    completed, missing = completion_rows(periods)
    result = defaultdict(list)
    for source_date, rows in completed.items():
        date = capacity_date(source_date)
        if date:
            result[date].extend(dict(row, **{'Capacity date': date}) for row in rows)
    return result, missing


def capacity_days(reports):
    periods = reports.get('daily', [])
    days = capacity_periods(periods)
    missing_dates = 0
    # Summary-only callers have no completion dates to inspect. Preserve their
    # supplied Completed counts rather than inferring dates from counts.
    if periods and all(isinstance(period.get('rows'), list) for period in periods):
        completed, missing_dates = capacity_completions(periods)
        for day in days.values():
            day['Completed'] = 0
        for date, rows in completed.items():
            day = days.setdefault(date, dict(Date=date, **{column: 0 for column in COUNTS}))
            day['Completed'] = len(rows)
    ordered = [days[date] for date in sorted(days)]
    previous_pending = 0
    for day in ordered:
        day['Raw Received'] = int(day.get('Received', 0) or 0)
        day['Rollover Received'] = previous_pending
        day['Received'] = day['Raw Received'] + previous_pending
        previous_pending = int(day.get('Clarification', 0) or 0) + int(day.get('Vendor Pending', 0) or 0)
    return ordered, missing_dates


def capacity_details(reports, date):
    """Explain one capacity row without changing source selection or Sheets."""
    days, _ = capacity_days(reports)
    index = next((i for i, day in enumerate(days) if day['Date'] == date), None)
    if index is None:
        raise ValueError('That date is no longer in the capacity report. Refresh the report and try again.')
    periods = reports.get('daily', [])
    if not all(isinstance(period.get('rows'), list) for period in periods):
        raise ValueError('Order details are unavailable for this report. Refresh the report and try again.')
    by_date = {date: period['rows'] for date, period in capacity_periods(periods).items()}
    previous_date = days[index - 1]['Date'] if index else None
    next_date = days[index + 1]['Date'] if index + 1 < len(days) else None
    completed, _ = capacity_completions(periods)
    received = by_date.get(date, [])
    rollover = [row for row in by_date.get(previous_date, [])
                if order_status(row) in ('awaiting for clarification', 'assign to abs')]
    workload = [dict(row, **{'Workload source': 'Newly received'}) for row in received]
    workload += [dict(row, **{'Workload source': 'Carried from ' + previous_date}) for row in rollover]
    groups = [
        {'key': 'received', 'label': 'Received workload', 'rows': workload,
         'description': 'New receipts plus Clarification and Vendor Pending from the previous reporting date.'},
        {'key': 'new', 'label': 'Newly received', 'rows': received},
        {'key': 'rollover', 'label': 'Carryover', 'rows': rollover},
        {'key': 'completed', 'label': 'Completed', 'rows': completed.get(date, []),
         'description': 'Completed orders use Out Time or Completed Time; missing completion dates use the received date. Saturday and Sunday activity is included on the preceding Friday.'},
        {'key': 'next_added', 'label': 'Added next reporting date', 'rows': by_date.get(next_date, []),
         'description': 'New receipts on the next available reporting date; carryover is excluded.'},
        {'key': 'next_completed', 'label': 'Completed next reporting date', 'rows': completed.get(next_date, [])},
    ]
    columns = list(dict.fromkeys(['Workload source', 'Source received date', 'Capacity date'] + [
        column for period in periods for column in period.get('columns', []) if not column.startswith('_')]))
    return {'date': date, 'previous_date': previous_date, 'next_date': next_date,
            'raw_received': days[index]['Raw Received'], 'rollover_received': days[index]['Rollover Received'],
            'counts': {column: days[index].get(column, 0) for column in COUNTS},
            'columns': columns, 'groups': groups}
