"""Manual SLA report entries, separate from immutable queue captures."""
from copy import deepcopy
import hashlib
import json

FIELDS = ['Borrower', 'SLA Expiration', 'Orig', 'Online/Ground', 'Client', 'Product',
          'State', 'County', 'Municipality', 'Parcel ID', 'Task Name', 'Task Status',
          'Last User', 'ETA', 'ETA Comments', 'Comment', 'Skill Grade']
ALIASES = {'slaexpiration': 'SLA Expiration', 'onlineground': 'Online/Ground', 'st': 'State'}


def canonical(column):
    import re
    key = re.sub('[^a-z0-9]', '', str(column).casefold())
    return ALIASES.get(key) or next((name for name in FIELDS
        if re.sub('[^a-z0-9]', '', name.casefold()) == key), column)


def editable_fields(row):
    result = {}
    for column, value in row.items():
        name = canonical(column)
        if name in FIELDS and (name not in result or column == name):
            result[name] = str(value if value is not None else '')
    return {name: result.get(name, '') for name in FIELDS}


def apply_fields(row, fields):
    """Keep portal aliases and canonical columns consistent after an edit."""
    for column in list(row):
        name = canonical(column)
        if name in fields:
            row[column] = fields[name]
    row.update(fields)


def revision(row):
    value = [str(row.get('Order Number', '')).strip().casefold(), row.get('Status'), editable_fields(row)]
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checked_status(value):
    from status_updates import status_name
    if not isinstance(value, str) or not value.strip() or len(value) > 1000:
        raise ValueError('Enter a status name (up to 1,000 characters).')
    name = status_name(value)
    if name.casefold() in ('grand total', '(blank)'):
        raise ValueError('Choose a different status name.')
    return name


def find_order(report, number):
    from import_identity import number_key
    identity = number_key({'Order Number': number})
    return next((row for row in report['rows'] + report['excluded_rows']
                 if number_key(row) == identity), None)


def checked_preview_status(value):
    from sla_status import completion_status
    name = checked_status(value)
    if completion_status(name):
        raise ValueError('Completed and Delivered is not used in extracted SLA Status. Choose the active queue status.')
    return name


def custom_statuses(settings, preview_id):
    """Older workspaces shared status names; edits now belong to one preview."""
    return list((settings.get('sla_preview_custom_statuses') or {}).get(
        str(preview_id), settings.get('sla_custom_statuses') or []))


def custom_status_changes(settings, preview_id, statuses):
    registry = deepcopy(settings.get('sla_preview_custom_statuses') or {})
    registry[str(preview_id)] = list(dict.fromkeys(statuses))
    return {'sla_preview_custom_statuses': registry}


def save_status(workspace, report, name, previous=None):
    name = checked_preview_status(name)
    known = [row['Status'] for row in report['summary']]
    name = next((status for status in known if status.casefold() == name.casefold()), name)
    with workspace.lock:
        settings = workspace.read()
        statuses = custom_statuses(settings, report['preview_id'])
        if previous:
            if previous not in statuses or any(row['Status'] == previous
                    for row in report['rows'] + report['excluded_rows']):
                raise ValueError('This status changed. Refresh SLA Status before renaming it.')
            statuses.remove(previous)
        if not any(status.casefold() == name.casefold() for status in statuses):
            statuses.append(name)
        from workspace_backup import save_safety_backup
        save_safety_backup(workspace.store, 'before-update')
        workspace.save(**custom_status_changes(settings, report['preview_id'], statuses))
    return name


def delete_status(workspace, report, body):
    """Remove a custom label and move its orders without removing any records."""
    from import_identity import number_key
    from tracker_sync import STATUS_NAMES
    name = checked_status(body.get('status'))
    settings = workspace.read()
    statuses = custom_statuses(settings, report['preview_id'])
    if name not in statuses:
        raise ValueError('Only manually added statuses can be deleted. Refresh SLA Status and try again.')
    matching = {number_key(row) for row in report['rows'] + report['excluded_rows'] if row['Status'] == name}
    selected = body.get('order_numbers')
    if (not isinstance(selected, list) or any(not isinstance(number, str) or not number.strip() for number in selected)
            or {number_key({'Order Number': number}) for number in selected} != matching):
        raise ValueError('Orders in this status changed. Reopen the delete dialog and try again.')
    replacement = None
    if matching:
        replacement = checked_preview_status(body.get('replacement'))
        known = [row['Status'] for row in report['summary']] + statuses + list(STATUS_NAMES.values())
        replacement = next((status for status in known if status.casefold() == replacement.casefold()), '')
        if not replacement or replacement.casefold() == name.casefold():
            raise ValueError('Choose another status for these orders before deleting this status.')
    with workspace.lock:
        settings = workspace.read()
        overrides = deepcopy(settings.get('sla_preview_statuses') or {})
        if matching:
            overrides.setdefault(str(report['preview_id']), {}).update(dict.fromkeys(matching, replacement))
        from workspace_backup import save_safety_backup
        save_safety_backup(workspace.store, 'before-update')
        workspace.save(sla_preview_statuses=overrides,
                       **custom_status_changes(settings, report['preview_id'], [status for status in statuses if status != name]))
    return {'status': name, 'deleted': True, 'moved': len(matching), 'replacement': replacement}


def save_order(workspace, report, body):
    from import_identity import number_key
    from monthly_production import local_datetime as local_time
    number = body.get('order_number')
    if not isinstance(number, str) or not number.strip() or len(number) > 1000:
        raise ValueError('Enter an Order Number (up to 1,000 characters).')
    number = number.strip()
    identity = number_key({'Order Number': number})
    status = checked_preview_status(body.get('status'))
    status = next((row['Status'] for row in report['summary']
                   if row['Status'].casefold() == status.casefold()), status)
    fields = body.get('fields')
    if (not isinstance(fields, dict) or any(name not in FIELDS or not isinstance(value, str)
            or len(value) > 10000 for name, value in fields.items())):
        raise ValueError('Enter valid order details.')
    existing = find_order(report, number)
    if existing:
        if body.get('expected_revision') != revision(existing):
            raise ValueError('This order already exists or changed. Look up the Order Number again before saving.')
        number = existing['Order Number']
    elif body.get('expected_revision'):
        raise ValueError('This order is no longer available. Look up the Order Number again.')
    expiry = fields.get('SLA Expiration', existing.get('SLA Expiration') if existing else '')
    if not local_time(expiry):
        raise ValueError('Enter a valid SLA expiration date and time so this order is included in the totals.')
    # Store absolute dates; relative durations would drift on future report refreshes.
    fields = dict(fields, **{'SLA Expiration': local_time(expiry).isoformat(sep=' ')})
    preview_key = str(report['preview_id'])
    with workspace.lock:
        settings = workspace.read()
        edits = deepcopy(settings.get('sla_preview_order_edits') or {})
        manual = deepcopy(settings.get('sla_preview_manual_orders') or {})
        overrides = deepcopy(settings.get('sla_preview_statuses') or {})
        if existing:
            edits.setdefault(preview_key, {}).setdefault(identity, {}).update(fields)
        else:
            manual.setdefault(preview_key, {})[identity] = dict(fields, **{'Order Number': number})
        overrides.setdefault(preview_key, {})[identity] = status
        from workspace_backup import save_safety_backup
        save_safety_backup(workspace.store, 'before-update')
        workspace.save(sla_preview_order_edits=edits, sla_preview_manual_orders=manual,
                       sla_preview_statuses=overrides)
    return {'order_number': number, 'status': status, 'created': existing is None}
