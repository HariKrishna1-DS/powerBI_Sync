"""Reconcile manual edits to the three imported order tabs against the last sync."""
from collections import defaultdict
from datetime import datetime, timezone
import json
import secrets


def editable_frames(snapshot, settings):
    from report_workspace import report_frames
    from monthly_views import view_identity
    frames, _ = report_frames(snapshot, settings)
    return {title: values for title, values in frames.items()
            if title == 'All Products' or view_identity(title)}


def records(values, title):
    from tracker_sync import canonical_headers, key, text, STATUS_NAMES
    from monthly_production import local_datetime
    headers = canonical_headers(values[0]) if values else []
    if ('Order Number' not in headers or not any(c in headers for c in ('Status', 'Task Status'))
            or len(headers) != len(set(headers)) or any(not h for h in headers)):
        raise ValueError(f'{title}: keep unique column headers including Order Number and Status. No orders were changed.')
    result = {}
    for number, cells in enumerate(values[1:], 2):
        if not any(text(cell).strip() for cell in cells):
            continue
        row = {column: text(cells[i]).strip() if i < len(cells) else ''
               for i, column in enumerate(headers) if column != 'No' and not column.startswith('_')}
        for i, column in enumerate(headers):
            if (i < len(cells) and isinstance(cells[i], (int, float)) and
                    column in ('Date', 'Order Date', 'In-Time', 'Out Time', 'ETA', 'SLA Expiration')):
                parsed = local_datetime(cells[i])
                if parsed:
                    row[column] = parsed.isoformat(sep=' ') if cells[i] % 1 and column not in ('Date', 'Order Date') else parsed.date().isoformat()
        identity = key(row)
        if not identity:
            raise ValueError(f'{title}, row {number}: enter an Order Number or remove the empty order row.')
        if identity in result:
            raise ValueError(f'{title}: Order Number {row["Order Number"]} appears more than once. Resolve it before refreshing.')
        status = row.get('Status') or row.get('Task Status', '')
        row['Status'] = STATUS_NAMES.get(status.casefold(),
            {'completed': 'Completed and Delivered', 'canceled': 'Cancelled'}.get(status.casefold(), status))
        result[identity] = row
    return headers, result


def read_editable_tabs(book, baseline):
    from monthly_views import view_identity
    sheets = {sheet.title: sheet for sheet in book.worksheets()}
    actual = {}
    for title in baseline:
        match = title if title in sheets else next((name for name in sheets
            if view_identity(title) and view_identity(name) == view_identity(title)), None)
        if match is None:
            raise ValueError(f'{title} is missing. Restore that order tab before refreshing; saved orders were kept.')
        actual[title] = match
    if hasattr(book, 'values_batch_get'):
        ranges = ["'" + name.replace("'", "''") + "'" for name in actual.values()]
        response = book.values_batch_get(ranges, params={'valueRenderOption': 'UNFORMATTED_VALUE',
                                                       'dateTimeRenderOption': 'SERIAL_NUMBER'})
        items = response.get('valueRanges', [])
        if len(items) != len(ranges):
            raise RuntimeError('Google Sheets returned an incomplete order-tab response. Retry refresh.')
        return {title: item.get('values', []) for title, item in zip(actual, items)}
    return {title: sheets[name].get_all_values(value_render_option='UNFORMATTED_VALUE')
            for title, name in actual.items()}


def equivalent(column, left, right):
    from monthly_production import local_datetime
    if str('' if left is None else left).strip() == str('' if right is None else right).strip():
        return True
    if column == 'Order Number':
        return str(left).strip().casefold() == str(right).strip().casefold()
    if column in ('Date', 'In-Time', 'Out Time', 'ETA', 'SLA Expiration', 'Order Date'):
        a, b = local_datetime(left), local_datetime(right)
        if a and b:
            return a == b
    return str('' if left is None else left).strip() == str('' if right is None else right).strip()


def tabs_unchanged(book, baseline):
    remote = read_editable_tabs(book, baseline)
    for title, values in remote.items():
        old_headers, old = records(baseline[title], title)
        new_headers, new = records(values, title)
        if old_headers != new_headers or old.keys() != new.keys():
            return False
        for identity, row in new.items():
            if any(not equivalent(column, old[identity].get(column, ''), value)
                   for column, value in row.items()):
                return False
    return True


