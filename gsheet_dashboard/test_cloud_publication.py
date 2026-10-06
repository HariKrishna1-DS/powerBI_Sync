from copy import deepcopy
import json
import unittest
import uuid
from requests.exceptions import Timeout
from gspread.exceptions import WorksheetNotFound

from cloud_backend.publication import SheetsPublisher, PROTOCOL, RECEIPT, digest, projection
from shared_backend import CloudError
from sheets_writer import SHARED_ID, SHARED_TITLE
from test_tracker_v2 import Sheet


class ProjectionBook:
    id = 'synthetic-workbook'
    def __init__(self):
        self.sheets, self.batches = [], []
        self.lost_reply = False
        self.fail = False
        self.interrupt_upload = False
    def worksheets(self):
        return self.sheets
    def get_worksheet_by_id(self, number):
        for sheet in self.sheets:
            if sheet.id == number:
                return sheet
        raise WorksheetNotFound(str(number))
    def values_batch_get(self, ranges, params=None):
        titles = [value[1:-1].replace("''", "'") for value in ranges]
        return {'valueRanges': [{'values': deepcopy(next(s.values for s in self.sheets if s.title == title))} for title in titles]}
    def fetch_sheet_metadata(self, params=None):
        return {'sheets': [{'properties': {'sheetId': s.id},
            'conditionalFormats': getattr(s, 'conditional_formats', [])} for s in self.sheets]}
    def batch_update(self, body):
        if self.fail:
            raise Timeout('Synthetic failure before commit')
        working = deepcopy(self.sheets)
        final = any('copyPaste' in request for request in body['requests'])
        if self.interrupt_upload and any('updateCells' in request for request in body['requests']) and not final:
            raise Timeout('Synthetic staging interruption')
        for request in body['requests']:
            def target(number):
                return next(s for s in working if s.id == number)
            if 'addSheet' in request:
                props = request['addSheet']['properties']
                if any(s.id == props['sheetId'] or s.title == props['title'] for s in working):
                    raise ValueError('Duplicate tab')
                working.append(Sheet(props['title'], props['sheetId']))
            elif 'deleteSheet' in request:
                working.remove(target(request['deleteSheet']['sheetId']))
            elif 'updateSheetProperties' in request:
                props = request['updateSheetProperties']['properties']
                sheet = target(props['sheetId'])
                grid = props.get('gridProperties', {})
                sheet.row_count = grid.get('rowCount', sheet.row_count)
                sheet.col_count = grid.get('columnCount', sheet.col_count)
            elif 'copyPaste' in request:
                copy = request['copyPaste']
                source, destination = copy['source'], copy['destination']
                target(destination['sheetId']).values = deepcopy([
                    row[source['startColumnIndex']:source['endColumnIndex']]
                    for row in target(source['sheetId']).values[source['startRowIndex']:source['endRowIndex']]])
            elif 'deleteConditionalFormatRule' in request:
                delete = request['deleteConditionalFormatRule']
                target(delete['sheetId']).conditional_formats.pop(delete['index'])
            elif 'addConditionalFormatRule' in request:
                add = request['addConditionalFormatRule']
                sheet = target(add['rule']['ranges'][0]['sheetId'])
                if not hasattr(sheet, 'conditional_formats'):
                    sheet.conditional_formats = []
                sheet.conditional_formats.insert(add['index'], deepcopy(add['rule']))
            elif 'repeatCell' in request and request['repeatCell']['fields'] == 'userEnteredValue':
                target(request['repeatCell']['range']['sheetId']).values = []
            elif 'updateCells' in request and request['updateCells']['fields'] == 'userEnteredValue':
                update = request['updateCells']
                start = update['start']
                sheet = target(start['sheetId'])
                for number, row in enumerate(update['rows'], start['rowIndex']):
                    while len(sheet.values) <= number:
                        sheet.values.append([])
                    sheet.values[number] = [next(iter(cell.get('userEnteredValue', {}).values()), '') for cell in row['values']]
        self.sheets = working
        self.batches.append(deepcopy(body))
        if self.lost_reply and final:
            self.lost_reply = False
            raise Timeout('Synthetic committed response loss')


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.book = ProjectionBook()
        self.workspace = str(uuid.uuid4())
        self.publisher = SheetsPublisher(self.book, self.workspace, self.book.id)
        self.book.sheets = [Sheet(SHARED_TITLE, SHARED_ID, [['Protocol','Workspace','Spreadsheet'],
            [PROTOCOL,self.workspace,self.book.id]]), Sheet(RECEIPT, 100, [['Receipt'], [json.dumps({
            'workspace':self.workspace,'spreadsheet':self.book.id,'revision':0,'digest':digest({}),'tabs':[]})]]),
            Sheet('Personal notes', 101, [['Keep this']])]
        self.tables = {'All Products': [['Order Number','Status'], ['001','Search In Progress']]}

    def test_lost_reply_and_repeated_revision_write_once_preserve_user_tabs(self):
        self.book.lost_reply = True
        receipt = self.publisher.publish(1, self.tables)
        self.assertEqual(self.publisher.publish(1, self.tables), receipt)
        self.assertEqual(sum(any('copyPaste' in r for r in b['requests']) for b in self.book.batches), 1)
        self.assertEqual(self.book.get_worksheet_by_id(101).values, [['Keep this']])
        self.assertEqual(receipt['revision'], 1)

    def test_direct_sheet_edit_blocks_publication(self):
        self.publisher.publish(1, self.tables)
        count = len(self.book.batches)
        next(s for s in self.book.sheets if s.title == 'All Products').values[1][0] = 'manual'
        with self.assertRaisesRegex(CloudError, 'edited outside'):
            self.publisher.publish(2, self.tables)
        self.assertEqual(len(self.book.batches), count)

    def test_wrong_binding_stale_revision_and_unreviewed_tab_are_rejected(self):
        with self.assertRaises(CloudError):
            SheetsPublisher(self.book, self.workspace, 'another-book')
        with self.assertRaisesRegex(CloudError, 'unreviewed'):
            self.publisher.publish(1, {'Personal notes': [['Replacement']]})
        self.publisher.publish(2, self.tables)
        with self.assertRaises(CloudError):
            self.publisher.publish(1, self.tables)
        with self.assertRaises(CloudError):
            self.publisher.publish(2, {'All Products': [['Changed']]})
        self.book.get_worksheet_by_id(SHARED_ID).values[1][1] = str(uuid.uuid4())
        with self.assertRaises(CloudError):
            self.publisher.publish(3, self.tables)

    def test_precommit_failure_retries_without_acknowledging(self):
        self.book.fail = True
        with self.assertRaises(CloudError):
            self.publisher.publish(1, self.tables)
        self.book.fail = False
        self.assertEqual(self.publisher.publish(1, self.tables)['revision'], 1)

    def test_shorter_snapshot_clears_stale_rows_and_canonical_hash_tolerates_blanks(self):
        self.publisher.publish(1, self.tables)
        self.publisher.publish(2, {'All Products': self.tables['All Products'][:1]})
        sheet = next(s for s in self.book.sheets if s.title == 'All Products')
        self.assertEqual(sheet.values, self.tables['All Products'][:1])
        self.assertEqual(digest({'A':[['a',1.0,''],[]]}), digest({'A':[['a',1]]}))

    def test_projection_keeps_same_tracker_and_monthly_schema(self):
        tables, _ = projection([{'order_key':'001','data':{'Order Number':'001','Product':'Full Title',
            'Status':'Completed and Delivered','In-Time':'10/01/2026 09:00 AM',
            'Out Time':'10/01/2026 10:00 AM','SLA Expiration':'10/01/2026 10:00 AM','Custom':'Preserved'}}], '2026-10-06T12:00:00Z')
        self.assertEqual(tables['Full_search_OCT_2026'][0], tables['TV_Search_Production_Report_Full_Search'][0])
        self.assertIn('Custom', tables['All Products'][0])
        self.assertEqual(tables['Daily Orders'][1][7], 1)

    def test_large_unicode_report_uses_bounded_uploads_and_removes_staging(self):
        rows = [['Order Number', 'Status', 'Comments']] + [
            [str(i), 'Search In Progress', '\u6d4b\u8bd5' * 40] for i in range(7500)]
        receipt = self.publisher.publish(1, {'All Products': rows})
        self.assertEqual(receipt['digest'], digest({'All Products': rows}))
        self.assertTrue(all(len(json.dumps(batch).encode()) < 2_000_000 for batch in self.book.batches))
        self.assertGreater(len(self.book.batches), 4)
        self.assertFalse(any(s.title.startswith('__TvTracker_Stage_') for s in self.book.sheets))
        self.assertEqual(next(s for s in self.book.sheets if s.title == 'All Products').values, rows)

    def test_interrupted_staging_preserves_visible_data_and_retries(self):
        self.publisher.publish(1, self.tables)
        self.book.interrupt_upload = True
        revised = {'All Products': [['Order Number', 'Status'], ['002', 'Available']]}
        with self.assertRaisesRegex(CloudError, 'staging was interrupted'):
            self.publisher.publish(2, revised)
        self.assertEqual(self.publisher._receipt()['revision'], 1)
        self.assertEqual(next(s for s in self.book.sheets if s.title == 'All Products').values, self.tables['All Products'])
        self.book.interrupt_upload = False
        self.assertEqual(self.publisher.publish(2, revised)['revision'], 2)
        self.assertFalse(any(s.title.startswith('__TvTracker_Stage_') for s in self.book.sheets))
