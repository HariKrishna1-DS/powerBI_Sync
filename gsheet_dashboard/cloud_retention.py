"""Explicit archive/restore of old app-generated backup tabs, never raw evidence."""
from sheets_writer import coordinated
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import json
import re
import uuid

from backup_protection import protect, unprotect
from workspace_backup import write_verified_backup

NAME = re.compile(r'^__DataTrace_Backup_([a-f0-9]{12})_\d+$')
FILE = re.compile(r'^cloud-history-[a-f0-9]{32}\.tvcloud$')
LIMIT = 64 * 1024 * 1024
CELL_FIELDS = ('userEnteredValue', 'userEnteredFormat', 'note', 'textFormatRuns', 'dataValidation')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def plan(book, keep=5):
    from monthly_production import LEDGER
    from gspread.exceptions import WorksheetNotFound
    if type(keep) is not int or keep < 2:
        raise ValueError('Retain at least two recent backup operations.')
    metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties)'})['sheets']
    try:
        ledger = book.worksheet(LEDGER).get_all_values()
    except WorksheetNotFound:
        ledger = []
    stamps = {}
    for row in ledger[1:]:
        if len(row) >= 7 and row[6] == 'Committed':
            try:
                stamp = datetime.fromisoformat(row[2]).replace(tzinfo=None).isoformat()
                stamps[row[0][:12]] = stamp
            except (TypeError, ValueError):
                continue
    groups = {match[1] for item in metadata if (match := NAME.fullmatch(item['properties']['title'])) and match[1] in stamps}
    retained = set(sorted(groups, key=lambda group: (stamps[group], group), reverse=True)[:keep])
    candidates = []
    cells = 0
    for item in metadata:
        props = item['properties']
        grid = props.get('gridProperties', {})
        count = grid.get('rowCount', 0) * grid.get('columnCount', 0)
        cells += count
        match = NAME.fullmatch(props['title'])
        if match and match[1] in groups - retained:
            candidates.append({'id': props['sheetId'], 'title': props['title'], 'cells': count, 'created': stamps[match[1]]})
    return {'tabs': candidates, 'allocated_cells': cells, 'reclaimable_cells': sum(t['cells'] for t in candidates),
            'fingerprint': fingerprint(candidates), 'keep_operations': keep,
            'policy': 'Keep the latest five recorded backup operations. Archive older generated backup tabs only. Canonical trackers, preview history, monthly evidence, unknown tabs and unrecognized backups are retained.'}


def read_tabs(book, tabs):
    ranges = ["'" + tab['title'].replace("'", "''") + "'" for tab in tabs]
    result = book.fetch_sheet_metadata(params={'includeGridData': True, 'ranges': ranges})['sheets']
    expected = {tab['id']: tab['title'] for tab in tabs}
    if {s['properties']['sheetId']: s['properties']['title'] for s in result} != expected:
        raise ValueError('Backup tabs changed. Preview archiving again.')
    normalized = []
    for sheet in result:
        if any(sheet.get(key) for key in ('charts', 'protectedRanges', 'bandedRanges', 'rowGroups', 'columnGroups', 'slicers', 'tables', 'developerMetadata')):
            raise ValueError('A backup tab has custom objects or protections; retain it and archive it manually.')
        value = {'properties': {key: val for key, val in sheet['properties'].items() if key in ('sheetId', 'title', 'gridProperties', 'hidden', 'tabColorStyle')},
                 'merges': sheet.get('merges', []), 'conditionalFormats': sheet.get('conditionalFormats', []), 'basicFilter': sheet.get('basicFilter'), 'data': []}
        for grid in sheet.get('data', []):
            part = {key: grid[key] for key in ('startRow', 'startColumn') if key in grid}
            part['rowData'] = [{'values': [{key: val for key, val in cell.items() if key in CELL_FIELDS} for cell in row.get('values', [])]} for row in grid.get('rowData', [])]
            for dimension in ('rowMetadata', 'columnMetadata'):
                part[dimension] = [{k: v for k, v in entry.items() if k in ('pixelSize', 'hiddenByUser')} for entry in grid.get(dimension, [])]
            value['data'].append(part)
        normalized.append(value)
    return sorted(normalized, key=lambda sheet: sheet['properties']['sheetId'])


