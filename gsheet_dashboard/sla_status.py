"""Current deadline categories shared by the UI, Sheets and Excel reports."""
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import re

IST = timezone(timedelta(hours=5, minutes=30))
CATEGORIES = ['Future SLA', 'Negative SLA', 'Today SLA']
SUMMARY_COLUMNS = ['Status', *CATEGORIES, 'Grand Total']
DETAIL_COLUMNS = ['Order Number', 'SLA Expiration', 'SLA', 'Online/ Ground',
                  'Client', 'Product', 'St', 'County', 'Municipality',
                  'Task Name', 'Task Status', 'Status', 'Source workbook']
COLORS = ['#81cbb5', '#ed8796', '#e5bf68']


def tracker_status_rows(book):
    """Read only the tracker order-number/status columns for queue labels."""
    from gspread.utils import rowcol_to_a1
    from tracker_sync import canonical_headers
    headers = book.values_get("'All Products'!1:1", params={'valueRenderOption': 'UNFORMATTED_VALUE'}).get('values', [[]])[0]
    headers = canonical_headers(headers)
    ranges = []
    for name in ('Order Number', 'Status'):
        column = rowcol_to_a1(1, headers.index(name)+1)[:-1]
        ranges.append(f"'All Products'!{column}2:{column}")
    values = book.values_batch_get(ranges, params={'valueRenderOption': 'UNFORMATTED_VALUE'})['valueRanges']
    numbers, statuses = (item.get('values', []) for item in values)
    return [{'Order Number': cells[0], 'Status': statuses[index][0] if index < len(statuses) and statuses[index] else ''}
            for index, cells in enumerate(numbers) if cells and str(cells[0]).strip()]


def queue_field(row, name):
    """Portal headers may contain spaces, line breaks, or no spaces."""
    compact = lambda value: re.sub(r'[^a-z0-9]', '', str(value).casefold())
    return next((str(value or '').strip() for column, value in row.items()
                 if compact(column) == compact(name)), '')


def special_product_status(raw):
    """Recognize full names and the portal's displayed, ellipsized product labels."""
    product = re.sub(r'[^a-z0-9]', '', raw.casefold())
    truncated = bool(re.search(r'(?:\.{2,}|\u2026)\s*$', raw))
    for status, names, prefix in (
            ('Attorney Approval', ('attorneyapproval', 'attorneyapproach'), 'attorneyapp'),
            ('Home Builder', ('homebuilder', 'homebuilders'), 'homebuil')):
        if product in names or (truncated and product.startswith(prefix)
                                and any(name.startswith(product) for name in names)):
            return status
    return ''


def eta_commitment_date(comments, today):
    """Use the last date attached to EOD/sooner, never receipt or fee dates."""
    matches = list(re.finditer(
        r'(?<![\w/.-])(?P<date>\d{4}-\d{1,2}-\d{1,2}|\d{1,2}/\d{1,2}(?:/(?:\d{4}|\d{2}))?)'
        r'\s*(?:[,;:-]\s*)?(?:eod|(?:or\s+)?sooner)\b', comments, re.I))
    if not matches:
        return '', None
    match = matches[-1]
    raw = match['date']
    if raw.count('/') == 1:
        raw = f'{raw}/{today.year}'
    for pattern in ('%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d'):
        try:
            return ' '.join(match.group(0).split()), datetime.strptime(raw, pattern).date()
        except ValueError:
            pass
    return ' '.join(match.group(0).split()), None


