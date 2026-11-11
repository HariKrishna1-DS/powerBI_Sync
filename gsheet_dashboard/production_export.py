"""Append-only production workbook workflow. Existing cells are never edited."""
from collections import Counter
from copy import copy
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import threading
from uuid import uuid4

from openpyxl import load_workbook
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from openpyxl.styles.numbers import is_date_format
from openpyxl.formatting.formatting import ConditionalFormattingList
from openpyxl.worksheet.cell_range import CellRange, MultiCellRange
from new_order_report import plain_comment
from portal_time import capture_time

LOCK = threading.Lock()
GOOGLE_COLUMNS = ['No', 'Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
    'Online/Ground', 'Product', 'Status', 'ETA', 'Comments', 'Assignee', 'Searcher',
    'Clarification Requested', 'Shift', 'Process date', 'Review/QC', 'Expense',
    'In-Time', 'Out Time', 'SLA Expiration', 'Free Site', 'review']


def norm(value):
    return re.sub(r'[^a-z0-9]', '', str(value or '').casefold())


# User-assigned C-O/Update products, including labels truncated by the queue UI.
def default_product_destination(product):
    value = norm(product)
    if value in {'bulktwoowner', 'clientreview', 'newowner', 'reofulltitle'}:
        return 'co'
    if value.startswith(('attorneyappro', 'homebuilderl', 'qualitycontro', 'updatelegal')):
        return 'co'
    return None


def number(value):
    # Preserve punctuation: hyphens and slashes can distinguish real orders.
    return str(value or '').strip().casefold()


def get(row, *keys):
    for key in keys:
        if row.get(key) not in (None, ''):
            return row[key]
    return ''


def google_row(row):
    result = dict(zip(GOOGLE_COLUMNS, ['', get(row, 'Arrival Date', 'Date'), row.get('Order Number', ''),
        get(row, 'TraceQ Id', 'TraceQ ID'), get(row, 'State', 'St'), row.get('County', ''), row.get('Client', ''),
        get(row, 'Online/Ground', 'Online/ Ground', 'Online/Gorund'), row.get('Product', ''),
        get(row, 'Status', 'Task Status'), get(row, 'ETA'), plain_comment(get(row, 'ETA Comments', 'Comments', 'Comment')),
        get(row, 'Assignee', 'Last User'), row.get('Searcher', ''), row.get('Clarification Requested', ''),
        row.get('Shift', ''), get(row, 'Process date', 'Completed Time'), row.get('Review/QC', ''),
        row.get('Expense', ''), get(row, 'Arrival Time', 'In-Time'), row.get('Out Time', ''),
        get(row, 'SLA Expiration', 'SLA Expiration*'), row.get('Free Site', ''), row.get('review', '')]))
    if norm(result['Status']) == 'searchinprogress':
        result['Comments'] = 'New Orders'
    return result


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def discover(folder):
    path = Path(str(folder).strip().strip('"')).expanduser()
    if not path.is_absolute() or not path.is_dir():
        raise ValueError('Enter an existing absolute folder path on the computer running Tv Tracker.')
    found = {'full': [], 'co': []}
    for file in path.glob('*.xlsx'):
        if file.name.startswith('~$'):
            continue
        name = norm(file.stem)
        if name.startswith('tvsearchproductionreportfullsearch'):
            found['full'].append(file)
        elif name.startswith('tvsearchproductionreportcoandupdate'):
            found['co'].append(file)
    if any(len(files) != 1 for files in found.values()):
        raise ValueError('The folder must contain exactly one Full Search report and one C-O and Update report. Use a separate folder for each month.')
    return {kind: files[0] for kind, files in found.items()}


