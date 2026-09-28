from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import pandas as pd

from datatrace_sync import retain_completed_orders, status_color, apply_status_rules
from order_reporting import automatic_sync_frame, daily_orders, completion_history
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

    def test_automatic_statuses_complete_only_missing_orders(self):
        frame, completed = automatic_sync_frame(self.after, self.before)
        self.assertEqual(completed, ['003'])
        self.assertEqual(dict(zip(frame['Order Number'], frame['Task Status'])), {
            '001':'Awaiting for Clarification', '002':'Available',
            '003':'Completed and Delivered', '004':'In Progress'})
        self.assertEqual(self.store.get(self.after['id'])['rows'][0]['Task Status'], 'Workflow Suspended')
        self.assertEqual(status_color('Completed and Delivered'), '#fff2cc')

    def test_first_capture_does_not_complete_every_order(self):
        frame, completed = automatic_sync_frame(self.before)
        self.assertEqual(completed, [])
        self.assertEqual(frame.iloc[0]['Task Status'], 'Awaiting for Clarification')
        self.assertEqual(frame.iloc[1]['Task Status'], 'Available')

    def test_daily_counts_use_all_captures_and_unique_order_numbers(self):
        rows = daily_orders(self.store)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Today Orders'], 4)
        self.assertEqual(rows[0]['Missing (Completed Orders)'], 1)
        self.assertEqual(rows[0]['Unchanged'], 2)
        self.assertEqual(rows[0]['Newly Orders'], 1)
        self.assertEqual(rows[0]['Previews'], ['preview1', 'preview2'])

    def test_daily_duplicates_reappearance_and_dates(self):
        captures = []
        for number, (created, ids) in enumerate([
            ('2026-09-24T10:00:00+05:30', ['old']),
            ('2026-09-25T10:00:00+05:30', ['a', 'a', 'b']),
            ('2026-09-25T11:00:00+05:30', ['b', 'c', 'd']),
            ('2026-09-25T12:00:00+05:30', ['a', 'b', 'c']),
        ], 1):
            captures.append({'id':number, 'name':f'preview{number}', 'created':created,
                             'columns':['Order Number','Task Status'],
                             'rows':[{'Order Number':identity,'Task Status':'Available'} for identity in ids]})
        store = Mock()
        store.list.return_value = list(reversed(captures))
        store.get.side_effect = lambda number: captures[number-1]
        days = daily_orders(store)
        self.assertEqual(len(days), 2)
        self.assertEqual(days[0]['Today Orders'], 4)
        self.assertEqual(days[0]['missing_ids'], ['d'])
        self.assertEqual(days[0]['new_ids'], ['c', 'd'])
        self.assertEqual(days[0]['unchanged_ids'], ['b'])
        self.assertEqual(days[1]['Newly Orders'], 0)
        self.assertEqual(days[1]['Missing (Completed Orders)'], 0)
        self.assertEqual(days[1]['Unchanged'], 1)

    def test_available_task_statuses_and_downloads(self):
        frame = pd.DataFrame([
            {'Order Number':'1','Task Name':'Search','Task Status':'Available'},
            {'Order Number':'2','Task Name':'TypingModule','Task Status':'Available'},
            {'Order Number':'3','Task Name':'Typing Module','Task Status':'Task Suspended'},
            {'Order Number':'4','Task Name':'Other','Task Status':'Available'},
            {'Order Number':'5','Task Name':'Search','Task Status':'Completed and Delivered'},
        ])
        expected = ['Search In Progress','Typing is Progress','Task Suspended','Available','Completed and Delivered']
        self.assertEqual(apply_status_rules(frame, [])['Task Status'].tolist(), expected)
        preview = self.store.save(frame)
        client = create_app(self.store.root).test_client()
        for kind in ('csv','xlsx'):
            response = client.get(f"/api/previews/{preview['id']}/download/{kind}")
            self.assertEqual(response.status_code, 200)
            data = BytesIO(response.data)
            exported = pd.read_excel(data) if kind == 'xlsx' else pd.read_csv(data)
            self.assertEqual(exported['Task Status'].tolist(), expected)

    def test_retained_completion_is_idempotent_and_matches_whole_order_number(self):
        incoming = pd.DataFrame([{'Order Number':'001','Task Status':'Available'},
                                 {'Order Number':'01','Task Status':'Available'}])
        existing = [['Order Number','Task Status'], ['001','Completed and Delivered'],
                    ['003','Completed and Delivered'], ['099','Available']]
        result = retain_completed_orders(incoming, existing)
        self.assertEqual(result['Order Number'].tolist(), ['001', '01', '003'])
        self.assertEqual(result['Task Status'].tolist(), ['Available','Available','Completed and Delivered'])
        repeated = retain_completed_orders(incoming, [list(result.columns)] + result.values.tolist())
        pd.testing.assert_frame_equal(result, repeated)

    def test_api_sync_uses_comparison_and_ignores_legacy_browser_rules(self):
        syncer = Mock(return_value=['Sheet1'])
        client = create_app(self.store.root, syncer=syncer).test_client()
        self.assertTrue(client.get('/api/state').json['capabilities']['automatic_statuses'])
        self.assertEqual(len(client.get('/api/daily-orders').json['rows']), 1)
        result = client.post('/api/sync', json={'preview':self.after['id'], 'previous':self.before['id'],
                                              'status_rules':[{'source':'Available','target':'Wrong'}]})
        self.assertEqual(result.status_code, 202)
        for _ in range(200):
            state = client.get('/api/state').json['job']
            if not state['running']:
                break
            time.sleep(.01)
        self.assertEqual(state['result']['completed_orders'], 1)
        frame = syncer.call_args.args[0]
        self.assertEqual(len(frame), 4)
        self.assertEqual(frame.loc[frame['Order Number']=='002','Task Status'].iloc[0], 'Available')
        self.assertEqual(client.post('/api/sync', json={'preview':1,'previous':2}).status_code, 422)

    def test_no_order_identity_fails_before_writing(self):
        latest = {**self.after, 'columns':['Task Status'], 'rows':[{'Task Status':'Available'}]}
        with self.assertRaisesRegex(ValueError, 'Order Number'):
            automatic_sync_frame(latest, self.before)

    def test_completion_tasks_out_time_and_report_sheets(self):
        from datatrace_sync import report_frames
        source = pd.DataFrame([
            {'Order Number':'1','Task Name':'CRSP2','Task Status':'Task Suspended','Product':'Full Title'},
            {'Order Number':'2','Task Name':'searchfix','Task Status':'Available','Product':'Current Owner'},
            {'Order Number':'3','Task Name':'N/A','Task Status':'Workflow Suspended','Product':'Current Owner'},
            {'Order Number':'4','Task Name':'Search','Task Status':'Completed and Delivered','Product':'Full Title'},
        ])
        result = apply_status_rules(source, [], reporting_date='2026-09-27')
        self.assertEqual(result['Task Status'].tolist(), ['Completed and Delivered']*4)
        self.assertEqual(result['Out Time'].tolist(), ['2026-09-27']*4)
        for report in report_frames(result):
            self.assertTrue(report['Out Time'].eq('2026-09-27').all())
        next_day = apply_status_rules(result, [], reporting_date='2026-09-28')
        self.assertEqual(next_day['Out Time'].tolist(), ['2026-09-27']*4)

    def test_only_missing_today_gets_today_out_time(self):
        today = datetime.now().date().isoformat()
        frame, _ = automatic_sync_frame(self.after, self.before)
        missing = frame['Order Number'].eq('003')
        self.assertEqual(frame.loc[missing,'Out Time'].iloc[0], today)
        repeated = apply_status_rules(frame, [])
        self.assertEqual(repeated.loc[missing,'Out Time'].iloc[0], today)
        older = {**self.after, 'created':(datetime.now()-timedelta(days=1)).isoformat()}
        historic, _ = automatic_sync_frame(older, self.before)
        self.assertEqual(historic.loc[historic['Order Number'].eq('003'),'Out Time'].iloc[0], older['created'][:10])

    def test_latest_arrival_date_drives_daily_reporting_and_missing_out_time(self):
        from reporting_dates import arrival_date, reporting_date
        previous = {'id':1,'name':'preview1','created':'2026-09-28T04:00:00Z',
                    'columns':['Order Number','Task Status','Arrival Time'],
                    'rows':[{'Order Number':'new','Task Status':'Available','Arrival Time':'09/27/2026 10:49 PM'},
                            {'Order Number':'old','Task Status':'Available','Arrival Time':'09/26/2026 10:00 AM'}]}
        latest = {**previous,'id':2,'name':'preview2','created':'2026-09-28T08:00:00Z','rows':previous['rows'][:1]}
        store = Mock()
        store.list.return_value = [latest,previous]
        store.get.side_effect = lambda number: {1:previous,2:latest}[number]
        day = daily_orders(store)[0]
        self.assertEqual(day['Date'], '2026-09-27')
        self.assertEqual(day['Previews'], ['preview1','preview2'])
        self.assertEqual(day['new_ids'], ['new'])
        self.assertEqual(day['Newly Orders'], 1)
        frame, _ = automatic_sync_frame(latest, previous)
        self.assertEqual(frame.loc[frame['Order Number'].eq('old'),'Out Time'].iloc[0], '2026-09-27')
        repeated = apply_status_rules(frame, [])
        self.assertEqual(repeated.loc[repeated['Order Number'].eq('old'),'Out Time'].iloc[0], '2026-09-27')
        self.assertEqual(reporting_date(latest), '2026-09-27')
        self.assertIsNone(arrival_date({'Arrival Time':'09/27'}))

    def test_sheet_sync_preserves_historical_out_times(self):
        import datatrace_sync as sync
        frame = pd.DataFrame([{'Order Number':'new','Product':'Current Owner','Task Status':'Completed and Delivered','Out Time':'2026-09-27'}])
        frame.attrs.update(reporting_date='2026-09-27',capture_date='2026-09-28')
        primary = Mock(title='Sheet1')
        primary.get_all_values.return_value = [list(frame.columns), ['old','Current Owner','Completed and Delivered','2026-09-28']]
        book = Mock()
        book.worksheets.return_value = [primary]+[Mock(title=title) for title in ['All Products','Full Title','Remaining Products','Status Report']]
        with patch.object(sync,'target_worksheet',return_value=(book,primary)), patch.object(sync,'sync_dataframe',return_value='OK') as upload:
            sync.sync_workbook(frame)
        sent = upload.call_args_list[3].args[0]
        self.assertEqual(sent['Out Time'].tolist(), ['2026-09-27','2026-09-28'])

    def test_existing_completion_date_wins_over_new_sync_date(self):
        incoming = pd.DataFrame([{'Order Number':'1','Task Status':'Completed and Delivered','Out Time':'2026-09-28'}])
        existing = [['Order Number','Task Status','Out Time'], ['1','Completed and Delivered','2026-09-25']]
        retained = retain_completed_orders(incoming, existing)
        result = apply_status_rules(retained, [], reporting_date='2026-09-29')
        self.assertEqual(result.iloc[0]['Out Time'], '2026-09-25')

    def test_history_recovers_first_observed_completion_date(self):
        dates = completion_history(self.store, self.after['id'])
        self.assertEqual(dates['003'], self.after['created'][:10])
        self.assertNotIn('004', dates)

    def test_remaining_excludes_attorneys_and_home_builders_only(self):
        from datatrace_sync import report_frames
        products = ['Full Title','Attorney','Attroney Review','Home Builders','HomeBuilders','Current Owner']
        frame = pd.DataFrame([{'Order Number':str(i),'Product':value} for i,value in enumerate(products)])
        all_products, full_title, remaining = report_frames(frame)
        self.assertEqual(len(all_products), 6)
        self.assertEqual(len(full_title), 1)
        self.assertEqual(remaining['Product'].tolist(), ['Current Owner'])

    def test_remaining_matches_reference_product_list_exactly(self):
        from datatrace_sync import report_frames, REMAINING_PRODUCTS
        products = REMAINING_PRODUCTS + [' current   OWNER ', 'Update Full Title', 'Unknown', '', 'Attorney', 'Home Builders']
        frame = pd.DataFrame([{'Order Number':str(i),'Product':product} for i,product in enumerate(products)])
        all_products, _, remaining = report_frames(frame)
        self.assertEqual(len(REMAINING_PRODUCTS), 15)
        self.assertEqual(len(all_products), len(products))
        self.assertEqual(remaining['Product'].tolist(), REMAINING_PRODUCTS + [' current   OWNER '])

    def test_raw_tabs_keep_extracted_tasks_and_statuses(self):
        import datatrace_sync as sync
        raw = pd.DataFrame([
            {'Order Number':'1','Task Name':'Search','Task Status':'Available','Product':'Full Title'},
            {'Order Number':'2','Task Name':'CRSP2','Task Status':'Task Suspended','Product':'Current Owner'},
            {'Order Number':'3','Task Name':'Search','Task Status':'Workflow Suspended','Product':'Current Owner'},
        ])
        preview = {'created':'2026-09-28T10:00:00Z','columns':list(raw.columns),'rows':raw.to_dict('records')}
        frame, _ = automatic_sync_frame(preview)
        primary = Mock(title='Sheet1')
        primary.get_all_values.return_value = [list(raw.columns)] + raw.values.tolist()
        sheets = [primary]+[Mock(title=title) for title in ['All Products','Full Title','Remaining Products','Status Report']]
        for sheet in sheets[1:]:
            sheet.get_all_values.return_value = []
        sheets[2].get_all_values.return_value = [['Order number','Product','Status','Out Time'],['historic','Full Title','Completed and Delivered','Completed']]
        book = Mock()
        book.worksheets.return_value = sheets
        with patch.object(sync,'target_worksheet',return_value=(book,primary)), patch.object(sync,'sync_dataframe',return_value='OK') as upload:
            sync.sync_workbook(frame)
        primary_sent, all_sent, full_sent, remaining_sent = [call.args[0] for call in upload.call_args_list[:4]]
        pd.testing.assert_frame_equal(primary_sent, raw)
        self.assertEqual(all_sent['Task Name'].tolist(), raw['Task Name'].tolist())
        self.assertEqual(all_sent['Task Status'].tolist(), raw['Task Status'].tolist())
        self.assertEqual(full_sent['Order number'].tolist(), ['1','historic'])
        self.assertEqual(full_sent['Status'].tolist(), ['Search In Progress','Completed and Delivered'])
        self.assertEqual(remaining_sent['Status'].tolist(), ['Completed and Delivered','Awaiting for Clarification'])
