"""Monthly product views derived from production; never extra order owners."""
import re
from collections import defaultdict


def view_name(full, month):
    from monthly_production import month_key, MONTHS
    month_key(month)
    return f'{"Full_search" if full else "Remaining"}_{MONTHS[int(month[5:])-1].upper()}_{month[:4]}'


def view_identity(title):
    from monthly_production import MONTHS
    match = re.fullmatch(r'(Full_search|Remaining)_([A-Za-z]{3})_(\d{4})', title, re.I)
    months = [month.upper() for month in MONTHS]
    if match and match[2].upper() in months:
        return match[1].casefold() == 'full_search', f'{match[3]}-{months.index(match[2].upper())+1:02}'
    return None


def monthly_view_values(trackers, raw_rows=()):
    """Keep every non-full product, including those outside UI selections.

    Long production tabs retain ownership. Short tabs are reporting views,
    enriched with the latest raw fields without duplicating production totals.
    """
    from tracker_sync import HEADERS, key
    from monthly_production import ARCHIVE, tab_identity, local_datetime, arrival_sort, encode, extend_headers
    latest = {key(row): row for row in raw_rows if key(row)}
    buckets, months = defaultdict(list), set()
    for title, rows in trackers.items():
        identity = tab_identity(title)
        for row in rows:
            date = local_datetime(row.get('In-Time')) or local_datetime(row.get('Date'))
            month = identity[1] if identity else date.strftime('%Y-%m') if date else None
            if not month or month <= ARCHIVE or not key(row):
                continue
            months.add(month)
            full = ' '.join(str(row.get('Product', '')).casefold().split()) in ('full title', 'full search')
            merged = {k: v for k, v in latest.get(key(row), {}).items() if k not in ('Preview', 'Preview Timestamp', 'Captured At')}
            merged.update({k: v for k, v in row.items() if not k.startswith('_')})
            buckets[view_name(full, month)].append(merged)
        if identity and identity[1] > ARCHIVE:
            months.add(identity[1])
    return {view_name(full, month): encode(arrival_sort(buckets[view_name(full, month)]),
                extend_headers(HEADERS, buckets[view_name(full, month)]))
            for month in sorted(months) for full in (True, False)}


def keep_view_headers(values, prior):
    """Keep the established Full_search column order while appending new fields."""
    from monthly_production import decode, encode, extend_headers
    if not prior:
        return values
    rows = decode(values)
    return encode(rows, extend_headers(prior[0], rows))


def refresh_monthly_views(book):
    """Safe repair on repeat syncs, including captures committed before this feature."""
    from tracker_sync import tracker_sources, records
    from monthly_production import snapshot, decode, new_plan, fingerprint, apply_plan
    sheets = {sheet.title: sheet for sheet in book.worksheets()}
    trackers = {sheet.title: decode(values) for _, sheet, values in tracker_sources(book)}
    raw = records(sheets['Sheet1'].get_all_values()) if 'Sheet1' in sheets else []
    writes = monthly_view_values(trackers, raw)
    plan = new_plan(snapshot(book), 'monthly_views')
    def normalized(values):
        result = []
        for row in values:
            cells = [str(v) for v in row]
            while cells and not cells[-1]:
                cells.pop()
            result.append(cells)
        return result
    for title, values in writes.items():
        prior = sheets[title].get_all_values(value_render_option='UNFORMATTED_VALUE') if title in sheets else []
        values = keep_view_headers(values, prior)
        if normalized(prior) != normalized(values):
            plan['writes'][title] = values
            plan.setdefault('archive_fingerprints', {})[title] = fingerprint(prior)
    if plan['writes']:
        apply_plan(book, plan)
    return list(writes)
