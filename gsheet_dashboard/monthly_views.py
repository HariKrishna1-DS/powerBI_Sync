"""Monthly product views derived from production; never extra order owners."""
import re
from collections import defaultdict


def capacity_report_values(monthly_reports, daily_reports=()):
    """Use the supplied daily targets only for dates present in the source."""
    from report_workspace import capacity_report, CAPACITY_COLUMNS
    from tracker_sync import matrix
    report = capacity_report({'monthly': monthly_reports, 'daily': list(daily_reports)}, {})
    rows = report['monthly']
    year = report['month'][:4]
    total = {'Date': f'{year} YTD Total', **{c: sum(r.get(c, 0) for r in rows if r['Date'].startswith(year)) for c in CAPACITY_COLUMNS[1:]}}
    daily_total = {'Date': 'Total', **{c: sum(r.get(c, 0) for r in report['daily']) for c in CAPACITY_COLUMNS[1:]}}
    return matrix(rows + [total], CAPACITY_COLUMNS) + matrix(report['daily'] + [daily_total], CAPACITY_COLUMNS)


def view_name(full, month):
    from monthly_production import month_key, MONTHS
    month_key(month)
    return f'{"Full_Search" if full else "Remaining_Search"}_{MONTHS[int(month[5:])-1].upper()}_{month[:4]}'


def view_identity(title):
    from monthly_production import MONTHS
    match = re.fullmatch(r'(Full_Search|Remaining_Search|Full_search|Remaining)_([A-Za-z]{3})_(\d{4})', title, re.I)
    months = [month.upper() for month in MONTHS]
    if match and match[2].upper() in months:
        return match[1].casefold() == 'full_search', f'{match[3]}-{months.index(match[2].upper())+1:02}'
    return None


def product_view_headers(headers):
    """Reserve Y for manual Typer values; deadline categories have their own report."""
    from tracker_sync import HEADERS
    return list(dict.fromkeys(HEADERS + ['Typer'] + [column for column in headers
        if column and column.strip() and column not in HEADERS and column not in ('Typer', 'SLA Category') and not column.startswith('_')]))


def monthly_view_values(trackers, raw_rows=(), headers=None):
    """Keep every non-full product, including those outside UI selections.

    Both short views use the Full Search production schema, never raw queue fields.
    """
    from tracker_sync import HEADERS, FULL, key
    from monthly_production import ARCHIVE, tab_identity, local_datetime, arrival_sort, encode, extend_headers
    if headers is None:
        full_rows = next((rows for title, rows in trackers.items()
            if title == FULL or (tab_identity(title) and tab_identity(title)[0] == FULL)), [])
        headers = extend_headers(HEADERS, full_rows)
    headers = product_view_headers(headers)
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
            buckets[view_name(full, month)].append(row)
        if identity and identity[1] > ARCHIVE:
            months.add(identity[1])
    # The newest pair is the searchable partition of retained production.
    # Arrival month must not hide an older Two Owner or other non-full order.
    if months:
        latest = max(months)
        from status_updates import full_product
        retained = {key(row): row for rows in trackers.values() for row in rows if key(row)}
        for full in (True, False):
            buckets[view_name(full, latest)] = [row for row in retained.values() if full_product(row) == full]
    return {view_name(full, month): encode(arrival_sort(buckets[view_name(full, month)]),
                headers)
            for month in sorted(months) for full in (True, False)}


def keep_view_headers(values, prior):
    """Legacy callers must not restore obsolete raw/extra view columns."""
    return values


def refresh_monthly_views(book, *, return_changed=False, only_completions=False):
    """Safe repair on repeat syncs, including captures committed before this feature."""
    from tracker_sync import tracker_sources, records, FULL, sheet_reports, matrix
    from monthly_production import snapshot, decode, encode, new_plan, fingerprint, apply_plan, preserve_formulas
    from preview_completion import reconcile_completions
    sheets = {sheet.title: sheet for sheet in book.worksheets()}
    before = snapshot(book)
    sources = tracker_sources(book)
    trackers = {sheet.title: decode(values) for _, sheet, values in sources}
    raw_values = sheets['Sheet1'].get_all_values(value_render_option='UNFORMATTED_VALUE') if 'Sheet1' in sheets else []
    raw = records(raw_values)
    plan = new_plan(before, 'monthly_views')
    repaired, changes = reconcile_completions(trackers, raw)
    if only_completions and not any(
            before.get(column, '') != after.get(column, '')
            for title, rows in repaired.items() for before, after in zip(trackers[title], rows)
            for column in ('Status', 'Out Time')):
        return False
    for title, rows in repaired.items():
        if rows != trackers[title]:
            original = decode(before[title]['values'])
            for wanted, saved in zip(rows, original):
                for column in ('Status', 'Out Time', 'SLA Expiration', 'Free Site'):
                    saved[column] = wanted.get(column, '')
            plan['writes'][title] = encode(original, before[title]['values'][0])
    schema = next((values[0] for base, _, values in sources if base == FULL and values), None)
    writes = monthly_view_values(repaired, headers=schema)
    if changes:
        from collections import Counter
        statuses = Counter(row.get('Status', '') for rows in repaired.values() for row in rows)
        total = sum(statuses.values())
        prior_status = sheets['Status Report'].get_all_values() if 'Status Report' in sheets else []
        status_headers = prior_status[0] if prior_status else ['Status', 'Orders', 'Share']
        metadata = records(prior_status)[0] if len(prior_status) > 1 else {}
        plan['writes']['Status Report'] = encode([dict(metadata, Status=s, Orders=n, Share=n/total if total else 0)
            for s, n in statuses.items()], status_headers)
        reports = sheet_reports(repaired)
        monthly_columns = ['Month', 'Received', 'Completed', 'Clarification', 'Cancelled',
                           'Vendor Pending', 'In-House Pending', 'SLA OnTime', 'SLA on Missing']
        monthly_rows = [dict(row, **{'SLA on Missing': row.get('Missing', 0)})
                        for row in reports['monthly']]
        plan['writes']['Monthly Orders'] = matrix(monthly_rows, monthly_columns)
        plan['writes']['PR Excel'] = capacity_report_values(reports['monthly'], reports['daily'])
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
    reports = sheet_reports(repaired)
    capacity_values = capacity_report_values(reports['monthly'], reports['daily'])
    capacity_sheet_name = 'PR Excel' if 'PR Excel' in sheets else 'Capacity Report'
    prior_capacity = sheets[capacity_sheet_name].get_all_values(value_render_option='UNFORMATTED_VALUE') if capacity_sheet_name in sheets else []
    from tracker_formatting import capacity_sheet_values
    if normalized(prior_capacity) != normalized(capacity_sheet_values(capacity_values)):
        plan['writes']['PR Excel'] = capacity_values
        plan.setdefault('archive_fingerprints', {})[capacity_sheet_name] = fingerprint(prior_capacity)
    if 'Capacity Report' in sheets and 'PR Excel' not in sheets:
        plan['renames']['Capacity Report'] = 'PR Excel'
    if plan['writes'] or plan['renames']:
        if 'Sheet1' in sheets:
            plan.setdefault('archive_fingerprints', {})['Sheet1'] = fingerprint(raw_values)
        apply_plan(book, preserve_formulas(plan, before))
    return bool(plan['writes'] or plan['renames']) if return_changed else list(writes)