def template(path):
    book = load_workbook(path)
    matches = []
    for sheet in book:
        for r in range(1, min(sheet.max_row, 15) + 1):
            headers = [str(c.value or '').strip() for c in sheet[r]]
            if {'ordernumber', 'product', 'status'}.issubset({norm(h) for h in headers}):
                matches.append((sheet, r, headers))
                break
    if len(matches) != 1:
        book.close()
        raise ValueError(f'{path.name}: expected one order worksheet with Order Number, Product and Status headers.')
    sheet, header_row, headers = matches[0]
    oi, pi = next(i for i,h in enumerate(headers) if norm(h)=='ordernumber'), next(i for i,h in enumerate(headers) if norm(h)=='product')
    existing, products = set(), set()
    for row in sheet.iter_rows(min_row=header_row+1, values_only=True):
        if row[oi]:
            existing.add(number(row[oi]))
            if row[pi]: products.add(str(row[pi]).strip())
    return book, sheet, header_row, headers, existing, products


def plan(folder, report, routes=None):
    files = discover(folder)
    info, known = {}, {}
    for kind, path in files.items():
        book, sheet, hr, headers, existing, products = template(path)
        info[kind] = dict(path=path, sheet=sheet.title, headers=headers, existing=existing,
                          sha256=digest(path), additions=[], skipped=0)
        for product in products:
            known.setdefault(norm(product), set()).add(kind)
        book.close()
    seen, unresolved, counts = set(), set(), Counter()
    preview = []
    for raw in report.get('rows', []) + report.get('excluded_rows', []):
        row = google_row(raw)
        key = number(row['Order Number'])
        if not key or key in seen: continue
        seen.add(key)
        product = str(row['Product']).strip()
        counts[product] += 1
        explicit = (routes or {}).get(product)
        choices = known.get(norm(product), set())
        # Queue captures can contain visibly truncated product labels.
        if not choices and product.endswith(('..', '…')):
            prefix=norm(product.rstrip('.…'))
            choices=set().union(*(kinds for name,kinds in known.items() if prefix and name.startswith(prefix)))
        present=next((kind for kind,item in info.items() if key in item['existing']),None)
        if present:
            info[present]['skipped'] += 1
            preview.append(dict(row,Destination=files[present].name))
            continue
        kind = explicit if explicit in files else default_product_destination(product)
        if kind is None:
            kind = next(iter(choices)) if len(choices)==1 else None
        if kind is None:
            unresolved.add(product or '(Blank)')
            continue
        # An existing order in either report is retained and never duplicated.
        info[kind]['additions'].append(row)
        preview.append(dict(row, Destination=files[kind].name))
    payload = {'preview_id': report.get('preview_id'), 'rows': preview,
               'files': {k: v['sha256'] for k,v in info.items()}, 'routes': routes or {}}
    fingerprint = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return info, dict(fingerprint=fingerprint, preview_id=report.get('preview_id'),
        preview_name=report.get('preview_name'), columns=GOOGLE_COLUMNS,
        rows=preview, unresolved=sorted(unresolved), products=dict(counts),
        reports=[{'kind':k, 'name':v['path'].name, 'sheet':v['sheet'],
            'existing':len(v['existing']), 'missing':len(v['additions']), 'skipped':v['skipped'],
            'orders':v['additions']} for k,v in info.items()])


def cell_value(header, source, occurrence=0):
    key = norm(header)
    if key in ('comments','comment','etacomments') and norm(source.get('Status'))=='searchinprogress':
        return 'New Orders'
    aliases = {'onlinegorund':'Online/Ground', 'processeddate':'Process date', 'processdate':'Process date',
        'freesite':'Free Site', 'intime':'In-Time', 'slaexpiration':'SLA Expiration'}
    if key == 'sla':
        # The second SLA column in Full Search is the completion classification.
        return source.get('Free Site', '') if occurrence else source.get('SLA Expiration', '')
    canonical = aliases.get(key) or next((c for c in GOOGLE_COLUMNS if norm(c)==key), None)
    return source.get(canonical, '') if canonical else ''


