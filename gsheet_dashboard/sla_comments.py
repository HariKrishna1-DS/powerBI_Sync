"""Stable identities and display values for editable monthly SLA results."""
from datatrace_sync import parse_report_datetime, sla_expiration


def sla_status(value):
    value = str(value or '').strip().casefold().replace(' ', '')
    if value in ('ontime', 'onetime'):
        return 'On Time'
    if value in ('missed', 'missing'):
        return 'Missing'
    return ''


def sla_key(row):
    # Completion timestamps retain the time; identity includes its calendar day.
    out = parse_report_datetime(row.get('Out Time', ''))
    return (str(row.get('Order Number', '')).strip(), out.date().isoformat() if out else '')


def sla_entry(row, status):
    identity, completion = sla_key(row)
    product = str(row.get('Product', '')).strip()
    group = 'Full Title' if ' '.join(product.casefold().split()) in ('full title', 'full search') else 'Remaining Products'
    expiration = sla_expiration(row)
    return {
        'Order Number': identity,
        'Product': product,
        'Product Group': group,
        'In Time': next((row.get(c) for c in ('Arrival Time', 'In-Time', 'In Time', 'RequestArrivalTime') if row.get(c)), ''),
        'Out Time': row.get('Out Time', ''),
        'SLA Expiration': expiration.strftime('%m/%d/%Y %I:%M %p') if expiration else row.get('SLA Expiration*', row.get('SLA Expiration', '')),
        'Free Site': status,
        'completion_date': completion,
        'source': 'Google Sheets' if row.get('_sheet') else 'Saved history',
    }
