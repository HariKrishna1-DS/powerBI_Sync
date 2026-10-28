"""Conflict-checked order edits and the history shown by report date dialogs."""
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import re
import secrets

READ_ONLY = {'No', 'Order Number', 'Free Site', 'SLA Category', 'Workload source', 'Source workbook', 'Source row ID'}
DATE_FIELDS = {'Date', 'Order Date', 'In-Time', 'Out Time', 'Completed Time'}


def public_row(row):
    return {column: value for column, value in row.items() if not column.startswith('_') and column != 'No'}


def find_order(snapshot, number, month='', source_workbook='', record_key=''):
    from tracker_sync import key
    rows = list(snapshot['sheets']['Overview']['rows'])
    # Daily capacity also includes archived rows omitted from the current Orders view.
    if snapshot.get('mode') != 'excel':
        rows.extend(row for period in snapshot.get('reports', {}).get('daily', []) for row in period.get('rows', []))
    matches = {}
    for row in rows:
        if (str(row.get('Order Number', '')).strip().casefold() == number.strip().casefold()
                and (not month or row.get('_month', '') == month)
                and (not record_key or key(row) == record_key)
                and (not source_workbook or str(row.get('Source workbook', '')).casefold() == source_workbook.casefold())):
            matches.setdefault((key(row), row.get('_sheet', ''), row.get('_month', '')), row)
    if len(matches) != 1:
        raise ValueError('This order is missing or has more than one reporting copy. Reopen its date and try again.')
    return next(iter(matches.values()))


def order_version(row, mode):
    value = [mode, row.get('_month', ''), row.get('_sheet', ''), public_row(row)]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def editor_details(snapshot, settings, number, month='', source_workbook='', record_key=''):
    from tracker_sync import key
    row = find_order(snapshot, number, month, source_workbook, record_key)
    columns = list(dict.fromkeys((snapshot['sheets']['Overview']['columns'] if settings['mode'] == 'excel' else []) + list(row)))
    return {'order': public_row(row), 'month': row.get('_month', ''), 'mode': settings['mode'],
            'source_workbook': row.get('Source workbook', ''),
            'record_key': key(row),
            'version': order_version(row, settings['mode']),
            'editable_columns': [column for column in columns if column not in READ_ONLY and not column.startswith('_')]}


def validated_changes(body, allowed):
    from monthly_production import local_datetime
    from status_updates import status_name
    changes = body.get('changes')
    if not isinstance(changes, dict) or not changes or len(changes) > 100:
        raise ValueError('Change at least one order field before saving.')
    result = {}
    for column, value in changes.items():
        if column not in allowed or not isinstance(value, str) or len(value) > 10000:
            raise ValueError('Choose an editable field and a text value of at most 10,000 characters.')
        value = value.strip()
        if column in DATE_FIELDS and value and not local_datetime(value):
            raise ValueError(f'{column}: use a valid date, for example 10/15/2026 09:30 AM or 2026-10-15 09:30.')
        if column in ('Status', 'Task Status'):
            if not value:
                raise ValueError('Status cannot be blank.')
            value = {'completed': 'Completed and Delivered', 'canceled': 'Cancelled'}.get(value.casefold(), status_name(value))
        result[column] = value
    if 'Status' in result and 'Task Status' in result and result['Status'] != result['Task Status']:
        raise ValueError('Status and Task Status must agree.')
    return result


def edit_events(before, after, changes, mode, report_date, source):
    now = datetime.now(timezone.utc).isoformat()
    return [{'Changed At': now, 'Order Number': before['Order Number'], 'Change': 'Updated',
             'Column': column, 'Previous Value': str(before.get(column, '') or ''), 'New Value': value,
             'Source Tabs': source, 'Before': public_row(before), 'After': public_row(after),
             'Mode': mode, 'Report Date': report_date, 'Month': before.get('_month', '')}
            for column, value in changes.items()]


def persist_edit(workspace, settings, events):
    with workspace.store.connect() as db:
        db.execute('INSERT OR REPLACE INTO report_workspace VALUES (1,?)', (json.dumps(settings),))
        db.executemany('INSERT INTO import_excel_changes(action,order_number,payload) VALUES (?,?,?)',
                      [(event['Change'], event['Order Number'], json.dumps(event)) for event in events])


