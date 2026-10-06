"""Completion inferred from archived queue transitions, using capture time in IST."""
from collections import Counter, defaultdict
import re
from datetime import datetime


def valid_queue(rows):
    from tracker_sync import key
    keys = [key(row) for row in rows]
    trusted = all(str(row.get('Capture Verified', '')).strip().casefold() not in ('false', '0', 'unverified') for row in rows)
    return trusted and bool(keys) and all(keys) and len(keys) == len(set(keys))


def missing_completion(row, out, previous=None):
    """Preserve manual timestamps and terminal exceptions; return a changed row."""
    from production_timing import precise_timestamp, status
    from monthly_production import local_datetime
    result = dict(row)
    if status(row) in ('cancelled', 'canceled', 'task suspended', 'workflow suspended'):
        return result
    arrival = local_datetime(row.get('In-Time') or row.get('Date'))
    if out is None or (arrival and out < arrival):
        return result
    result['Status'] = 'Completed and Delivered'
    if not precise_timestamp(row.get('Out Time')):
        result['Out Time'] = out.strftime('%m/%d/%Y %I:%M:%S %p')
        result['Completion Evidence'] = 'Inferred from queue absence'
    elif precise_timestamp(row.get('Out Time')) == out and not row.get('Completion Evidence'):
        result['Completion Evidence'] = 'Inferred from queue absence'
    # A countdown is relative to the last preview that actually contained the order.
    from tracker_sync import deadline, value
    if previous and not precise_timestamp(result.get('SLA Expiration')):
        due = deadline(value(previous[0], 'SLA Expiration'), previous[1])
        if due:
            result['SLA Expiration'] = due.strftime('%m/%d/%Y %I:%M:%S %p')
    return result


def reconcile_completions(trackers, history):
    """Use the first absence in the current absent run; never the repair wall clock.

    Empty/duplicate/malformed snapshots break comparison continuity. Previously
    inferred completion is reopened only when its exact timestamp has evidence
    in this archive and the order returns. Unrelated manual times are retained.
    """
    from tracker_sync import key
    from production_timing import precise_timestamp, sla_result, status
    groups = defaultdict(list)
    for row in history:
        name = str(row.get('Preview', ''))
        if re.fullmatch(r'preview[1-9]\d*', name):
            groups[int(name[7:])].append(row)
    absent, inferred, present = {}, defaultdict(set), {}
    previous, previous_time = None, None
    for number in sorted(groups):
        rows = groups[number]
        def capture_time(raw):
            parsed = precise_timestamp(raw)
            if parsed is None:
                return None
            try:
                iso = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
                if iso.tzinfo is not None:
                    from tracker_sync import IST
                    parsed = iso.astimezone(IST).replace(tzinfo=None)
            except ValueError:
                pass
            return parsed.replace(microsecond=0)
        times = {capture_time(row.get('Preview Timestamp')) for row in rows}
        stamp = next(iter(times)) if len(times) == 1 else None
        if not valid_queue(rows) or stamp is None or (previous_time and stamp <= previous_time):
            previous, previous_time = None, None
            absent.clear()
            present = {}
            continue
        present = {key(row): row for row in rows}
        for identity in present:
            absent.pop(identity, None)
        if previous is not None:
            for identity in previous.keys() - present.keys():
                absent[identity] = (stamp, previous[identity], previous_time)
                inferred[identity].add(stamp)
        previous, previous_time = present, stamp
    result, changes = {}, []
    counts = Counter(key(row) for rows in trackers.values() for row in rows if key(row))
    for title, rows in trackers.items():
        from monthly_production import tab_identity, ARCHIVE
        month = tab_identity(title)
        if month and month[1] <= ARCHIVE:
            result[title] = [dict(row) for row in rows]
            continue
        result[title] = []
        for row in rows:
            changed = dict(row)
            identity = key(row)
            if counts[identity] == 1 and status(row) not in ('cancelled', 'canceled', 'task suspended', 'workflow suspended'):
                if identity in absent:
                    out, raw, stamp = absent[identity]
                    if precise_timestamp(row.get('Out Time')) in inferred[identity] and precise_timestamp(row.get('Out Time')) != out:
                        changed['Out Time'] = ''
                    changed = missing_completion(changed, out, (raw, stamp))
                elif identity in present and precise_timestamp(row.get('Out Time')) in inferred[identity] and not (
                        status(present[identity]) == 'completed and delivered' and (
                            precise_timestamp(present[identity].get('Out Time')) or precise_timestamp(present[identity].get('Completed Time')))):
                    from tracker_sync import mapped_status
                    changed['Status'] = mapped_status(present[identity], new=True)
                    changed['Out Time'] = ''
                    changed['Completion Evidence'] = ''
            sla, _ = sla_result(changed)
            if sla or 'Free Site' in changed:
                changed['Free Site'] = sla
            result[title].append(changed)
            if changed != row:
                changes.append({'Order Number': row.get('Order Number', ''), 'Action': 'updated',
                    'Old Status': row.get('Status', ''), 'New Status': changed.get('Status', ''),
                    'Out Time': changed.get('Out Time', '')})
    return result, changes
