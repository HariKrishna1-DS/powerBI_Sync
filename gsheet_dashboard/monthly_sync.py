"""Month-aware adapter around the established capture merge and receipt rules."""
from datetime import datetime
import hashlib
import json

from monthly_production import (ARCHIVE, BASES, active_locations, apply_plan, arrival_sort,
    decode, encode, extend_headers, local_datetime, new_plan, preserve_formulas, ensure_pairs,
    snapshot, tab_identity, tab_name, fingerprint)


def sync_monthly(book, frame, store, on_progress=None):
    from tracker_sync import (HEADERS, IST, key, records, matrix, text, merge_trackers,
                              sheet_reports, archive_value_matches)
    from tracker_formatting import ensure_tracker_formatting
    from monthly_views import refresh_monthly_views, capacity_report_values
    from report_workspace import ReportWorkspace
    publish_tracker_reports = ReportWorkspace(store).read()['mode'] != 'excel'
    if frame is None:
        if publish_tracker_reports:
            refresh_monthly_views(book)
        ensure_tracker_formatting(book)
        return [s.title for s in book.worksheets() if tab_identity(s.title)]
    original = frame.attrs.get('original_capture')
    incoming = original['rows'] if original else frame.fillna('').to_dict('records')
    columns = original['columns'] if original else list(frame.columns)
    preview = frame.attrs.get('preview_name', 'Preview')
    number = frame.attrs.get('preview_id', 0)
    digest = hashlib.sha256(json.dumps(incoming, sort_keys=True, default=str).encode()).hexdigest()
    sheets = {s.title: s for s in book.worksheets()}
    history_values = sheets['Sheet1'].get_all_values(value_render_option='UNFORMATTED_VALUE') if 'Sheet1' in sheets else []
    history = records(history_values)
    committed = [r for r in history if r.get('Preview') == preview]
    saved = store.get_sync_report(number, include_staged=True)
    if committed:
        actual = committed if incoming else [r for r in committed if any(text(r.get(c)) for c in columns)]
        if len(actual) != len(incoming) or any(not archive_value_matches(wanted.get(c, ''), got.get(c, ''))
            for wanted, got in zip(incoming, actual) for c in columns) or (saved and saved['sha256'] != digest):
            raise ValueError('This preview name already identifies a different saved snapshot.')
        if saved and not saved['committed']:
            # Raw archive and production changes shared a single atomic batch.
            store.commit_sync_report(number, digest)
        frame.attrs['pass_report'] = {k: v for k, v in (saved or {}).get('report', {}).items() if not k.startswith('_')}
        if publish_tracker_reports:
            refresh_monthly_views(book)
        ensure_tracker_formatting(book)
        return list(sheets)
    history_ids = [int(r['Preview'][7:]) for r in history if str(r.get('Preview', '')).startswith('preview') and str(r['Preview'][7:]).isdigit()]
    if number and history_ids and number < max(history_ids):
        raise ValueError('An unsynced older preview cannot overwrite a newer tracker state. Review it in history.')
    before = snapshot(book)
    if any(not tab_identity(title) for title in before):
        raise ValueError('Legacy and monthly tabs both exist. Confirm monthly setup before syncing to avoid leaving orders behind.')
    locations = active_locations(before)
    current = {base: [] for base in BASES}
    for title, row in locations.values():
        current[tab_identity(title)[0]].append(row)
    previous = []
    if history_ids:
        last = max(history_ids)
        try:
            previous = store.get(last)['rows']
        except KeyError:
            previous = [r for r in history if r.get('Preview') == f'preview{last}']
    created = frame.attrs.get('preview_created')
    anchor = datetime.fromisoformat(created).astimezone(IST).replace(tzinfo=None) if created else datetime.now(IST).replace(tzinfo=None)
    accepted, reviews = [], []
    for row in incoming:
        arrival = local_datetime(row.get('In-Time', row.get('Arrival Time', row.get('RequestArrivalTime'))))
        out = local_datetime(row.get('Out Time'))
        period = (out or arrival or anchor).strftime('%Y-%m')
        if key(row) not in locations and period <= ARCHIVE:
            reviews.append({'Order Number': row.get('Order Number', ''), 'Reason': 'Archived month; capture retained without re-importing September'})
        else:
            accepted.append(row)
    completion_history = history + ([dict(r, Preview=preview, **{'Preview Timestamp': anchor.isoformat()}) for r in incoming]
        or [{'Preview': preview, 'Preview Timestamp': anchor.isoformat()}]) if created else None
    merged, report = merge_trackers(current, accepted, previous, anchor, completion_history)
    report['scanned'] = len(incoming)
    report['unprocessed'] += len(reviews)
    report['ambiguous'].extend(reviews)
    plan = new_plan(before, 'sync')
    plan['preserve_report_views'] = not publish_tracker_reports
    plan['view_raw_rows'] = history + incoming
    plan['format_titles'] = list(before)
    grouped = {title: [] for title in before if tab_identity(title) and tab_identity(title)[1] > ARCHIVE}
    for base in BASES:
        grouped.setdefault(tab_name(base, anchor.strftime('%Y-%m')), [])
        for row in merged[base]:
            prior = locations.get(key(row))
            period = (local_datetime(row.get('Out Time')) or local_datetime(row.get('In-Time')) or anchor).strftime('%Y-%m')
            title = prior[0] if prior else tab_name(base, period)
            grouped.setdefault(title, []).append(row)
    for title, rows in grouped.items():
        headers = before.get(title, {}).get('values', [HEADERS])[0]
        ordered = arrival_sort(rows, report['ambiguous'])
        values = encode(ordered, extend_headers(headers, ordered))
        def normalized(values):
            normalized_rows = []
            for cells in values:
                cells = [text(v) for v in cells]
                while cells and not cells[-1]:
                    cells.pop()
                normalized_rows.append(cells)
            return normalized_rows
        if normalized(values) != normalized(before.get(title, {}).get('values', [])):
            plan['writes'][title] = values
    report.update(preview_name=preview, timestamp=anchor.isoformat(), seeded=0, default_conflicts_count=0,
                  default_conflicts=[], ambiguous_count=len(report['ambiguous']), not_in_latest_count=len(report['not_in_latest']))
    raw_rows = [dict(r, Preview=preview, **{'Preview Timestamp': anchor.isoformat()}) for r in incoming]
    raw_rows = raw_rows or [{'Preview': preview, 'Preview Timestamp': anchor.isoformat()}]
    for title in (('All Products', 'Sheet1') if publish_tracker_reports else ('Sheet1',)):
        prior = sheets[title].get_all_values(value_render_option='UNFORMATTED_VALUE') if title in sheets else []
        headers = list(dict.fromkeys((prior[0] if prior else []) + ['Preview', 'Preview Timestamp'] + list(columns)))
        plan['writes'][title] = matrix(records(prior) + raw_rows, headers)
        plan.setdefault('archive_fingerprints', {})[title] = fingerprint(prior)
        if prior and headers == prior[0]:
            plan.setdefault('append_from', {})[title] = len(prior)
    all_trackers = {title: decode(plan['writes'].get(title, sheet['values'])) for title, sheet in before.items() if tab_identity(title)}
    all_trackers.update({title: decode(values) for title, values in plan['writes'].items() if tab_identity(title)})
    reports = sheet_reports(all_trackers, report)
    if publish_tracker_reports:
        for title, kind, period in (('Monthly Orders', 'monthly', 'Month'),):
            headers = [period, 'Received' if kind == 'daily' else 'Month Orders', 'Completed',
                       'Clarification', 'Cancelled', 'Vendor Pending',
                       'In-House Pending', 'SLA OnTime', 'Missing']
            plan['writes'][title] = matrix(reports[kind], headers)
        plan['writes']['Capacity Report'] = capacity_report_values(reports['monthly'], reports['daily'])
        from collections import Counter
        statuses = Counter(text(r.get('Status')) or '(Blank)' for rows in merged.values() for r in rows)
        total = sum(statuses.values())
        plan['writes']['Status Report'] = [['Status', 'Orders', 'Share', 'Preview', 'Sync Date & Time']] + [
            [status, count, count/total if total else 0, preview, anchor.isoformat()] for status, count in statuses.items()]
    store.stage_sync_report(number, digest, report)
    if on_progress:
        on_progress('Saving monthly production, backups and capture receipt')
    apply_plan(book, preserve_formulas(ensure_pairs(plan, before), before))
    ensure_tracker_formatting(book)
    store.commit_sync_report(number, digest)
    frame.attrs['pass_report'] = report
    return list(plan['writes'])