def queue_rule(row, as_of=None):
    """Return priority, status and evidence shared by extraction and SLA reports."""
    from production_timing import completed, precise_timestamp
    comments = queue_field(row, 'ETA Comments')
    # Apply the new queue classification only to its ETA comment evidence.
    # Other captures keep the established tracker and task-status behavior.
    if not re.search(r'\b(?:abstract(?:ors?)?|eod|sooner|apoloize|apologize|apologise)\b'
                     r'|\bassigned\s+to\s+the\s+abst\b|\bon\s+hold\b', comments, re.I):
        return 9, '', ''
    if precise_timestamp(queue_field(row, 'Out Time')):
        return -1, 'Completed and Delivered', 'Valid Out Time'
    normalized = {name: queue_field(row, name) for name in ('Status', 'Task Status', 'Completed Time')}
    normalized['Status'] = normalized['Status'] or normalized['Task Status']
    if completed(normalized) and precise_timestamp(normalized['Completed Time']):
        return -1, 'Completed and Delivered', 'Completed status with a valid Completed Time'
    compact = lambda value: re.sub(r'[^a-z0-9]', '', value.casefold())
    product, task = compact(queue_field(row, 'Product')), compact(queue_field(row, 'Task Name'))
    task_status = compact(queue_field(row, 'Task Status'))
    if task in ('crsp2', 'searchfix'):
        return 0, 'SearchFix', 'Task Name is CRSP2' if task == 'crsp2' else 'Task Name is SearchFix'
    if product in ('clientreview', 'qualitycontrol', 'quailtycontrol'):
        return 0, 'SearchFix', 'Product is ClientReview / Quality Control'
    if re.search(r'\bon\s+hold\b', comments, re.I):
        return 1, 'Waiting for Effective Date', 'ETA Comments contains ON HOLD'
    special = special_product_status(queue_field(row, 'Product'))
    if special:
        return 2, special, f"Product is {queue_field(row, 'Product')}"
    apology = re.search(r'\b(?:apoloize|apologize|apologise)\b', comments, re.I)
    if apology:
        return 3, 'Need to Assign ABS', f'ETA Comments contains {apology.group(0)}'
    assigned = re.search(r'\bassigned\s+to\s+the\s+(?:abstractor|abst)\b', comments, re.I)
    abstractor = re.search(r'\babstract(?:ors?)?\b', comments, re.I)
    commitment = re.search(r'\b(?:eod|sooner)\b', comments, re.I)
    if assigned or abstractor or commitment:
        evidence = assigned or abstractor or commitment
        reason = f'ETA Comments contains {" ".join(evidence.group(0).split())}'
        if commitment:
            today = local_time(as_of or datetime.now(IST)).date()
            wording, due = eta_commitment_date(comments, today)
            if due:
                reason = f'ETA Comments contains {wording}; ETA date {due.isoformat()}'
                if due == today:
                    return 3, 'Need to Assign ABS', f'{reason} matches today {today.isoformat()} (India time)'
                reason += f' does not match today {today.isoformat()} (India time)'
            elif wording:
                reason += f'; invalid ETA date in {wording}'
        return 4, 'Assign to ABS', reason
    if task == 'typingmodule' and task_status == 'inprogress':
        return 5, 'Typing in Progress', 'Task Name is TypingModule and Task Status is In Progress'
    from tracker_sync import suspended
    if suspended(dict(row, **{'Task Status': queue_field(row, 'Task Status')})):
        return 6, 'Awaiting for Clarification', 'Workflow is suspended'
    last_user = queue_field(row, 'Last User').casefold()
    if (last_user in ('', '(blank)', 'null', 'none', 'n/a', '-')
            and task_status == 'available'):
        return 7, 'Search In Progress', 'Last User is blank and Task Status is Available'
    if task_status == 'tasksuspended':
        return 8, 'Typing in Progress', 'Task Status is Task Suspended; no higher-priority queue rule matches'
    return 9, '', ''


def queue_orders(preview, as_of=None):
    """Count each Order Number once even when the queue contains several tasks."""
    from import_identity import number_key
    orders = {}
    for original in preview['rows'] if preview else []:
        identity = number_key(original)
        if identity and (identity not in orders or queue_rule(original, as_of)[0] < queue_rule(orders[identity], as_of)[0]):
            orders[identity] = original
    return orders


