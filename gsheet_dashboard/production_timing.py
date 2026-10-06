"""Completion and SLA eligibility shared by sync, reports and maintenance."""
from datetime import datetime
import re


def status(row):
    return ' '.join(str(row.get('Status', '') or '').casefold().split())


def completed(row):
    return status(row) == 'completed and delivered'


def precise_timestamp(value):
    """Dates alone and elapsed hours are not enough to judge an SLA boundary.

    Imported sheet times are local wall clocks. A datetime value (including
    midnight) or a fractional Excel serial has explicit time precision.
    """
    from monthly_production import local_datetime
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    raw = re.sub(r'\s+', ' ', str(value or '')).strip()
    if re.fullmatch(r'\d{5}\.\d+', raw):
        return None if float(raw).is_integer() else local_datetime(raw)
    if not re.search(r'\d{1,2}:\d{2}', raw):
        return None
    return local_datetime(raw)


def sla_eligible(row):
    return bool(sla_result(row)[0])


def sla_review_reason(row):
    """Explain unavailable timing without inventing completion or SLA evidence."""
    from report_metrics import status_bucket, completion_inferred
    if status_bucket(row) != 'Completed':
        return ''
    if completion_inferred(row):
        return 'Completion inferred from queue absence; delivery needs verification'
    if not str(row.get('Out Time', '') or '').strip():
        return 'Out Time is missing'
    if precise_timestamp(row.get('Out Time')) is None:
        return 'Out Time needs a valid date and time (a date alone is insufficient)'
    if not str(row.get('SLA Expiration', '') or '').strip():
        return 'SLA Expiration is missing'
    outcome, reason = sla_result(dict(row, Status='Completed and Delivered'))
    return '' if outcome else (reason or 'SLA Expiration needs a valid date and time')


def sla_result(row, anchor=None):
    from tracker_sync import deadline
    if not completed(row):
        return '', None
    if not str(row.get('Out Time', '') or '').strip():
        return '', None
    out = precise_timestamp(row.get('Out Time'))
    raw_due = str(row.get('SLA Expiration', '') or '').strip()
    # Absolute dates require a time; relative countdowns require their capture anchor.
    relative = bool(re.fullmatch(r'-?(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?', raw_due, re.I) and re.search(r'\d+[dhm]', raw_due, re.I))
    due = deadline(raw_due, anchor) if relative else precise_timestamp(raw_due)
    if due is None and anchor and re.fullmatch(r'\d{1,2}/\d{1,2} \d{1,2}:\d{2}(?::\d{2})?(?: [AP]M)?', raw_due, re.I):
        due = deadline(raw_due, anchor)
    if out is None or due is None:
        return '', 'Completion time or SLA deadline lacks a valid date and time'
    from monthly_production import local_datetime
    arrival = local_datetime(row.get('In-Time', row.get('Arrival Time')))
    if arrival and out < arrival:
        return '', 'Out Time precedes In-Time; review completion evidence'
    return ('On Time' if out <= due else 'Missing'), None
