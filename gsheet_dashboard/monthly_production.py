"""Month ownership and atomic, previewed production maintenance.

New orders enter their arrival month. Blank Out Time is carried only by a
confirmed rollover, never by an ordinary capture. Once carried, an order stays
in its current month when completed. September 2026 is a read-only archive.
Raw capture history remains immutable; sorting applies to production records.
"""
from collections import Counter
from datetime import datetime, timedelta
from io import BytesIO
import hashlib
import json
import re
import secrets
import time
from zipfile import ZipFile

from sync_config import FULL_TRACKER_TITLE, REMAINING_TRACKER_TITLE

BASES = (FULL_TRACKER_TITLE, REMAINING_TRACKER_TITLE)
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
ARCHIVE = '2026-09'
LEDGER = '__DataTrace_MonthlyOps'


def month_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value):
        raise ValueError('Choose a month in YYYY-MM format.')
    datetime.strptime(value, '%Y-%m')
    return value


def next_month(month):
    date = datetime.strptime(month_key(month), '%Y-%m')
    return (date.replace(day=28) + timedelta(days=4)).strftime('%Y-%m')


def tab_name(base, month):
    month_key(month)
    if base not in BASES:
        raise ValueError('Unknown production report type.')
    return f'{base}_{MONTHS[int(month[5:])-1]}_{month[:4]}'


def tab_identity(title):
    for base in BASES:
        match = re.fullmatch(re.escape(base) + r'_([A-Za-z]{3})_(\d{4})', title)
        if match and match[1] in MONTHS:
            return base, f'{match[2]}-{MONTHS.index(match[1])+1:02}'
    return None


def local_datetime(value):
    """Parse wall-clock values without converting their timezone."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    raw = re.sub(r'\s+', ' ', str(value or '')).strip()
    if not raw:
        return None
    if re.fullmatch(r'\d{5}(?:\.\d+)?', raw) and 20000 <= float(raw) < 100000:
        return datetime(1899, 12, 30) + timedelta(days=float(raw))
    try:
        return datetime.fromisoformat(raw.replace('Z', '+00:00')).replace(tzinfo=None)
    except ValueError:
        pass
    for pattern in ('%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M:%S',
                    '%m/%d/%Y %H:%M', '%m/%d/%Y', '%m/%d/%y %I:%M:%S %p', '%m/%d/%y'):
        try:
            return datetime.strptime(raw.upper(), pattern)
        except ValueError:
            pass
    return None


def arrival_sort(rows, reviews=None):
    from tracker_sync import key
    decorated = []
    for row in rows:
        date = local_datetime(row.get('In-Time', row.get('Arrival Time', row.get('RequestArrivalTime'))))
        if date is None and reviews is not None:
            reviews.append({'Order Number': row.get('Order Number', ''), 'Reason': 'Missing or invalid In-Time; sorted last'})
        decorated.append((date or datetime.max, key(row), row))
    return [dict(item[2], No=index) for index, item in enumerate(sorted(decorated, key=lambda item: item[:2]), 1)]


def decode(values):
    from tracker_sync import canonical_headers
    if not values:
        return []
    headers = canonical_headers(values[0])
    return [dict(zip(headers, list(row) + [''] * (len(headers)-len(row)))) for row in values[1:] if any(str(v).strip() for v in row)]


def encode(rows, headers):
    from tracker_sync import canonical_headers
    keys = canonical_headers(headers)
    return [list(headers)] + [[row.get(key, '') for key in keys] for row in rows]


def extend_headers(headers, rows):
    from tracker_sync import canonical_headers
    result, keys = list(headers), set(canonical_headers(headers))
    for row in rows:
        for name in row:
            if name not in keys and not name.startswith('_'):
                result.append(name)
                keys.add(name)
    return result


def production_sources(book, sheets=None):
    from sheet_reads import read_values
    selected = [sheet for sheet in (book.worksheets() if sheets is None else sheets) if tab_identity(sheet.title)]
    return [(tab_identity(sheet.title)[0], sheet, values) for sheet, values in zip(selected, read_values(book, selected))]


def snapshot(book):
    aliases = set(BASES) | {'Full Title', 'Remaining Products'} | {base + '_-_September_2026' for base in BASES}
    data = {s.title: {'id': s.id, 'values': s.get_all_values(value_render_option='FORMULA'), 'formula_cells': []}
            for s in book.worksheets() if tab_identity(s.title) or s.title in aliases}
    candidates = [title for title, sheet in data.items() if any(isinstance(v, str) and v.startswith('=') for row in sheet['values'] for v in row)]
    if candidates:
        # FORMULA rendering alone cannot distinguish a formula from literal '=text'.
        # Read the actual value type before retaining anything executable.
        meta = book.fetch_sheet_metadata(params={'ranges': ["'"+title.replace("'", "''")+"'" for title in candidates],
            'fields': 'sheets(properties(title),data(startRow,startColumn,rowData(values(userEnteredValue(formulaValue)))))'})
        for sheet in meta.get('sheets', []):
            title = sheet['properties']['title']
            if title not in data:
                continue
            for grid in sheet.get('data', []):
                for i, row in enumerate(grid.get('rowData', []), grid.get('startRow', 0)):
                    for j, cell in enumerate(row.get('values', []), grid.get('startColumn', 0)):
                        if 'formulaValue' in cell.get('userEnteredValue', {}):
                            data[title]['formula_cells'].append([i, j])
    return data


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def new_plan(data, kind):
    return {'id': secrets.token_hex(16), 'kind': kind, 'created': time.time(), 'fingerprint': fingerprint(data),
            'writes': {}, 'renames': {}, 'reviews': [], 'counts': [], 'moves': []}


def ensure_pairs(plan, data):
    from tracker_sync import HEADERS
    periods = {tab_identity(title)[1] for title in plan['writes'] if tab_identity(title)}
    for month in periods:
        for base in BASES:
            title = tab_name(base, month)
            if title not in plan['writes'] and title not in data:
                plan['writes'][title] = [HEADERS]
    return plan


def migration_plan(data, working_month='2026-10'):
    from tracker_sync import HEADERS
    month_key(working_month)
    plan = new_plan(data, 'setup')
    if working_month <= ARCHIVE:
        raise ValueError('Working month must be after the September archive.')
    for base, short in zip(BASES, ('Full Title', 'Remaining Products')):
        old = [name for name in (base, base + '_-_September_2026', short) if name in data]
        if len(old) > 1:
            raise ValueError(f'Multiple legacy tabs for {base}; reconcile them before setup.')
        target = tab_name(base, ARCHIVE)
        if old:
            if target in data:
                raise ValueError(f'Both {old[0]} and {target} exist; no automatic overwrite is safe.')
            plan['renames'][old[0]] = target
            plan['counts'].append({'source': old[0], 'target': target, 'renamed': len(decode(data[old[0]]['values']))})
        title = tab_name(base, working_month)
        if title not in data:
            plan['writes'][title] = [HEADERS]
            plan['counts'].append({'target': title, 'added': 0})
    return plan


def read_import(content, base):
    """Read positional headers (including both SLA columns), never pandas mangling."""
    from openpyxl import load_workbook
    from tracker_sync import canonical_headers, key, text
    with ZipFile(BytesIO(content)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('Expanded workbook exceeds the 100 MB import limit.')
    book = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        name = 'TV Orders' if base == BASES[0] else 'Sheet1'
        if name not in book.sheetnames:
            raise ValueError(f'Workbook must contain the {name} worksheet.')
        sheet = book[name]
        if sheet.max_row > 100001 or sheet.max_column > 100:
            raise ValueError('Workbook exceeds 100,000 rows or 100 columns.')
        iterator = sheet.iter_rows(values_only=True)
        headers = [text(v) for v in next(iterator, ())]
        while headers and not headers[-1]:
            headers.pop()
        keys = canonical_headers(headers)
        if 'Order Number' not in keys or 'In-Time' not in keys or 'Out Time' not in keys or any(not h for h in headers):
            raise ValueError('Headers must include Order Number, In-Time and Out Time, without blank columns.')
        saved, reviews, read = {}, [], 0
        for index, cells in enumerate(iterator, 2):
            if not any(v is not None for v in cells):
                continue
            read += 1
            row = dict(zip(keys, [text(v) for v in cells]))
            identity = key(row)
            if not identity:
                reviews.append({'row': index, 'Reason': 'Missing Order Number; skipped'})
                continue
            if identity in saved:
                reviews.append({'row': index, 'Order Number': row['Order Number'], 'Reason': 'Duplicate Order Number; last source row retained'})
            saved[identity] = row
        return {'headers': headers, 'rows': list(saved.values()), 'read': read, 'reviews': reviews,
                'skipped': read-len(saved)}
    finally:
        book.close()


def active_locations(data):
    from tracker_sync import key
    result = {}
    for title, sheet in data.items():
        identity = tab_identity(title)
        if not identity or identity[1] <= ARCHIVE:
            continue
        for row in decode(sheet['values']):
            number = key(row)
            if not number or number in result:
                raise ValueError('Missing or duplicate Order Number in active month tabs. Resolve it before changing production.')
            result[number] = (title, row)
    return result


def import_plan(data, uploads, month):
    from tracker_sync import key
    month_key(month)
    if month <= ARCHIVE:
        raise ValueError('September is archived and cannot be imported.')
    if not any(tab_identity(title) for title in data):
        raise ValueError('Set up monthly tabs before importing production workbooks.')
    plan, locations = new_plan(data, 'import'), active_locations(data)
    rows_by_title, headers_by_title = {}, {}
    for base, name, source in uploads:
        count = {'source': name, 'read': source['read'], 'added': 0, 'updated': 0, 'unchanged': 0, 'skipped': source['skipped'], 'targets': {}}
        plan['reviews'].extend(dict(r, source=name) for r in source['reviews'])
        for row in source['rows']:
            number = key(row)
            existing = locations.get(number)
            out, arrival = local_datetime(row.get('Out Time')), local_datetime(row.get('In-Time'))
            if str(row.get('Out Time', '')).strip() and out is None:
                plan['reviews'].append({'source': name, 'Order Number': row['Order Number'], 'Reason': 'Invalid Out Time; retained for review'})
            period = (out or arrival).strftime('%Y-%m') if (out or arrival) else month
            if existing:
                title, prior = existing
                if tab_identity(title)[0] != base:
                    count['skipped'] += 1
                    plan['reviews'].append({'source': name, 'Order Number': row['Order Number'], 'Reason': 'Existing product group differs; skipped'})
                    continue
            else:
                if period <= ARCHIVE:
                    count['skipped'] += 1
                    plan['reviews'].append({'source': name, 'Order Number': row['Order Number'], 'Reason': 'Arrival/completion targets archived month; skipped'})
                    continue
                title, prior = tab_name(base, period), None
            if title not in rows_by_title:
                rows_by_title[title] = {key(r): r for r in decode(data.get(title, {}).get('values', []))}
                # Input headers lead, extra existing columns follow without losing data.
                headers_by_title[title] = extend_headers(source['headers'], rows_by_title[title].values())
            merged = dict(prior or {}, **row)
            if prior and prior.get('Carried From'):
                merged['Carried From'] = prior['Carried From']
            # Re-importing an earlier workbook cannot erase later completion evidence.
            if prior and local_datetime(prior.get('Out Time')) and not str(row.get('Out Time', '')).strip():
                for column in ('Out Time', 'Status', 'Free Site'):
                    if column in prior:
                        merged[column] = prior[column]
                plan['reviews'].append({'source': name, 'Order Number': row['Order Number'], 'Reason': 'Kept later completion evidence from current production'})
            count['added' if prior is None else 'unchanged' if all(str(prior.get(k, '')) == str(v) for k, v in merged.items() if k != 'No') else 'updated'] += 1
            rows_by_title[title][number] = merged
            locations[number] = (title, merged)
            count['targets'][title] = count['targets'].get(title, 0)+1
        plan['counts'].append(count)
    for title, rows in rows_by_title.items():
        ordered = arrival_sort(rows.values(), plan['reviews'])
        plan['writes'][title] = encode(ordered, extend_headers(headers_by_title[title], ordered))
    return ensure_pairs(plan, data)


def rollover_plan(data, month):
    from tracker_sync import key
    month_key(month)
    if month <= ARCHIVE:
        raise ValueError('September is an archive and cannot be rolled over.')
    active_locations(data)  # Reject ambiguous ownership before planning removals.
    plan = new_plan(data, 'rollover')
    plan['month'] = month
    rows_by_title = {}
    for base in BASES:
        title = tab_name(base, month)
        if title not in data:
            continue
        rows = decode(data[title]['values'])
        retained = []
        counts = Counter()
        for row in rows:
            raw_out = str(row.get('Out Time', '')).strip()
            out = local_datetime(raw_out)
            # Already carried orders stay in their current month when completed.
            target_month = (out.strftime('%Y-%m') if out and not row.get('Carried From') else month) if raw_out else next_month(month)
            if raw_out and not out:
                plan['reviews'].append({'Order Number': row.get('Order Number'), 'Reason': 'Invalid Out Time; retained for review'})
            if target_month <= ARCHIVE or target_month == month:
                retained.append(row)
                continue
            target = tab_name(base, target_month)
            rows_by_title.setdefault(target, decode(data.get(target, {}).get('values', [])))
            moved = dict(row)
            if not raw_out:
                previous = str(moved.get('Carried From', '')).strip()
                label = f'{MONTHS[int(month[5:])-1]}_{month[:4]}'
                moved['Carried From'] = ', '.join(filter(None, [previous, label]))
            rows_by_title[target].append(moved)
            reason = 'No Out Time at rollover' if not raw_out else 'Completion month'
            plan['moves'].append({'Order Number': row['Order Number'], 'from': title, 'to': target, 'reason': reason})
            counts[target] += 1
        if counts:
            rows_by_title[title] = retained
        plan['counts'].extend({'source': title, 'target': target, 'moved': count} for target, count in counts.items())
    for title, rows in rows_by_title.items():
        base = tab_identity(title)[0]
        headers = data.get(title, data.get(tab_name(base, month), {})).get('values', [[]])[0]
        plan['writes'][title] = encode(arrival_sort(rows, plan['reviews']), extend_headers(headers, rows))
    return ensure_pairs(plan, data)


def plain_format(sheet_id, rows, cols):
    region = {'sheetId': sheet_id, 'startRowIndex': 0, 'endRowIndex': max(rows, 1), 'startColumnIndex': 0, 'endColumnIndex': max(cols, 1)}
    black, white = {'red': 0, 'green': 0, 'blue': 0}, {'red': 1, 'green': 1, 'blue': 1}
    border = {'style': 'SOLID', 'color': black}
    return [
        {'repeatCell': {'range': region, 'cell': {'userEnteredFormat': {'backgroundColor': white,
          'textFormat': {'foregroundColor': black, 'bold': False}}}, 'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat'}},
        {'repeatCell': {'range': dict(region, endRowIndex=1), 'cell': {'userEnteredFormat': {'textFormat': {'foregroundColor': black, 'bold': True}}}, 'fields': 'userEnteredFormat.textFormat'}},
        {'updateBorders': {'range': region, **{side: border for side in ('top', 'bottom', 'left', 'right', 'innerHorizontal', 'innerVertical')}}},
    ]


def receipt(book, operation):
    ledger = next((s for s in book.worksheets() if s.title == LEDGER), None)
    return bool(ledger and any(row and row[0] == operation for row in ledger.get_all_values()[1:]))


def apply_plan(book, plan, check=True):
    """Backups, creates, renames, replacements and receipt are one atomic batch.

    A stable cloud receipt handles a lost reply. Only replay when it is absent;
    fixed sheet IDs mean an uncertain creation cannot execute twice.
    """
    from tracker_sync import text
    from datatrace_sync import write_sheet_batch
    from tracker_formatting import format_requests
    from monthly_views import view_identity, keep_view_headers
    if receipt(book, plan['id']):
        return {'applied': True, 'recovered': True}
    before = snapshot(book)
    if check and fingerprint(before) != plan['fingerprint']:
        raise ValueError('Production changed after this preview. Generate a fresh preview before confirming.')
    if check and time.time() - plan['created'] > 1800:
        raise ValueError('This preview expired. Generate a fresh preview before confirming.')
    sheets = {s.title: s for s in book.worksheets()}
    for title, expected in plan.get('archive_fingerprints', {}).items():
        values = sheets[title].get_all_values(value_render_option='UNFORMATTED_VALUE') if title in sheets else []
        if fingerprint(values) != expected:
            raise ValueError('Capture history changed during sync. Retry after reviewing its latest contents.')
    if plan['kind'] != 'monthly_views' and not plan.get('preserve_report_views'):
        from monthly_views import monthly_view_values
        after = {plan['renames'].get(title, title): decode(sheet['values']) for title, sheet in before.items()}
        after.update({title: decode(values) for title, values in plan['writes'].items() if tab_identity(title) or title in BASES})
        schema = next((plan['writes'].get(title, sheet['values'])[0] for title, sheet in before.items()
            if title == BASES[0] or (tab_identity(title) and tab_identity(title)[0] == BASES[0])), None)
        plan['writes'].update(monthly_view_values(after, headers=schema))
    used = {s.id for s in sheets.values()}
    def new_id():
        number = secrets.randbelow(2**30)
        while number in used:
            number = secrets.randbelow(2**30)
        used.add(number)
        return number
    requests, ids, backups = [], {name: s.id for name, s in sheets.items()}, []
    affected = set(plan['renames']) | (set(plan['writes']) & set(before))
    affected.update(title for title in ('All Products', 'Sheet1') if title in plan['writes'] and title in sheets and title not in plan.get('append_from', {}))
    affected.update(title for title in plan['writes'] if view_identity(title) and title in sheets)
    affected.update(name for title in plan['writes'] if view_identity(title)
                    for name in sheets if view_identity(name) == view_identity(title))
    for index, title in enumerate(sorted(affected)):
        backup = f'__DataTrace_Backup_{plan["id"][:12]}_{index}'
        backups.append(backup)
        requests.append({'duplicateSheet': {'sourceSheetId': ids[title], 'newSheetId': new_id(), 'newSheetName': backup}})
    for old, new in plan['renames'].items():
        ids[new] = ids.pop(old)
        requests.append({'updateSheetProperties': {'properties': {'sheetId': ids[new], 'title': new}, 'fields': 'title'}})
    writes = dict(plan['writes'])
    old_ledger = sheets[LEDGER].get_all_values() if LEDGER in sheets else [['Operation', 'Kind', 'Timestamp', 'Order Number', 'From tab', 'To tab', 'Reason']]
    stamp = datetime.now().isoformat(timespec='seconds')
    ledger_rows = [[plan['id'], plan['kind'], stamp, m['Order Number'], m['from'], m['to'], m['reason']] for m in plan['moves']]
    writes[LEDGER] = old_ledger + [[plan['id'], plan['kind'], stamp, '', '', '', 'Committed']] + ledger_rows
    append_from = dict(plan.get('append_from', {}))
    if LEDGER in sheets:
        append_from[LEDGER] = len(old_ledger)
    metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats)'})
    for title, values in writes.items():
        if title not in ids and view_identity(title):
            alias = next((name for name in list(ids) if view_identity(name) == view_identity(title)), None)
            if alias:
                ids[title] = ids.pop(alias)
                sheets[title] = sheets.pop(alias)
                requests.append({'updateSheetProperties': {'properties': {'sheetId': ids[title], 'title': title}, 'fields': 'title'}})
        if view_identity(title) and title in sheets:
            values = keep_view_headers(values, sheets[title].get_all_values())
        if title not in ids:
            ids[title] = new_id()
            requests.append({'addSheet': {'properties': {'sheetId': ids[title], 'title': title,
                'hidden': title == LEDGER, 'gridProperties': {'rowCount': max(2, len(values)), 'columnCount': max(1, len(values[0]))}}}})
        prior_values = before.get(title, {}).get('values', [])
        if view_identity(title) and title in sheets:
            prior_values = sheets[title].get_all_values()
        cols = max(len(values[0]), max((len(r) for r in prior_values), default=0))
        height = max(len(values), len(prior_values), 2)
        requests.append({'updateSheetProperties': {'properties': {'sheetId': ids[title], 'gridProperties': {
            'rowCount': max(height, getattr(sheets.get(title), 'row_count', 0)), 'columnCount': max(cols, getattr(sheets.get(title), 'col_count', 0)), 'frozenRowCount': 1}}, 'fields': 'gridProperties'}})
        # All imported text is literal; existing formulas are explicitly preserved.
        formula_cells = plan.get('formula_cells', {}).get(title, [])
        formula_positions = {tuple(cell) for cell in formula_cells}
        cell_rows = []
        start_row = append_from.get(title, 0)
        for i, row in enumerate(values[start_row:], start_row):
            cells = []
            for j, value in enumerate(row):
                val = {'formulaValue' if (i, j) in formula_positions else 'stringValue': text(value)}
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    val = {'numberValue': value}
                cells.append({'userEnteredValue': val})
            cell_rows.append({'values': cells})
        location = {'start': {'sheetId': ids[title], 'rowIndex': start_row, 'columnIndex': 0}} if start_row else {
            'range': {'sheetId': ids[title], 'startRowIndex': 0, 'endRowIndex': height, 'startColumnIndex': 0, 'endColumnIndex': cols}}
        requests.append({'updateCells': {**location, 'rows': cell_rows, 'fields': 'userEnteredValue'}})
        if title != LEDGER:
            rules = next((item.get('conditionalFormats', []) for item in metadata['sheets'] if item['properties']['sheetId'] == ids[title]), [])
            requests.extend(format_requests(ids[title], values, rules))
    # Renamed archive values stay untouched while status colors follow the palette.
    for old, new in plan['renames'].items():
        values = before[old]['values']
        rules = next((item.get('conditionalFormats', []) for item in metadata['sheets'] if item['properties']['sheetId'] == ids[new]), [])
        requests.extend(format_requests(ids[new], values, rules))
    for title in plan.get('format_titles', []):
        if title in writes or title in plan['renames'].values() or title not in before:
            continue
        values = before[title]['values']
        rules = next((item.get('conditionalFormats', []) for item in metadata['sheets'] if item['properties']['sheetId'] == ids[title]), [])
        requests.extend(format_requests(ids[title], values, rules))
    target = next(iter(sheets.values()), type('Target', (), {'title': 'monthly production'})())
    write_sheet_batch(book, target, requests, verify_commit=lambda: receipt(book, plan['id']))
    if not receipt(book, plan['id']):
        raise RuntimeError('The monthly operation could not be verified. Keep this preview and retry to recover its receipt.')
    return {'applied': True, 'backups': backups}


def preserve_formulas(plan, before):
    """Track formulas by order/column as sorting changes their physical positions."""
    from tracker_sync import key, canonical_headers
    from openpyxl.formula.translate import Translator, TranslatorError
    from openpyxl.utils import get_column_letter
    originals = {}
    for title, sheet in before.items():
        identity = tab_identity(title)
        if identity and identity[1] <= ARCHIVE:
            continue
        keys = canonical_headers(sheet['values'][0]) if sheet['values'] else []
        formula_cells = {tuple(cell) for cell in sheet.get('formula_cells', [])}
        for i, row in enumerate(decode(sheet['values']), 1):
            columns = {column: f'{get_column_letter(j+1)}{i+1}' for j, column in enumerate(keys) if (i, j) in formula_cells}
            originals[(identity[0] if identity else title, key(row))] = (row, columns)
    positions = {}
    for title, values in plan['writes'].items():
        identity = tab_identity(title)
        if not identity:
            continue
        keys = canonical_headers(values[0])
        for i, row in enumerate(decode(values), 1):
            original, formula_columns = originals.get((identity[0], key(row)), ({}, {}))
            for j, column in enumerate(keys):
                val = row.get(column, '')
                if column in formula_columns and isinstance(val, str) and val.startswith('=') and original.get(column) == val:
                    try:
                        values[i][j] = Translator(val, origin=formula_columns[column]).translate_formula(f'{get_column_letter(j+1)}{i+1}')
                    except (TranslatorError, ValueError, IndexError) as exc:
                        raise ValueError(f'Cannot safely relocate the formula for order {row.get("Order Number")}, column {column}. Review it before continuing.') from exc
                    positions.setdefault(title, []).append([i, j])
    plan['formula_cells'] = positions
    return plan


def monthly_workbook(report, sources):
    """Use the app's existing openpyxl runtime for its generated export API."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    month = month_key(report['Month'])
    book = Workbook()
    book.remove(book.active)
    for base, name in zip(BASES, ('Full Search', 'C-O and Update')):
        selected = [(title, values) for source_base, title, values in sources if source_base == base]
        headers = next((v[0] for t, v in selected if t == tab_name(base, month) and v), None)
        rows = [r for r in report['rows'] if r.get('_tracker', r.get('_sheet')) == base or tab_identity(r.get('_sheet', '')) == (base, month)]
        if headers is None:
            headers = next((v[0] for _, v in selected if v), report['columns'])
        values = encode(arrival_sort(rows), extend_headers(headers, rows))
        sheet = book.create_sheet(name)
        for row in values:
            sheet.append(row)
    summary = book.create_sheet('Summary')
    summary.append(['Month', month, None])
    summary.append(['Metric', 'Count', 'Percentage'])
    for name in ('Month Orders', 'Completed Orders', 'Unchanged', 'Awaiting for Clarification', 'SLA On Time', 'SLA Missed'):
        denominator = report.get('SLA On Time', 0) + report.get('SLA Missed', 0) if name.startswith('SLA ') else report['Month Orders']
        count = report.get(name, 0)
        summary.append([name, count, count/denominator if denominator else 0])
        summary.cell(summary.max_row, 3).number_format = '0.0%'
    border = Border(**{side: Side(style='thin', color='000000') for side in ('left', 'right', 'top', 'bottom')})
    for sheet in book:
        sheet.freeze_panes = 'A3' if sheet.title == 'Summary' else 'A2'
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                cell.font = Font(name='Calibri', size=11, color='000000', bold=cell.row == (2 if sheet.title == 'Summary' else 1))
                cell.fill = PatternFill('solid', fgColor='FFFFFF')
                cell.border = border
                cell.alignment = Alignment(vertical='top', wrap_text=True)
        for column in sheet.columns:
            width = min(40, max(14, max(len(str(c.value or '')) for c in column)+2))
            sheet.column_dimensions[column[0].column_letter].width = width
        if sheet.title != 'Summary':
            sheet.auto_filter.ref = sheet.dimensions
            from server import color_export_sheet
            color_export_sheet(sheet, list(sheet.values))
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream, f'TV_Search_Production_Report_{MONTHS[int(month[5:])-1]}_{month[:4]}.xlsx'
