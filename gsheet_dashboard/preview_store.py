"""Durable numbered captures and task-level snapshot comparison."""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

import pandas as pd

IGNORED = {'Sync Timestamp', 'Queue Age Hours', 'Time Since Arrival', 'Task Time in Queue'}
CHANGE_COLUMNS = ['Change', 'Task Key', 'Column', 'Previous Value', 'Latest Value']


class PreviewStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS previews (id INTEGER PRIMARY KEY AUTOINCREMENT, '
                       'created TEXT NOT NULL, source TEXT NOT NULL, columns_json TEXT NOT NULL, rows_json TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.root / 'previews.sqlite', timeout=30)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, frame, source='DataTrace'):
        from datatrace_sync import export_to_excel_and_csv
        frame = frame.copy().fillna('')
        frame.columns = [str(c).strip() for c in frame.columns]
        if frame.empty or frame.columns.duplicated().any() or any(not c for c in frame.columns):
            raise ValueError('The file must contain data and unique, nonblank column names.')
        rows = json.loads(frame.to_json(orient='records', date_format='iso'))
        created = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            cursor = db.execute('INSERT INTO previews(created,source,columns_json,rows_json) VALUES(?,?,?,?)',
                                (created, source, json.dumps(list(frame.columns)), json.dumps(rows)))
            number = cursor.lastrowid
            export_to_excel_and_csv(frame, self.root / f'preview{number}')
        return self.get(number)

    def list(self):
        with self.connect() as db:
            return [{'id': i, 'name': f'preview{i}', 'created': created, 'source': source,
                     'row_count': len(json.loads(rows))} for i, created, source, rows in
                    db.execute('SELECT id,created,source,rows_json FROM previews ORDER BY id DESC')]

    def get(self, number):
        with self.connect() as db:
            record = db.execute('SELECT created,source,columns_json,rows_json FROM previews WHERE id=?', (number,)).fetchone()
        if not record:
            raise KeyError('Preview not found.')
        return {'id': number, 'name': f'preview{number}', 'created': record[0], 'source': record[1],
                'columns': json.loads(record[2]), 'rows': json.loads(record[3])}


def text_value(value):
    return '' if value is None else str(value)


def compare(previous, latest, keys=None, ignore=None):
    ignored = IGNORED if ignore is None else set(ignore)
    columns = [c for c in dict.fromkeys(previous['columns'] + latest['columns']) if c not in ignored]
    old, new = previous['rows'], latest['rows']

    def valid(candidate):
        if not candidate or any(c not in previous['columns'] or c not in latest['columns'] for c in candidate):
            return False
        for rows in (old, new):
            identities = [tuple(text_value(row.get(c)) for c in candidate) for row in rows]
            if any(not any(k) for k in identities) or len(set(identities)) != len(identities):
                return False
        return True

    if keys and not valid(keys):
        raise ValueError('Matching columns must form a unique, nonblank key in both previews. Select additional columns.')
    if not keys:
        keys = next((candidate for candidate in [['OPON'], ['Task ID'],
                    ['Arrival Time', 'Parcel ID', 'Task Name', 'Client', 'Product']] if valid(candidate)), [])
    changes = []
    counts = {'added': 0, 'removed': 0, 'modified': 0, 'unchanged': 0}
    if keys:
        def index(rows):
            return {tuple(text_value(row.get(c)) for c in keys): row for row in rows}
        before, after = index(old), index(new)
        for key in dict.fromkeys(list(before) + list(after)):
            a, b = before.get(key), after.get(key)
            label = ' | '.join(key)
            if a is None or b is None:
                kind = 'Added' if a is None else 'Removed'
                counts[kind.lower()] += 1
                changes.append({'Change': kind, 'Task Key': label, 'Column': '(entire row)',
                                'Previous Value': json.dumps(a, ensure_ascii=False) if a else '',
                                'Latest Value': json.dumps(b, ensure_ascii=False) if b else ''})
            else:
                changed = [c for c in columns if text_value(a.get(c)) != text_value(b.get(c))]
                counts['modified' if changed else 'unchanged'] += 1
                for c in changed:
                    changes.append({'Change': 'Modified', 'Task Key': label, 'Column': c,
                                    'Previous Value': text_value(a.get(c)), 'Latest Value': text_value(b.get(c))})
        method = 'Matched by ' + ', '.join(keys)
    else:
        def fingerprints(rows):
            return Counter(tuple(text_value(row.get(c)) for c in columns) for row in rows)
        before, after = fingerprints(old), fingerprints(new)
        counts['unchanged'] = sum((before & after).values())
        for kind, delta in [('Removed', before - after), ('Added', after - before)]:
            counts[kind.lower()] = sum(delta.values())
            for values, frequency in delta.items():
                for _ in range(frequency):
                    row = json.dumps(dict(zip(columns, values)), ensure_ascii=False)
                    changes.append({'Change': kind, 'Task Key': '(unmatched)', 'Column': '(entire row)',
                                    'Previous Value': row if kind == 'Removed' else '',
                                    'Latest Value': row if kind == 'Added' else ''})
        method = 'No unique task key: exact-row comparison. Updates appear as removed and added rows.'
    return {'columns': CHANGE_COLUMNS, 'rows': changes, 'counts': counts, 'keys': keys, 'method': method,
            'ignored': sorted(ignored), 'previous': previous['name'], 'latest': latest['name'],
            'added_columns': [c for c in latest['columns'] if c not in previous['columns']],
            'removed_columns': [c for c in previous['columns'] if c not in latest['columns']]}
