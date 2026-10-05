"""Read-only batching that preserves worksheet order and formatted cell values."""


def read_values(book, sheets):
    sheets = list(sheets)
    if not sheets:
        return []
    # Legacy adapters and fixture books may only expose worksheet reads.
    if not callable(getattr(type(book), 'values_batch_get', None)):
        return [sheet.get_all_values() for sheet in sheets]
    values = []
    for offset in range(0, len(sheets), 50):
        group = sheets[offset:offset + 50]
        ranges = ["'" + sheet.title.replace("'", "''") + "'" for sheet in group]
        response = book.values_batch_get(ranges, params={'valueRenderOption': 'FORMATTED_VALUE'})
        blocks = response.get('valueRanges') if isinstance(response, dict) else None
        if not isinstance(blocks, list) or len(blocks) != len(group):
            raise RuntimeError('Google Sheets returned an incomplete production read. Refresh to retry.')
        for block in blocks:
            rows = block.get('values', [])
            if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
                raise RuntimeError('Google Sheets returned invalid production values. Refresh to retry.')
            width = max((len(row) for row in rows), default=0)
            values.append([list(row) + [''] * (width - len(row)) for row in rows])
    return values
