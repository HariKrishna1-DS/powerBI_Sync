"""Update existing product-tab date and SLA cells without replacing other columns."""
import argparse
import json
from pathlib import Path
import tempfile

from datatrace_sync import parse_report_datetime, sla_expiration, sla_result, sheet_cell, target_worksheet


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    book, _ = target_worksheet()
    requests, backups, checks = [], {}, []
    for title in ('Full Title', 'Remaining Products'):
        sheet = book.worksheet(title)
        values = sheet.get_all_values()
        if not values:
            continue
        backups[title] = values
        headers = values[0]
        for row_index, cells in enumerate(values[1:], start=1):
            row = dict(zip(headers, cells))
            if not str(row.get('Order Number', '')).strip():
                continue
            updates = {'Free Site': sla_result(row)}
            for column in ('Date', 'In-Time', 'Out Time', 'Process date'):
                parsed = parse_report_datetime(row.get(column, ''))
                if parsed:
                    updates[column] = parsed.strftime('%m/%d/%Y')
            expiration = sla_expiration(row)
            if expiration:
                updates['SLA Expiration'] = expiration.strftime('%m/%d/%Y %I:%M %p')
            for column, value in updates.items():
                if column not in headers or value == row.get(column, ''):
                    continue
                column_index = headers.index(column)
                requests.append({'updateCells': {
                    'start': {'sheetId': sheet.id, 'rowIndex': row_index, 'columnIndex': column_index},
                    'rows': [{'values': [sheet_cell(value)]}], 'fields': 'userEnteredValue'}})
                checks.append((title, row_index, column_index, value))
    print(f'{len(requests)} cells to update across {len(backups)} tabs.', flush=True)
    if args.apply and requests:
        folder = Path(tempfile.mkdtemp(prefix='datatrace-sla-backup-'))
        backup = folder / 'product-tabs.json'
        backup.write_text(json.dumps(backups), encoding='utf-8')
        print(f'Backup: {backup}', flush=True)
        book.batch_update({'requests': requests})
        actual = {title: book.worksheet(title).get_all_values() for title in backups}
        for title, row_index, column_index, value in checks:
            cells = actual[title][row_index]
            received = cells[column_index] if column_index < len(cells) else ''
            if received != value:
                raise RuntimeError(f'Verification failed: {title}, row {row_index + 1}, column {column_index + 1}')
        print('Updated and verified all changed cells.', flush=True)


if __name__ == '__main__':
    main()
