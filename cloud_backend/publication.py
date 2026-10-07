"""Deterministic Sheets projection with a permanent legacy-writer fence.

Supabase job ownership must cover the entire call. Sheets is a derived report;
edits outside the central publisher stop publication instead of being erased.
"""
from copy import deepcopy
import hashlib
import json
import math
import re
import uuid

from shared_backend import CloudError
from sheets_repository import Batch
from sheets_writer import SHARED_TITLE, SharedWriterGuard

PROTOCOL = 'tv-tracker-supabase-v1'
RECEIPT = '__TvTracker_CloudPublication'
GRID_LIMIT = 10_000_000


def projection(orders, stamp, context=None):
    from tracker_sync import HEADERS, FULL, REMAINING, sheet_reports
    from report_metrics import capacity_report
    from report_publishing import view_matrices
    from production_rules import full_title
    rows = [deepcopy(item['data']) for item in sorted(orders, key=lambda r: r['order_key'])]
    from monthly_production import month_key, local_datetime, tab_name
    for row in rows:
        if row.get('Reporting Month'):
            row['_month'] = month_key(row['Reporting Month'])
    columns = HEADERS + sorted({key for row in rows for key in row if not key.startswith('_')} - set(HEADERS))
    full = [row for row in rows if full_title(row)]
    rest = [row for row in rows if not full_title(row)]
    snapshot = {'sheets': {name: {'columns': columns, 'rows': selected} for name, selected in (
        ('All Products', rows), ('Overview', rows), ('Full Title', full), ('Remaining Products', rest))},
        'reports': sheet_reports({FULL: full, REMAINING: rest}), 'updated_at': stamp, 'source': 'Shared workspace'}
    from report_metrics import enrich_reports
    enrich_reports(snapshot['reports'])
    tracker_snapshot = snapshot
    context = context or {}
    prefs = context.get('preferences', {'source':'tracker','import_id':None,'default_capacity':700,'default_extended':750})
    if prefs['source'] == 'import':
        dataset = context.get('dataset')
        if not isinstance(dataset, dict) or not dataset.get('rows') or not dataset.get('columns'):
            raise CloudError('The selected shared report import is unavailable. Reports were retained.')
        from report_workspace import dataset_snapshot
        snapshot = dataset_snapshot(dataset, prefs['import_id'], stamp, 'shared-import')
        enrich_reports(snapshot['reports'])
    capacity = capacity_report(snapshot['reports']['daily'], context.get('targets'),
        prefs.get('default_capacity'), prefs.get('default_extended'), year=stamp[:4])
    snapshot.update(source_mode=prefs['source'], report_preferences=deepcopy(prefs), capacity=capacity)
    tables = view_matrices(snapshot, capacity)
    for title, selected in ((FULL, full), (REMAINING, rest)):
        tables[title] = [columns] + [[row.get(c, '') for c in columns] for row in selected]
    periods = set(context.get('periods', []))
    grouped = {}
    for row in rows:
        arrival = local_datetime(row.get('In-Time') or row.get('Date'))
        period = row.get('Reporting Month') or (arrival.strftime('%Y-%m') if arrival else None)
        if period:
            month_key(period)
            periods.add(period)
            grouped.setdefault((FULL if full_title(row) else REMAINING,period), []).append(row)
    from monthly_production import arrival_sort
    for period in sorted(periods):
        for base in (FULL, REMAINING):
            selected = arrival_sort(grouped.get((base,period), []))
            tables[tab_name(base,period)] = [columns] + [[row.get(c,'') for c in columns] for row in selected]
    snapshot['canonical_orders'] = len(tracker_snapshot['sheets']['All Products']['rows'])
    return tables, snapshot


def canonical(tables):
    def cell(value):
        if value is None:
            return ''
        if isinstance(value, bool):
            return 'TRUE' if value else 'FALSE'
        if isinstance(value, (int, float)):
            if not math.isfinite(value):
                raise ValueError('Report contains a non-finite number.')
            return format(value, '.14g')
        if not isinstance(value, str):
            raise ValueError('Report contains an unsupported cell value.')
        return value
    result = {}
    for title, matrix in tables.items():
        rows = [[cell(value) for value in row] for row in matrix]
        for row in rows:
            while row and row[-1] == '':
                row.pop()
        while rows and not rows[-1]:
            rows.pop()
        result[title] = rows
    return result