def extend_status_formatting(sheet, header_row, headers, end_row):
    """Extend the original status rules, retaining their formulas and differential styles."""
    status_col=next((i+1 for i,h in enumerate(headers) if norm(h) in ('status','taskstatus')),None)
    if status_col is None: return
    reference=re.compile(r'(?<![A-Z0-9_])\$?'+get_column_letter(status_col)+r'\$?\d+\b',re.I)
    updated=ConditionalFormattingList()
    for region in sheet.conditional_formatting:
        for rule in sheet.conditional_formatting[region]:
            ranges=MultiCellRange(str(region.sqref))
            status_rule=rule.type=='expression' and any(reference.search(formula or '') for formula in (rule.formula or []))
            if status_rule:
                extended=[]
                for area in ranges.ranges:
                    area=CellRange(str(area))
                    if area.min_row<=header_row+1<=area.max_row and area.min_col<=status_col<=area.max_col:
                        area.max_row=max(area.max_row,end_row)
                    extended.append(str(area))
                ranges=MultiCellRange(' '.join(extended))
            new_region=copy(region)
            new_region.sqref=ranges
            updated.add(new_region,copy(rule))
    sheet.conditional_formatting=updated


def append_rows(path, rows):
    book, sheet, hr, headers, _, _ = template(path)
    order_col = next(i+1 for i,h in enumerate(headers) if norm(h)=='ordernumber')
    last = max([hr] + [r for r in range(hr+1,sheet.max_row+1) if sheet.cell(r,order_col).value])
    # Never overwrite preformatted totals, notes, or non-order cells beneath the data.
    start = max([last] + [r for r in range(last+1,sheet.max_row+1)
        if any(sheet.cell(r,c).value is not None for c in range(1,sheet.max_column+1))]) + 1
    # Match established body rows rather than inheriting a previously enlarged append.
    body_rows=[r for r in range(max(hr+1,last-99),last+1) if sheet.cell(r,order_col).value]
    row_height=lambda r:sheet.row_dimensions[r].height or sheet.sheet_format.defaultRowHeight or 15
    common_height=Counter(row_height(r) for r in body_rows).most_common(1)[0][0] if body_rows else 15
    style_row=next((r for r in reversed(body_rows) if row_height(r)==common_height),last)
    numbers = [sheet.cell(r,1).value for r in range(hr+1,last+1)]
    seq = max([int(v) for v in numbers if isinstance(v,(int,float))] or [0])
    for offset, source in enumerate(rows):
        r = start+offset
        occurrences = Counter()
        for col, header in enumerate(headers,1):
            cell = sheet.cell(r,col)
            previous = sheet.cell(last,col)
            if last>hr:
                cell._style = copy(sheet.cell(style_row,col)._style)
                cell.alignment = copy(sheet.cell(style_row,col).alignment)
                if not sheet.cell(style_row,col).has_style:
                    cell.font = copy(sheet.cell(style_row,order_col).font)
                    cell.alignment = copy(sheet.cell(style_row,order_col).alignment)
            value = seq+offset+1 if norm(header)=='no' else cell_value(header,source,occurrences[norm(header)])
            occurrence = occurrences[norm(header)]
            occurrences[norm(header)] += 1
            expiration_column = norm(header)=='slaexpiration' or (norm(header)=='sla' and occurrence==0)
            parsed_expiration = capture_time(value) if expiration_column and value not in (None,'') else None
            if parsed_expiration is not None:
                if norm(header)=='sla':
                    value = parsed_expiration.replace(hour=0,minute=0,second=0,microsecond=0)
                    cell.number_format = 'dd/mm/yyyy'
                else:
                    value = parsed_expiration
                    cell.number_format = 'mm/dd/yyyy hh:mm:ss AM/PM'
            if norm(header)=='date' and value not in (None,''):
                parsed_date=capture_time(value)
                if parsed_date is not None:
                    value=parsed_date
                    if not is_date_format(cell.number_format): cell.number_format='dd-mm-yyyy'
            if norm(header) in ('comments','comment','etacomments'):
                value = plain_comment(value)
            if not value and previous.data_type=='f':
                value = Translator(previous.value,origin=previous.coordinate).translate_formula(cell.coordinate)
                cell.value = value
            else:
                cell.value = value
                if isinstance(value,str): cell.data_type='s'
        if last>hr: sheet.row_dimensions[r].height = row_height(style_row)
    if rows: extend_status_formatting(sheet,hr,headers,start+len(rows)-1)
    for table in sheet.tables.values():
        if rows and table.ref.split(':')[-1] == f'{get_column_letter(len(headers))}{last}':
            table.ref = f'{table.ref.split(":")[0]}:{get_column_letter(len(headers))}{start+len(rows)-1}'
    if sheet.auto_filter.ref and rows:
        sheet.auto_filter.ref = f'A{hr}:{get_column_letter(len(headers))}{start+len(rows)-1}'
    stream=BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def proceed(info, output):
    """Stage both files, verify no external edits, back up, then replace with rollback."""
    output.mkdir(parents=True, exist_ok=False)
    staged, backups, replaced = {}, {}, []
    try:
        for kind,item in info.items():
            path=item['path']
            if path.with_name('~$'+path.name).exists():
                raise ValueError(f'Close {path.name} in Excel before proceeding.')
            data=append_rows(path,item['additions']) if item['additions'] else path.read_bytes()
            (output/path.name).write_bytes(data)
            if item['additions']:
                temporary=path.with_name('.tv-tracker-'+uuid4().hex+'.xlsx')
                temporary.write_bytes(data)
                staged[kind]=temporary
        for item in info.values():
            if digest(item['path'])!=item['sha256']:
                raise ValueError('A workbook changed during preparation. Check the folder again.')
        for kind in staged:
            path=info[kind]['path']
            backup=path.parent/'.tv-tracker-backups'/output.name/path.name
            backup.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,backup)
            backups[kind]=backup
        for kind,temporary in staged.items():
            os.replace(temporary,info[kind]['path'])
            replaced.append(kind)
    except Exception:
        for kind in replaced:
            shutil.copy2(backups[kind],info[kind]['path'])
        raise
    finally:
        for temporary in staged.values(): temporary.unlink(missing_ok=True)
    return {k:str(p) for k,p in backups.items()}


def register_production_export(app, workspace, load_report):
    from flask import request, jsonify, send_file
    exports = workspace.store.root.parent/'production-exports'

    @app.get('/api/production-report')
    def production_config():
        settings=workspace.read()
        return jsonify(folder=settings.get('production_report_folder',''), previews=workspace.store.list(),
                       selected_preview_id=settings.get('sla_preview_id'))

    @app.post('/api/production-report/<action>')
    def production_action(action):
        if action not in ('check','proceed'): return jsonify(error='Unknown action'),404
        body=request.get_json(silent=True) or {}
        try:
            if not isinstance(body.get('routes',{}),dict): raise ValueError('Invalid product destinations.')
            with LOCK:
                previews=workspace.store.list()
                preview_id=body.get('preview_id') or workspace.read().get('sla_preview_id') or (previews[0]['id'] if previews else None)
                if type(preview_id) is not int or preview_id<1: raise ValueError('Extract or choose a saved preview first.')
                report=load_report(preview_id)
                info,result=plan(body.get('folder',''),report,body.get('routes'))
                if action=='proceed':
                    if result['unresolved']: raise ValueError('Choose destinations for all unfamiliar products, then check again.')
                    if body.get('fingerprint')!=result['fingerprint']:
                        return jsonify(error='The preview, routing or workbooks changed. Check again before proceeding.'),409
                    token=uuid4().hex
                    backups=proceed(info,exports/token)
                    result.update(completed=True,backups=backups,downloads=[{'name':v['path'].name,
                        'url':f'/api/production-report/download/{token}/{kind}'} for kind,v in info.items()])
                    (exports/token/'files.json').write_text(json.dumps({k:v['path'].name for k,v in info.items()}))
                workspace.save(production_report_folder=str(next(iter(info.values()))['path'].parent))
                return jsonify(result)
        except (ValueError,KeyError,PermissionError,OSError) as exc:
            return jsonify(error=str(exc) if not isinstance(exc,PermissionError) else 'Close the workbooks in Excel and check write permission for the folder.'),400

    @app.get('/api/production-report/download/<token>/<kind>')
    def production_download(token,kind):
        if not re.fullmatch('[a-f0-9]{32}',token) or kind not in ('full','co'): return jsonify(error='Download not found'),404
        folder=exports/token
        try: name=json.loads((folder/'files.json').read_text())[kind]
        except (OSError,KeyError): return jsonify(error='Download not found'),404
        return send_file(folder/name,as_attachment=True,download_name=name)
