"""Production reports derived exclusively from the current local capture history."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import threading


def preview_revision(previews, settings):
    value = [settings.get('data_revision', ''),
             [(p['id'], p['created'], p['row_count']) for p in previews]]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def build_preview_snapshot(history, settings=None, corrections=None):
    from tracker_sync import FULL, REMAINING, HEADERS, SOURCE, key, merge_trackers, value
    from monthly_production import local_datetime
    from production_timing import sla_result
    from report_workspace import imported_snapshot
    settings, corrections = settings or {}, corrections or {}
    trackers = {FULL: [], REMAINING: []}
    previous, archive, latest_raw, first_seen = [], [], {}, {}
    audit = {}
    columns = list(HEADERS)
    history = sorted(history, key=lambda capture: capture['id'])
    for capture in history:
        columns = list(dict.fromkeys(columns + [c for c in capture['columns'] if not c.startswith('_')]))
        anchor = local_datetime(capture['created'])
        if anchor is None:
            raise ValueError(f"{capture['name']} has an invalid capture timestamp.")
        # A capture is a snapshot, not an additional copy of an existing order.
        incoming = {}
        for original in capture['rows']:
            raw = {c: v for c, v in original.items() if not c.startswith('_') and c != 'Source workbook'}
            identity = key(raw)
            if identity:
                incoming[identity] = raw
                latest_raw[identity] = raw
                first_seen.setdefault(identity, capture['name'])
        queue = [dict(row, Product=row.get('Product') or '(Blank)') for row in incoming.values()]
        archive.extend(dict(row, Preview=capture['name'], **{'Preview Timestamp': capture['created']}) for row in capture['rows'])
        if not capture['rows']:
            archive.append({'Preview': capture['name'], 'Preview Timestamp': capture['created']})
        trackers, audit = merge_trackers(trackers, queue, previous, anchor)
        audit.update(preview_name=capture['name'], timestamp=capture['created'])
        for rows in trackers.values():
            for row in rows:
                identity = key(row)
                raw = latest_raw[identity]
                protected = {'No', 'Date', 'In-Time', 'Out Time', 'Status', 'SLA Expiration', 'Free Site'}
                row.update({c: v for c, v in raw.items() if c not in protected})
                for column in ('TraceQ Id', 'State', 'County', 'Client', 'Online/Ground', 'Comments', 'Assignee'):
                    if any(alias in raw for alias in SOURCE.get(column, (column,))):
                        row[column] = value(raw, column)
                row['First preview'] = first_seen[identity]
                if identity in incoming:
                    row['Latest preview'] = capture['name']
        previous = queue
    # Replay the raw transitions once; re-reading the growing archive at every
    # capture makes a long capture history unnecessarily expensive to open.
    from preview_completion import reconcile_completions
    trackers, completion_changes = reconcile_completions(trackers, archive)
    if audit:
        audit['changes'].extend(completion_changes)
        audit['updated'] += len(completion_changes)
    rows = [row for group in trackers.values() for row in group]
    for row in rows:
        identity = key(row)
        row.update(settings.get('preview_edits', {}).get(identity, {}))
        row['Free Site'] = sla_result(row)[0]
        completed = local_datetime(row.get('Out Time'))
        correction = corrections.get((str(row.get('Order Number', '')).strip(), completed.strftime('%Y-%m-%d'))) if completed else None
        if correction:
            row['Free Site'] = 'Missing' if correction == 'Missed' else correction
        edits = settings.get('preview_edits', {}).get(identity, {})
        received = ((local_datetime(edits['Date']) if 'Date' in edits else None)
                    or local_datetime(row.get('In-Time')) or local_datetime(row.get('Date')))
        row['_received_at'] = received.isoformat() if received else ''
        row['_month'] = received.strftime('%Y-%m') if received else ''
    columns = list(dict.fromkeys(columns + ['First preview', 'Latest preview']))
    updated = history[-1]['created'] if history else None
    snapshot = imported_snapshot({'rows': rows, 'columns': columns, 'created': updated})
    names = [capture['name'] for capture in history]
    for periods in snapshot['reports'].values():
        for period in periods:
            period['Previews'] = names
    snapshot.update(source='Saved previews', mode='tracker', report_origin='previews', offline=False,
                    preview_count=len(history), preview_names=names,
                    preview_name=history[-1]['name'] if history else None,
                    updated_at=updated, audit=audit)
    return snapshot


class PreviewReports:
    def __init__(self, store):
        self.store, self.lock = store, threading.RLock()
        self.revision, self.snapshot = None, None

    def get(self, settings, known_revision=None):
        with self.lock:
            revision = preview_revision(self.store.list(), settings)
            if revision != self.revision:
                self.snapshot = build_preview_snapshot(self.store.history(), settings, self.store.sla_corrections())
                self.snapshot.update(revision=revision, data_revision=revision)
                self.revision = revision
            if known_revision == revision:
                return {**{k: v for k, v in self.snapshot.items() if k not in ('sheets', 'reports', 'audit')}, 'unchanged': True}
            return deepcopy(self.snapshot)


def save_preview_edits(workspace, rows, changes):
    from tracker_sync import key
    settings = workspace.read()
    edits = deepcopy(settings.get('preview_edits') or {})
    for row in rows:
        edits.setdefault(key(row), {}).update(changes)
    workspace.save(preview_edits=edits)
