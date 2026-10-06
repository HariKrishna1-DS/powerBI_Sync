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


def read_workbooks(uploads):
    from openpyxl import load_workbook
    from monthly_production import local_datetime
    from tracker_sync import canonical_headers, HEADERS, text
    if not uploads or len(uploads) > MAX_FILES:
        raise ValueError(f'Select between 1 and {MAX_FILES} Excel workbooks.')
    by_order, files, skipped, duplicates, examined = {}, [], [], 0, 0
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
        accepted = 0
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
                    comparable = {k: v for k, v in row.items() if k != 'No' and v != ''}
                    if identity in by_order:
                        prior = {k: v for k, v in by_order[identity].items() if k != 'No' and v != ''}
                        if prior != comparable:
                            raise ValueError(f'{filename} / {sheet.title}, row {index}: conflicting duplicate order across imported sheets. Resolve it before importing.')
                        duplicates += 1
                        continue
                    by_order[identity] = row
                    accepted += 1
        finally:
            workbook.close()
        files.append({'name': filename, 'accepted': accepted})
    if not by_order:
        raise ValueError('No production orders found. Import order-level workbooks, not summary reports.')
    rows = list(by_order.values())
    columns = list(dict.fromkeys(HEADERS + [c for row in rows for c in row if c != 'No']))
    for index, row in enumerate(rows, 1):
        row['No'] = index
    return {'rows': rows, 'columns': columns, 'files': files, 'skipped': skipped, 'duplicates_removed': duplicates}


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

    def save_import(self, uploads):
        dataset = read_workbooks(uploads)
        digest = hashlib.sha256(json.dumps(dataset, sort_keys=True).encode()).hexdigest()
        identity = uuid.uuid4().hex
        with self.store.connect() as db:
            db.execute('INSERT INTO report_imports VALUES(?,?,?,?)', (identity, now(), digest, json.dumps(dataset)))
        return dict(id=identity, digest=digest, count=len(dataset['rows']), **{k: dataset[k] for k in ('files', 'skipped', 'duplicates_removed')})

    def imports(self):
        with self.store.connect() as db:
            return [{'id': identity, 'created': created, 'count': count, 'files': json.loads(files)} for identity, created, count, files in
                    db.execute("SELECT id,created,json_array_length(dataset_json,'$.rows'),json_extract(dataset_json,'$.files') FROM report_imports ORDER BY created DESC")]

    def imported_snapshot(self, identity=None):
        from tracker_sync import FULL, REMAINING, sheet_reports
        identity = identity or self.preferences()['import_id']
        with self.store.connect() as db:
            record = db.execute('SELECT created,dataset_json,digest FROM report_imports WHERE id=?', (identity,)).fetchone()
        if record is None:
            raise ValueError('Import production Excel files before choosing Import Excel report.')
        created, raw, digest = record
        dataset = json.loads(raw)
        rows, columns = dataset['rows'], dataset['columns']
        full = [r for r in rows if ' '.join(r['Product'].casefold().split()) in ('full title', 'full search')]
        rest = [r for r in rows if ' '.join(r['Product'].casefold().split()) not in ('full title', 'full search')]
        sheets = {name: {'rows': values, 'columns': columns} for name, values in (
            ('Overview', rows), ('All Products', rows), ('Full Title', full), ('Remaining Products', rest))}
        return {'sheets': sheets, 'reports': sheet_reports({FULL: full, REMAINING: rest}),
                'source': 'Imported Excel', 'source_mode': 'import', 'import_id': identity,
                'offline': False, 'updated_at': created, 'revision': f'import:{digest}', 'files': dataset['files']}

    def capacity(self, snapshot):
        prefs = self.preferences()
        with self.store.connect() as db:
            targets = {date: {'capacity': capacity, 'extended': extended} for date, capacity, extended in db.execute('SELECT date,capacity,extended FROM capacity_targets')}
        return capacity_report(snapshot['reports']['daily'], targets, prefs['default_capacity'], prefs['default_extended'])

    def set_targets(self, date, capacity, extended):
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
        if date == 'default':
            self.update(default_capacity=capacity, default_extended=extended)
        else:
            with self.store.connect() as db:
                db.execute('INSERT INTO capacity_targets VALUES(?,?,?) ON CONFLICT(date) DO UPDATE SET capacity=excluded.capacity,extended=excluded.extended', (date, capacity, extended))
            self.update()
