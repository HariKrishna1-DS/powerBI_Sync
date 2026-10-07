"""Apply the October tracker presentation/column update without changing history."""
from collections import Counter
from datetime import datetime
import json

from tracker_sync import (BASE, IST, TRACKERS, EMPTY_COLUMNS, STATUS_NAMES, text, records,
                          key, free_site, timestamp, sync_lock, read_pass_report, sheet_reports)
from tracker_formatting import ensure_tracker_formatting


def refresh_production_trackers(book, backup=True):
    from datatrace_sync import sheet_cell, write_sheet_batch
    with sync_lock():
        sheets = {s.title: s for s in book.worksheets()}
        titles = [*TRACKERS, 'Status Report', 'Daily Orders', 'Monthly report']
        before = {title: sheets[title].get_all_values() for title in titles if title in sheets}
        metadata = book.fetch_sheet_metadata(params={'fields': 'sheets(properties,conditionalFormats)'})
        if backup:
            path = BASE / 'previews' / f'tracker-before-formatting-{datetime.now().strftime("%Y%m%d-%H%M%S")}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'values': before, 'metadata': metadata}, ensure_ascii=False), encoding='utf-8')
        audit = read_pass_report(book)
        # Relative SLAs already become absolute at capture time during sync.
        # A legacy relative value has no reliable reference here; leave it blank.
        anchor = datetime.fromisoformat(audit['timestamp']) if audit.get('timestamp') else datetime.now(IST).replace(tzinfo=None)
        requests, trackers, summary = [], {}, {}
        for title in TRACKERS:
            values = before[title]
            headers = values[0]
            rows = records(values)
            cleared = Counter()
            ambiguous = 0
            for i, row in enumerate(rows, 1):
                desired = {column: '' for column in EMPTY_COLUMNS if column in headers}
                desired['Status'] = STATUS_NAMES.get(text(row.get('Status')).casefold(), row.get('Status', ''))
                raw_sla = text(row.get('SLA Expiration'))
                if raw_sla and not timestamp(raw_sla) and any(unit in raw_sla.lower() for unit in ('d', 'h', 'm')):
                    desired['Free Site'] = ''
                    ambiguous += bool(text(row.get('Out Time')))
                else:
                    desired['Free Site'], reason = free_site(row, anchor)
                    ambiguous += bool(reason)
                for column, val in desired.items():
                    if column not in headers:
                        continue
                    if text(row.get(column)) != text(val):
                        requests.append({'updateCells': {'start': {'sheetId': sheets[title].id, 'rowIndex': i,
                            'columnIndex': headers.index(column)}, 'rows': [{'values': [sheet_cell(val)]}],
                            'fields': 'userEnteredValue'}})
                        if column in EMPTY_COLUMNS:
                            cleared[column] += 1
                    row[column] = val
            trackers[title] = rows
            summary[title] = {'orders': sum(bool(key(r)) for r in rows), 'cleared': dict(cleared),
                'free_site': dict(Counter(r.get('Free Site', '') for r in rows)), 'sla_needs_review': ambiguous}
        def write_report(title, values):
            target = sheets.get(title) or book.add_worksheet(title=title, rows=max(2, len(values)), cols=len(values[0]))
            requests.append({'updateSheetProperties': {'properties': {'sheetId': target.id,
                'gridProperties': {'rowCount': max(target.row_count, len(values)), 'columnCount': max(target.col_count, len(values[0]))}},
                'fields': 'gridProperties.rowCount,gridProperties.columnCount'}})
            requests.append({'updateCells': {'range': {'sheetId': target.id, 'startRowIndex': 0,
                'endRowIndex': max(len(values), len(before.get(title, []))), 'startColumnIndex': 0,
                'endColumnIndex': len(values[0])}, 'rows': [{'values': [sheet_cell(v) for v in row]} for row in values],
                'fields': 'userEnteredValue'}})
        all_rows = [r for rows in trackers.values() for r in rows if key(r)]
        counts = Counter(text(r.get('Status')) or '(Blank)' for r in all_rows)
        write_report('Status Report', [['Status', 'Orders', 'Share', 'Preview', 'Sync Date & Time']] +
            [[status, count, count / len(all_rows) if all_rows else 0, audit.get('preview_name', ''), audit.get('timestamp', '')]
             for status, count in counts.most_common()])
        reports = sheet_reports(trackers, audit)
        for title, kind, period in (('Monthly report', 'monthly', 'Month'),):
            columns = [period, 'Today Orders' if kind == 'daily' else 'Month Orders', 'Completed Orders',
                       'Awaiting for Clarification', 'Not in latest preview', 'SLA On Time', 'SLA Missed']
            write_report(title, [columns] + [[row[c] for c in columns] for row in reports[kind]])
        write_sheet_batch(book, sheets[TRACKERS[0]], requests)
        ensure_tracker_formatting(book)
        for title in TRACKERS:
            actual = records(sheets[title].get_all_values())
            if [key(r) for r in actual] != [key(r) for r in trackers[title]]:
                raise RuntimeError(f'Order identities or row order changed in {title}')
            if any(text(r.get(c)) for r in actual for c in EMPTY_COLUMNS):
                raise RuntimeError(f'Comments or Assignee readback was not empty in {title}')
            if [r.get('Free Site', '') for r in actual] != [r.get('Free Site', '') for r in trackers[title]]:
                raise RuntimeError(f'Free Site readback mismatch in {title}')
        return summary


if __name__ == '__main__':
    from datatrace_sync import target_worksheet
    book, _ = target_worksheet()
    print(json.dumps(refresh_production_trackers(book), indent=2))
