"""Reporting dates from portal arrival timestamps, without timezone conversion."""
from datetime import datetime


def arrival_details(row):
    """Keep source arrival wall-clock values; never substitute capture time."""
    from monthly_production import local_datetime
    import re
    values = {re.sub(r'[^a-z0-9]', '', str(key).casefold()): value for key, value in row.items()}
    def value(name):
        return values.get(re.sub(r'[^a-z0-9]', '', name.casefold()), '')
    timestamps = [value(name) for name in ('Arrival Time', 'RequestArrivalTime', 'In-Time')]
    timestamp = next((raw for raw in timestamps if local_datetime(raw)), '')
    received = next((parsed for name in ('Arrival Date', 'Date')
                     if (parsed := local_datetime(value(name)))), None) or local_datetime(timestamp)
    # Some Excel reports put the full timestamp in Date and have no In-Time.
    if not timestamp and received and (received.hour or received.minute or received.second):
        timestamp = next((value(name) for name in ('Arrival Date', 'Date') if local_datetime(value(name))), '')
    return {'Arrival Date': received.date().isoformat() if received else '',
            'Arrival Time': str(timestamp).strip() if timestamp else ''}


def arrival_date(row):
    for column in ('Arrival Time', 'RequestArrivalTime', 'Arrival Date'):
        value = str(row.get(column, '') or '').strip()
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
        except ValueError:
            for pattern in ('%m/%d/%Y %I:%M %p', '%m/%d/%Y %I:%M:%S %p',
                            '%m/%d/%Y %H:%M:%S', '%m/%d/%Y'):
                try:
                    return datetime.strptime(value, pattern).date().isoformat()
                except ValueError:
                    continue
    return None


def reporting_date(preview):
    dates = [day for row in preview['rows'] if (day := arrival_date(row))]
    return max(dates) if dates else datetime.fromisoformat(preview['created']).astimezone().date().isoformat()
