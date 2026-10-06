from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from cloud_retention import plan, archive, restore, read_tabs


class Book:
    id = 'synthetic-test-workbook'
    def __init__(self):
        self.sheets = [{'properties': {'sheetId': i, 'title': f'__DataTrace_Backup_{i:012x}_0', 'gridProperties': {'rowCount': 2, 'columnCount': 1}},
                        'data': [{'rowData': [{'values': [{'userEnteredValue': {'stringValue': f'QA-{i}'}, 'note': 'keep note'}]}]}]} for i in range(1, 7)]
        self.sheets.append({'properties': {'sheetId': 99, 'title': 'Sheet1', 'gridProperties': {'rowCount': 100, 'columnCount': 5}}})
        self.lost_reply = False
    def worksheet(self, title):
        return SimpleNamespace(get_all_values=lambda: [['Operation', 'Kind', 'Timestamp', '', '', '', 'Reason']] + [[f'{i:012x}', 'fixture', f'2026-09-0{i}T12:00:00', '', '', '', 'Committed'] for i in range(1, 7)])
    def worksheets(self):
        return [SimpleNamespace(id=s['properties']['sheetId'], title=s['properties']['title']) for s in self.sheets]
    def fetch_sheet_metadata(self, params=None):
        if params.get('ranges'):
            names = [name[1:-1] for name in params['ranges']]
            return {'sheets': deepcopy([s for s in self.sheets if s['properties']['title'] in names])}
        return {'sheets': deepcopy(self.sheets)}
    def batch_update(self, body):
        for request in body['requests']:
            if 'deleteSheet' in request:
                self.sheets = [s for s in self.sheets if s['properties']['sheetId'] != request['deleteSheet']['sheetId']]
            if 'addSheet' in request:
                self.sheets.append({'properties': deepcopy(request['addSheet']['properties']), 'data': []})
            if 'updateCells' in request:
                value = request['updateCells']
                target = next(s for s in self.sheets if s['properties']['sheetId'] == value['start']['sheetId'])
                target['data'] = [{'rowData': deepcopy(value['rows'])}]
        if self.lost_reply:
            raise ConnectionError('synthetic lost reply')


class CloudRetentionTests(unittest.TestCase):
    def test_archive_and_restore_preserve_values_notes_and_raw_data(self):
        book = Book()
        expected = read_tabs(book, plan(book)['tabs'])
        with tempfile.TemporaryDirectory() as folder:
            value = archive(book, Path(folder), plan(book)['fingerprint'])
            self.assertEqual(value['archived_tabs'], 1)
            self.assertIn('Sheet1', [s.title for s in book.worksheets()])
            raw = (Path(folder) / value['archive']).read_bytes()
            restore(book, raw)
            self.assertEqual(read_tabs(book, plan(book)['tabs']), expected)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                restore(book, raw)

    def test_disk_failure_or_stale_plan_never_deletes(self):
        book = Book()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'preview changed'):
                archive(book, Path(folder), 'stale')
            with patch('cloud_retention.write_verified_backup', side_effect=OSError('full')):
                with self.assertRaises(OSError):
                    archive(book, Path(folder), plan(book)['fingerprint'])
        self.assertEqual(len(book.worksheets()), 7)

    def test_lost_reply_verified_without_replaying_and_unknown_objects_retained(self):
        book = Book()
        book.sheets[0]['charts'] = [{'chartId': 1}]
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, 'custom objects'):
                archive(book, Path(folder), plan(book)['fingerprint'])
            del book.sheets[0]['charts']
            book.lost_reply = True
            result = archive(book, Path(folder), plan(book)['fingerprint'])
            self.assertEqual(result['archived_tabs'], 1)
            raw = (Path(folder) / result['archive']).read_bytes()
            self.assertEqual(restore(book, raw)['restored_tabs'], 1)
