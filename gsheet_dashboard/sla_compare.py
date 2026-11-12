"""SLA vs Production Report side-by-side comparison and status diff matching."""
from collections import Counter, defaultdict
from datetime import datetime, date, timezone
from io import BytesIO
from pathlib import Path
import re
import csv
import openpyxl

from tracker_sync import canonical_headers, key, text, STATUS_NAMES
from sla_status import preview_snapshot, build_sla_status
from import_identity import number_key
from sla_manual import revision as sla_revision
from new_order_report import NEW_ORDER_COLUMNS, production_record, comparison_record, plain_comment

COMPARISON_CATEGORIES = ['Future SLA', 'Negative SLA', 'Today SLA']
COMPARISON_COLUMNS = ['Status', *COMPARISON_CATEGORIES, 'Grand Total']

def clean_key(val):
    if val is None:
        return ''
    return re.sub(r'[^a-z0-9]', '', str(val).strip().casefold())

def extract_date_only(val):
    """Extract date part only from datetime or date strings, ignoring time entirely."""
    if val is None:
        return ''
    if isinstance(val, (datetime, date)):
        return f"{val.month}/{val.day}/{val.year}"
    s = str(val).strip()
    if not s:
        return ''
    # Match MM/DD/YYYY or M/D/YYYY
    m = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})', s)
    if m:
        return m.group(1)
    # Match YYYY-MM-DD
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        try:
            return f"{int(m.group(2))}/{int(m.group(3))}/{m.group(1)}"
        except Exception:
            return m.group(0)
    # If string contains space separated tokens, test first token
    parts = s.split()
    if len(parts) > 1 and ('/' in parts[0] or '-' in parts[0]):
        return parts[0]
    return s

