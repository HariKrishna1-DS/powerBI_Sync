"""Imported orders belong to a workbook; matching numbers in other files stay separate."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

SOURCE_COLUMN = 'Source workbook'


def number_key(row):
    value = row.get('Order Number')
    return str(value if value is not None else '').strip().casefold()


def order_key(row):
    number = number_key(row)
    source = str(row.get(SOURCE_COLUMN) or '').strip().casefold()
    return json.dumps([source, number], separators=(',', ':')) if source and number else number


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
    first_owner = {}
    for source in sources:
        columns = list(dict.fromkeys(columns + source['columns'] + [SOURCE_COLUMN]))
        reviews.extend(source.get('reviews', []))
        owners = {}
        metadata = source['files']
        if sum(item['rows'] for item in metadata) != len(source['rows']):
            metadata = [dict(file=source['name'], sheet='', rows=len(source['rows']))]
        offset = 0
        for item in metadata:
            numbers = []
            for original in source['rows'][offset:offset+item['rows']]:
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
                        'Replacement file': source['name'], 'Replacement worksheet': item.get('sheet', ''),
                        'Replacement row': row.get('_source_row', '')})
                saved[order_key(row)] = row
                owners[number] = row, item.get('sheet', '')
            files.append(dict(item, duplicates=len(numbers), within_file_duplicates=len(numbers),
                              shared_rows=0, duplicate_order_numbers=numbers))
            offset += item['rows']
        # Compare retained workbook records so repeats within a file never inflate
        # the informational across-workbook list or change the duplicate count.
        for number, (row, sheet) in owners.items():
            if number in first_owner:
                earlier, earlier_sheet = first_owner[number]
                overlaps.append({**row, 'Occurrence type': 'Across workbooks',
                    'Earlier file': earlier[SOURCE_COLUMN], 'Earlier worksheet': earlier_sheet,
                    'Earlier row': earlier.get('_source_row', ''),
                    'Earlier product': earlier.get('Product', ''),
                    'Earlier date': earlier.get('Date') or earlier.get('In-Time', ''),
                    'Earlier status': earlier.get('Status', ''),
                    'Replacement file': source['name'], 'Replacement worksheet': sheet,
                    'Replacement row': row.get('_source_row', '')})
            else:
                first_owner[number] = row, sheet
    if len(saved) > 100000:
        raise ValueError('The combined report exceeds 100,000 order records.')
    return {'rows': list(saved.values()), 'columns': columns, 'files': files, 'reviews': reviews,
            'sources': sources, 'duplicate_orders': repeats, 'source_overlap_orders': overlaps, 'diagnostics_version': 4,
            'order_identity': 'workbook', 'created': datetime.now(timezone.utc).isoformat()}


def upgrade_workbook_orders(imported):
    """Recover each workbook copy and apply saved edits only to its previous owner."""
    if imported.get('order_identity') == 'workbook' or not imported.get('sources'):
        return imported
    rebuilt = combine_sources(imported['sources'])
    owners = {number_key(row): source['name'] for source in imported['sources'] for row in source['rows']}
    retained = {order_key(row): row for row in rebuilt['rows']}
    effective_numbers = {number_key(row) for row in imported['rows']}
    for number in owners.keys() - effective_numbers:
        retained.pop(order_key({'Order Number': number, SOURCE_COLUMN: owners[number]}), None)
    for old in imported['rows']:
        source = old.get(SOURCE_COLUMN) or owners.get(number_key(old), 'Saved imported orders')
        updated = sourced_row(old, source)
        retained[order_key(updated)] = deepcopy(updated)
    result = dict(imported, **{field: rebuilt[field] for field in
                  ('sources', 'files', 'columns', 'duplicate_orders', 'source_overlap_orders', 'diagnostics_version', 'order_identity')})
    result['rows'] = list(retained.values())
    result['columns'] = list(dict.fromkeys(imported['columns'] + result['columns']))
    # Old membership keys referenced the global winning copy. Recompute the
    # source views from the now-independent rows, retaining all business edits.
    result.pop('view_members', None)
    return result
