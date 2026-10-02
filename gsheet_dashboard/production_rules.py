"""Production tracker rules. Missing queue rows are never evidence of completion."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import re

IST = timezone(timedelta(hours=5, minutes=30))
TRACKER_COLUMNS = ['No', 'Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
                   'Online/Ground', 'Product', 'Status', 'ETA', 'Comments', 'Assignee', 'Searcher',
                   'Clarification Requested', 'Shift', 'Process date', 'Review/QC', 'Expense',
                   'In-Time', 'Out Time', 'SLA Expiration', 'Free Site', 'review']
ALIASES = {
    'Date': ('Date', 'Arrival Date'), 'State': ('State', 'St'),
    'Client': ('Client', 'ClientCode'), 'Online/Ground': ('Online/Ground', 'Online/ Ground'),
    'Comments': ('Comments', 'Comment', 'ETA Comments'), 'Assignee': ('Assignee', 'Last User'),
    'In-Time': ('In-Time', 'Arrival Time', 'RequestArrivalTime'),
    'SLA Expiration': ('SLA Expiration', 'SLA Expiration*'),
}
DRIVING = ('Task Name', 'Task Status', 'Status', 'WorkflowSuspended', 'Is Suspended', 'Completed Time')


def text(value):
    return '' if value is None else str(value).strip()


def order_key(value):
    return text(value).casefold()


def field(row, name):
    return next((row[c] for c in ALIASES.get(name, (name,)) if c in row), None)


def capture_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(IST).replace(tzinfo=None)


def timestamp(value):
    value = text(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(IST).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        pass
    for pattern in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
                    '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%m/%d/%Y'):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass
    return None


def expiration(value, anchor):
    value = text(value)
    absolute = timestamp(value)
    if absolute:
        return absolute
    # The sign applies to the entire duration, including all its components.
    match = re.fullmatch(r'(-)?(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?', value, re.I)
    if match and any(match.groups()[1:]):
        if anchor is None:
            return None
        days, hours, minutes = (int(v or 0) for v in match.groups()[1:])
        delta = timedelta(days=days, hours=hours, minutes=minutes)
        return anchor - delta if match.group(1) else anchor + delta
    if anchor:
        for pattern in ('%Y/%m/%d %I:%M %p', '%Y/%m/%d %H:%M'):
            try:
                return datetime.strptime(f'{anchor.year}/{value}', pattern)
            except ValueError:
                pass
    return None


def free_site(row):
    if not text(row.get('Out Time')):
        return '', None
    out, sla = timestamp(row.get('Out Time')), timestamp(row.get('SLA Expiration'))
    if out is None or sla is None:
        return '', 'Out Time or SLA Expiration is missing or is not a date and time.'
    return ('On Time' if out <= sla else 'Missing'), None


def suspended(row):
    flags = [row[c] for c in ('WorkflowSuspended', 'Is Suspended') if c in row]
    return (any(text(v).casefold() in ('true', '1', 'yes') for v in flags)
            or text(row.get('Task Status')).casefold() == 'workflow suspended')


def mapped_status(row, existing='Search In Progress'):
    if suspended(row):
        return 'Awaiting for Clarification'
    if (text(row.get('Task Name')).casefold() == 'search'
            and text(row.get('Task Status')).casefold() == 'available'):
        return 'Search In Progress'
    return existing


def full_title(row):
    return ' '.join(text(row.get('Product')).casefold().split()) in ('full title', 'full search')


def merge_trackers(preview, previous, tracker_rows):
    """Return stable rows and a pass report; never mutate inputs or manual fields."""
    anchor = capture_time(preview['created'])
    output = [[dict(row) for row in rows] for rows in tracker_rows]
    existing = {}
    for group, rows in enumerate(output):
        for index, row in enumerate(rows):
            key = order_key(row.get('Order Number'))
            if not key:
                continue
            if key in existing:
                raise ValueError(f'Duplicate tracker Order Number: {row["Order Number"]}. Fix the duplicate before syncing.')
            existing[key] = (group, index)
    prior = {order_key(row.get('Order Number')): row for row in (previous or {}).get('rows', [])}
    counts = Counter(order_key(row.get('Order Number')) for row in preview['rows'])
    incoming_keys = set(counts) - {''}
    report = {'preview_name': preview['name'], 'timestamp': preview['created'],
              'scanned': len(preview['rows']), 'added': 0, 'updated': 0, 'unchanged': 0,
              'updates': [], 'not_in_latest': [], 'unprocessed': [], 'ambiguous': [], 'processed_orders': []}
    report['not_in_latest'] = [text(row.get('Order Number')) for key, row in prior.items()
                               if key and key not in incoming_keys]
    for group, rows in enumerate(output):
        serials = [text(row.get('No')) for row in rows if order_key(row.get('Order Number'))]
        if serials != [str(number) for number in range(1, len(serials) + 1)]:
            report['ambiguous'].append({'order': '', 'reason': f'Tracker {group + 1} has existing invalid or discontinuous No serials; values retained.'})
        for row in rows:
            if any('#REF!' in text(value) for value in row.values()):
                report['ambiguous'].append({'order': text(row.get('Order Number')), 'reason': 'Existing tracker formula has a #REF! error; manual cells retained.'})
    for raw in preview['rows']:
        identity = text(raw.get('Order Number'))
        key = order_key(identity)
        if not key or counts[key] > 1:
            report['unprocessed'].append({'order': identity, 'reason': 'Blank or duplicate Order Number in preview.'})
            continue
        is_new = key not in existing
        if is_new and not text(raw.get('Product')):
            report['unprocessed'].append({'order': identity, 'reason': 'Product is required to route a new order.'})
            continue
        group = 0 if full_title(raw) else 1
        if is_new:
            serials = [int(text(row.get('No'))) for row in output[group] if text(row.get('No')).isdigit()]
            row = dict.fromkeys(TRACKER_COLUMNS, '')
            row['No'] = max(serials, default=0) + 1
            for name in ('Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
                         'Online/Ground', 'Product', 'ETA', 'Comments', 'Assignee', 'In-Time', 'SLA Expiration'):
                row[name] = field(raw, name) if field(raw, name) is not None else ''
            if not row['Date']:
                arrived = timestamp(row['In-Time'])
                row['Date'] = arrived.strftime('%m/%d/%Y') if arrived else ''
            row['Status'] = mapped_status(raw)
            output[group].append(row)
            existing[key] = (group, len(output[group]) - 1)
            before = None
        else:
            old_group, index = existing[key]
            if 'Product' in raw and text(raw['Product']) and old_group != group:
                report['unprocessed'].append({'order': identity, 'reason': 'Product changed tracker; keep the original row for review.'})
                continue
            group = old_group
            row = output[group][index]
            before = dict(row)
            old_raw = prior.get(key)
            if old_raw is None or any(text(raw.get(c)).casefold() != text(old_raw.get(c)).casefold() for c in DRIVING):
                row['Status'] = mapped_status(raw, row.get('Status', ''))
            for name in ('ETA', 'Comments', 'Assignee', 'SLA Expiration'):
                value = field(raw, name)
                if value is not None:
                    row[name] = value
            if text(row.get('Status')).casefold() == 'completed and delivered':
                completed = timestamp(raw.get('Completed Time'))
                if completed:
                    row['Out Time'] = completed.strftime('%m/%d/%Y %I:%M:%S %p')
                elif text(raw.get('Completed Time')):
                    report['ambiguous'].append({'order': identity, 'reason': 'Completed Time is not a timestamp; Out Time retained.'})
        sla_text = text(row.get('SLA Expiration'))
        negative_sla = sla_text.startswith('-')
        sla = expiration(sla_text, anchor)
        if sla:
            row['SLA Expiration'] = sla.strftime('%m/%d/%Y %I:%M:%S %p')
        elif sla_text:
            report['ambiguous'].append({'order': identity, 'reason': f'Ambiguous SLA: {sla_text}'})
        row['Free Site'], reason = free_site(row)
        if negative_sla and row['Free Site']:
            row['Free Site'] = 'Missing'
        if reason:
            report['ambiguous'].append({'order': identity, 'reason': reason})
        report['processed_orders'].append(identity)
        if is_new:
            report['added'] += 1
        elif row != before:
            report['updated'] += 1
            report['updates'].append({'order': identity, 'old_status': before.get('Status', ''),
                                      'new_status': row.get('Status', '')})
        else:
            report['unchanged'] += 1
    return output, report