@coordinated('Archive cloud backups')
def archive(book, folder, expected):
    current = plan(book)
    if current['fingerprint'] != expected:
        raise ValueError('The archive preview changed. Review a fresh preview.')
    if not current['tabs']:
        return {'archived_tabs': 0, 'archive': None}
    sheets = read_tabs(book, current['tabs'])
    value = {'format': 'tv-tracker-cloud-history', 'version': 1, 'workbook': book.id,
             'created': datetime.now(timezone.utc).isoformat(), 'sheets': sheets, 'digest': fingerprint(sheets)}
    raw = json.dumps(value, separators=(',', ':')).encode()
    if len(raw) > LIMIT:
        raise ValueError('Cloud archive exceeds 64 MB. No tabs were removed; export them manually.')
    destination = folder / ('cloud-history-' + uuid.uuid4().hex + '.tvcloud')
    encoded = protect(gzip.compress(raw))
    write_verified_backup(destination, encoded)
    if decode(destination.read_bytes()) != value:
        raise ValueError('Cloud archive verification failed. No tabs were removed.')
    if read_tabs(book, current['tabs']) != sheets:
        raise ValueError('Cloud data changed after archiving. No tabs were removed; retry from a fresh preview.')
    try:
        book.batch_update({'requests': [{'deleteSheet': {'sheetId': tab['id']}} for tab in current['tabs']]})
    except Exception:
        remaining = {s.id for s in book.worksheets()}
        if any(tab['id'] in remaining for tab in current['tabs']):
            raise ValueError('Archive is safe locally, but cloud removal was not confirmed. Review the workbook before retrying.') from None
    remaining = {s.id for s in book.worksheets()}
    if any(tab['id'] in remaining for tab in current['tabs']):
        raise ValueError('Cloud removal could not be verified; the recovery archive is retained.')
    return {'archived_tabs': len(sheets), 'archive': destination.name, 'reclaimed_cells': current['reclaimable_cells']}


def decode(raw):
    from io import BytesIO
    with gzip.GzipFile(fileobj=BytesIO(unprotect(raw))) as stream:
        expanded = stream.read(LIMIT + 1)
    if len(expanded) > LIMIT:
        raise ValueError('Cloud recovery archive is too large.')
    value = json.loads(expanded)
    if value.get('format') != 'tv-tracker-cloud-history' or value.get('version') != 1 or value.get('digest') != fingerprint(value.get('sheets')):
        raise ValueError('Cloud recovery archive is invalid.')
    if not value['sheets'] or any(not NAME.fullmatch(s['properties']['title']) for s in value['sheets']):
        raise ValueError('Only generated backup tabs may be restored.')
    return value


@coordinated('Restore cloud backups')
def restore(book, raw):
    value = decode(raw)
    if value['workbook'] != book.id:
        raise ValueError('This archive belongs to a different workbook.')
    existing = book.worksheets()
    if any(s.id == data['properties']['sheetId'] or s.title == data['properties']['title'] for s in existing for data in value['sheets']):
        raise ValueError('A tab with this identity already exists. No cloud data was replaced.')
    requests = []
    for sheet in value['sheets']:
        props = deepcopy(sheet['properties'])
        identity = props['sheetId']
        requests.append({'addSheet': {'properties': props}})
        for grid in sheet['data']:
            if grid['rowData']:
                requests.append({'updateCells': {'start': {'sheetId': identity, 'rowIndex': grid.get('startRow', 0), 'columnIndex': grid.get('startColumn', 0)},
                                                 'rows': grid['rowData'], 'fields': ','.join(CELL_FIELDS)}})
            for key, axis, start in (('rowMetadata', 'ROWS', grid.get('startRow', 0)), ('columnMetadata', 'COLUMNS', grid.get('startColumn', 0))):
                # Consecutive equal dimensions share a request to bound payload size.
                entries = grid.get(key, [])
                first = 0
                while first < len(entries):
                    last = first + 1
                    while last < len(entries) and entries[last] == entries[first]:
                        last += 1
                    if entries[first]:
                        requests.append({'updateDimensionProperties': {'range': {'sheetId': identity, 'dimension': axis, 'startIndex': start + first, 'endIndex': start + last}, 'properties': entries[first], 'fields': ','.join(entries[first])}})
                    first = last
        requests.extend({'mergeCells': {'range': region, 'mergeType': 'MERGE_ALL'}} for region in sheet['merges'])
        requests.extend({'addConditionalFormatRule': {'index': i, 'rule': rule}} for i, rule in enumerate(sheet['conditionalFormats']))
        if sheet['basicFilter']:
            requests.append({'setBasicFilter': {'filter': sheet['basicFilter']}})
    tabs = [{'id': s['properties']['sheetId'], 'title': s['properties']['title']} for s in value['sheets']]
    try:
        book.batch_update({'requests': requests})
    except Exception:
        if read_tabs(book, tabs) != value['sheets']:
            raise ValueError('Cloud restore was not confirmed. Keep the archive and review the workbook.') from None
    if read_tabs(book, tabs) != value['sheets']:
        raise ValueError('Cloud restore readback differs. Keep the archive for recovery.')
    return {'restored_tabs': len(tabs)}
