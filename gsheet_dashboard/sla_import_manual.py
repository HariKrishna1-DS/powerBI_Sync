"""Date-scoped SLA editing of the actual imported report records."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import secrets

from import_identity import order_key, number_key
from sla_manual import FIELDS as PREVIEW_FIELDS, checked_status, apply_fields

FIELDS = PREVIEW_FIELDS + ['Out Time']
MANUAL_SOURCE = 'Manual SLA orders'


def decorate(snapshot, settings):
    rows = snapshot['sheets']['Overview']['rows']
    return dict(snapshot, data_revision=settings.get('data_revision'), custom_statuses=list((settings.get('sla_import_custom_statuses') or {}).get(snapshot['report_date'], [])),
                source_workbooks=sorted({str(row.get('Source workbook') or '') for row in
                    (settings.get('imported') or {}).get('rows', []) if row.get('Source workbook')}, key=str.casefold),
                manual_order_count=sum(bool(row.get('_sla_manual')) for row in rows))


def find_order(report, number, source=''):
    matches = [row for row in report['rows'] + report['excluded_rows']
               if number_key(row) == number.strip().casefold() and
               (not source or str(row.get('Source workbook', '')).casefold() == source.casefold())]
    if len(matches) > 1:
        raise ValueError('This Order Number occurs in multiple workbooks. Choose its workbook before looking it up.')
    return next(iter(matches), None)


def editable_fields(row):
    from sla_manual import editable_fields as preview_fields
    from sla_status import local_time
    result = dict(preview_fields(row), **{'Out Time': str(row.get('Out Time') or '')})
    due = local_time(result['SLA Expiration'])
    if due:
        result['SLA Expiration'] = due.isoformat(sep=' ')
    return result


def revision(row):
    value = [order_key(row), row.get('Date'), row.get('Status'), editable_fields(row)]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def custom_changes(settings, report, statuses):
    registry = deepcopy(settings.get('sla_import_custom_statuses') or {})
    registry[report['report_date']] = list(dict.fromkeys(statuses))
    return {'sla_import_custom_statuses': registry, 'data_revision': secrets.token_hex(12),
            'publication_state': 'pending'}


def check_scope(settings, report):
    if settings.get('mode') != 'excel' or settings.get('data_revision') != report.get('data_revision'):
        raise ValueError('The imported report changed. Refresh SLA Status before saving.')


def save_status(workspace, report, name, previous=None):
    name = checked_status(name)
    name = next((row['Status'] for row in report['summary'] if row['Status'].casefold() == name.casefold()), name)
    with workspace.lock:
        settings = workspace.read()
        check_scope(settings, report)
        statuses = list((settings.get('sla_import_custom_statuses') or {}).get(report['report_date'], []))
        if previous:
            if previous not in statuses or any(row['Status'] == previous for row in report['rows'] + report['excluded_rows']):
                raise ValueError('This status changed. Refresh SLA Status before renaming it.')
            statuses.remove(previous)
        if name not in statuses:
            statuses.append(name)
        from workspace_backup import save_safety_backup
        save_safety_backup(workspace.store, 'before-update')
        workspace.save(**custom_changes(settings, report, statuses))
    return name


def persist(workspace, settings, imported, events, **changes):
    from order_details import persist_edit
    from report_workspace import imported_snapshot
    from workspace_backup import save_safety_backup
    save_safety_backup(workspace.store, 'before-update')
    snapshot = imported_snapshot(imported)
    imported['view_members'] = {name: [order_key(row) for row in snapshot['sheets'][name]['rows']]
                                for name in ('Full Title', 'Remaining Products')}
    imported['created'] = datetime.now(timezone.utc).isoformat()
    settings.update(imported=imported, row_count=len(imported['rows']),
                    data_revision=secrets.token_hex(12), publication_state='pending', **changes)
    persist_edit(workspace, settings, events)


def update_status(row, status):
    from production_timing import completion_from_out_time, sla_result
    after = dict(row, Status=status)
    if 'Task Status' in after:
        after['Task Status'] = status
    if completion_from_out_time(after).get('Status') != status:
        raise ValueError('A valid Out Time keeps this order Completed and Delivered. Clear Out Time in the order editor before reopening it.')
    after['Free Site'] = sla_result(after)[0]
    return after


def move_status(workspace, report, old, new, selected, individual=False, delete=False):
    from order_details import edit_events
    old, new = checked_status(old), checked_status(new)
    current = {order_key(row): row for row in report['rows'] + report['excluded_rows'] if row['Status'] == old}
    selected = set(selected)
    if not selected or not selected <= current.keys() or (not individual and selected != current.keys()):
        raise ValueError('Orders in this status changed. Refresh SLA Status and choose the orders again.')
    with workspace.lock:
        settings = workspace.read()
        check_scope(settings, report)
        imported = deepcopy(settings['imported'])
        events = []
        for index, row in enumerate(imported['rows']):
            if order_key(row) not in selected:
                continue
            after = update_status(row, new)
            imported['rows'][index] = after
            events += edit_events(row, after, {'Status': new}, 'excel', report['report_date'], 'SLA order editor')
        changes = {}
        if delete:
            statuses = (settings.get('sla_import_custom_statuses') or {}).get(report['report_date'], [])
            changes = custom_changes(settings, report, [name for name in statuses if name != old])
            changes.pop('data_revision')
            changes.pop('publication_state')
        persist(workspace, settings, imported, events, **changes)
    return len(selected)


def delete_status(workspace, report, body):
    name = checked_status(body.get('status'))
    settings = workspace.read()
    statuses = (settings.get('sla_import_custom_statuses') or {}).get(report['report_date'], [])
    if name not in statuses:
        raise ValueError('Only manually added statuses can be deleted.')
    matching = {order_key(row) for row in report['rows'] + report['excluded_rows'] if row['Status'] == name}
    selected = body.get('order_numbers')
    if not isinstance(selected, list) or any(not isinstance(value, str) for value in selected) or set(selected) != matching:
        raise ValueError('Orders in this status changed. Reopen the delete dialog and try again.')
    replacement = None
    if matching:
        replacement = checked_status(body.get('replacement'))
        from tracker_sync import STATUS_NAMES
        known = [row['Status'] for row in report['summary']] + list(STATUS_NAMES.values())
        replacement = next((status for status in known if status.casefold() == replacement.casefold()), '')
        if replacement == name or not replacement:
            raise ValueError('Choose another existing status for these orders before deleting this status.')
        move_status(workspace, report, name, replacement, selected, delete=True)
    else:
        with workspace.lock:
            from workspace_backup import save_safety_backup
            check_scope(workspace.read(), report)
            save_safety_backup(workspace.store, 'before-update')
            workspace.save(**custom_changes(settings, report, [status for status in statuses if status != name]))
    return {'status': name, 'deleted': True, 'moved': len(matching), 'replacement': replacement}


def save_order(workspace, report, body):
    from sla_status import local_time
    from order_details import edit_events
    from report_workspace import import_sources, combine_sources
    number = body.get('order_number')
    source = body.get('source_workbook') or ''
    if not isinstance(number, str) or not number.strip() or len(number) > 1000:
        raise ValueError('Enter an Order Number (up to 1,000 characters).')
    if not isinstance(source, str) or len(source) > 255:
        raise ValueError('Choose a valid workbook.')
    number = number.strip()
    status = checked_status(body.get('status'))
    status = next((row['Status'] for row in report['summary'] if row['Status'].casefold() == status.casefold()), status)
    fields = body.get('fields')
    if not isinstance(fields, dict) or any(name not in FIELDS or not isinstance(value, str) or len(value) > 10000 for name, value in fields.items()):
        raise ValueError('Enter valid order details.')
    existing = find_order(report, number, source)
    if existing and body.get('expected_revision') != revision(existing):
        raise ValueError('This order already exists or changed. Look up the Order Number again before saving.')
    if not existing and body.get('expected_revision'):
        raise ValueError('This order is no longer available. Look up the Order Number again.')
    due = local_time(fields.get('SLA Expiration', existing.get('SLA Expiration') if existing else ''))
    if not due:
        raise ValueError('Enter a valid SLA expiration date and time so this order is included in the totals.')
    if fields.get('Out Time') and not local_time(fields['Out Time']):
        raise ValueError('Enter a valid Out Time or leave it blank.')
    fields = dict(fields, **{'SLA Expiration': due.isoformat(sep=' ')})
    source = existing.get('Source workbook', '') if existing else source or MANUAL_SOURCE
    if not existing and source not in report.get('source_workbooks', []) + [MANUAL_SOURCE]:
        raise ValueError('Choose one of the imported workbooks or Manual SLA orders.')
    with workspace.lock:
        settings = workspace.read()
        check_scope(settings, report)
        imported = deepcopy(settings['imported'])
        identity = order_key({'Order Number': number, 'Source workbook': source})
        actual = next((row for row in imported['rows'] if order_key(row) == identity), None)
        if actual and not existing:
            raise ValueError('This order belongs to another report date. Select its date before editing it.')
        if actual and revision(actual) != body.get('expected_revision'):
            raise ValueError('This order changed. Look up the Order Number again before saving.')
        if not actual and not fields.get('Product', '').strip():
            raise ValueError('Enter a Product for the new order.')
        before = actual or {'Order Number': number, 'Source workbook': source,
                            'Date': '' if report['report_date'] == 'Undated' else report['report_date'], '_sla_manual': True}
        after = dict(before)
        apply_fields(after, fields)
        after = update_status(after, status)
        if actual:
            imported['rows'][imported['rows'].index(actual)] = after
        else:
            sources = deepcopy(import_sources(imported))
            owner = next((item for item in sources if item['name'] == source), None)
            if owner is None:
                owner = {'name': source, 'rows': [], 'columns': [], 'files': [{'file': source, 'sheet': 'Manual orders', 'rows': 0}], 'reviews': []}
                sources.append(owner)
            owner['rows'].append(dict(after))
            owner['columns'] = list(dict.fromkeys(owner['columns'] + [name for name in after if not name.startswith('_')]))
            owner['files'][-1]['rows'] += 1
            for name in ('rows_seen',):
                if name in owner['files'][-1]:
                    owner['files'][-1][name] += 1
            effective_rows = imported['rows'] + [after]
            imported = dict(imported, **combine_sources(sources))
            imported['rows'] = effective_rows
        imported['columns'] = list(dict.fromkeys(imported['columns'] + [name for name in after if not name.startswith('_')]))
        changes = {name: after.get(name, '') for name in fields if before.get(name, '') != after.get(name, '')}
        changes['Status'] = after['Status']
        events = edit_events(before, after, changes, 'excel', report['report_date'], 'SLA order editor')
        if actual is None:
            events = [dict(events[0], Change='Added', Column='Order Number', **{'Previous Value': '', 'New Value': number, 'Before': {}})]
        persist(workspace, settings, imported, events)
    return {'order_number': number, 'source_workbook': source, 'status': after['Status'], 'created': actual is None}