def preview_snapshot(store, settings=None, preview_id=None, production=None, as_of=None):
    """One captured queue, independent of retained production and imported orders."""
    settings = settings or {}
    as_of = as_of or datetime.now(IST)
    previews = store.list()
    if preview_id is not None:
        preview = store.get(preview_id)
    else:
        saved = settings.get('sla_preview_id')
        selected = next((p for p in previews if p['id'] == saved), None) or next(iter(previews), None)
        preview = store.get(selected['id']) if selected else None
    overrides = (settings.get('sla_preview_statuses') or {}).get(str(preview['id']), {}) if preview else {}
    from tracker_sync import key, SOURCE, value, text, mapped_status, deadline
    anchor = local_time(preview['created']) if preview else None
    statuses = {}
    for row in (production or {}).get('sheets', {}).get('Overview', {}).get('rows', []):
        identity = text(row.get('Order Number')).casefold()
        status = text(row.get('Status'))
        if identity and status:
            statuses.setdefault(identity, set()).add(status)
    rows = []
    for original in queue_orders(preview, as_of).values():
        row = dict(original)
        for column in ('Product', 'Task Name', 'Task Status', 'Last User', 'ETA Comments'):
            if queue_field(original, column):
                row[column] = queue_field(original, column)
        for column in SOURCE:
            if not text(row.get(column)):
                row[column] = value(original, column)
        _, automatic, reason = queue_rule(original, as_of)
        if automatic:
            row['Status'] = automatic
        elif not text(row.get('Status')):
            known = statuses.get(text(row.get('Order Number')).casefold(), set())
            row['Status'] = next(iter(known)) if len(known) == 1 else mapped_status(original, new=True)
        expiry = deadline(row.get('SLA Expiration'), anchor)
        if expiry:
            row['SLA Expiration'] = expiry.isoformat(sep=' ')
        if key(row) in overrides:
            row['Status'] = overrides[key(row)]
            reason = 'Manual status edit for this preview'
        row['Status Reason'] = reason or 'Saved preview or matched tracker Status'
        rows.append(row)
    columns = list(dict.fromkeys((preview['columns'] if preview else []) + list(SOURCE) + ['Status', 'Status Reason']))
    return {'mode': 'tracker', 'report_scope': 'preview', 'offline': False,
            'source': 'Saved preview', 'preview_id': preview['id'] if preview else None,
            'preview_name': preview['name'] if preview else None, 'preview_row_count': len(rows),
            'uses_queue_status': any(not text(row.get('Status')) and not queue_rule(row, as_of)[1] for row in preview['rows']) if preview else False,
            'previews': previews, 'updated_at': preview['created'] if preview else None,
            'sheets': {'Overview': {'rows': rows, 'columns': columns}}}


def rename_preview_status(workspace, snapshot, old, new, selected):
    from copy import deepcopy
    from tracker_sync import key
    from status_updates import status_name
    matching = {key(row) for row in snapshot['sheets']['Overview']['rows']
                if (status_name(row.get('Status') or row.get('Task Status')) or '(Blank)') == old}
    if not matching or matching != set(selected):
        raise ValueError('Orders in this preview changed. Refresh SLA Status and try again.')
    from workspace_backup import save_safety_backup
    save_safety_backup(workspace.store, 'before-update')
    with workspace.lock:
        edits = deepcopy(workspace.read().get('sla_preview_statuses') or {})
        edits.setdefault(str(snapshot['preview_id']), {}).update(dict.fromkeys(matching, new))
        workspace.save(sla_preview_statuses=edits)
    return len(matching)


def local_time(value):
    from monthly_production import local_datetime
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        except ValueError:
            parsed = local_datetime(value)
    return (parsed.astimezone(IST).replace(tzinfo=None) if parsed.tzinfo else parsed) if parsed else None


def category(value, as_of, anchor=None):
    raw = str(value if value is not None else '').strip()
    if not raw:
        return ''
    # Queue exports express overdue deadlines as signed elapsed durations.
    relative = re.fullmatch(r'(-)?(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?', raw, re.I)
    if relative and any(relative.groups()[1:]):
        if relative[1]:
            return 'Negative SLA'
        days, hours, minutes = (int(part or 0) for part in relative.groups()[1:])
        due = (anchor or as_of) + timedelta(days=days, hours=hours, minutes=minutes)
    else:
        due = local_time(value)
    if due is None:
        return ''
    return 'Today SLA' if due.date() == as_of.date() else 'Negative SLA' if due.date() < as_of.date() else 'Future SLA'


