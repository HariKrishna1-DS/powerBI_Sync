"""Capacity receipts and completions on their recorded source dates."""
from collections import defaultdict
from datetime import datetime, timedelta
import re

COUNTS = ['Received', 'Completed', 'Clarification', 'Cancelled', 'Vendor Pending', 'In-House Pending']
PENDING = ('Clarification', 'Vendor Pending', 'In-House Pending')


def completion_rows(periods, *, use_report_date=False, out_time_only=False):
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
            completed = local_datetime(row.get('Out Time'))
            if not out_time_only:
                completed = completed or local_datetime(row.get('Completed Time'))
            month = str(row.get('_month') or '')
            rank = (month if re.fullmatch(r'\d{4}-\d{2}', month) else (received.strftime('%Y-%m') if received else ''),
                    received or datetime.min, completed or datetime.min)
            if identity not in orders or rank >= orders[identity][0]:
                orders[identity] = (rank, row, period['Date'], completed)
    result, missing_dates = defaultdict(list), 0
    for _, row, arrival_day, completed in orders.values():
        statuses = ('completed and delivered',) if out_time_only else ('completed and delivered', 'completed')
        if order_status(row) not in statuses:
            continue
        if completed:
            date = completed.date().isoformat()
        else:
            missing_dates += 1
            if out_time_only:
                continue
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


def capacity_completions(periods, *, use_report_date=False, out_time_only=False):
    completed, missing = completion_rows(periods, use_report_date=use_report_date, out_time_only=out_time_only)
    result = defaultdict(list)
    for source_date, rows in completed.items():
        date = capacity_date(source_date)
        if date:
            result[date].extend(dict(row, **{'Source completion date': source_date, 'Capacity date': date}) for row in rows)
    return result, missing


def pending_bucket(row):
    status = order_status(row)
    return ('Clarification' if status == 'awaiting for clarification' else
            'Vendor Pending' if status == 'assign to abs' else 'In-House Pending')


def capacity_ledger(reports, include_rows=False, *, use_report_date=False, out_time_only=False):
    """Count receipts by source date and completions by their completion time."""
    periods = reports.get('daily', [])
    days = capacity_periods(periods)
    has_rows = all(isinstance(period.get('rows'), list) for period in periods)
    missing_dates = 0
    completed = {}
    if has_rows:
        completed, missing_dates = capacity_completions(periods,
            use_report_date=use_report_date, out_time_only=out_time_only)
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


def capacity_days(reports, *, use_report_date=False, out_time_only=False):
    return capacity_ledger(reports, use_report_date=use_report_date, out_time_only=out_time_only)


def capacity_total(rows, label, columns=COUNTS):
    """All activity/status columns sum the selected dates without carryover."""
    return dict(Date=label, **{column: sum(int(row.get(column, 0) or 0) for row in rows)
                              for column in columns})


def capacity_details(reports, date='', *, month='', year='', use_report_date=False, out_time_only=False):
    """Return the exact rows behind a daily, monthly or YTD count."""
    days, _ = capacity_ledger(reports, include_rows=True, use_report_date=use_report_date, out_time_only=out_time_only)
    selected = [day for day in days if day['Date'] == date] if date else [
        day for day in days if day['Date'].startswith(month or year)]
    if date and not selected:
        raise ValueError('That date is no longer in the capacity report. Refresh the report and try again.')
    periods = reports.get('daily', [])
    if not all(isinstance(period.get('rows'), list) for period in periods):
        raise ValueError('Order details are unavailable for this report. Refresh the report and try again.')
    day = capacity_total(selected, date or month or year)
    received = [row for item in selected for row in item['_received_rows']]
    pending = [row for item in selected for row in item['_pending_rows']]
    completed = [row for item in selected for row in item['_completed_rows']]
    completion_description = (
        'Orders with status Completed and Delivered count by Out Time, including orders received in previous months. '
        'Saturday and Sunday completions are included on the preceding Friday. '
        'Orders without a valid Out Time are excluded from completed counts.' if out_time_only else
        'Completed orders use Out Time or Completed Time, including orders received in previous months; missing completion dates use the received date. '
        'Saturday and Sunday activity is included on the preceding Friday.')
    groups = [
        {'key': 'received', 'label': 'Received', 'rows': received,
         'description': 'Orders received in this reporting period. Saturday and Sunday receipts are included on the preceding Friday.'},
        {'key': 'completed', 'label': 'Completed', 'rows': completed,
         'description': completion_description},
        {'key': 'clarification', 'label': 'Clarification',
         'rows': [row for row in pending if pending_bucket(row) == 'Clarification']},
        {'key': 'cancelled', 'label': 'Cancelled',
         'rows': [row for row in received if order_status(row) in ('cancelled', 'canceled')]},
        {'key': 'vendor', 'label': 'Vendor Pending',
         'rows': [row for row in pending if pending_bucket(row) == 'Vendor Pending']},
        {'key': 'in_house', 'label': 'In-House Pending',
         'rows': [row for row in pending if pending_bucket(row) == 'In-House Pending']},
    ]
    columns = list(dict.fromkeys(['Source received date', 'Source completion date', 'Capacity date'] + [
        column for period in periods for column in period.get('columns', []) if not column.startswith('_')]))
    index = days.index(selected[0]) if date else None
    return {'date': date, 'period': date or month or year,
            'completion_date_basis': 'out_time' if out_time_only else 'completion_time',
            'previous_date': days[index-1]['Date'] if index else None,
            'next_date': days[index+1]['Date'] if index is not None and index+1 < len(days) else None,
            'raw_received': day['Received'], 'rollover_received': 0,
            'counts': {column: day.get(column, 0) for column in COUNTS},
            'columns': columns, 'groups': groups}
