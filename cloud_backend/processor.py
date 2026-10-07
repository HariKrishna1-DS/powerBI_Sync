"""Canonical capture adapter. Runs centrally, reusing desktop production rules."""
from datetime import datetime

from tracker_sync import FULL, REMAINING, IST, key, merge_trackers, mapped_status
from preview_completion import missing_completion, valid_queue
from production_timing import sla_result, status, precise_timestamp
from shared_backend import verified_capture


def process_capture(claim):
    capture, previous = claim['capture'], claim.get('previous')
    stamp = datetime.fromisoformat(capture['captured_at'].replace('Z', '+00:00'))
    if stamp.tzinfo is None:
        raise ValueError('Capture timestamp needs a timezone.')
    anchor = stamp.astimezone(IST).replace(tzinfo=None)
    last = claim.get('last_capture_at')
    if last and stamp <= datetime.fromisoformat(last.replace('Z', '+00:00')):
        return [], {'reason': 'Late capture retained for review; current orders were not changed.'}, True
    payload = capture['payload']
    incoming = payload['rows']
    if not verified_capture(payload) or not valid_queue(incoming):
        return [], {'reason': 'Incomplete or empty capture requires review.'}, True
    identities = [key(r) for r in incoming]
    if not all(identities) or len(identities) != len(set(identities)):
        return [], {'reason': 'Duplicate or missing order identities require review.'}, True
    old = previous['payload']['rows'] if previous else []
    old_by_key, current_keys = {key(r): r for r in old}, set(identities)
    original = {item['order_key']: dict(item['data']) for item in claim['orders']}
    current = {identity: dict(row) for identity, row in original.items()}
    # Manual assignments/comments survive a capture; the existing Sheets merge
    # clears some operational columns, which must not erase concurrent user work.
    override_columns = ('SLA Override Status','SLA Override Out Time','SLA Override Deadline','SLA Override Completion')
    manual = {identity: {c: row[c] for c in ('Comments', 'Assignee', 'Searcher', 'Shift', 'Review/QC', 'review', 'Reporting Month', 'Carried From',*override_columns) if c in row}
              for identity, row in current.items()}
    for raw in incoming:
        row = current.get(key(raw))
        if row and str(row.get('Completion Evidence', '')).startswith('Inferred') and status(row) not in ('cancelled','canceled','task suspended','workflow suspended'):
            if status(raw) != 'completed and delivered' or not (precise_timestamp(raw.get('Out Time')) or precise_timestamp(raw.get('Completed Time'))):
                row.update(Status=mapped_status(raw, new=True), **{'Out Time': '', 'Completion Evidence': ''})
    trackers = {FULL: [], REMAINING: []}
    for row in current.values():
        route = FULL if str(row.get('Product', '')).strip().casefold() in ('full title','full search') else REMAINING
        trackers[route].append(row)
    merged, report = merge_trackers(trackers, incoming, old, anchor)
    prior_complete = previous and verified_capture(previous['payload']) and valid_queue(old)
    prior_time = datetime.fromisoformat(previous['captured_at'].replace('Z', '+00:00')).astimezone(IST).replace(tzinfo=None) if previous else None
    result = []
    for rows in merged.values():
        for row in rows:
            identity = key(row)
            if prior_complete and identity in old_by_key and identity not in current_keys:
                row = missing_completion(row, anchor, (old_by_key[identity], prior_time))
            row.update(manual.get(identity, {}))
            row['Free Site'], _ = sla_result(row)
            if row.get('SLA Override Status'):
                if (row['Free Site'] and not str(row.get('Completion Evidence','')).casefold().startswith('inferred')
                        and row.get('Out Time')==row.get('SLA Override Out Time')
                        and row.get('SLA Expiration')==row.get('SLA Override Deadline')):
                    row['Free Site'] = row['SLA Override Status']
                else:
                    for column in override_columns:
                        row[column] = ''
            if row != original.get(identity):
                result.append(row)
    # Report the final result, including incremental completion/reappearance,
    # rather than the intermediate merge's changes before those corrections.
    report['canonical_changes'] = [{'Order Number': row['Order Number'],
        'Old Status': original.get(key(row), {}).get('Status', ''),
        'New Status': row.get('Status', ''), 'Out Time': row.get('Out Time', ''),
        'Completion Evidence': row.get('Completion Evidence', '')} for row in result]
    return result, report, False
