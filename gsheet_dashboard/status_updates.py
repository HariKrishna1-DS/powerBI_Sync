"""Order status edits shared by tracker reports and the SLA editor."""
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json


def status_name(value):
    from tracker_sync import STATUS_NAMES
    raw = str(value or '').strip()
    return STATUS_NAMES.get(raw.casefold(), raw)


def full_product(row):
    return ' '.join(str(row.get('Product', '')).casefold().split()) in ('full title', 'full search')


def status_records(values, title):
    """Status-only reads tolerate legacy duplicated descriptive columns."""
    from tracker_sync import canonical_headers, text
    headers = canonical_headers(values[0]) if values else []
    if 'Order Number' not in headers or 'Status' not in headers:
        raise ValueError(f'{title}: keep Order Number and Status headers before refreshing.')
    number_col, status_col = headers.index('Order Number'), headers.index('Status')
    result = {}
    for cells in values[1:]:
        if not any(text(cell) for cell in cells):
            continue
        identity = text(cells[number_col] if number_col < len(cells) else '').casefold()
        if not identity or identity in result:
            raise ValueError(f'{title}: resolve blank or repeated Order Numbers before refreshing.')
        result[identity] = status_name(cells[status_col] if status_col < len(cells) else '')
    return result


def tracker_state(book):
    from tracker_sync import tracker_sources, canonical_headers, key
    from monthly_production import decode
    sources = tracker_sources(book)
    owners, states = defaultdict(list), {}
    for _, sheet, values in sources:
        headers = canonical_headers(values[0]) if values else []
        states[sheet.title] = {}
        for index, cells in enumerate(values[1:], 1):
            decoded = decode([values[0], cells])
            if not decoded:
                continue
            row = decoded[0]
            identity = key(row)
            if not identity:
                continue
            status = status_name(row.get('Status'))
            states[sheet.title][identity] = status
            owners[identity].append((sheet, headers, index, row))
    return owners, states


def write_tracker_statuses(workspace, book, owners, replacements):
    from datatrace_sync import sheet_cell
    from production_timing import sla_result
    requests, originals = [], {}
    for identity, status in replacements.items():
        for sheet, headers, index, row in owners[identity]:
            if status_name(row.get('Status')) == status:
                continue
            if 'Status' not in headers:
                raise ValueError(f'{sheet.title} is missing its Status column. No statuses were changed.')
            originals.setdefault(sheet.title, sheet)
            values = {'Status': status}
            if 'Free Site' in headers:
                values['Free Site'] = sla_result(dict(row, Status=status))[0]
            for column, value in values.items():
                requests.append({'updateCells': {'start': {'sheetId': sheet.id, 'rowIndex': index,
                    'columnIndex': headers.index(column)}, 'rows': [{'values': [sheet_cell(value)]}],
                    'fields': 'userEnteredValue'}})
    if requests:
        directory = workspace.store.root.parent / 'backups' / 'reports'
        directory.mkdir(parents=True, exist_ok=True)
        with gzip.open(directory / f'status-edit-{datetime.now():%Y%m%d-%H%M%S-%f}.json.gz', 'wt', encoding='utf-8') as stream:
            json.dump({title: sheet.get_all_values(value_render_option='FORMULA') for title, sheet in originals.items()}, stream)
        book.batch_update({'requests': requests})
        actual, _ = tracker_state(book)
        for identity, status in replacements.items():
            if any(status_name(row.get('Status')) != status for _, _, _, row in actual[identity]):
                raise RuntimeError('The status save could not be verified. Refresh before retrying.')
    return len(replacements)


def sync_tracker_status_tabs(workspace, book):
    """Compare each copy to its own baseline so unchanged copies cannot undo edits.

    Missing rows in a derived tab do not delete production orders. A first read
    compares report statuses with their owning tracker, allowing existing edits.
    """
    from tracker_sync import key
    from monthly_views import view_identity
    owners, states = tracker_state(book)
    current = {identity: status_name(items[0][3].get('Status')) for identity, items in owners.items()}
    previous = workspace.read().get('tracker_status_baseline') or {}
    sheets = book.worksheets()
    latest = max((view_identity(s.title)[1] for s in sheets if view_identity(s.title)), default='')
    for sheet in sheets:
        detail = view_identity(sheet.title)
        if sheet.title != 'All Products' and (not detail or detail[1] != latest):
            continue
        values = sheet.get_all_values(value_render_option='UNFORMATTED_VALUE')
        # A legacy capture archive is not an editable order view.
        if not values or 'Preview' in values[0]:
            continue
        states[sheet.title] = status_records(values, sheet.title)
    proposals = defaultdict(set)
    for title, statuses in states.items():
        baseline = previous.get(title, current)
        for identity, status in statuses.items():
            if identity in owners and status != baseline.get(identity, current[identity]):
                proposals[identity].add(status)
    if any(len(options) > 1 for options in proposals.values()):
        raise ValueError('Conflicting Status edits exist in different Google Sheets tabs. Make those statuses agree, then refresh. No statuses were changed.')
    replacements = {identity: next(iter(options)) for identity, options in proposals.items()}
    if any(not status for status in replacements.values()):
        raise ValueError('Enter a nonblank Status before refreshing. No statuses were changed.')
    changed = any(status != previous.get(title, {}).get(identity, status)
                  for title, statuses in states.items() if title in {items[0][0].title for items in owners.values()}
                  for identity, status in statuses.items())
    changed = changed or any(status != current[identity] for identity, status in replacements.items())
    write_tracker_statuses(workspace, book, owners, replacements)
    for identity, status in replacements.items():
        for sheet, _, _, _ in owners[identity]:
            states[sheet.title][identity] = status
    workspace.save(tracker_status_baseline=states, cloud_checked_at=datetime.now(timezone.utc).isoformat(), cloud_refresh_error=None)
    return changed


def rename_status(workspace, book, snapshot, old, new, selected):
    from tracker_sync import key
    from production_timing import sla_result
    rows = snapshot['sheets']['Overview']['rows']
    matching = {key(row): row for row in rows if (status_name(row.get('Status') or row.get('Task Status')) or '(Blank)') == old}
    if not matching or set(matching) != set(selected):
        raise ValueError('Orders in this status changed since you opened the editor. Refresh SLA Status and try again.')
    settings = workspace.read()
    if settings['mode'] == 'excel':
        from copy import deepcopy
        imported = deepcopy(settings['imported'])
        for row in imported['rows']:
            if key(row) in matching:
                row['Status'] = new
                if 'Task Status' in row:
                    row['Task Status'] = new
                row['Free Site'] = sla_result(row)[0]
        workspace.save(imported=imported, row_count=len(imported['rows']))
    elif snapshot.get('report_origin') == 'previews':
        from preview_reporting import save_preview_edits
        save_preview_edits(workspace, matching.values(), {'Status': new, 'Task Status': new})
    else:
        owners, states = tracker_state(book)
        replacements = {identity: new for identity in matching}
        write_tracker_statuses(workspace, book, owners, replacements)
        baseline = settings.get('tracker_status_baseline', states)
        for identity in matching:
            for sheet, _, _, _ in owners[identity]:
                baseline.setdefault(sheet.title, {})[identity] = new
        workspace.save(tracker_status_baseline=baseline)
    return len(matching)