def build_sla_status(snapshot, as_of=None):
    as_of = as_of or datetime.now(IST)
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time())
    if as_of.tzinfo:
        as_of = as_of.astimezone(IST).replace(tzinfo=None)
    sheets = snapshot.get('sheets', {})
    source = sheets.get('Overview') or sheets.get('All Products') or {'rows': [], 'columns': []}
    anchor = local_time(snapshot.get('updated_at'))
    rows, excluded, counts = [], [], Counter()
    for original in source['rows']:
        if not str(original.get('Order Number') or '').strip():
            continue
        expiry = original.get('SLA Expiration', original.get('SLA Expiration*'))
        result = category(expiry, as_of, anchor)
        row = dict(original, **{'SLA Category': result})
        row['Status'] = str(original.get('Status') or original.get('Task Status') or '(Blank)').strip()
        if not result:
            row['SLA issue'] = 'Missing SLA expiration' if not str(original.get('SLA Expiration') or '').strip() else 'Invalid SLA expiration'
            excluded.append(row)
            continue
        counts[row['Status'], result] += 1
        rows.append(row)
    statuses = sorted({status for status, _ in counts}, key=str.casefold)
    summary = [dict(Status=status, **{key: counts[status, key] for key in CATEGORIES},
                    **{'Grand Total': sum(counts[status, key] for key in CATEGORIES)}) for status in statuses]
    totals = dict(Status='Grand Total', **{key: sum(row[key] for row in summary) for key in CATEGORIES},
                  **{'Grand Total': len(rows)})
    return {'as_of': as_of.date().isoformat(), 'rows': rows, 'excluded_rows': excluded,
            'excluded_count': len(excluded), 'summary': summary, 'totals': totals,
            'columns': list(dict.fromkeys(source.get('columns', []) + ['SLA Category'])),
            'summary_columns': SUMMARY_COLUMNS, **{key: snapshot.get(key) for key in (
                'source', 'mode', 'offline', 'updated_at', 'report_scope', 'preview_id',
                'preview_name', 'preview_row_count', 'previews')}}


def summary_values(report):
    return [SUMMARY_COLUMNS] + [[row[column] for column in SUMMARY_COLUMNS]
        for row in report['summary'] + [report['totals']]]


def sheet_summary_values(report):
    """Reference layout, with empty category counts displayed as blank cells."""
    return [['Count of Order Number', 'Column Labels', '', '', '']] + [
        [value if index in (0, 4) or value else '' for index, value in enumerate(row)]
        for row in summary_values(report)]


def sheet_format_requests(sheet_id, values, existing):
    """Keep the SLA table plain, including when replacing an older colored report."""
    table = {'sheetId': sheet_id, 'endRowIndex': len(values), 'endColumnIndex': 5}
    requests = [{'deleteConditionalFormatRule': {'sheetId': sheet_id, 'index': index}}
                for index in reversed(range(len(existing.get('conditionalFormats', []))))]
    requests.append({'repeatCell': {'range': {'sheetId': sheet_id},
        'cell': {}, 'fields': 'userEnteredFormat'}})
    requests.append({'repeatCell': {'range': table,
        'cell': {'userEnteredFormat': {'horizontalAlignment': 'CENTER',
            'verticalAlignment': 'MIDDLE', 'textFormat': {'fontFamily': 'Calibri', 'fontSize': 11}}},
        'fields': 'userEnteredFormat'}})
    for start, end in ((0, 2), (len(values)-1, len(values))):
        requests.append({'repeatCell': {'range': dict(table, startRowIndex=start, endRowIndex=end),
            'cell': {'userEnteredFormat': {'textFormat': {'bold': True}}},
            'fields': 'userEnteredFormat.textFormat.bold'}})
    requests.append({'repeatCell': {'range': dict(table, startRowIndex=2, startColumnIndex=1),
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER', 'pattern': '#,##0'}}},
        'fields': 'userEnteredFormat.numberFormat'}})
    border = {'style': 'SOLID', 'color': {'red': 0, 'green': 0, 'blue': 0}}
    requests.append({'updateBorders': {'range': dict(table, startRowIndex=1),
        **{side: border for side in ('top', 'bottom', 'left', 'right', 'innerHorizontal', 'innerVertical')}}})
    for start, end, width in ((0, 1, 220), (1, 4, 115), (4, 5, 120)):
        requests.append({'updateDimensionProperties': {
            'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': start, 'endIndex': end},
            'properties': {'pixelSize': width}, 'fields': 'pixelSize'}})
    return requests