def reconcile(imported, baseline, remote):
    """Merge changes to fields; an unchanged copy in another tab is not a new edit."""
    from tracker_sync import key
    from monthly_views import view_identity
    from report_workspace import imported_snapshot
    from production_timing import sla_result
    snapshot = imported_snapshot(imported)
    members = {label: {key(row) for row in snapshot['sheets'][label]['rows']}
               for label in ('Full Title', 'Remaining Products')}
    current = {key(row): dict(row) for row in imported['rows']}
    updates, additions, removals, tab_additions = defaultdict(dict), defaultdict(list), defaultdict(list), defaultdict(set)
    columns = list(imported['columns'])
    for title, values in remote.items():
        headers, after = records(values, title)
        _, before = records(baseline[title], title)
        columns = list(dict.fromkeys(columns + headers))
        for identity in before.keys() - after.keys():
            removals[identity].append(title)
        for identity, row in after.items():
            if identity not in before:
                if identity not in current:
                    additions[identity].append((title, row))
                else:
                    tab_additions[identity].add(title)
            old = before.get(identity, current.get(identity, {}))
            for column, value in row.items():
                if not equivalent(column, old.get(column, ''), value):
                    options = updates[identity].setdefault(column, [])
                    options.append((title, value))
    for identity, fields in updates.items():
        if identity in removals and fields:
            raise ValueError(f'Order {current.get(identity, {}).get("Order Number", identity)} was removed in one tab and edited in another. Make those edits agree before refreshing.')
        for column, options in fields.items():
            if any(not equivalent(column, options[0][1], value) for _, value in options[1:]):
                raise ValueError(f'Order {current.get(identity, {}).get("Order Number", identity)} has conflicting {column} edits in {", ".join(title for title, _ in options)}. Make the values agree before refreshing.')
    if removals.keys() & tab_additions.keys():
        raise ValueError('An order was removed and added in different tabs. Make those edits agree before refreshing.')
    now = datetime.now(timezone.utc).isoformat()
    events = []
    def event(identity, action, column, before, after, tabs, old_row=None, new_row=None):
        row = new_row or old_row or current.get(identity, {})
        events.append({'Changed At': now, 'Order Number': row.get('Order Number', identity),
            'Change': action, 'Column': column, 'Previous Value': str(before or ''),
            'New Value': str(after or ''), 'Source Tabs': ', '.join(sorted(set(tabs))),
            'Before': old_row or {}, 'After': new_row or {}})
    for identity, tabs in removals.items():
        old = current.pop(identity, None)
        if old:
            event(identity, 'Removed', 'Order', old.get('Status'), '', tabs, old_row=old)
        for group in members.values():
            group.discard(identity)
    for identity, candidates in additions.items():
        new = dict(candidates[0][1])
        current[identity] = new
        event(identity, 'Added', 'Order', '', new.get('Status'), [title for title, _ in candidates], new_row=new)
        tab_additions[identity].update(title for title, _ in candidates)
    for identity, fields in updates.items():
        if identity not in current:
            continue
        old = dict(current[identity])
        new = current[identity]
        for column, options in fields.items():
            new[column] = options[0][1]
            if identity not in additions and not equivalent(column, old.get(column, ''), new[column]):
                event(identity, 'Updated', column, old.get(column, ''), new[column],
                      [title for title, _ in options], old_row=old, new_row=dict(new))
        if 'Free Site' not in fields and any(column in fields for column in ('Status', 'In-Time', 'Out Time', 'SLA Expiration')):
            new['Free Site'] = sla_result(new)[0]
    for identity, tabs in tab_additions.items():
        if identity not in current:
            continue
        before = [label for label, group in members.items() if identity in group]
        for title in tabs:
            detail = view_identity(title)
            if detail:
                members['Full Title' if detail[0] else 'Remaining Products'].add(identity)
        if not any(identity in group for group in members.values()):
            full = current[identity].get('Product', '').strip().casefold() in ('full title', 'full search')
            members['Full Title' if full else 'Remaining Products'].add(identity)
        after = [label for label, group in members.items() if identity in group]
        if identity not in additions and before != after:
            event(identity, 'Updated', 'Report tab membership', ', '.join(before), ', '.join(after), tabs,
                  new_row=current[identity])
    if not events:
        return imported, []
    if len(current) > 100000:
        raise ValueError('The Google Sheets report exceeds 100,000 unique orders.')
    return dict(imported, rows=list(current.values()), columns=columns, created=now,
                view_members={label: sorted(group) for label, group in members.items()}), events


