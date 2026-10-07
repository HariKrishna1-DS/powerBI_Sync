"""Durable report sources and validated multi-workbook imports, separate from queues."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
from pathlib import Path
import uuid
import sqlite3
from zipfile import ZipFile, BadZipFile

from report_metrics import capacity_report

MAX_ROWS = 100_000
MAX_FILES = 20
MAX_EXPANDED = 128 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


class ImportConflictError(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(f'{len(conflicts)} conflicting duplicate orders need review. Choose the source row to retain for each order, then validate again.')


def comparable_value(column, value):
    from monthly_production import local_datetime
    raw = ' '.join(str(value or '').split())
    if column in ('In-Time', 'Out Time', 'SLA Expiration', 'Date'):
        parsed = local_datetime(raw)
        if parsed is not None:
            return parsed.isoformat()
    return raw.casefold()


def merge_rows(prior, current):
    """Merge complementary fields only when every overlapping value agrees."""
    ignored = {'No', 'Free Site'}  # Generated fields are recalculated after selection.
    for column in (prior.keys() & current.keys()) - ignored:
        if prior[column] and current[column] and comparable_value(column, prior[column]) != comparable_value(column, current[column]):
            return None
    return {column: prior.get(column) or current.get(column, '') for column in dict.fromkeys([*prior, *current])}


def resolve_import_rows(groups, choices):
    resolved, conflicts, reviewed = [], [], 0
    for identity, candidates in groups.items():
        merged = candidates[0]['row']
        for candidate in candidates[1:]:
            merged = merge_rows(merged, candidate['row'])
            if merged is None:
                break
        if merged is not None:
            resolved.append((candidates[0]['file_index'], merged))
            continue
        choice = choices.get(identity)
        selected = next((candidate for candidate in candidates if candidate['token'] == choice), None)
        if selected is not None:
            resolved.append((selected['file_index'], selected['row']))
            reviewed += 1
            continue
        columns = list(dict.fromkeys(column for candidate in candidates for column in candidate['row'] if column not in ('No', 'Free Site')))
        different = [column for column in columns if len({comparable_value(column, candidate['row'].get(column, '')) for candidate in candidates}) > 1]
        conflicts.append({'identity': identity, 'order': candidates[0]['row']['Order Number'], 'columns': different,
                          'options': [{key: candidate[key] for key in ('token', 'source', 'row')} for candidate in candidates]})
    if conflicts:
        raise ImportConflictError(conflicts)
    return resolved, reviewed


def read_workbooks(uploads, choices=None):
    from openpyxl import load_workbook
    from monthly_production import local_datetime
    from tracker_sync import canonical_headers, HEADERS, text
    if not uploads or len(uploads) > MAX_FILES:
        raise ValueError(f'Select between 1 and {MAX_FILES} Excel workbooks.')
    choices = choices or {}
    if not isinstance(choices, dict) or len(choices) > MAX_ROWS or any(not isinstance(k, str) or not isinstance(v, str) for k, v in choices.items()):
        raise ValueError('Use the reviewed source-row selections from import validation.')
    # Bind choices to the entire upload, including its order and filenames.
    digest = hashlib.sha256()
    for filename, raw in uploads:
        digest.update(filename.encode()); digest.update(hashlib.sha256(raw).digest())
    upload_digest = digest.hexdigest()
    by_order, files, skipped, examined = {}, [], [], 0
    aliases = {'in time': 'In-Time', 'in-time': 'In-Time', 'arrival time': 'In-Time',
               'out time': 'Out Time', 'sla expiration*': 'SLA Expiration'}
    for filename, raw in uploads:
        filename = Path(filename.replace('\\', '/')).name
        if not filename.lower().endswith('.xlsx'):
            raise ValueError(f'{filename}: use an .xlsx workbook.')
        try:
            with ZipFile(BytesIO(raw)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED:
                    raise ValueError(f'{filename}: expanded workbook exceeds 128 MB.')
            workbook = load_workbook(BytesIO(raw), read_only=True, data_only=False, keep_links=False)
        except (BadZipFile, OSError, KeyError) as exc:
            raise ValueError(f'{filename}: invalid Excel workbook.') from exc
        file_index = len(files)
        try:
            for sheet in workbook:
                iterator = iter(sheet.iter_rows(values_only=True))
                headers, header_index = None, 0
                for header_index, values in enumerate(iterator, 1):
                    if header_index > 25:
                        break
                    candidate = [aliases.get(str(v or '').strip().casefold(), c) for v, c in zip(values, canonical_headers(values))]
                    if 'Order Number' in candidate:
                        headers = candidate
                        break
                if headers is None:
                    skipped.append(f'{filename} / {sheet.title}: no order table')
                    continue
                while headers and not headers[-1]:
                    headers.pop()
                if len(set(headers)) != len(headers) or not all(headers):
                    raise ValueError(f'{filename} / {sheet.title}: duplicate or blank column headers.')
                required = {'Order Number', 'Product', 'Status'}
                if not required.issubset(headers) or not {'Date', 'In-Time'} & set(headers):
                    raise ValueError(f'{filename} / {sheet.title}: require Order Number, Product, Status and Date or In-Time.')
                for index, cells in enumerate(iterator, header_index + 1):
                    if not any(value is not None and str(value).strip() for value in cells):
                        continue
                    examined += 1
                    if examined > MAX_ROWS:
                        raise ValueError(f'Import exceeds {MAX_ROWS:,} rows; split the workbooks.')
                    row = {h: text(value) for h, value in zip(headers, cells)}
                    if any(str(value or '').startswith('=') for value in cells):
                        raise ValueError(f'{filename} / {sheet.title}, row {index}: formulas require a values-only Excel copy.')
                    if any(not row.get(name, '').strip() for name in required):
                        raise ValueError(f'{filename} / {sheet.title}, row {index}: missing order number, product or status.')
                    arrived = local_datetime(row.get('In-Time')) or local_datetime(row.get('Date'))
                    if arrived is None:
                        raise ValueError(f'{filename} / {sheet.title}, row {index}: invalid arrival date. Use an Excel date or MM/DD/YYYY.')
                    row['Date'] = arrived.strftime('%m/%d/%Y')
                    row.setdefault('In-Time', '')
                    from report_metrics import status_bucket
                    bucket = status_bucket(row)
                    canonical = {'Completed': 'Completed and Delivered', 'Cancelled': 'Cancelled',
                                 'Clarification': 'Awaiting for Clarification', 'Vendor Pending': 'Assign to ABS'}
                    row['Status'] = canonical.get(bucket, row['Status'])
                    from production_timing import sla_result
                    row['Free Site'], _ = sla_result(row)
                    identity = row['Order Number'].strip().casefold()
                    source = f'{filename} / {sheet.title}, row {index}'
                    token = hashlib.sha256(f'{upload_digest}|{file_index}|{source}'.encode()).hexdigest()
                    by_order.setdefault(identity, []).append({'row': row, 'file_index': file_index, 'source': source, 'token': token})
        finally:
            workbook.close()
        files.append({'name': filename, 'accepted': 0})
    if not by_order:
        raise ValueError('No production orders found. Import order-level workbooks, not summary reports.')
    selected, reviewed = resolve_import_rows(by_order, choices)
    rows = []
    for file_index, row in selected:
        row['Free Site'], _ = sla_result(row)
        rows.append(row)
        files[file_index]['accepted'] += 1
    columns = list(dict.fromkeys(HEADERS + [c for row in rows for c in row if c != 'No']))
    for index, row in enumerate(rows, 1):
        row['No'] = index
    return {'rows': rows, 'columns': columns, 'files': files, 'skipped': skipped,
            'duplicates_removed': examined - len(rows), 'conflicts_resolved': reviewed}


def dataset_snapshot(dataset, identity, created, revision):
    from tracker_sync import FULL, REMAINING, sheet_reports
    from production_rules import full_title
    rows, columns = dataset['rows'], dataset['columns']
    full = [r for r in rows if full_title(r)]
    rest = [r for r in rows if not full_title(r)]
    sheets = {name: {'rows': values, 'columns': columns} for name, values in (
        ('Overview', rows), ('All Products', rows), ('Full Title', full), ('Remaining Products', rest))}
    return {'sheets': sheets, 'reports': sheet_reports({FULL: full, REMAINING: rest}),
        'source': 'Imported Excel', 'source_mode': 'import', 'import_id': identity,
        'offline': False, 'updated_at': created, 'revision': revision, 'files': dataset['files']}


def validate_targets(date, capacity, extended):
    if not isinstance(date, str):
        raise ValueError('Use a valid capacity date.')
    if date != 'default':
        if datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%d') != date:
            raise ValueError('Use a valid YYYY-MM-DD capacity date.')
    for value in (capacity, extended):
        if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000):
            raise ValueError('Capacity must be a whole number between 0 and 1,000,000, or blank.')
    if capacity is not None and extended is not None and extended < capacity:
        raise ValueError('Extended capacity must be at least the normal capacity.')


class ReportWorkspace:
    def __init__(self, store):
        self.store = store
        self.initialize()
        with store.connect() as db:
            db.execute("UPDATE report_preferences SET value_json=json_set(value_json,'$.publish_status','failed','$.publish_error','Publishing was interrupted. Retry publishing the saved report source.') WHERE json_extract(value_json,'$.publish_status')='publishing'")

    def initialize(self):
        with self.store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS report_imports (id TEXT PRIMARY KEY, created TEXT NOT NULL, digest TEXT NOT NULL, dataset_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS report_preferences (id INTEGER PRIMARY KEY CHECK(id=1), value_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS capacity_targets (date TEXT PRIMARY KEY, capacity INTEGER, extended INTEGER)')
            db.execute('INSERT OR IGNORE INTO report_preferences VALUES(1,?)', (json.dumps({
                'source': 'tracker', 'import_id': None, 'revision': 0, 'publish_status': 'idle',
                'default_capacity': 700, 'default_extended': 750}),))

    def preferences(self):
        try:
            with self.store.connect() as db:
                record = db.execute('SELECT value_json FROM report_preferences WHERE id=1').fetchone()
        except sqlite3.OperationalError as exc:
            if 'no such table' not in str(exc):
                raise
            record = None
        if record is None:  # Older workspace restored while the service is running.
            self.initialize()
            return self.preferences()
        return json.loads(record[0])

    def update(self, **changes):
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            value = json.loads(db.execute('SELECT value_json FROM report_preferences WHERE id=1').fetchone()[0])
            value.update(changes)
            value['revision'] += 1
            db.execute('UPDATE report_preferences SET value_json=? WHERE id=1', (json.dumps(value),))
        return value

    def save_import(self, uploads, choices=None):
        dataset = read_workbooks(uploads, choices)
        digest = hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
        identity = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('INSERT INTO report_imports VALUES(?,?,?,?)', (identity, now(), digest, json.dumps(dataset)))
        return dict(id=identity, digest=digest, count=len(dataset['rows']), **{k: dataset[k] for k in ('files', 'skipped', 'duplicates_removed', 'conflicts_resolved')})

    def imports(self):
        with self.store.connect() as db:
            return [{'id': identity, 'created': created, 'count': count, 'files': json.loads(files)} for identity, created, count, files in
                    db.execute("SELECT id,created,json_array_length(dataset_json,'$.rows'),json_extract(dataset_json,'$.files') FROM report_imports ORDER BY created DESC")]

    def imported_snapshot(self, identity=None):
        identity = identity or self.preferences()['import_id']
        with self.store.connect() as db:
            record = db.execute('SELECT created,dataset_json,digest FROM report_imports WHERE id=?', (identity,)).fetchone()
        if record is None:
            raise ValueError('Import production Excel files before choosing Import Excel report.')
        created, raw, digest = record
        dataset = json.loads(raw)
        return dataset_snapshot(dataset, identity, created, f'import:{digest}')

    def capacity(self, snapshot):
        prefs = self.preferences()
        with self.store.connect() as db:
            targets = {date: {'capacity': capacity, 'extended': extended} for date, capacity, extended in db.execute('SELECT date,capacity,extended FROM capacity_targets')}
        return capacity_report(snapshot['reports']['daily'], targets, prefs['default_capacity'], prefs['default_extended'])

    def set_targets(self, date, capacity, extended):
        validate_targets(date,capacity,extended)
        if date == 'default':
            self.update(default_capacity=capacity, default_extended=extended)
        else:
            with self.store.connect() as db:
                db.execute('INSERT INTO capacity_targets VALUES(?,?,?) ON CONFLICT(date) DO UPDATE SET capacity=excluded.capacity,extended=excluded.extended', (date, capacity, extended))
            self.update()
