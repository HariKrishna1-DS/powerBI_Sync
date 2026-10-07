"""Shared production row formatting, including Free Site cells."""
import json
from pathlib import Path

PALETTE = json.loads(Path(__file__).with_name('status_colors.json').read_text(encoding='utf-8'))
MARKER = 'DataTrace production formatting v3'


def foreground(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return '#111827' if (r * 299 + g * 587 + b * 114) / 1000 > 155 else '#ffffff'


def rules_for(sheet_id, headers, row_count=None):
    from gspread.utils import rowcol_to_a1
    from datatrace_sync import sheet_color
    rules = []
    status_header = next((column for column in ('Status', 'Task Status') if column in headers), None)
    if status_header is None:
        return rules
    status_col = rowcol_to_a1(1, headers.index(status_header) + 1)[:-1]
    def rule(ranges, expression, color):
        return {'ranges': ranges, 'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA', 'values': [{'userEnteredValue':
                f'=AND(N("{MARKER}")=0,{expression})'}]},
            'format': {'backgroundColor': sheet_color(color),
                       'textFormat': {'foregroundColor': sheet_color(foreground(color))}}}}
    ranges = [{'sheetId': sheet_id, 'startRowIndex': 1, 'startColumnIndex': 0,
               'endColumnIndex': len(headers)}]
    if row_count is not None:
        if row_count <= 1:
            return []
        ranges[0]['endRowIndex'] = row_count
    for status, color in PALETTE.items():
        rules.append(rule(ranges, f'LOWER(TRIM(${status_col}2))="{status}"', color))
    return rules


def format_requests(sheet_id, values, existing_rules=(), replace_rules=False):
    """Style app-owned output while preserving unrelated conditional rules."""
    from monthly_production import plain_format
    headers = values[0] if values else []
    requests = [{'deleteConditionalFormatRule': {'sheetId': sheet_id, 'index': i}}
                for i in reversed(range(len(existing_rules))) if replace_rules or MARKER in json.dumps(existing_rules[i])]
    requests.extend(plain_format(sheet_id, len(values), len(headers)))
    requests.extend({'addConditionalFormatRule': {'index': i, 'rule': rule}}
                    for i, rule in enumerate(rules_for(sheet_id, headers, len(values))))
    return requests


def comparable_rule(rule, row_count=None):
    """Sheets adds resolved range bounds, color styles and rounded RGB values."""
    ranges = [dict(region) for region in rule['ranges']]
    for region in ranges:
        if row_count is not None and region.get('endRowIndex', row_count) >= row_count:
            region.pop('endRowIndex', None)
    fmt = rule['booleanRule']['format']
    def rgb(color):
        return tuple(round(color.get(channel, 0), 6) for channel in ('red', 'green', 'blue'))
    return (ranges, rule['booleanRule']['condition'], rgb(fmt.get('backgroundColor', {})),
            rgb(fmt.get('textFormat', {}).get('foregroundColor', {})))


def ensure_tracker_formatting(book, attempt=0):
    """Reconcile owned rules; rereading makes recovery safe after a lost reply.

    Open-ended ranges cover future rows and respond to manual Status edits.
    Existing unrelated conditional rules, borders and number formats are kept.
    """
    from tracker_sync import TRACKERS
    from datatrace_sync import sheet_color
    from monthly_production import tab_identity
    from monthly_views import view_identity
    meta = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats)'})
    requests = []
    for item in meta['sheets']:
        props = item['properties']
        if props['title'] not in (*TRACKERS, 'Status Report', 'All Products', 'Sheet1') and not tab_identity(props['title']) and not view_identity(props['title']):
            continue
        values = book.worksheet(props['title']).get_all_values()
        if not values or not any(column in values[0] for column in ('Status', 'Task Status')):
            continue
        rules = item.get('conditionalFormats', [])
        owned = [i for i, rule in enumerate(rules) if MARKER in json.dumps(rule)]
        wanted = rules_for(props['sheetId'], values[0])
        row_count = props.get('gridProperties', {}).get('rowCount')
        if ([comparable_rule(rules[i], row_count) for i in owned] ==
                [comparable_rule(rule, row_count) for rule in wanted]
                and owned == list(range(len(wanted)))):
            continue
        for i in reversed(owned):
            requests.append({'deleteConditionalFormatRule': {'sheetId': props['sheetId'], 'index': i}})
        # Remove old static status and SLA fills, including font colors; then
        # conditional rules determine the visible row color.
        requests.append({'repeatCell': {'range': {'sheetId': props['sheetId'], 'startRowIndex': 1,
            'startColumnIndex': 0, 'endColumnIndex': len(values[0])},
            'cell': {'userEnteredFormat': {'backgroundColor': sheet_color('#ffffff'),
                     'textFormat': {'foregroundColor': sheet_color('#111827')}}},
            'fields': 'userEnteredFormat.backgroundColor,userEnteredFormat.textFormat.foregroundColor'}})
        for i, rule in enumerate(wanted):
            requests.append({'addConditionalFormatRule': {'index': i, 'rule': rule}})
    if requests:
        # Do not retry a precomputed list of add/delete rule requests: on the
        # next attempt reconcile against fresh metadata instead.
        try:
            book.batch_update({'requests': requests})
        except Exception as exc:
            from requests.exceptions import Timeout, ConnectionError
            from gspread.exceptions import APIError
            import time
            transient = isinstance(exc, (Timeout, ConnectionError)) or (isinstance(exc, APIError) and exc.code in (429, 500, 502, 503, 504))
            if not transient or attempt >= 2:
                raise
            time.sleep(2 ** attempt)
            return ensure_tracker_formatting(book, attempt+1)
    return len(requests)
