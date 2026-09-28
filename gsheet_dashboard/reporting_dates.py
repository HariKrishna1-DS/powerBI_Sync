"""Reporting dates from portal arrival timestamps, without timezone conversion."""
from datetime import datetime


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
