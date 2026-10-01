import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from datatrace_sync import sync_workbook
from order_reporting import monthly_orders
from preview_store import PreviewStore
from server import create_app


class SlaCommentsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = PreviewStore(Path(self.folder.name) / 'previews')
        self.rows = [dict(zip(
            ['Order Number', 'Product', 'Arrival Time', 'Out Time', 'SLA Expiration*', 'Task Status'],
            [identity, product, '09/30/2026 09:00 AM', '09/30/2026', sla, 'Completed and Delivered']))
            for identity, product, sla in [('001', 'Full Title', '-2h'), ('002', 'Update', '6h'), ('003', 'Full Title', '-1h')]]
        self.preview = self.store.save(pd.DataFrame(self.rows))
        header = ['Order Number', 'Product', 'In-Time', 'Out Time', 'SLA Expiration', 'Free Site']
        self.values = {
            'Full Title': [header.copy(), ['001', 'Full Title', '09/30/2026', '09/30/2026', '-2h', 'Missed']],
            'Remaining Products': [header.copy(), ['002', 'Update', '09/30/2026', '09/30/2026', '6h', 'OnTime']],
        }
        self.book = Mock()
        self.book.worksheet.side_effect = lambda title: Mock(get_all_values=Mock(side_effect=lambda: self.values[title]))

        def cell(address):
            match = re.fullmatch(r"'([^']+)'!F(\d+)", address)
            self.assertIsNotNone(match, address)
            return self.values[match[1]][int(match[2]) - 1]

        def write(body):
            self.assertEqual(body['valueInputOption'], 'RAW')
            for update in body['data']:
                cell(update['range'])[5] = update['values'][0][0]

        self.book.values_batch_update.side_effect = write
        self.book.values_batch_get.side_effect = lambda ranges: {'valueRanges': [{'values': [[cell(address)[5]]]} for address in ranges]}
        self.target = patch('server.target_worksheet', return_value=(self.book, Mock()))
        self.target.start()
        self.addCleanup(self.target.stop)
        self.client = create_app(self.store.root).test_client()

    def save(self, identity='001', status='On Time', expected='Missed', **extra):
        return self.client.post('/api/sla-comments', json=dict(
            order_number=identity, completion_date='2026-09-30', status=status, expected_status=expected, **extra))

    def report(self):
        return self.client.get('/api/monthly-orders').json['rows'][0]

    def test_details_match_totals_and_both_product_groups(self):
        report = self.report()
        self.assertEqual(len(report['sla_rows']), report['SLA On Time'] + report['SLA Missed'])
        self.assertEqual((report['SLA On Time'], report['SLA Missed']), (1, 2))
        by_id = {row['Order Number']: row for row in report['sla_rows']}
        self.assertEqual(by_id['001']['Product Group'], 'Full Title')
        self.assertEqual(by_id['002']['Product Group'], 'Remaining Products')
        self.assertEqual(by_id['003']['source'], 'Saved history')
        self.assertEqual(by_id['003']['In Time'], '09/30/2026 09:00 AM')
        self.assertEqual(by_id['001']['SLA Expiration'], '-2h')

    def test_both_directions_update_exact_cells_totals_and_persist(self):
        before = self.store.get(self.preview['id'])
        result = self.save()
        self.assertEqual(result.status_code, 200, result.json)
        self.assertEqual(self.values['Full Title'][1][-1], 'On Time')
        report = result.json['rows'][0]
        self.assertEqual((report['SLA On Time'], report['SLA Missed']), (2, 1))
        self.assertEqual(self.book.values_batch_update.call_args.args[0]['data'], [
            {'range': "'Full Title'!F2", 'values': [['On Time']]}])
        result = self.save('002', 'Missed', 'On Time')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.values['Remaining Products'][1][-1], 'Missed')
        self.assertEqual(self.report()['SLA On Time'], 1)
        reopened = PreviewStore(self.store.root)
        self.assertEqual(reopened.sla_corrections(), {('001', '2026-09-30'): 'On Time', ('002', '2026-09-30'): 'Missed'})
        self.assertEqual(reopened.get(self.preview['id']), before)
        with patch('server.target_worksheet', side_effect=RuntimeError('offline')):
            fallback = self.report()
        self.assertEqual((fallback['SLA On Time'], fallback['SLA Missed']), (1, 2))

    def test_historical_order_can_be_edited_without_finding_preview(self):
        response = self.save('003')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn('not in the current Google Sheet', response.json['message'])
        self.book.values_batch_update.assert_not_called()
        self.assertEqual(self.report()['SLA On Time'], 2)
        self.assertEqual(self.store.sla_corrections()[('003', '2026-09-30')], 'On Time')

    def test_unknown_or_moved_order_and_invalid_input_do_not_write(self):
        self.assertEqual(self.save('unknown').status_code, 409)
        for body in (None, [], {'order_number': '001'}, {'order_number': '001', 'completion_date': '2026-99-30',
                        'status': 'On Time', 'expected_status': 'Missed'}):
            self.assertEqual(self.client.post('/api/sla-comments', json=body).status_code, 422)
        self.assertEqual(self.save(status='Anything').status_code, 422)
        self.values['Full Title'][1][3] = '10/01/2026'
        self.assertEqual(self.save().status_code, 409)
        self.book.values_batch_update.assert_not_called()
        self.assertEqual(self.store.sla_corrections(), {})

    def test_write_failure_keeps_database_unchanged_and_releases_lock(self):
        write = self.book.values_batch_update.side_effect
        self.book.values_batch_update.side_effect = RuntimeError('Google failed')
        self.assertEqual(self.save().status_code, 502)
        self.assertEqual(self.store.sla_corrections(), {})
        self.book.values_batch_update.side_effect = write
        self.assertEqual(self.save().status_code, 200)

    def test_unconfirmed_write_does_not_report_success(self):
        self.book.values_batch_get.side_effect = lambda ranges: {'valueRanges': [{'values': [['Missed']]}]}
        response = self.save()
        self.assertEqual(response.status_code, 502)
        self.assertIn('could not be confirmed', response.json['error'])
        self.assertEqual(self.store.sla_corrections(), {})

    def test_database_failure_after_sheet_write_is_retryable(self):
        with patch.object(PreviewStore, 'save_sla_correction', side_effect=RuntimeError('Database failed')):
            response = self.save()
        self.assertEqual(response.status_code, 503)
        self.assertIn('Google Sheets was updated', response.json['error'])
        self.assertEqual(self.save().status_code, 200)
        self.assertEqual(self.store.sla_corrections()[('001', '2026-09-30')], 'On Time')

    def test_live_sheet_changes_and_blanks_remain_authoritative(self):
        self.save()
        self.values['Full Title'][1][-1] = 'Missed'
        self.assertEqual(self.report()['SLA Missed'], 2)
        self.values['Full Title'][1][-1] = ''
        self.assertNotIn('001', [row['Order Number'] for row in self.report()['sla_rows']])

    def test_edits_blocked_during_sync_and_cross_origin_writes(self):
        entered, release, finished = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def syncer(frame):
            entered.set()
            release.wait(5)
            finished.set()
            return ['Sheet1']

        client = create_app(self.store.root, syncer=syncer).test_client()
        client.post('/api/sync', json={'preview': self.preview['id']})
        try:
            self.assertTrue(entered.wait(3))
            response = client.post('/api/sla-comments', json={'order_number': '001', 'completion_date': '2026-09-30',
                                   'status': 'On Time', 'expected_status': 'Missed'})
            self.assertEqual(response.status_code, 409)
        finally:
            release.set()
            finished.wait(3)
        self.assertEqual(client.post('/api/sla-comments', json={}, headers={'Origin': 'https://elsewhere.test'}).status_code, 403)
        self.book.values_batch_update.assert_not_called()

    def test_saved_correction_applies_to_next_sync_without_changing_other_completion(self):
        frame = pd.DataFrame(self.rows)
        frame.attrs['sla_corrections'] = {('001', '2026-09-30'): 'On Time', ('002', '2026-09-29'): 'Missed'}
        sheets = [Mock(title=title) for title in ('Sheet1', 'All Products', 'Full Title', 'Remaining Products', 'Status Report')]
        for sheet in sheets:
            sheet.get_all_values.return_value = []
        book = Mock()
        book.worksheets.return_value = sheets
        with patch('datatrace_sync.target_worksheet', return_value=(book, sheets[0])), \
                patch('datatrace_sync.sync_dataframe', return_value='ok') as upload:
            sync_workbook(frame)
        full = upload.call_args_list[2].args[0].set_index('Order Number')
        remaining = upload.call_args_list[3].args[0].set_index('Order Number')
        self.assertEqual(full.loc['001', 'Free Site'], 'On Time')
        self.assertEqual(full.loc['003', 'Free Site'], 'Missed')
        self.assertEqual(remaining.loc['002', 'Free Site'], 'On Time')

    def test_repeated_snapshots_have_one_detail_row_per_counted_order(self):
        self.store.save(pd.DataFrame(self.rows))
        report = monthly_orders(self.store)[0]
        self.assertEqual(len(report['sla_rows']), 3)
        self.assertEqual(report['SLA On Time'] + report['SLA Missed'], 3)


if __name__ == '__main__':
    unittest.main()
