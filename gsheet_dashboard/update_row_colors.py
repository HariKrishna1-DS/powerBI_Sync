"""Apply status row colors without changing existing worksheet values."""
import pandas as pd
import sys
from datatrace_sync import target_worksheet, REPORT_SHEETS, status_row_format_request, status_color, sheet_color


def main():
    book, primary = target_worksheet()
    targets = [primary] + [book.worksheet(title) for title, _ in REPORT_SHEETS]
    snapshots = []
    requests = []
    for sheet in targets:
        values = sheet.get_all_values()
        if not values:
            continue
        width = len(values[0])
        frame = pd.DataFrame([row + [''] * (width - len(row)) for row in values[1:]], columns=values[0])
        update = status_row_format_request(frame, sheet.id)
        if update:
            requests.append(update)
            snapshots.append((sheet, frame, values))
    if '--verify-only' not in sys.argv:
        book.batch_update({'requests': requests})
    for sheet, frame, before in snapshots:
        assert sheet.get_all_values() == before, f'Values changed on {sheet.title}'
        from gspread.utils import rowcol_to_a1
        end = rowcol_to_a1(len(frame) + 1, len(frame.columns))
        title = sheet.title.replace("'", "''")
        metadata = book.fetch_sheet_metadata(params={
            'includeGridData': 'true', 'ranges': [f"'{title}'!A2:{end}"],
            'fields': 'sheets(merges,data(rowData(values(userEnteredFormat/backgroundColor))))'})
        grid = metadata['sheets'][0]['data'][0]['rowData']
        merges = metadata['sheets'][0].get('merges', [])
        column = 'Task Status' if 'Task Status' in frame.columns else 'Status'
        for index, status in enumerate(frame[column]):
            expected = sheet_color(status_color(status))
            cells = grid[index]['values']
            assert len(cells) == len(frame.columns), f'Missing cell colors on {sheet.title}'
            for column_index, cell in enumerate(cells):
                # A merged region displays the format of its top-left cell.
                if any(merge['startRowIndex'] <= index + 1 < merge['endRowIndex']
                       and merge['startColumnIndex'] <= column_index < merge['endColumnIndex']
                       and (index + 1, column_index) != (merge['startRowIndex'], merge['startColumnIndex'])
                       for merge in merges):
                    continue
                actual = cell.get('userEnteredFormat', {}).get('backgroundColor', {})
                assert all(abs(actual.get(key, 0) - value) < 0.000001 for key, value in expected.items()), f'Color mismatch on {sheet.title}, row {index + 2}, column {column_index + 1}, status {status}: expected {expected}, actual {actual}'
        print(f'{sheet.title}: verified full-row colors on {len(frame)} rows; values unchanged', flush=True)


if __name__ == '__main__':
    main()