def sample_rows(report):
    aliases = {'SLA': 'SLA Category', 'Online/ Ground': 'Online/Ground', 'St': 'State'}
    return [{column: row.get(column, row.get(aliases.get(column, column), ''))
             if column != 'SLA' else row['SLA Category'] for column in DETAIL_COLUMNS} for row in report['rows']]


def add_excel_pivot(summary, detail, report):
    """Serialize the reference's native Status/SLA/count pivot and its cache.

    Materialized cells and cache records both use the shared report, so the
    downloaded workbook opens with its totals and can refresh from Sheet1.
    """
    from openpyxl.pivot.cache import CacheDefinition, CacheSource, WorksheetSource, CacheField, SharedItems
    from openpyxl.pivot.fields import Text, Index, DateTimeField
    from openpyxl.pivot.record import Record, RecordList
    from openpyxl.pivot.table import (TableDefinition, Location, PivotField, FieldItem,
                                     RowColField, RowColItem, DataField, PivotTableStyle)
    statuses = [row['Status'] for row in report['summary']]
    dimensions = {2: CATEGORIES, 11: statuses}
    lookups = {column: {value: index for index, value in enumerate(values)} for column, values in dimensions.items()}
    fields = [CacheField(name=name, sharedItems=SharedItems(
        _fields=[Text(v=value) for value in dimensions.get(column, [])]))
        for column, name in enumerate(DETAIL_COLUMNS)]
    cache = CacheDefinition(cacheSource=CacheSource(type='worksheet',
        worksheetSource=WorksheetSource(ref=detail.dimensions, sheet=detail.title)),
        cacheFields=fields, recordCount=len(report['rows']), saveData=True,
        refreshOnLoad=False, enableRefresh=True, createdVersion=6, refreshedVersion=6,
        minRefreshableVersion=3)
    cache.records = RecordList(r=[Record(_fields=[
        Index(v=lookups[column][str(value)]) if column in dimensions else
        DateTimeField(v=value) if isinstance(value, datetime) else Text(v=str(value if value is not None else ''))
        for column, value in enumerate(values)]) for values in detail.iter_rows(min_row=2, values_only=True)])
    pivot_fields = [PivotField(showAll=False) for _ in DETAIL_COLUMNS]
    pivot_fields[0].dataField = True
    for column, axis in ((2, 'axisCol'), (11, 'axisRow')):
        pivot_fields[column] = PivotField(axis=axis, showAll=True, compact=False,
            defaultSubtotal=False, items=[FieldItem(x=index) for index in range(len(dimensions[column]))] + [FieldItem(t='default')])
    def items(length):
        return [RowColItem(x=[Index(v=index)]) for index in range(length)] + [RowColItem(t='grand', x=[Index(v=0)])]
    pivot = TableDefinition(name='SLAStatusPivot', cacheId=1, dataCaption='Values',
        rowHeaderCaption='Status', compact=False, compactData=False, outline=False, outlineData=False,
        rowGrandTotals=True, colGrandTotals=True,
        location=Location(ref=f'A3:E{len(statuses)+5}', firstHeaderRow=1, firstDataRow=2, firstDataCol=1),
        pivotFields=pivot_fields, rowFields=[RowColField(x=11)], rowItems=items(len(statuses)),
        colFields=[RowColField(x=2)], colItems=items(3),
        dataFields=[DataField(name='Count of Order Number', fld=0, subtotal='count')],
        pivotTableStyleInfo=PivotTableStyle(name='PivotStyleLight16', showRowHeaders=True,
            showColHeaders=True, showRowStripes=False, showColStripes=False, showLastColumn=True))
    pivot.cache = cache
    summary.add_pivot(pivot)


