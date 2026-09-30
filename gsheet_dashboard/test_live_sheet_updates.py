import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from datatrace_sync import report_frames, sync_workbook
from preview_store import PreviewStore
from server import create_app


class LiveSheetUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = PreviewStore(Path(self.folder.name) / 'previews')
        self.preview = self.store.save(pd.DataFrame([{
            'Order Number':'A1','Product':'Full Title','Task Status':'Completed and Delivered',
            'Arrival Time':'09/29/2026 10:00 AM','Out Time':'09/30/2026',
            'SLA Expiration*':'09/29/2026 01:00 PM'}]))

    def test_live_endpoint_reflects_sheet_edits_without_new_capture(self):
        sheets = {}
        for title in ('All Products','Full Title','Remaining Products','Status Report'):
            sheet = Mock(title=title)
            sheets[title] = sheet
        sheets['All Products'].get_all_values.return_value = [['Order Number','Comment'],['A1','Original']]
        sheets['Full Title'].get_all_values.return_value = [
            ['Order Number','Out Time','Free Site'],['A1','09/30/2026','Missed']]
        sheets['Remaining Products'].get_all_values.return_value = [['Order Number','Out Time','Free Site']]
        sheets['Status Report'].get_all_values.return_value = [['Preview'],[self.preview['name']]]
        book = Mock()
        book.worksheet.side_effect = sheets.__getitem__
        client = create_app(self.store.root).test_client()
        with patch('server.target_worksheet', return_value=(book,sheets['All Products'])):
            before = client.get('/api/monthly-orders').json['rows'][0]
            self.assertEqual((before['SLA On Time'],before['SLA Missed']),(0,1))
            sheets['All Products'].get_all_values.return_value = [['Order Number','Comment'],['A1','Edited in Sheet']]
            sheets['Full Title'].get_all_values.return_value = [
                ['Order Number','Out Time','Free Site'],['A1','09/30/2026','OnTime']]
            after = client.get('/api/monthly-orders').json['rows'][0]
            live = client.get('/api/live-sheets').json
        self.assertEqual((after['SLA On Time'],after['SLA Missed']),(1,0))
        self.assertEqual(live['preview_name'],self.preview['name'])
        self.assertEqual(live['sheets']['All Products']['rows'][0]['Comment'],'Edited in Sheet')

    def test_later_sync_preserves_manual_free_site_for_unchanged_out_time(self):
        frame = pd.DataFrame(self.preview['rows'])
        frame.attrs['preview_name'] = self.preview['name']
        titles = ('Sheet1','All Products','Full Title','Remaining Products','Status Report')
        sheets = [Mock(title=title) for title in titles]
        sheets[0].get_all_values.return_value = []
        for sheet in sheets[1:]:
            sheet.get_all_values.return_value = []
        sheets[2].get_all_values.return_value = [
            ['Order Number','Out Time','Free Site'],['A1','09/30/2026','OnTime']]
        book = Mock()
        book.worksheets.return_value = sheets
        with patch('datatrace_sync.target_worksheet', return_value=(book,sheets[0])), \
                patch('datatrace_sync.sync_dataframe', return_value='ok') as upload:
            sync_workbook(frame)
        full_title = upload.call_args_list[2].args[0]
        self.assertEqual(full_title['Free Site'].tolist(), ['OnTime'])


if __name__ == '__main__':
    unittest.main()
