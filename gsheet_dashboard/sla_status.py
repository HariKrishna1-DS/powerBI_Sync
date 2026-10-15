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
            'summary_columns': SUMMARY_COLUMNS, **{key: snapshot.get(key) for key in ('source', 'mode', 'offline', 'updated_at')}}


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


def sheet_chart_requests(sheet_id, values, existing):
    """Replace the report's chart in place, excluding Grand Total from series."""
    chart = next((item for item in existing.get('charts', []) if item.get('spec', {}).get('title') == 'SLA Status'), None)
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