def excel_report(report):
    """A report snapshot in the supplied Sheet2/Sheet1 layout."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.chart import BarChart, Reference
    from openpyxl.utils import get_column_letter
    book = Workbook()
    summary = book.active
    summary.title = 'Sheet2'
    summary.append([])
    summary.append([])
    summary.append(['Count of Order Number', 'Column Labels'])
    for values in summary_values(report):
        # The reference displays zero category cells as blanks.
        summary.append([value if index == 0 or value or index == 4 else None
                        for index, value in enumerate(values)])
    detail = book.create_sheet('Sheet1')
    detail.append(DETAIL_COLUMNS)
    for row in sample_rows(report):
        values = [row[column] for column in DETAIL_COLUMNS]
        values[1] = local_time(values[1]) or values[1]
        detail.append(values)
    border = Border(**{edge: Side(style='thin', color='D4D4D4') for edge in ('left', 'right', 'top', 'bottom')})
    for sheet in (summary, detail):
        sheet.sheet_view.showGridLines = False
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                cell.font = Font(name='Calibri', size=11)
                if cell.row >= (4 if sheet == summary else 1):
                    cell.border = border
                cell.alignment = Alignment(vertical='center')
        header = 4 if sheet == summary else 1
        for cell in sheet[header]:
            cell.font = Font(name='Calibri', size=11, bold=True)
            cell.fill = PatternFill('solid', fgColor='F2F2F2')
        sheet.freeze_panes = f'A{header+1}'
        for index, width in enumerate(([30, 17, 17, 15, 17] if sheet == summary else [29, 24, 17, 18, 22, 27, 8, 22, 24, 22, 22, 30, 56]), 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
    for cells in detail.iter_rows(min_row=2, min_col=2, max_col=2):
        if isinstance(cells[0].value, datetime):
            cells[0].number_format = 'mm/dd/yyyy hh:mm'
    for cell in summary[summary.max_row]:
        cell.font = Font(name='Calibri', size=11, bold=True)
    detail.auto_filter.ref = detail.dimensions
    if report['summary']:
        add_excel_pivot(summary, detail, report)
        chart = BarChart()
        chart.type, chart.grouping, chart.overlap = 'bar', 'stacked', 100
        chart.title = 'SLA Status'
        chart.x_axis.title = 'Orders'
        chart.y_axis.title = 'Status'
        chart.add_data(Reference(summary, min_col=2, max_col=4, min_row=4, max_row=summary.max_row-1), titles_from_data=True)
        chart.set_categories(Reference(summary, min_col=1, min_row=5, max_row=summary.max_row-1))
        chart.width, chart.height = 27, max(12, len(report['summary']) * 0.65)
        for series, color in zip(chart.series, COLORS):
            series.graphicalProperties.solidFill = color.lstrip('#')
        summary.add_chart(chart, 'G4')
    stream = BytesIO()
    book.save(stream)
    stream.seek(0)
    return stream


def sheet_chart_requests(sheet_id, values, existing, preserve_format=False):
    """Replace the report's chart in place, excluding Grand Total from series."""
    chart = next((item for item in existing.get('charts', []) if item.get('spec', {}).get('title') == 'SLA Status'), None)
    if preserve_format and chart:
        if len(values) <= 3:
            return []
        from copy import deepcopy
        spec = deepcopy(chart['spec'])
        basic = spec['basicChart']
        for item in basic.get('domains', []):
            for source in item['domain']['sourceRange']['sources']:
                source.update(startRowIndex=1, endRowIndex=len(values)-1)
        for item in basic.get('series', []):
            for source in item['series']['sourceRange']['sources']:
                source.update(startRowIndex=1, endRowIndex=len(values)-1)
        return [{'updateChartSpec': {'chartId': chart['chartId'], 'spec': spec}}]
    if len(values) <= 3:
        return [{'deleteEmbeddedObject': {'objectId': chart['chartId']}}] if chart else []
    def source(column):
        return {'sourceRange': {'sources': [{'sheetId': sheet_id, 'startRowIndex': 1,
            'endRowIndex': len(values)-1, 'startColumnIndex': column, 'endColumnIndex': column+1}]}}
    from datatrace_sync import sheet_color
    spec = {'title': 'SLA Status', 'basicChart': {'chartType': 'BAR', 'stackedType': 'STACKED',
        'legendPosition': 'BOTTOM_LEGEND', 'headerCount': 1,
        'axis': [{'position': 'BOTTOM_AXIS', 'title': 'Orders'}, {'position': 'LEFT_AXIS', 'title': 'Status'}],
        'domains': [{'domain': source(0)}], 'series': [
            {'series': source(index), 'targetAxis': 'BOTTOM_AXIS', 'color': sheet_color(color)}
            for index, color in enumerate(('#555555', '#999999', '#cccccc'), 1)]}}
    position = {'overlayPosition': {'anchorCell': {'sheetId': sheet_id, 'rowIndex': 1, 'columnIndex': 6},
                                   'widthPixels': 950, 'heightPixels': max(400, (len(values)-3)*32)}}
    if chart:
        return [{'updateChartSpec': {'chartId': chart['chartId'], 'spec': spec}},
                {'updateEmbeddedObjectPosition': {'objectId': chart['chartId'], 'newPosition': position,
                                                 'fields': 'anchorCell,widthPixels,heightPixels'}}]
    return [{'addChart': {'chart': {'spec': spec, 'position': position}}}]


