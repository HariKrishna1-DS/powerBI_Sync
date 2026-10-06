"""One reporting vocabulary for tracker data, Excel imports and cloud views.

Daily rows are received-date cohorts. Each order belongs to exactly one status
bucket; SLA outcomes are a subset of completed orders, not another status bucket.
"""
from collections import Counter
from datetime import datetime

DAILY_COLUMNS = ['Date', 'Received', 'Completed', 'Clarification', 'Cancelled',
                 'Vendor Pending', 'In-House Pending', 'On time SLA', 'Missed SLA']
CAPACITY_COLUMNS = DAILY_COLUMNS[:7] + ['Capacity', 'Ext capacity']
STATUS_COLUMNS = DAILY_COLUMNS[2:7]


def normalized(value):
    return ' '.join(str(value or '').casefold().split())


def status_bucket(row):
    status = normalized(row.get('Status'))
    if status in ('completed and delivered', 'completed & delivered', 'completed', 'delivered'):
        return 'Completed'
    if status in ('cancelled', 'canceled'):
        return 'Cancelled'
    if status in ('awaiting for clarification', 'awaiting clarification', 'clarification'):
        return 'Clarification'
    if status in ('assign to abs', 'assigned to abs', 'assign to abs.', 'assigned to abs.'):
        return 'Vendor Pending'
    return 'In-House Pending'


def completion_inferred(row):
    return normalized(row.get('Completion Evidence')).startswith('inferred')


def counts(rows):
    from production_timing import sla_result
    buckets = Counter(status_bucket(row) for row in rows)
    result = {'Received': len(rows), **{name: buckets[name] for name in STATUS_COLUMNS},
              'On time SLA': 0, 'Missed SLA': 0, 'SLA Unclassified': 0,
              'Inferred Completions': 0}
    for row in rows:
        if status_bucket(row) != 'Completed':
            continue
        inferred = completion_inferred(row)
        result['Inferred Completions'] += inferred
        # Imported synonyms share the same strict timing rule.
        outcome, _ = sla_result(dict(row, Status='Completed and Delivered'))
        override = normalized(row.get('Free Site'))
        if outcome and override in ('on time', 'missing', 'missed'):
            outcome = 'On Time' if override == 'on time' else 'Missing'
        if inferred or not outcome:
            result['SLA Unclassified'] += 1
        else:
            result['On time SLA' if outcome == 'On Time' else 'Missed SLA'] += 1
    return result


def enrich_reports(reports):
    for kind in ('daily', 'monthly'):
        for report in reports.get(kind, []):
            report.update(counts(report.get('rows', [])))
    return reports


def capacity_report(daily, targets=None, default_capacity=None, default_extended=None, year=None):
    """Sum only explicitly represented days; never invent historical staffing."""
    targets = targets or {}
    days = []
    months = {}
    for report in daily:
        date = report['Date']
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            continue
        selected = targets.get(date, {})
        row = {name: report.get(name, 0) for name in DAILY_COLUMNS[:7]}
        row.update(Capacity=selected.get('capacity', default_capacity),
                   **{'Ext capacity': selected.get('extended', default_extended)})
        days.append(row)
        month = months.setdefault(date[:7], {'Date': date[:7], **{c: 0 for c in CAPACITY_COLUMNS[1:]}, 'Target Days': 0, 'Days': 0})
        month['Days'] += 1
        month['Target Days'] += row['Capacity'] is not None and row['Ext capacity'] is not None
        for column in CAPACITY_COLUMNS[1:]:
            month[column] += row.get(column) or 0
    year = year or (max(months)[:4] if months else str(datetime.now().year))
    yearly = {'Date': f'{year} YTD', **{c: sum(m[c] for period, m in months.items() if period.startswith(year + '-')) for c in CAPACITY_COLUMNS[1:]}}
    return {'daily': days, 'monthly': sorted(months.values(), key=lambda r: r['Date'], reverse=True), 'ytd': yearly,
            'basis': 'Received-date cohorts; targets total only represented reporting days.'}


def report_matrices(snapshot, capacity):
    reports = snapshot['reports']
    def capacity_rows(rows):
        return [[row.get(c, '') if row.get(c) is not None else '' for c in CAPACITY_COLUMNS] for row in rows]
    capacity_values = [CAPACITY_COLUMNS] + capacity_rows(capacity['monthly'] + [capacity['ytd']])
    if capacity['daily']:
        # Separate totals from a contiguous, labelled daily chart source.
        capacity_values += [[''] * len(CAPACITY_COLUMNS), CAPACITY_COLUMNS] + capacity_rows(capacity['daily'])
    return {
        'Daily Orders': [DAILY_COLUMNS] + [[row.get(c, '') for c in DAILY_COLUMNS] for row in reports['daily']],
        'Monthly Orders': [['Month'] + DAILY_COLUMNS[1:]] + [[row.get('Month', '')] + [row.get(c, '') for c in DAILY_COLUMNS[1:]] for row in reports['monthly']],
        'Capacity Report': capacity_values,
    }
