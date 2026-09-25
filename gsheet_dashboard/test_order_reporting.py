from io import BytesIO
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock

import pandas as pd

from datatrace_sync import retain_completed_orders, status_color
from order_reporting import automatic_sync_frame, daily_orders
from preview_store import PreviewStore
from server import create_app


class OrderReportingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = PreviewStore(Path(self.folder.name) / 'previews')
        self.before = self.store.save(pd.DataFrame([
            {'Order Number':'001', 'Task Status':'Workflow Suspended', 'Product':'Full Title'},
            {'Order Number':'002', 'Task Status':'Available', 'Product':'Full Title'},
            {'Order Number':'003', 'Task Status':'Task Suspended', 'Product':'Current Owner'},
        ]))
        self.after = self.store.save(pd.DataFrame([
            {'Order Number':'001', 'Task Status':'Workflow Suspended', 'Product':'Full Title'},
            {'Order Number':'002', 'Task Status':'Available', 'Product':'Full Title'},
            {'Order Number':'004', 'Task Status':'In Progress', 'Product':'Current Owner'},
        ]))

    def test_automatic_statuses_include_missing_and_new_orders(self):
        frame, completed = automatic_sync_frame(self.after, self.before)
        self.assertEqual(completed, ['003', '004'])
        self.assertEqual(dict(zip(frame['Order Number'], frame['Task Status'])), {
            '001':'Awaiting for Clarification', '002':'Available',
            '003':'Completed and Delivered', '004':'Completed and Delivered'})
        self.assertEqual(self.store.get(self.after['id'])['rows'][0]['Task Status'], 'Workflow Suspended')
        self.assertEqual(status_color('Completed and Delivered'), '#fff2cc')

    def test_first_capture_does_not_complete_every_order(self):
        frame, completed = automatic_sync_frame(self.before)
        self.assertEqual(completed, [])
        self.assertEqual(frame.iloc[0]['Task Status'], 'Awaiting for Clarification')
        self.assertEqual(frame.iloc[1]['Task Status'], 'Available')

    def test_daily_counts_use_previous_capture_without_first_capture_invention(self):
        rows = daily_orders(self.store)
        self.assertEqual(rows[0]['Total Orders'], 3)
        self.assertEqual(rows[0]['Missing (Completed Orders)'], 1)
        self.assertEqual(rows[0]['Unchanged'], 2)
        self.assertEqual(rows[0]['Newly Added'], 1)
        self.assertIsNone(rows[1]['Unchanged'])

    def test_retained_completion_is_idempotent_and_matches_whole_order_number(self):
        incoming = pd.DataFrame([{'Order Number':'001','Task Status':'Available'},
                                 {'Order Number':'01','Task Status':'Available'}])
        existing = [['Order Number','Task Status'], ['001','Completed and Delivered'],
                    ['003','Completed and Delivered'], ['099','Available']]
        result = retain_completed_orders(incoming, existing)
        self.assertEqual(result['Order Number'].tolist(), ['001', '01', '003'])
        self.assertEqual(result['Task Status'].tolist(), ['Completed and Delivered','Available','Completed and Delivered'])
        repeated = retain_completed_orders(incoming, [list(result.columns)] + result.values.tolist())
        pd.testing.assert_frame_equal(result, repeated)

    def test_api_sync_uses_comparison_and_ignores_legacy_browser_rules(self):
        syncer = Mock(return_value=['Sheet1'])
        client = create_app(self.store.root, syncer=syncer).test_client()
        self.assertTrue(client.get('/api/state').json['capabilities']['automatic_statuses'])
        self.assertEqual(len(client.get('/api/daily-orders').json['rows']), 2)
        result = client.post('/api/sync', json={'preview':self.after['id'], 'previous':self.before['id'],
                                              'status_rules':[{'source':'Available','target':'Wrong'}]})
        self.assertEqual(result.status_code, 202)
        for _ in range(200):
            state = client.get('/api/state').json['job']
            if not state['running']:
                break
            time.sleep(.01)
        self.assertEqual(state['result']['completed_orders'], 2)
        frame = syncer.call_args.args[0]
        self.assertEqual(len(frame), 4)
        self.assertEqual(frame.loc[frame['Order Number']=='002','Task Status'].iloc[0], 'Available')
        self.assertEqual(client.post('/api/sync', json={'preview':1,'previous':2}).status_code, 422)

    def test_no_order_identity_fails_before_writing(self):
        latest = {**self.after, 'columns':['Task Status'], 'rows':[{'Task Status':'Available'}]}
        with self.assertRaisesRegex(ValueError, 'Order Number'):
            automatic_sync_frame(latest, self.before)