def digest(tables):
    return hashlib.sha256(json.dumps(canonical(tables), ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


class SheetsPublisher:
    def __init__(self, book, workspace, spreadsheet):
        uuid.UUID(workspace)
        if getattr(book, 'id', None) != spreadsheet:
            raise CloudError('The publishing workbook does not match the workspace destination.')
        self.book, self.workspace, self.spreadsheet = book, workspace, spreadsheet

    def _read(self, titles):
        from sheet_reads import read_values
        from types import SimpleNamespace
        return dict(zip(titles, read_values(self.book, [SimpleNamespace(title=title) for title in titles], render='UNFORMATTED_VALUE')))

    def _receipt(self):
        try:
            rows = self._read([RECEIPT])[RECEIPT]
            receipt = json.loads(rows[1][0])
            if (receipt['workspace'] != self.workspace or receipt['spreadsheet'] != self.spreadsheet
                    or type(receipt['revision']) is not int or receipt['revision'] < 0
                    or not isinstance(receipt['tabs'], list) or len(receipt['tabs']) > 200
                    or any(not isinstance(title, str) or not title or title.startswith('__') for title in receipt['tabs'])
                    or len(set(receipt['tabs'])) != len(receipt['tabs'])):
                raise ValueError('Receipt mismatch')
            return receipt
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise CloudError('The central publication receipt is invalid. Review the workbook before retrying.') from exc

    def _fence(self):
        rows = self._read([SHARED_TITLE])[SHARED_TITLE]
        if len(rows) < 2 or rows[1][:3] != [PROTOCOL, self.workspace, self.spreadsheet]:
            raise CloudError('This workbook is not bound to this shared workspace. No reports were changed.')

    def _stage(self, revision, tables, content_digest):
        """Bound transfer size; readers never see partially uploaded report data."""
        from datatrace_sync import sheet_cell
        batch = Batch(self.book)
        stages = {}
        for index, (title, rows) in enumerate(sorted(tables.items())):
            name = f'__TvTracker_Stage_{self.workspace[:8]}_{revision}_{content_digest[:8]}_{index}'
            sheet = batch.sheet(name)
            batch.capacity(sheet, max(2,len(rows)), len(rows[0]))
            batch.requests.append({'updateSheetProperties': {'properties': {'sheetId':sheet.id,'hidden':True},'fields':'hidden'}})
            stages[title] = (name, sheet.id)
        self.book.batch_update({'requests':batch.requests})
        pending, pending_size = [], 16
        def flush():
            nonlocal pending, pending_size
            if pending:
                self.book.batch_update({'requests':pending})
                pending, pending_size = [], 16
        for title, rows in sorted(tables.items()):
            identity = stages[title][1]
            offset, encoded, size = 0, [], 0
            def write():
                nonlocal pending_size
                request = {'updateCells':{'start':{'sheetId':identity,'rowIndex':offset,'columnIndex':0},
                    'rows':encoded,'fields':'userEnteredValue'}}
                request_size = len(json.dumps(request).encode()) + 2
                if request_size > 1_600_000:
                    raise CloudError('A staged report transfer exceeds the bounded upload size.')
                if pending and pending_size + request_size > 1_600_000:
                    flush()
                pending.append(request)
                pending_size += request_size
            for row in rows:
                if any(isinstance(cell,str) and len(cell)>50000 for cell in row):
                    raise CloudError('A report cell exceeds Google Sheets’ 50,000-character limit.')
                values = [sheet_cell(value) if value not in ('',None) else {} for value in row]
                while values and not values[-1]:
                    values.pop()
                record = {'values':values}
                # requests serializes JSON with escaped Unicode by default.
                length = len(json.dumps(record).encode()) + 2
                if length > 1_400_000:
                    raise CloudError('A report row exceeds the bounded upload size.')
                if encoded and size+length>1_400_000:
                    write()
                    offset += len(encoded)
                    encoded = []
                    size = 0
                encoded.append(record); size+=length
            if encoded:
                write()
        flush()
        copied = self._read([name for name,_ in stages.values()])
        if digest({title:copied[name] for title,(name,_) in stages.items()}) != digest(tables):
            raise CloudError('Staged reports could not be verified. Visible reports were retained.', 'retry')
        return stages

    def _prepare_storage(self, tables):
        """Only disposable staging for this bound workspace can be reclaimed."""
        prefix = '__TvTracker_Stage_' + self.workspace[:8] + '_'
        pattern = re.compile(re.escape(prefix) + r'\d+_[a-f0-9]{8}_\d+$')
        sheets = self.book.worksheets()
        abandoned = [sheet for sheet in sheets if pattern.fullmatch(sheet.title)]
        if abandoned:
            self.book.batch_update({'requests': [{'deleteSheet': {'sheetId': sheet.id}} for sheet in abandoned]})
            sheets = self.book.worksheets()
            if any(pattern.fullmatch(sheet.title) for sheet in sheets):
                raise CloudError('Temporary report cleanup could not be verified. Visible reports were retained.', 'retry')
        existing = {sheet.title: sheet for sheet in sheets}
        allocated = sum(sheet.row_count * sheet.col_count for sheet in sheets)
        # Staging and destination must fit simultaneously, before any uploads.
        peak = allocated
        for title, rows in tables.items():
            count, columns = max(2, len(rows)), len(rows[0])
            peak += count * columns
            destination_rows = count + (25 if title == 'Capacity Report' else 0)
            if title in existing:
                sheet = existing[title]
                peak += max(sheet.row_count, destination_rows) * max(sheet.col_count, columns) - sheet.row_count * sheet.col_count
            else:
                peak += destination_rows * columns
        if peak > GRID_LIMIT:
            raise CloudError('The workbook lacks space for a verified atomic publication. Archive obsolete report copies or use a reviewed new workbook; current reports were retained.')

    def bind(self, baseline_titles, expected_digest):
        """Explicit migration only; caller must retain the reviewed baseline backup."""
        from sheets_writer import SHARED_ID
        from gspread.exceptions import APIError
        titles = sorted(baseline_titles)
        if any(not isinstance(t, str) or not t or t.startswith('__') for t in titles):
            raise ValueError('Only reviewed report tabs can be bound.')
        try:
            existing = self._read([SHARED_TITLE])[SHARED_TITLE]
        except APIError as exc:
            if exc.code != 400:
                raise
            existing = []
        if len(existing) > 1 and existing[1][:1] == [PROTOCOL]:
            self._fence()
            return self._receipt()
        guard = SharedWriterGuard(self.book, 'supabase-migration')
        with guard.session('Activate shared database'):
            if digest(self._read(titles)) != expected_digest:
                raise CloudError('The workbook changed after migration review. Review it again.', 'conflict')
            batch = Batch(self.book)
            if RECEIPT in batch.sheets:
                raise CloudError('An unexpected cloud receipt already exists. Review migration state.')
            receipt = {'workspace': self.workspace, 'spreadsheet': self.spreadsheet,
                'revision': 0, 'digest': expected_digest, 'tabs': titles}
            target = batch.sheet(RECEIPT)
            batch.capacity(target, 2, 1)
            batch.cells(target, 0, 0, [['Receipt'], [json.dumps(receipt, sort_keys=True)]])
            batch.requests.extend([
                {'updateSheetProperties': {'properties': {'sheetId': target.id, 'hidden': True}, 'fields': 'hidden'}},
                {'updateSheetProperties': {'properties': {'sheetId': SHARED_ID, 'gridProperties': {'columnCount': 3}}, 'fields': 'gridProperties.columnCount'}},
                guard.cells(SHARED_ID, [['Protocol', 'Workspace', 'Spreadsheet'], [PROTOCOL, self.workspace, self.spreadsheet]])])
            try:
                self.book.batch_update({'requests': batch.requests})
            except Exception:
                self._fence()
                if self._receipt() != receipt:
                    raise
            self._fence()
            if self._receipt() != receipt:
                raise CloudError('Migration binding could not be verified.', 'retry')
            return receipt

    def publish(self, revision, tables, capacity=None):
        if type(revision) is not int or revision < 1 or not tables or len(tables) > 200:
            raise ValueError('A bounded report and positive revision are required.')
        if any(not isinstance(title, str) or not title or title.startswith('__') or not rows for title, rows in tables.items()):
            raise ValueError('Report tabs need names and headers.')
        self._fence()
        previous = self._receipt()
        previous_tables = self._read(previous['tabs'])
        # A report-source switch clears obsolete generated monthly views, while
        # preserving canonical/historical tracker tabs and unrelated worksheets.
        from monthly_views import view_identity
        from monthly_production import tab_identity
        from sheet_titles import existing_title
        existing = {sheet.title for sheet in self.book.worksheets()}
        resolved = {}
        for title, values in tables.items():
            actual = existing_title(existing, title) or title
            if actual in resolved and resolved[actual] != values:
                raise CloudError('Two reports target the same worksheet. Publishing was stopped.', 'conflict')
            resolved[actual] = values
        tables = resolved
        for title in previous_tables.keys()-tables.keys():
            if view_identity(title) or tab_identity(title):
                tables[title] = [previous_tables[title][0]] if previous_tables[title] else [['Order Number']]
        updated_titles = set(tables)
        tables = {**{title: rows for title, rows in previous_tables.items() if title not in tables}, **tables}
        current_digest = digest(tables)
        if previous['revision'] > revision or (previous['revision'] == revision and previous['digest'] != current_digest):
            raise CloudError('A different or newer report is already published.', 'conflict')
        # One batched read checks for direct edits and reconciles lost replies.
        if digest(previous_tables) != previous['digest']:
            raise CloudError('Google Sheets reports were edited outside Tv Tracker. Preserve and reconcile those edits before publishing.', 'conflict')
        if previous['revision'] == revision:
            return previous
        existing = {sheet.title for sheet in self.book.worksheets()}
        if any(title not in previous['tabs'] and title in existing for title in updated_titles):
            raise CloudError('A new report would replace an unreviewed tab. Review migration first.', 'conflict')
        self._prepare_storage({title: tables[title] for title in updated_titles})
        try:
            stages = self._stage(revision, {title:tables[title] for title in updated_titles}, current_digest)
        except CloudError:
            raise
        except Exception as error:
            raise CloudError('Report staging was interrupted. Visible reports were retained; the durable job will retry.', 'retry') from error
        # Check direct edits again after potentially lengthy staging uploads.
        if self._receipt()!=previous or digest(self._read(previous['tabs']))!=previous['digest']:
            raise CloudError('Reports changed during staging. Visible reports were retained.', 'conflict')
        metadata = self.book.fetch_sheet_metadata(params={'fields':'sheets(properties(sheetId),conditionalFormats)'})
        formats = {sheet['properties']['sheetId']:sheet.get('conditionalFormats',[]) for sheet in metadata['sheets']}
        batch = Batch(self.book)
        for title, values in tables.items():
            if title not in updated_titles:
                continue
            if title not in previous['tabs'] and title in batch.sheets:
                raise CloudError('A new report would replace an unreviewed tab. Review migration first.', 'conflict')
            sheet = batch.sheet(title)
            batch.capacity(sheet, max(2, len(values)), len(values[0]))
            if title == 'Capacity Report':
                batch.capacity(sheet, max(2, len(values)) + 25, len(values[0]))
            batch.requests.append({'repeatCell': {'range': {'sheetId': sheet.id}, 'cell': {}, 'fields': 'userEnteredValue'}})
            batch.requests.append({'copyPaste':{'source':{'sheetId':stages[title][1],'startRowIndex':0,'endRowIndex':len(values),
                'startColumnIndex':0,'endColumnIndex':len(values[0])},'destination':{'sheetId':sheet.id,'startRowIndex':0,
                'endRowIndex':len(values),'startColumnIndex':0,'endColumnIndex':len(values[0])},'pasteType':'PASTE_VALUES'}})
            batch.requests.append({'updateSheetProperties': {'properties': {'sheetId': sheet.id,
                'gridProperties': {'frozenRowCount': 1}}, 'fields': 'gridProperties.frozenRowCount'}})
            from tracker_formatting import format_requests, MARKER
            from datatrace_sync import sheet_color
            from gspread.utils import rowcol_to_a1
            batch.requests.extend(format_requests(sheet.id, values, formats.get(sheet.id,[])))
            if 'Free Site' in values[0]:
                column = values[0].index('Free Site')
                letter = rowcol_to_a1(1,column+1)[:-1]
                for label,color in (('On Time','#00b050'),('Missing','#ff0000'),('Missed','#ff0000')):
                    batch.requests.append({'addConditionalFormatRule':{'index':0,'rule':{
                        'ranges':[{'sheetId':sheet.id,'startRowIndex':1,'startColumnIndex':column,'endColumnIndex':column+1}],
                        'booleanRule':{'condition':{'type':'CUSTOM_FORMULA','values':[{'userEnteredValue':f'=AND(N("{MARKER}")=0,${letter}2="{label}")'}]},
                            'format':{'backgroundColor':sheet_color(color)}}}}})
        if capacity is not None and 'Capacity Report' in updated_titles:
            from report_publishing import capacity_chart_requests
            batch.requests.extend(capacity_chart_requests(self.book, batch.sheets['Capacity Report'].id, capacity))
        receipt = {'workspace': self.workspace, 'spreadsheet': self.spreadsheet,
            'revision': revision, 'digest': digest(tables), 'tabs': sorted(tables)}
        batch.cells(batch.sheets[RECEIPT], 0, 0, [['Receipt'], [json.dumps(receipt, sort_keys=True)]])
        batch.requests.extend({'deleteSheet':{'sheetId':identity}} for _,identity in stages.values())
        if len(json.dumps(batch.requests).encode()) > 2_000_000:
            raise CloudError('The atomic report exceeds the supported publish size. Archive history before retrying.')
        self._fence()
        try:
            self.book.batch_update({'requests': batch.requests})
        except Exception as error:
            # A single attempt avoids replaying addSheet after an ambiguous write.
            # A later job retry rebuilds from the verified remote receipt.
            if self._receipt() != receipt:
                raise CloudError('Publication could not be confirmed. Its durable job will retry.', 'retry') from error
        if self._receipt() != receipt or digest(self._read(receipt['tabs'])) != receipt['digest']:
            raise CloudError('Published report readback did not match. The job remains pending.', 'retry')
        return receipt