def save_order(workspace, book, snapshot, body):
    from import_excel_changes import equivalent
    from production_timing import sla_result, completion_from_out_time
    from tracker_sync import key
    from workspace_backup import save_safety_backup
    settings = workspace.read()
    mode = 'excel' if body.get('context') == 'capacity' else settings['mode']
    if body.get('mode') != mode:
        raise ValueError('The report source changed. Reopen the order before saving.')
    details = editor_details(snapshot, dict(settings, mode=mode), body.get('order_number', ''), body.get('month', ''), body.get('source_workbook', ''), body.get('record_key', ''))
    if body.get('version') != details['version']:
        raise ValueError('This order changed since you opened it. Reopen the editor to review the latest values.')
    before = find_order(snapshot, body['order_number'], body.get('month', ''), body.get('source_workbook', ''), body.get('record_key', ''))
    changes = validated_changes(body, details['editable_columns'])
    changes = {column: value for column, value in changes.items() if not equivalent(column, before.get(column, ''), value)}
    if not changes:
        raise ValueError('No order values have changed.')
    report_date = body.get('report_date', '')
    if not isinstance(report_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}|Undated', report_date):
        raise ValueError('Reopen the order from a report date before saving.')
    after = dict(before, **changes)
    normalized = completion_from_out_time(after)
    for column in ('Status', 'Task Status'):
        if column in normalized and normalized[column] != after.get(column):
            after[column] = normalized[column]
            changes[column] = normalized[column]
    if 'Status' in changes and 'Task Status' in after:
        after['Task Status'] = changes['Status']
    elif 'Task Status' in changes:
        after['Status'] = changes['Task Status']
    changes = {column: after[column] for column in changes
               if not equivalent(column, before.get(column, ''), after[column])}
    if not changes:
        raise ValueError('A valid Out Time keeps this order Completed and Delivered. Clear Out Time before reopening it.')
    after['Free Site'] = sla_result(after)[0]
    backup = save_safety_backup(workspace.store, 'before-update')
    if mode == 'excel':
        imported = deepcopy(settings['imported'])
        row = next(row for row in imported['rows'] if key(row) == key(before))
        row.update(changes)
        for column in ('Status', 'Task Status', 'Free Site'):
            if column in after and (column in row or column != 'Task Status'):
                row[column] = after[column]
        imported['created'] = datetime.now(timezone.utc).isoformat()
        settings.update(imported=imported, row_count=len(imported['rows']))
        source = 'Report order editor'
    else:
        source, states = write_tracker_order(workspace, book, before, after, changes)
        baseline = deepcopy(settings.get('tracker_status_baseline') or states)
        baseline.setdefault(source, {})[key(before)] = after.get('Status', '')
        settings['tracker_status_baseline'] = baseline
    settings['data_revision'] = secrets.token_hex(12)
    persist_edit(workspace, settings, edit_events(before, after, changes, mode, report_date, source))
    return {'updated': 1, 'order_number': before['Order Number'], 'recovery_backup': backup.name}


def write_tracker_order(workspace, book, before, after, changes):
    from datatrace_sync import sheet_cell
    from import_excel_changes import equivalent
    from monthly_production import tab_identity
    from status_updates import tracker_state
    from tracker_sync import key
    owners, states = tracker_state(book)
    candidates = [item for item in owners.get(key(before), [])
                  if (not before.get('_sheet') or item[0].title == before['_sheet'])
                  and (not before.get('_month') or (tab_identity(item[0].title) or ('', ''))[1] == before['_month'])]
    if len(candidates) != 1:
        raise ValueError('The owning tracker row changed. Refresh the report before saving.')
    sheet, headers, index, current = candidates[0]
    values = dict(changes)
    if 'Status' in changes and 'Task Status' in headers:
        values['Task Status'] = after['Task Status']
    if 'Task Status' in changes and 'Status' in headers:
        values['Status'] = after['Status']
    if 'Free Site' in headers:
        values['Free Site'] = after['Free Site']
    if any(column not in headers for column in values):
        raise ValueError('One of the edited columns is missing from the owning tracker. Refresh before saving.')
    if any(not equivalent(column, before.get(column, ''), current.get(column, '')) for column in changes):
        raise ValueError('The tracker values changed while saving. Reopen the order to review them.')
    original = sheet.get_all_values(value_render_option='FORMULA')
    if any(index < len(original) and headers.index(column) < len(original[index])
           and str(original[index][headers.index(column)]).startswith('=') for column in changes):
        raise ValueError('A selected tracker field contains a formula. Edit its source value in Google Sheets.')
    directory = workspace.store.root.parent / 'backups' / 'reports'
    directory.mkdir(parents=True, exist_ok=True)
    with gzip.open(directory / f'order-edit-{datetime.now():%Y%m%d-%H%M%S-%f}.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump({sheet.title: original}, stream)
    requests = [{'updateCells': {'start': {'sheetId': sheet.id, 'rowIndex': index, 'columnIndex': headers.index(column)},
                 'rows': [{'values': [sheet_cell(value)]}], 'fields': 'userEnteredValue'}} for column, value in values.items()]
    book.batch_update({'requests': requests})
    actual, _ = tracker_state(book)
    saved = next((row for owner, _, _, row in actual.get(key(before), []) if owner.title == sheet.title), None)
    if saved is None or any(not equivalent(column, saved.get(column, ''), value) for column, value in values.items()):
        raise RuntimeError('The order save could not be verified. Refresh the report before retrying.')
    return sheet.title, states


def recorded_changes(workspace, mode, date):
    # Detection dates are India time; explicit report-date edits also remain
    # attached to the historical date from which the user opened the editor.
    with workspace.store.connect() as db:
        rows = db.execute('''SELECT payload FROM import_excel_changes
            WHERE COALESCE(json_extract(payload,'$.Mode'),'excel')=? AND
            (json_extract(payload,'$."Report Date"')=? OR
             date(json_extract(payload,'$."Changed At"'),'+5 hours','+30 minutes')=?)
            ORDER BY id DESC''', (mode, date, date)).fetchall()
    result = []
    for (payload,) in rows:
        event = json.loads(payload)
        record = dict(event.get('Before') or {}, **(event.get('After') or {}))
        record.update({column: event.get(column, '') for column in
                       ('Order Number', 'Change', 'Column', 'Previous Value', 'New Value', 'Changed At', 'Source Tabs')})
        record['_month'] = event.get('Month', record.get('_month', ''))
        result.append(record)
    return result