def parse_date_obj(val):
    """Parse date-only string or object into a date object for comparison."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except Exception:
            pass
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            pass
    return None

def normalize_status(val):
    raw = str(val or '').strip()
    if not raw:
        return ''
    compact = ' '.join(raw.casefold().split())
    if compact == '(blank)':
        return ''
    # These are intentional Excel workflow labels, not aliases for queue statuses.
    if clean_key(compact).startswith('needtoassign'):
        return raw
    # Handle known aliases
    aliases = {
        'completed': 'Completed and Delivered',
        'completed and delivered': 'Completed and Delivered',
        'completed and delivered ': 'Completed and Delivered',
        'qc in progress': 'QC in Progress',
        'typing in progress': 'Typing in Progress',
        'search in progress': 'Search In Progress',
        'searchfix': 'SearchFix',
        'waiting for effective date': 'Waiting for Effective Date',
        'attorney approval': 'Attorney Approval',
        'home builders': 'Home Builders',
        'assign to abs': 'Assign to ABS',
        'awaiting for clarification': 'Awaiting for Clarification',
        'cancelled': 'Cancelled',
        'canceled': 'Cancelled',
        'responded': 'Responded',
        'need to add subscription': 'Need To Add Subscription',
        'need to add subs': 'Need To Add Subscription',
        'need subscription': 'Need To Add Subscription',
        'site down': 'Site Down',
    }
    return aliases.get(compact, STATUS_NAMES.get(compact, raw.strip()))


def assignment_pending(value):
    return clean_key(value).startswith('needtoassign')

def read_production_file(content_or_path, filename=''):
    """Parse XLSX, XLS, or CSV production reports into a list of standardized order dicts.
    Production deadlines are ignored; SLA categories come only from SLA Status.
    Skips non-production log sheets like Escalations.
    """
    is_path = isinstance(content_or_path, (str, Path))
    name = Path(str(content_or_path)).name if is_path else filename
    suffix = Path(name).suffix.lower()

    rows = []
    if suffix in ('.xlsx', '.xlsm'):
        file_obj = str(content_or_path) if is_path else BytesIO(content_or_path)
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            # Skip non-production sheets (such as escalations, history logs, summary pivots)
            s_clean = sheet_name.strip().lower()
            if any(k in s_clean for k in ('escalat', 'history', 'log', 'pivot', 'summary', 'lookup', 'instruction', 'readme', 'clarificat', 'exception', 'note')):
                continue

            sheet = wb[sheet_name]
            iterator = sheet.iter_rows(values_only=True)
            # Find the header row (look within first 15 rows for 'Order Number' or 'Order No')
            headers = None
            for _ in range(15):
                candidate_row = next(iterator, None)
                if not candidate_row:
                    break
                candidate_headers = [str(c or '').strip() for c in candidate_row]
                if any(clean_key(c) in ('ordernumber', 'orderno') for c in candidate_headers):
                    headers = candidate_headers
                    break
            if not headers:
                continue

            # Find column positions
            col_map = {}
            for idx, h in enumerate(headers):
                c_name = clean_key(h)
                if c_name in ('ordernumber', 'orderno'):
                    col_map.setdefault('order_number', idx)
                elif c_name in ('product', 'productname'):
                    col_map.setdefault('product', idx)
                elif c_name in ('state', 'st'):
                    col_map.setdefault('state', idx)
                elif c_name in ('county',):
                    col_map.setdefault('county', idx)
                elif c_name in ('client',):
                    col_map.setdefault('client', idx)
                elif c_name in ('intime', 'receiveddate', 'arrivaltime', 'date'):
                    col_map.setdefault('in_time', idx)
                elif c_name in ('outtime', 'processeddate', 'completeddate', 'processdate'):
                    col_map.setdefault('out_time', idx)
                elif c_name in ('searcher',):
                    col_map.setdefault('searcher', idx)
                elif c_name in ('typer',):
                    col_map.setdefault('typer', idx)
                elif c_name in ('comments', 'etacomments'):
                    col_map.setdefault('comments', idx)

            # Strict Status Column Mapping: Look for exact 'Status' first!
            for idx, h in enumerate(headers):
                if str(h or '').strip().casefold() == 'status':
                    col_map['status'] = idx
                    break
            if 'status' not in col_map:
                for idx, h in enumerate(headers):
                    if str(h or '').strip().casefold() in ('production status', 'task status', 'order status'):
                        col_map['status'] = idx
                        break

            # Must have order_number and at least one order identifier (not an empty log)
            if 'order_number' not in col_map or not any(k in col_map for k in ('product', 'client', 'state', 'county', 'searcher', 'typer')):
                continue

            for row_idx, row in enumerate(iterator, start=2):
                if not any(row):
                    continue
                num_idx = col_map['order_number']
                if num_idx >= len(row) or not row[num_idx]:
                    continue
                order_num = str(row[num_idx]).strip()
                if not order_num or order_num.lower() in ('order number', 'order no', 'none'):
                    continue

                def get_val(key_name):
                    idx = col_map.get(key_name)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        val = row[idx]
                        if isinstance(val, (datetime, date)):
                            return val.strftime('%Y-%m-%d %H:%M:%S')
                        return str(val).strip()
                    return ''


                rows.append({
                    'order_number': order_num,
                    'status': normalize_status(get_val('status')),
                    'product': get_val('product'),
                    'state': get_val('state'),
                    'county': get_val('county'),
                    'client': get_val('client'),
                    'in_time': get_val('in_time'),
                    'out_time': get_val('out_time'),
                    'prod_sla': '',
                    'searcher': get_val('searcher'),
                    'typer': get_val('typer'),
                    'comments': get_val('comments'),
                    'source_sheet': f'{name} [{sheet_name}]',
                })
        wb.close()
    elif suffix == '.csv':
        raw_text = (Path(content_or_path).read_text(encoding='utf-8-sig', errors='replace')
                    if is_path else content_or_path.decode('utf-8-sig', errors='replace'))

        reader = csv.reader(raw_text.splitlines())
        col_map = {}
        for row in reader:
            if not row or not any(row):
                continue
            compact_cells = [clean_key(c) for c in row]
            if any(h in ('ordernumber', 'orderno') for h in compact_cells):
                col_map = {}
                for idx, c_name in enumerate(compact_cells):
                    if c_name in ('ordernumber', 'orderno'):
                        col_map['order_number'] = idx
                    elif c_name in ('product', 'productname'):
                        col_map['product'] = idx
                    elif c_name in ('state', 'st'):
                        col_map['state'] = idx
                    elif c_name in ('county',):
                        col_map['county'] = idx
                    elif c_name in ('client',):
                        col_map['client'] = idx
                    elif c_name in ('intime', 'receiveddate', 'arrivaltime', 'date'):
                        col_map['in_time'] = idx
                    elif c_name in ('outtime', 'processeddate', 'completeddate', 'processdate'):
                        col_map['out_time'] = idx
                    elif c_name in ('searcher',):
                        col_map['searcher'] = idx
                    elif c_name in ('typer',):
                        col_map['typer'] = idx
                    elif c_name in ('comments', 'etacomments'):
                        col_map['comments'] = idx

                # Strict Status mapping for CSV
                for idx, h in enumerate(row):
                    if str(h or '').strip().casefold() == 'status':
                        col_map['status'] = idx
                        break
                if 'status' not in col_map:
                    for idx, h in enumerate(row):
                        if str(h or '').strip().casefold() in ('production status', 'task status', 'order status'):
                            col_map['status'] = idx
                            break

                continue

            if 'order_number' not in col_map:
                continue

            num_idx = col_map['order_number']
            if num_idx >= len(row) or not row[num_idx]:
                continue
            order_num = str(row[num_idx]).strip()
            if not order_num or clean_key(order_num) in ('ordernumber', 'orderno'):
                continue

            def get_csv_val(key_name):
                idx = col_map.get(key_name)
                if idx is not None and idx < len(row) and row[idx] is not None:
                    return str(row[idx]).strip()
                return ''


            rows.append({
                'order_number': order_num,
                'status': normalize_status(get_csv_val('status')),
                'product': get_csv_val('product'),
                'state': get_csv_val('state'),
                'county': get_csv_val('county'),
                'client': get_csv_val('client'),
                'in_time': get_csv_val('in_time'),
                'out_time': get_csv_val('out_time'),
                'prod_sla': '',
                'searcher': get_csv_val('searcher'),
                'typer': get_csv_val('typer'),
                'comments': get_csv_val('comments'),
                'source_sheet': name,
            })
    else:
        raise ValueError(f'Unsupported file format: {suffix}. Choose an Excel (.xlsx) or CSV (.csv) file.')

    return rows

def compare_sla_with_production(sla_report, production_rows, preview_name=''):
    """Compare production statuses using the selected SLA Status report's orders and categories."""
    if not production_rows:
        return {
            'has_production': False,
            'orders': [],
            'metrics': {
                'total_sla': len(sla_report.get('rows', [])),
                'total_production': 0,
                'matched': 0,
                'status_moved': 0,
                'same_status': 0,
                'sla_only': 0,
                'prod_only': 0,
            },
            'transitions': [],
            'sla_summary': {
                'columns': COMPARISON_COLUMNS,
                'rows': [],
                'totals': {
                    'Status': 'Grand Total',
                    'Future SLA': 0,
                    'Negative SLA': 0,
                    'Today SLA': 0,
                    'Unknown SLA': 0,
                    'Grand Total': 0
                },
            },
            'preview_name': preview_name,
            'source_files': '',
        }

    # Build unique SLA orders dictionary by clean key
    sla_map = {}
    for r in sla_report.get('rows', []):
        order_no = str(r.get('Order Number') or '').strip()
        if not order_no:
            continue
        k = number_key({'Order Number': order_no})
        if k:
            sla_map[k] = r

    # Build unique Production orders dictionary
    # Prefer complete production entries over sparse or log rows
    prod_map = {}
    production_candidates = defaultdict(list)
    for r in production_rows:
        order_no = str(r.get('order_number') or '').strip()
        if not order_no:
            continue
        k = number_key({'Order Number': order_no})
        if not k:
            continue
        production_candidates[k].append(r)

        existing = prod_map.get(k)
        if existing is None:
            prod_map[k] = r
        else:
            existing_fields = sum(1 for field in ('product', 'state', 'client', 'searcher', 'typer', 'comments') if existing.get(field))
            new_fields = sum(1 for field in ('product', 'state', 'client', 'searcher', 'typer', 'comments') if r.get(field))
            existing_status = existing.get('status', '').casefold()
            new_status = r.get('status', '').casefold()
            # Do not let sparse or 'Responded' row overwrite an active production status
            if new_status == 'responded' and existing_status != 'responded':
                continue
            if new_fields >= existing_fields:
                prod_map[k] = r

    # An order can occur in both workbooks for different products. Compare the
    # queue task with its corresponding production row, not whichever file is last.
    from monthly_production import local_datetime
    for identity, candidates in production_candidates.items():
        if identity not in sla_map or len(candidates) < 2:
            continue
        queue_product = clean_key(sla_map[identity].get('Product'))
        def score(row):
            product = clean_key(row.get('product'))
            product_match = 2 if product and product == queue_product else 1 if product and (
                queue_product.startswith(product) or product.startswith(queue_product) and queue_product) else 0
            received = local_datetime(row.get('in_time')) or datetime.min
            return product_match, received.replace(tzinfo=None), bool(row.get('status'))
        prod_map[identity] = max(candidates, key=score)

    all_keys = list(dict.fromkeys(list(sla_map.keys()) + list(prod_map.keys())))

    orders = []
    matched_count = 0
    moved_count = 0
    same_count = 0
    sla_only_count = 0
    prod_only_count = 0

    transitions = Counter()

    for k in all_keys:
        in_sla = k in sla_map
        in_prod = k in prod_map

        sla_item = sla_map.get(k)
        prod_item = prod_map.get(k)

        order_no = (sla_item.get('Order Number') if sla_item else None) or (prod_item.get('order_number') if prod_item else '')

        if in_sla and in_prod:
            matched_count += 1
            sla_status_str = normalize_status(sla_item.get('Status', ''))
            prod_status_str = normalize_status(prod_item.get('status', ''))
            imported_prod_status = prod_status_str
            # Completed Excel rows must not replace the active preview status.
            if prod_status_str == 'Completed and Delivered':
                prod_status_str = sla_status_str

            # Check if statuses differ
            is_changed = (sla_status_str.casefold() != prod_status_str.casefold()) and bool(sla_status_str and prod_status_str) and not assignment_pending(prod_status_str)

            if is_changed:
                moved_count += 1
                match_type = 'status_moved'
                transitions[(sla_status_str, prod_status_str)] += 1
            else:
                same_count += 1
                match_type = 'same_status'

            # Excel deadlines are not a classification source. Preserve SLA Status exactly.
            sla_category = sla_item.get('SLA Category') or 'Unknown SLA'

            orders.append({
                'order_number': order_no,
                'match_type': match_type,
                'status_changed': is_changed,
                'sla_status': sla_status_str or '(Blank)',
                'sla_category': sla_category,
                'queue_sla_category': sla_item.get('SLA Category') or 'Unknown SLA',
                'prod_sla_category': sla_category,
                'prod_status': prod_status_str or '(Blank)',
                'imported_prod_status': imported_prod_status or '(Blank)',
                'change_label': f'{sla_status_str} ➔ {prod_status_str}' if is_changed else 'Unchanged',
                'product': sla_item.get('Product') or prod_item.get('product') or '',
                'state': sla_item.get('State') or sla_item.get('St') or prod_item.get('state') or '',
                'county': sla_item.get('County') or prod_item.get('county') or '',
                'client': sla_item.get('Client') or prod_item.get('client') or '',
                'in_time': sla_item.get('Arrival Time') or sla_item.get('Arrival Date') or prod_item.get('in_time') or '',
                'out_time': prod_item.get('out_time') or '',
                'prod_sla': '',
                'sla_expiration': sla_item.get('SLA Expiration') or sla_item.get('SLA Expiration*') or '',
                'sla_revision': sla_revision(sla_item),
                'eta_comments': plain_comment(sla_item.get('ETA Comments') or ''),
                'searcher': prod_item.get('searcher') or '',
                'typer': prod_item.get('typer') or '',
                'comments': prod_item.get('comments') or '',
                'source_sheet': prod_item.get('source_sheet') or '',
            })
        elif in_sla:
            sla_only_count += 1
            sla_status_str = normalize_status(sla_item.get('Status', ''))
            orders.append({
                'order_number': order_no,
                'match_type': 'sla_only',
                'production_report': production_record(sla_item, sla_status_str or '(Blank)'),
                'status_changed': False,
                'sla_status': sla_status_str or '(Blank)',
                'sla_category': sla_item.get('SLA Category') or 'Unknown SLA',
                'queue_sla_category': sla_item.get('SLA Category') or 'Unknown SLA',
                'prod_sla_category': sla_item.get('SLA Category') or 'Unknown SLA',
                'prod_status': 'Home Builders' if sla_status_str == 'Home Builders' else 'Not in Production Report',
                'change_label': 'Home Builders' if sla_status_str == 'Home Builders' else 'Pending in Queue (SLA only)',
                'product': sla_item.get('Product') or '',
                'state': sla_item.get('State') or sla_item.get('St') or '',
                'county': sla_item.get('County') or '',
                'client': sla_item.get('Client') or '',
                'in_time': sla_item.get('Arrival Time') or sla_item.get('Arrival Date') or '',
                'arrival_date': sla_item.get('Arrival Date') or '',
                'traceq_id': sla_item.get('TraceQ id') or sla_item.get('TraceQ ID') or '',
                'online_ground': sla_item.get('Online/Ground') or '',
                'assignee': sla_item.get('Assignee') or '',
                'queue_comments': plain_comment(sla_item.get('ETA Comments') or sla_item.get('Comments') or sla_item.get('Comment') or ''),
                'eta_comments': plain_comment(sla_item.get('ETA Comments') or ''),
                'out_time': '',
                'prod_sla': '',
                'sla_expiration': sla_item.get('SLA Expiration') or sla_item.get('SLA Expiration*') or '',
                'sla_revision': sla_revision(sla_item),
                'searcher': '',
                'typer': '',
                'comments': '',
                'source_sheet': '',
            })
        else:
            prod_only_count += 1
            prod_status_str = normalize_status(prod_item.get('status', ''))
            orders.append({
                'order_number': order_no,
                'match_type': 'prod_only',
                'status_changed': False,
                'sla_status': 'Not in SLA Queue',
                'sla_category': 'Not in SLA Queue',
                'queue_sla_category': 'Not in SLA Queue',
                'prod_sla_category': 'Not in SLA Queue',
                'prod_status': prod_status_str or '(Blank)',
                'change_label': 'Production Report Only',
                'product': prod_item.get('product') or '',
                'state': prod_item.get('state') or '',
                'county': prod_item.get('county') or '',
                'client': prod_item.get('client') or '',
                'in_time': prod_item.get('in_time') or '',
                'out_time': prod_item.get('out_time') or '',
                'prod_sla': '',
                'sla_expiration': '',
                'searcher': prod_item.get('searcher') or '',
                'typer': prod_item.get('typer') or '',
                'comments': prod_item.get('comments') or '',
                'source_sheet': prod_item.get('source_sheet') or '',
            })

    # Sort orders: status_moved first, then same_status, then sla_only, then prod_only
    type_priority = {'status_moved': 1, 'same_status': 2, 'sla_only': 3, 'prod_only': 4}
    orders.sort(key=lambda x: (type_priority.get(x['match_type'], 9), x['order_number']))

    result = {
        'preview_name': preview_name,
        'has_production': True,
        'as_of': sla_report.get('as_of', ''),
        'metrics': {
            'total_sla': len(sla_map),
            'total_production': len(prod_map),
            'matched': matched_count,
            'status_moved': moved_count,
            'same_status': same_count,
            'sla_only': sla_only_count,
            'prod_only': prod_only_count,
        },
        'transitions': [],
        'sla_summary': {
            'columns': COMPARISON_COLUMNS,
            'rows': [],
            'totals': {},
        },
        'orders': orders,
    }
    return recalculate_summary(result)