def initialize_history(workspace):
    with workspace.store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS import_excel_changes (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL, order_number TEXT NOT NULL, payload TEXT NOT NULL)')
        db.execute('CREATE INDEX IF NOT EXISTS import_changes_action ON import_excel_changes(action, id)')


def preserve_sheet_edits(previous, imported, replaced_names=(), replace_all=False):
    """Replacing one workbook resets its orders; other saved Sheet edits survive."""
    if replace_all or not previous or 'view_members' not in previous:
        return imported
    from tracker_sync import key
    from report_workspace import combine_sources, import_sources, imported_snapshot
    old_sources = import_sources(previous)
    originals = {key(row): row for row in combine_sources(old_sources)['rows']}
    effective = {key(row): row for row in previous['rows']}
    result = {key(row): dict(row) for row in imported['rows']}
    replaced_names = {name.casefold() for name in replaced_names}
    reset = {key(row) for source in old_sources + import_sources(imported)
             if source['name'].casefold() in replaced_names for row in source['rows']}
    for identity in originals.keys() - effective.keys() - reset:
        result.pop(identity, None)
    preserved = set()
    for identity, row in effective.items():
        if identity in reset:
            continue
        original = originals.get(identity)
        if original is None:
            result.setdefault(identity, dict(row)); preserved.add(identity)
        elif identity in result:
            for column, value in row.items():
                if column != 'No' and not column.startswith('_') and not equivalent(column, original.get(column, ''), value):
                    result[identity][column] = value
            preserved.add(identity)
    prior_snapshot, next_snapshot = imported_snapshot(previous), imported_snapshot(imported)
    members = {}
    for label in ('Full Title', 'Remaining Products'):
        old = {key(row) for row in prior_snapshot['sheets'][label]['rows']}
        new = {key(row) for row in next_snapshot['sheets'][label]['rows']}
        members[label] = sorted(((new - preserved) | (old & preserved)) & result.keys())
    return dict(imported, rows=list(result.values()), view_members=members,
                columns=list(dict.fromkeys(imported['columns'] + previous['columns'])))


def sync_imported_tabs(workspace, book, settings):
    from report_workspace import imported_snapshot
    if settings.get('mode') != 'excel' or not settings.get('imported') or settings.get('cloud_reset'):
        return False
    baseline = settings.get('cloud_baseline')
    if not baseline and not settings.get('synced_at'):
        return False
    baseline = baseline or editable_frames(imported_snapshot(settings['imported']), settings)
    remote = read_editable_tabs(book, baseline)
    imported, events = reconcile(settings['imported'], baseline, remote)
    with workspace.lock:
        latest = workspace.read()
        if latest.get('data_revision') != settings.get('data_revision'):
            raise RuntimeError('The report source changed during refresh. Refresh again to read the current source.')
        latest.update(cloud_baseline=remote, cloud_checked_at=datetime.now(timezone.utc).isoformat(), cloud_refresh_error=None)
        if events:
            latest.update(imported=imported, row_count=len(imported['rows']),
                          data_revision=secrets.token_hex(12), publication_state='pending')
        with workspace.store.connect() as db:
            db.execute('INSERT OR REPLACE INTO report_workspace VALUES (1,?)', (json.dumps(latest),))
            db.executemany('INSERT INTO import_excel_changes(action,order_number,payload) VALUES (?,?,?)',
                          [(event['Change'], event['Order Number'], json.dumps(event)) for event in events])
    return bool(events)


def change_history(workspace, action='', search='', offset=0, limit=100):
    clauses, parameters = [], []
    if action in ('Added', 'Updated', 'Removed'):
        clauses.append('action=?'); parameters.append(action)
    if search:
        clauses.append('order_number LIKE ?'); parameters.append('%' + search + '%')
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    with workspace.store.connect() as db:
        total = db.execute('SELECT COUNT(*) FROM import_excel_changes' + where, parameters).fetchone()[0]
        counts = dict(db.execute('SELECT action,COUNT(*) FROM import_excel_changes GROUP BY action').fetchall())
        rows = db.execute('SELECT id,payload FROM import_excel_changes' + where + ' ORDER BY id DESC LIMIT ? OFFSET ?',
                          [*parameters, limit, offset]).fetchall()
    return {'rows': [dict(json.loads(payload), id=identity) for identity, payload in rows],
            'total': total, 'counts': counts, 'offset': offset, 'limit': limit}
