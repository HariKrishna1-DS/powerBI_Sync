"""Imported orders belong to a workbook; matching numbers in other files stay separate."""
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

SOURCE_COLUMN = 'Source workbook'
ROW_COLUMN = 'Source row ID'


def number_key(row):
    value = row.get('Order Number')
    return str(value if value is not None else '').strip().casefold()


def order_key(row):
    number = number_key(row)
    source = str(row.get(SOURCE_COLUMN) or '').strip().casefold()
    if source and number:
        parts = [source, number]
        if row.get(ROW_COLUMN):
            parts.append(str(row[ROW_COLUMN]).strip())
        return json.dumps(parts, separators=(',', ':'))
    return number


def sourced_row(row, source):
    return dict(row, **{SOURCE_COLUMN: source})


def source_group(name, worksheet=''):
    """A named input report owns all its orders, regardless of Product."""
    def classify(value):
        hint = re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()
        if any(term in hint for term in ('remaining', 'c o', 'co update', 'current owner')):
            return False
        if 'full search' in hint or hint in ('full xlsx', 'full csv', 'tv orders'):
            return True
        return None
    named = classify(name)
    return named if named is not None else classify(worksheet)


def combine_sources(sources):
    saved, columns, files, reviews, repeats, overlaps = {}, [], [], [], [], []
    first_owner, normalized_sources = {}, []
    for original_source in sources:
        source = deepcopy(original_source)
        frequencies = Counter(number_key(row) for row in source['rows'])
        normalized_sources.append(source)
        columns = list(dict.fromkeys(columns + source['columns'] + [SOURCE_COLUMN]))
        reviews.extend(source.get('reviews', []))
        owners = {}
        metadata = source['files']
        if sum(item['rows'] for item in metadata) != len(source['rows']):
            metadata = [dict(file=source['name'], sheet='', rows=len(source['rows']))]
        offset = 0
        for item in metadata:
            numbers = []
            for position, original in enumerate(source['rows'][offset:offset+item['rows']], offset+2):
                if frequencies[number_key(original)] > 1:
                    sheet = original.get('_source_sheet') or item.get('sheet') or 'Sheet'
                    original[ROW_COLUMN] = f"{sheet}!{original.get('_source_row') or position}"
                    columns = list(dict.fromkeys(columns + [ROW_COLUMN]))
                    source['columns'] = list(dict.fromkeys(source['columns'] + [ROW_COLUMN]))
                row = sourced_row(original, source['name'])
                number = number_key(row)
                if not number:
                    continue
                if number in owners:
                    earlier, earlier_sheet = owners[number]
                    numbers.append(row['Order Number'])
                    repeats.append({**row, 'Occurrence type': 'Within workbook',
                        'Earlier file': source['name'], 'Earlier worksheet': earlier_sheet,
                        'Earlier row': earlier.get('_source_row', ''),
                        'Earlier product': earlier.get('Product', ''),
                        'Earlier date': earlier.get('In-Time') or earlier.get('Date', ''),
                        'Earlier status': earlier.get('Status', ''),
                        'Earlier Out Time': earlier.get('Out Time', ''),
                        'Replacement file': source['name'], 'Replacement worksheet': item.get('sheet', ''),
                        'Replacement row': row.get('_source_row', '')})
                saved[order_key(row)] = row
                owners[number] = row, item.get('sheet', '')
            files.append(dict(item, duplicates=len(numbers), within_file_duplicates=len(numbers),
                              shared_rows=0, duplicate_order_numbers=numbers))
            offset += item['rows']
        # Keep across-workbook diagnostics informational; every source row remains.
        for number, (row, sheet) in owners.items():
            if number in first_owner:
                earlier, earlier_sheet = first_owner[number]
                overlaps.append({**row, 'Occurrence type': 'Across workbooks',
                    'Earlier file': earlier[SOURCE_COLUMN], 'Earlier worksheet': earlier_sheet,
                    'Earlier row': earlier.get('_source_row', ''),
                    'Earlier product': earlier.get('Product', ''),
                    'Earlier date': earlier.get('Date') or earlier.get('In-Time', ''),
                    'Earlier status': earlier.get('Status', ''),
                    'Earlier Out Time': earlier.get('Out Time', ''),
                    'Replacement file': source['name'], 'Replacement worksheet': sheet,
                    'Replacement row': row.get('_source_row', '')})
            else:
                first_owner[number] = row, sheet
    if len(saved) > 100000:
        raise ValueError('The combined report exceeds 100,000 order records.')
    return {'rows': list(saved.values()), 'columns': columns, 'files': files, 'reviews': reviews,
            'sources': normalized_sources, 'duplicate_orders': repeats, 'source_overlap_orders': overlaps, 'diagnostics_version': 5,
            'order_identity': 'occurrence', 'created': datetime.now(timezone.utc).isoformat()}


def upgrade_workbook_orders(imported):
    """Recover each source occurrence; apply saved edits only to its old winning row."""
    if imported.get('order_identity') == 'occurrence' or not imported.get('sources'):
        return imported
    rebuilt = combine_sources(imported['sources'])
    owners = {number_key(row): source['name'] for source in imported['sources'] for row in source['rows']}
    retained = {order_key(row): row for row in rebuilt['rows']}
    def base_key(row):
        return order_key({SOURCE_COLUMN: row.get(SOURCE_COLUMN), 'Order Number': row.get('Order Number')})
    effective = {base_key(dict(row, **{SOURCE_COLUMN: row.get(SOURCE_COLUMN) or owners.get(number_key(row), '')}))
                 for row in imported['rows']}
    if imported.get('order_identity') == 'workbook':
        retained = {identity: row for identity, row in retained.items() if base_key(row) in effective}
    else:
        effective_numbers = {number_key(row) for row in imported['rows']}
        retained = {identity: row for identity, row in retained.items()
                    if number_key(row) in effective_numbers or row[SOURCE_COLUMN] != owners.get(number_key(row))}
    matches_by_number = defaultdict(list)
    for row in retained.values():
        matches_by_number[base_key(row)].append(row)
    renamed = {}
    for old in imported['rows']:
        source = old.get(SOURCE_COLUMN) or owners.get(number_key(old), 'Saved imported orders')
        updated = sourced_row(old, source)
        matches = matches_by_number[base_key(updated)]
        chosen = next((row for row in matches if updated.get(ROW_COLUMN) and row.get(ROW_COLUMN) == updated[ROW_COLUMN]), None)
        if chosen is None:
            chosen = next((row for row in reversed(matches) if updated.get('_source_row')
                           and row.get('_source_row') == updated['_source_row']
                           and (not updated.get('_source_sheet') or row.get('_source_sheet') == updated['_source_sheet'])), None)
        chosen = chosen or next(iter(reversed(matches)), None)
        if chosen and chosen.get(ROW_COLUMN):
            updated[ROW_COLUMN] = chosen[ROW_COLUMN]
        renamed[order_key(old)] = order_key(updated)
        retained[order_key(updated)] = deepcopy(updated)
    result = dict(imported, **{field: rebuilt[field] for field in
                  ('sources', 'files', 'columns', 'duplicate_orders', 'source_overlap_orders', 'diagnostics_version', 'order_identity')})
    result['rows'] = list(retained.values())
    result['columns'] = list(dict.fromkeys(imported['columns'] + result['columns']))
    if 'view_members' in imported:
        result['view_members'] = {label: [renamed.get(identity, identity) for identity in group]
                                  for label, group in imported['view_members'].items()}
    return result