def comparison_summary_status(order):
    if order.get('match_type') == 'prod_only':
        return None
    if normalize_status(order.get('sla_status')) == 'Home Builders':
        return 'Home Builders'
    if order.get('match_type') in ('status_moved', 'same_status'):
        return order.get('prod_status') or '(Blank)'
    return None


def recalculate_summary(result):
    """Recalculate metrics, transitions, and SLA summary matrix from result['orders']."""
    orders = result.get('orders', [])
    matched_count = 0
    moved_count = 0
    same_count = 0
    sla_only_count = 0
    prod_only_count = 0
    transitions = Counter()

    for o in orders:
        mtype = o.get('match_type')
        if mtype in ('status_moved', 'same_status'):
            matched_count += 1
            sla_st = normalize_status(o.get('sla_status', ''))
            prod_st = normalize_status(o.get('prod_status', ''))
            is_changed = (sla_st.casefold() != prod_st.casefold()) and bool(sla_st and prod_st and prod_st != 'Not in Production Report') and not assignment_pending(prod_st)
            o['status_changed'] = is_changed
            if is_changed:
                o['match_type'] = 'status_moved'
                o['change_label'] = f"{sla_st} ➔ {prod_st}"
                moved_count += 1
                transitions[(sla_st, prod_st)] += 1
            else:
                o['match_type'] = 'same_status'
                o['change_label'] = 'Unchanged (protected Excel status)' if assignment_pending(prod_st) else 'Unchanged'
                same_count += 1
        elif mtype == 'sla_only':
            sla_only_count += 1
        elif mtype == 'prod_only':
            prod_only_count += 1

    all_transitions = [
        {'from_status': k[0], 'to_status': k[1], 'count': v, 'label': f'{k[0]} ➔ {k[1]}'}
        for k, v in transitions.items()
    ]
    all_transitions.sort(key=lambda t: (t['from_status'].casefold(), t['to_status'].casefold()))

    summary_by_status = {}
    for o in orders:
        st = comparison_summary_status(o)
        if st is None:
            continue
        if st not in summary_by_status:
            summary_by_status[st] = {
                'Status': st,
                'Future SLA': 0,
                'Negative SLA': 0,
                'Today SLA': 0,
                'Unknown SLA': 0,
                'Not in SLA Queue': 0,
                'Grand Total': 0,
            }
        cat = o.get('sla_category')
        if cat in summary_by_status[st]:
            summary_by_status[st][cat] += 1
        else:
            summary_by_status[st]['Unknown SLA'] += 1
        summary_by_status[st]['Grand Total'] += 1

    sla_summary_rows = sorted(summary_by_status.values(), key=lambda x: str(x['Status']).casefold())
    sla_summary_totals = {
        'Status': 'Grand Total',
        'Future SLA': sum(r['Future SLA'] for r in sla_summary_rows),
        'Negative SLA': sum(r['Negative SLA'] for r in sla_summary_rows),
        'Today SLA': sum(r['Today SLA'] for r in sla_summary_rows),
        'Unknown SLA': sum(r['Unknown SLA'] for r in sla_summary_rows),
        'Not in SLA Queue': sum(r['Not in SLA Queue'] for r in sla_summary_rows),
        'Grand Total': sum(r['Grand Total'] for r in sla_summary_rows),
    }

    if 'metrics' not in result:
        result['metrics'] = {}
    result['metrics']['matched'] = matched_count
    result['metrics']['status_moved'] = moved_count
    result['metrics']['same_status'] = same_count
    result['metrics']['sla_only'] = sla_only_count
    result['metrics']['prod_only'] = prod_only_count
    result['transitions'] = all_transitions
    result['sla_summary'] = {
        'columns': ['Status', *COMPARISON_CATEGORIES, *(['Unknown SLA'] if sla_summary_totals['Unknown SLA'] else []), 'Grand Total'],
        'rows': sla_summary_rows,
        'totals': sla_summary_totals,
    }
    return result

