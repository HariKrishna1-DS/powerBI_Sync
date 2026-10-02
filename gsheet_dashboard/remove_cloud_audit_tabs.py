"""Archive and remove cloud preview/audit tabs while preserving local history."""
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import re

from datatrace_sync import target_worksheet
from preview_store import PreviewStore
from tracker_sync import BASE, records, text, read_trackers, TRACKERS

REMOVE = {'Preview History', 'Default conflicts', 'Changes', 'Ambiguous - Needs review'}


def remove_cloud_audit_tabs(book=None, store=None):
    book = book or target_worksheet()[0]
    store = store or PreviewStore(BASE / 'previews')
    sheets = {sheet.title: sheet for sheet in book.worksheets()}
    names = [name for name in sheets if name in REMOVE or re.fullmatch(r'preview[1-9]\d*', name)]
    if not names:
        return {'deleted': [], 'backup': None}
    for title in (*TRACKERS, 'All Products', 'Sheet1', 'Status Report'):
        if title not in sheets:
            raise RuntimeError(f'Required tracker or history tab is missing: {title}')
    local_ids = {preview['id'] for preview in store.list()}
    cloud_ids = {int(name[7:]) for name in names if name.startswith('preview')}
    missing = cloud_ids - local_ids
    if missing:
        raise RuntimeError(f'Local preview copies are missing for: {sorted(missing)}')
    meta = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats)'})
    properties = {item['properties']['title']: item for item in meta['sheets']}
    snapshots = {}
    for name in names:
        values = sheets[name].get_all_values()
        if name.startswith('preview'):
            local = store.get(int(name[7:]))
            if not values or values[0] != local['columns'] or len(values) - 1 != len(local['rows']):
                raise RuntimeError(f'Local and cloud preview sizes/headers differ: {name}')
            if [text(row.get('Order Number')) for row in records(values)] != [text(row.get('Order Number')) for row in local['rows']]:
                raise RuntimeError(f'Local and cloud preview order identities differ: {name}')
        snapshots[name] = {'values': values, 'metadata': properties[name]}
    archive = BASE / 'previews' / f'removed-cloud-tabs-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json.gz'
    archive.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(archive, 'wt', encoding='utf-8') as out:
        json.dump({'spreadsheet_id': book.id, 'tabs': snapshots}, out, ensure_ascii=False)
    with gzip.open(archive, 'rt', encoding='utf-8') as saved:
        content = json.load(saved)
    if set(content['tabs']) != set(names) or any(content['tabs'][name]['values'] != snapshots[name]['values'] for name in names):
        raise RuntimeError('The local cloud tab backup did not verify. No tabs were deleted.')
    # Move every existing report receipt into SQLite before deleting the ledger.
    if 'Preview History' in snapshots:
        history = records(snapshots['Preview History']['values'])
        changes = defaultdict(list)
        ambiguous = defaultdict(list)
        for row in records(snapshots.get('Changes', {}).get('values', [])):
            changes[row.get('Preview')].append(row)
        for row in records(snapshots.get('Ambiguous - Needs review', {}).get('values', [])):
            ambiguous[row.get('Preview')].append(row)
        for receipt in history:
            name = receipt.get('Preview', '')
            match = re.fullmatch(r'preview([1-9]\d*)', name)
            if not match and name != 'Default trackers':
                continue
            number = int(match[1]) if match else 0
            report = json.loads(receipt['Report'])
            report['preview_name'] = name
            report['timestamp'] = receipt.get('Timestamp', '')
            report['changes'] = changes[name]
            report['not_in_latest'] = [row['Order Number'] for row in changes[name]
                                       if row.get('Action') == 'Not in latest preview']
            report['ambiguous'] = ambiguous[name]
            digest = receipt['SHA256']
            store.stage_sync_report(number, digest, report)
            store.commit_sync_report(number, digest)
    if not store.latest_sync_report():
        raise RuntimeError('No local sync report was preserved. No tabs were deleted.')
    ids_before = {title: sheet.id for title, sheet in sheets.items()}
    ids_after = {sheet.title: sheet.id for sheet in book.worksheets()}
    if ids_before != ids_after:
        raise RuntimeError('The spreadsheet tabs changed during backup. No tabs were deleted.')
    book.batch_update({'requests': [{'deleteSheet': {'sheetId': sheets[name].id}} for name in names]})
    remaining = {sheet.title for sheet in book.worksheets()}
    if any(name in remaining for name in names):
        raise RuntimeError('Some requested tabs still exist after the delete request.')
    read_trackers(book)
    return {'deleted': names, 'backup': str(archive),
            'backup_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}


if __name__ == '__main__':
    print(json.dumps(remove_cloud_audit_tabs(), indent=2))