def preserve_table_formats(sheet_id, previous, values):
    """Move the existing total style and extend its existing body style."""
    old_total = next((i for i, row in enumerate(previous) if row and row[0] == 'Grand Total'), None)
    new_total = len(values)-1
    if old_total is None or old_total == new_total:
        return []
    def copy(start, end, row):
        return {'copyPaste': {'source': {'sheetId': sheet_id, 'startRowIndex': row,
                    'endRowIndex': row+1, 'endColumnIndex': 5},
                'destination': {'sheetId': sheet_id, 'startRowIndex': start,
                    'endRowIndex': end, 'endColumnIndex': 5}, 'pasteType': 'PASTE_FORMAT'}}
    requests = [copy(new_total, new_total+1, old_total)]
    if old_total >= 3 and new_total > old_total:
        requests.append(copy(old_total, new_total, 2))
    return requests


def publish_preview_sla(book, report, backup_root):
    """Replace only SLA values and chart ranges; preserve existing Sheet styling."""
    from pathlib import Path
    from datetime import timezone
    import gzip
    import json
    import secrets
    from datatrace_sync import sheet_cell
    metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats,charts)'})['sheets']
    existing = next((s for s in metadata if s['properties']['title'] == 'SLA Status'), None)
    previous = book.worksheet('SLA Status').get_all_values(value_render_option='FORMULA') if existing else []
    values = sheet_summary_values(report)
    number = existing['properties']['sheetId'] if existing else secrets.randbelow(2**30)
    requests = []
    if not existing:
        requests.append({'addSheet': {'properties': {'sheetId': number, 'title': 'SLA Status',
            'gridProperties': {'rowCount': len(values)+25, 'columnCount': 18, 'frozenRowCount': 2}}}})
    elif existing['properties'].get('gridProperties', {}).get('rowCount', 0) < len(values):
        requests.append({'updateSheetProperties': {'properties': {'sheetId': number,
            'gridProperties': {'rowCount': len(values)+25}}, 'fields': 'gridProperties.rowCount'}})
    requests.extend(preserve_table_formats(number, previous, values))
    requests.append({'updateCells': {'range': {'sheetId': number,
        'endRowIndex': max(len(values), len(previous)), 'endColumnIndex': 5},
        'rows': [{'values': [sheet_cell(value) for value in row]} for row in values],
        'fields': 'userEnteredValue'}})
    if not existing:
        requests.extend(sheet_format_requests(number, values, {}))
    requests.extend(sheet_chart_requests(number, values, existing or {}, preserve_format=True))
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / ('sla-preview-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.json.gz')
    with gzip.open(backup, 'wt', encoding='utf-8') as stream:
        json.dump({'metadata': existing, 'values': previous, 'preview_id': report['preview_id']}, stream)
    book.batch_update({'requests': requests})
    def normalized(matrix):
        result = []
        for row in matrix:
            row = [str(value) if value is not None else '' for value in row[:5]]
            while row and not row[-1]:
                row.pop()
            result.append(row)
        while result and not result[-1]:
            result.pop()
        return result
    actual = book.worksheet('SLA Status').get_all_values(value_render_option='UNFORMATTED_VALUE')
    if normalized(actual) != normalized(values):
        raise RuntimeError('SLA Status could not be verified. Refresh SLA Status to retry.')
    return {'synced': True, 'tabs': ['SLA Status'], 'preview_id': report['preview_id']}