def update_order_production_status(result, order_number, new_prod_status, prod_rows=None):
    """Update production status of an order and recalculate summary matrix and metrics."""
    order_number_str = str(order_number).strip()
    norm_new_status = normalize_status(new_prod_status)
    target_key = number_key({'Order Number': order_number_str})

    if prod_rows:
        for r in prod_rows:
            if number_key({'Order Number': r.get('order_number')}) == target_key:
                r['status'] = norm_new_status

    for o in result.get('orders', []):
        if number_key({'Order Number': o.get('order_number')}) == target_key:
            o['prod_status'] = norm_new_status
            o['status_conflict'] = False
            sla_status_str = o.get('sla_status', '')
            if o.get('match_type') in ('status_moved', 'same_status'):
                is_changed = (sla_status_str.casefold() != norm_new_status.casefold()) and bool(sla_status_str and norm_new_status and norm_new_status != 'Not in Production Report')
                o['status_changed'] = is_changed
                if is_changed:
                    o['match_type'] = 'status_moved'
                    o['change_label'] = f"{sla_status_str} ➔ {norm_new_status}"
                else:
                    o['match_type'] = 'same_status'
                    o['change_label'] = 'Unchanged'
            break

    return recalculate_summary(result)

def export_comparison_excel(result, table_scope='all', filter_type=None, sla_status=None, prod_status=None, category=None, from_status=None, to_status=None, search=None, summary_status=None):
    """Generate clean, styled Excel workbooks for the SLA comparison.
    Supports table_scope in ('all', 'sla_summary', 'movements', 'orders').
    """
    export_categories = [*COMPARISON_CATEGORIES, *(['Unknown SLA'] if result.get('sla_summary', {}).get('totals', {}).get('Unknown SLA') else [])]
    export_columns = ['Status', *export_categories, 'Grand Total']
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    header_font = Font(name='Calibri', size=14, bold=True, color='1F2937')
    sub_font = Font(name='Calibri', size=10, color='4B5563')
    bold_font = Font(name='Calibri', size=11, bold=True)
    body_font = Font(name='Calibri', size=11)
    th_fill = PatternFill('solid', fgColor='1E293B')
    th_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
    matrix_hdr_fill = PatternFill('solid', fgColor='0F766E')
    matrix_hdr_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
    tot_fill = PatternFill('solid', fgColor='F1F5F9')
    status_moved_fill = PatternFill('solid', fgColor='FEF3C7')
    same_fill = PatternFill('solid', fgColor='ECFDF5')
    new_order_fill = PatternFill('solid', fgColor='EFF6FF')
    prod_only_fill = PatternFill('solid', fgColor='F5F3FF')

    preview_name = result.get('preview_name', '')
    as_of = result.get('as_of', '')
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    sla_sum = result.get('sla_summary', {})
    transitions = result.get('transitions', [])
    orders = result.get('orders', [])

    # Filter orders if scope is orders or if filters are passed
    def filter_order_list(order_list):
        res = list(order_list)
        if filter_type:
            ft = filter_type.strip().lower()
            if ft in ('status_moved', 'moved'):
                res = [o for o in res if o['match_type'] == 'status_moved']
            elif ft in ('matched', 'both'):
                res = [o for o in res if o['match_type'] in ('status_moved', 'same_status')]
            elif ft in ('same_status', 'same', 'identical'):
                res = [o for o in res if o['match_type'] == 'same_status']
            elif ft in ('sla_only', 'new_orders', 'new'):
                res = [o for o in res if o['match_type'] == 'sla_only']
            elif ft in ('prod_only', 'production_only'):
                res = [o for o in res if o['match_type'] == 'prod_only']
            elif ft in ('queue', 'sla_queue'):
                res = [o for o in res if o['match_type'] != 'prod_only']
            elif ft == 'summary':
                res = [o for o in res if comparison_summary_status(o) is not None]
        if sla_status:
            res = [o for o in res if o['sla_status'] == sla_status]
        if prod_status:
            res = [o for o in res if o['prod_status'] == prod_status]
        if summary_status:
            res = [o for o in res if comparison_summary_status(o) == summary_status]
        if category:
            res = [o for o in res if o['sla_category'] == category]
        if from_status and to_status:
            res = [o for o in res if o['sla_status'] == from_status and o['prod_status'] == to_status]
        if search and search.strip():
            q = search.strip().lower()
            res = [o for o in res if (
                q in str(o.get('order_number', '')).lower() or
                q in str(o.get('sla_status', '')).lower() or
                q in str(o.get('prod_status', '')).lower() or
                q in str(o.get('client', '')).lower() or
                q in str(o.get('county', '')).lower() or
                q in str(o.get('product', '')).lower()
            )]
        return res

    # A paste-ready report, with headers on row 1 and no comparison-only fields.
    if table_scope == 'orders' and (filter_type or '').strip().lower() in ('sla_only', 'new_orders', 'new'):
        ws = wb.active
        ws.title = 'New Orders'
        ws.append(NEW_ORDER_COLUMNS)
        for cell in ws[1]:
            cell.fill = th_fill
            cell.font = th_font
        for order in filter_order_list(orders):
            record = comparison_record(order)
            ws.append([record.get(column, '') for column in NEW_ORDER_COLUMNS])
            for cell in ws[ws.max_row]:
                if isinstance(cell.value, str): cell.data_type = 's'
                cell.font = body_font
                cell.alignment = Alignment(vertical='top', wrap_text=NEW_ORDER_COLUMNS[cell.column-1]=='Comments')
                if NEW_ORDER_COLUMNS[cell.column-1] in ('Date','ETA','Process date','In-Time','Out Time','SLA Expiration') and cell.value:
                    parsed = None
                    for fmt in ('%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y-%m-%d','%m/%d/%Y %I:%M:%S %p','%m/%d/%Y'):
                        try:
                            parsed = datetime.strptime(str(cell.value), fmt)
                            break
                        except ValueError:
                            continue
                    if parsed:
                        cell.value = parsed
                        cell.number_format = 'm/d/yyyy' if NEW_ORDER_COLUMNS[cell.column-1] in ('Date','ETA','Process date') else 'm/d/yyyy h:mm:ss AM/PM'
        ws.freeze_panes = 'A2'
        ws.auto_filter.ref = ws.dimensions
        for index, column in enumerate(NEW_ORDER_COLUMNS, 1):
            ws.column_dimensions[get_column_letter(index)].width = 24 if column in ('Order Number','In-Time','Out Time','SLA Expiration','Comments') else 18
        stream = BytesIO()
        wb.save(stream)
        stream.seek(0)
        return stream

    # 1. Summary and the exact orders counted in its matrix.
    if table_scope == 'sla_summary':
        ws = wb.active
        ws.title = 'SLA Status Summary'
        ws.views.sheetView[0].showGridLines = True

        ws['A1'] = "SLA Status Summary Matrix (SLA Status categories)"
        ws['A1'].font = header_font
        ws['A2'] = f"Preview: {preview_name} | SLA Orders: {result.get('metrics', {}).get('total_sla', 0)} | As of: {as_of} | Exported: {now_str}"
        ws['A2'].font = sub_font

        headers = ['Production Status', *export_categories, 'Grand Total']
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=c_idx, value=h)
            cell.font = matrix_hdr_font
            cell.fill = matrix_hdr_fill
            cell.alignment = Alignment(horizontal='center' if c_idx > 1 else 'left', vertical='center')

        cur_r = 5
        for r in sla_sum.get('rows', []):
            ws.cell(row=cur_r, column=1, value=r['Status']).font = bold_font
            for c_idx, col_name in enumerate([*export_categories, 'Grand Total'], start=2):
                val_cell = ws.cell(row=cur_r, column=c_idx, value=r.get(col_name, 0))
                val_cell.alignment = Alignment(horizontal='right')
                if col_name == 'Grand Total':
                    val_cell.font = bold_font
            cur_r += 1

        tot = sla_sum.get('totals', {})
        if tot:
            ws.cell(row=cur_r, column=1, value='Grand Total').font = bold_font
            for c_idx, col_name in enumerate([*export_categories, 'Grand Total'], start=2):
                tot_cell = ws.cell(row=cur_r, column=c_idx, value=tot.get(col_name, 0))
                tot_cell.font = bold_font
                tot_cell.alignment = Alignment(horizontal='right')
            for c_idx in range(1, len(export_columns) + 1):
                ws.cell(row=cur_r, column=c_idx).fill = tot_fill

        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max(len(str(c.value or '')) for c in col)
            ws.column_dimensions[col_letter].width = max(14, min(36, max_len + 3))

        ws.freeze_panes = 'B5'
        ws.auto_filter.ref = f'A4:{get_column_letter(len(headers))}{cur_r-1}'
        details = wb.create_sheet('Related Orders')
        fields = [('Order Number','order_number'), ('Production Status',None),
                  ('SLA Category','sla_category'), ('SLA Status (Queue)','sla_status'),
                  ('Imported Production Status','imported_prod_status'),
                  ('Status Movement','change_label'), ('Product','product'), ('State','state'),
                  ('County','county'), ('Client','client'), ('SLA Expiration','sla_expiration'),
                  ('In-Time / Received','in_time'), ('Production Out-Time','out_time'),
                  ('Searcher','searcher'), ('Typer','typer'), ('ETA Comments','eta_comments')]
        details.append([label for label,key in fields])
        for cell in details[1]:
            cell.font = matrix_hdr_font
            cell.fill = matrix_hdr_fill
            cell.alignment = Alignment(vertical='center',wrap_text=True)
        for order in orders:
            status = comparison_summary_status(order)
            if status is None: continue
            details.append([status if key is None else order.get(key,'') for label,key in fields])
            for cell in details[details.max_row]:
                if isinstance(cell.value,str): cell.data_type = 's'
                cell.font = body_font
                cell.alignment = Alignment(vertical='top',wrap_text=True)
        details.freeze_panes = 'C2'
        details.auto_filter.ref = details.dimensions
        details.row_dimensions[1].height = 32
        for index,(label,key) in enumerate(fields,1):
            details.column_dimensions[get_column_letter(index)].width = 38 if key=='eta_comments' else 26

    # 2. SCOPE: MOVEMENTS ONLY
    elif table_scope == 'movements':
        ws = wb.active
        ws.title = 'Status Movements'
        ws.views.sheetView[0].showGridLines = True

        ws['A1'] = "Order-wise Status Movements (SLA Status ➔ Production Status)"
        ws['A1'].font = header_font
        ws['A2'] = f"Preview: {preview_name} | Total Status Moved: {result.get('metrics', {}).get('status_moved', 0)} | As of: {as_of} | Exported: {now_str}"
        ws['A2'].font = sub_font

        headers = ['#', 'From (SLA Status)', '➔', 'To (Production Status)', 'Moved Orders', 'Share (%)']
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=c_idx, value=h)
            cell.font = th_font
            cell.fill = th_fill
            cell.alignment = Alignment(horizontal='center' if c_idx in (1, 3, 5, 6) else 'left', vertical='center')

        total_moved = sum(t['count'] for t in transitions) or 1
        cur_r = 5
        for idx, t in enumerate(transitions, start=1):
            pct = (t['count'] / total_moved) * 100.0
            ws.cell(row=cur_r, column=1, value=idx).alignment = Alignment(horizontal='center')
            ws.cell(row=cur_r, column=2, value=t['from_status']).font = body_font
            arrow_c = ws.cell(row=cur_r, column=3, value='➔')
            arrow_c.alignment = Alignment(horizontal='center')
            arrow_c.font = Font(name='Calibri', size=11, bold=True, color='D97706')
            ws.cell(row=cur_r, column=4, value=t['to_status']).font = bold_font
            cnt_c = ws.cell(row=cur_r, column=5, value=t['count'])
            cnt_c.font = bold_font
            cnt_c.alignment = Alignment(horizontal='right')
            pct_c = ws.cell(row=cur_r, column=6, value=f"{pct:.1f}%")
            pct_c.alignment = Alignment(horizontal='right')
            cur_r += 1

        # Totals row
        ws.cell(row=cur_r, column=1, value='Total').font = bold_font
        ws.cell(row=cur_r, column=5, value=sum(t['count'] for t in transitions)).font = bold_font
        ws.cell(row=cur_r, column=5).alignment = Alignment(horizontal='right')
        ws.cell(row=cur_r, column=6, value='100.0%').font = bold_font
        ws.cell(row=cur_r, column=6).alignment = Alignment(horizontal='right')
        for c_idx in range(1, 7):
            ws.cell(row=cur_r, column=c_idx).fill = tot_fill

        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max(len(str(c.value or '')) for c in col)
            ws.column_dimensions[col_letter].width = max(10, min(38, max_len + 3))

    # 3. SCOPE: ORDERS ONLY (OR FILTERED ORDERS)
    elif table_scope == 'orders':
        ws = wb.active
        ws.title = 'Comparison Orders'
        ws.views.sheetView[0].showGridLines = True

        filtered = filter_order_list(orders)
        ws['A1'] = "SLA vs Production Report · Filtered Orders"
        ws['A1'].font = header_font
        ws['A2'] = f"Preview: {preview_name} | Showing {len(filtered)} orders | As of: {as_of} | Exported: {now_str}"
        ws['A2'].font = sub_font

        headers = [
            'Order Number', 'Match Type', 'Status Movement',
            'SLA Status (Queue)', 'SLA Category', 'Production Status', 'SLA Status Expiration',
            'Product', 'State', 'County', 'Client',
            'In-Time / Received', 'Production Out-Time', 'Searcher', 'Typer', 'ETA Comments'
        ]
        for c_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=4, column=c_idx, value=h)
            cell.font = th_font
            cell.fill = th_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')

        cur_r = 5
        for o in filtered:
            m_type = o['match_type']
            m_label = 'New Order (SLA Queue Only)' if m_type == 'sla_only' else (
                'Status Moved / Changed' if m_type == 'status_moved' else (
                    'Identical Status' if m_type == 'same_status' else 'Production Only'
                )
            )
            vals = [
                o['order_number'],
                m_label,
                o['change_label'],
                o['sla_status'],
                o['sla_category'],
                o['prod_status'],
                o.get('sla_expiration', ''),
                o['product'],
                o['state'],
                o['county'],
                o['client'],
                o['in_time'],
                o['out_time'],
                o['searcher'],
                o['typer'],
                o.get('eta_comments', '')
            ]
            for c_idx, v in enumerate(vals, start=1):
                c = ws.cell(row=cur_r, column=c_idx, value=v)
                c.font = body_font
            fill = status_moved_fill if m_type == 'status_moved' else (
                same_fill if m_type == 'same_status' else (
                    new_order_fill if m_type == 'sla_only' else prod_only_fill
                )
            )
            if fill:
                for c_idx in range(1, len(vals) + 1):
                    ws.cell(row=cur_r, column=c_idx).fill = fill
            cur_r += 1

        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max(len(str(c.value or '')) for c in col)
            ws.column_dimensions[col_letter].width = max(12, min(42, max_len + 3))

    # 4. SCOPE: ALL (FULL WORKBOOK)
    else:
        # Sheet 1: Summary & Status Movements
        ws_sum = wb.active
        ws_sum.title = 'Comparison Summary'
        ws_sum.views.sheetView[0].showGridLines = True

        ws_sum['A1'] = "SLA Status vs Production Report Comparison"
        ws_sum['A1'].font = header_font
        ws_sum['A2'] = f"Preview: {preview_name} | As of: {as_of} | Generated: {now_str}"
        ws_sum['A2'].font = sub_font

        # Metrics table
        metrics = result.get('metrics', {})
        metric_rows = [
            ('Total Orders in SLA Queue', metrics.get('total_sla', 0)),
            ('Total Orders in Production Report', metrics.get('total_production', 0)),
            ('Matched Orders (Both)', metrics.get('matched', 0)),
            ('Orders with Status Moved / Changed', metrics.get('status_moved', 0)),
            ('Orders with Identical Status', metrics.get('same_status', 0)),
            ('New Orders (SLA Queue Only)', metrics.get('sla_only', 0)),
            ('Orders in Production Report Only', metrics.get('prod_only', 0)),
        ]

        ws_sum['A4'] = 'Metric'
        ws_sum['B4'] = 'Count'
        ws_sum['A4'].font = bold_font
        ws_sum['B4'].font = bold_font

        for idx, (label, val) in enumerate(metric_rows, start=5):
            ws_sum[f'A{idx}'] = label
            ws_sum[f'B{idx}'] = val
            ws_sum[f'A{idx}'].font = body_font
            ws_sum[f'B{idx}'].font = bold_font
            ws_sum[f'B{idx}'].alignment = Alignment(horizontal='right')
            if 'Moved' in label:
                ws_sum[f'A{idx}'].fill = status_moved_fill
                ws_sum[f'B{idx}'].fill = status_moved_fill

        # Top Transitions table
        ws_sum['D4'] = 'From (SLA Status)'
        ws_sum['E4'] = '➔'
        ws_sum['F4'] = 'To (Production Status)'
        ws_sum['G4'] = 'Moved Orders'
        for col in ('D4', 'E4', 'F4', 'G4'):
            ws_sum[col].font = bold_font

        for idx, t in enumerate(transitions, start=5):
            ws_sum[f'D{idx}'] = t['from_status']
            ws_sum[f'E{idx}'] = '➔'
            ws_sum[f'F{idx}'] = t['to_status']
            ws_sum[f'G{idx}'] = t['count']
            ws_sum[f'D{idx}'].font = body_font
            ws_sum[f'E{idx}'].font = sub_font
            ws_sum[f'F{idx}'].font = bold_font
            ws_sum[f'G{idx}'].font = bold_font
            ws_sum[f'G{idx}'].alignment = Alignment(horizontal='right')

        # SLA Status Summary Matrix Table (Matched Orders)
        sum_start = max(len(metric_rows) + 7, len(transitions) + 7)
        ws_sum[f'A{sum_start}'] = 'SLA Status Summary Matrix (SLA Status categories)'
        ws_sum[f'A{sum_start}'].font = Font(name='Calibri', size=12, bold=True, color='1F2937')

        sla_headers = ['Production Status', *export_categories, 'Grand Total']
        for c_idx, h_name in enumerate(sla_headers, start=1):
            cell = ws_sum.cell(row=sum_start + 1, column=c_idx, value=h_name)
            cell.font = matrix_hdr_font
            cell.fill = matrix_hdr_fill
            cell.alignment = Alignment(horizontal='center' if c_idx > 1 else 'left', vertical='center')

        cur_r = sum_start + 2
        for r_data in sla_sum.get('rows', []):
            ws_sum.cell(row=cur_r, column=1, value=r_data['Status']).font = bold_font
            for c_idx, col_name in enumerate([*export_categories, 'Grand Total'], start=2):
                val_cell = ws_sum.cell(row=cur_r, column=c_idx, value=r_data.get(col_name, 0))
                val_cell.alignment = Alignment(horizontal='right')
                if col_name == 'Grand Total':
                    val_cell.font = bold_font
            cur_r += 1

        # Totals row
        tot = sla_sum.get('totals', {})
        if tot:
            ws_sum.cell(row=cur_r, column=1, value='Grand Total').font = bold_font
            for c_idx, col_name in enumerate([*export_categories, 'Grand Total'], start=2):
                tot_c = ws_sum.cell(row=cur_r, column=c_idx, value=tot.get(col_name, 0))
                tot_c.font = bold_font
                tot_c.alignment = Alignment(horizontal='right')
            for c_idx in range(1, len(export_columns) + 1):
                ws_sum.cell(row=cur_r, column=c_idx).fill = tot_fill

        # Sheet 2: Side-by-Side Orders
        ws_det = wb.create_sheet(title='Side-by-Side Comparison')
        ws_det.views.sheetView[0].showGridLines = True

        columns = [
            'Order Number', 'Match Type', 'Status Movement',
            'SLA Status (Queue)', 'SLA Category', 'Production Status', 'SLA Status Expiration',
            'Product', 'State', 'County', 'Client',
            'In-Time / Received', 'Production Out-Time', 'Searcher', 'Typer'
        ]

        ws_det.append(columns)
        for cell in ws_det[1]:
            cell.fill = th_fill
            cell.font = th_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

        for row_data in orders:
            m_type = row_data['match_type']
            m_label = 'New Order (SLA Queue Only)' if m_type == 'sla_only' else (
                'Status Moved / Changed' if m_type == 'status_moved' else (
                    'Identical Status' if m_type == 'same_status' else 'Production Only'
                )
            )
            row_vals = [
                row_data['order_number'],
                m_label,
                row_data['change_label'],
                row_data['sla_status'],
                row_data['sla_category'],
                row_data['prod_status'],
                row_data.get('sla_expiration', ''),
                row_data['product'],
                row_data['state'],
                row_data['county'],
                row_data['client'],
                row_data['in_time'],
                row_data['out_time'],
                row_data['searcher'],
                row_data['typer'],
                row_data.get('eta_comments', ''),
            ]
            ws_det.append(row_vals)
            cur_row = ws_det[ws_det.max_row]
            fill = status_moved_fill if m_type == 'status_moved' else (
                same_fill if m_type == 'same_status' else (
                    new_order_fill if m_type == 'sla_only' else prod_only_fill
                )
            )
            if fill:
                for c in cur_row:
                    c.fill = fill

        # Set column widths
        for sheet in (ws_sum, ws_det):
            for col in sheet.columns:
                col_letter = get_column_letter(col[0].column)
                max_len = max(len(str(c.value or '')) for c in col)
                sheet.column_dimensions[col_letter].width = max(12, min(40, max_len + 3))

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream
