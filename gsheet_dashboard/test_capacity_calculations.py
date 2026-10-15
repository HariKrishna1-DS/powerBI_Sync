from copy import deepcopy
from datetime import datetime
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from flask import Flask
from openpyxl import load_workbook
from capacity_calculations import capacity_date, capacity_days, capacity_details
from report_workspace import capacity_report, imported_snapshot, report_frames, register_report_routes, ReportWorkspace
from preview_store import PreviewStore
from tracker_sync import sheet_reports, FULL


def order(number, status='QC in Progress', received='10/01/2026 09:00 AM', completed=''):
    return {'Order Number':number, 'Product':'Full Title', 'Status':status,
            'In-Time':received, 'Out Time':completed, 'SLA Expiration':'10/20/2026 09:00 AM'}


class CapacityCalculationTests(unittest.TestCase):
    def setUp(self):
        clock = patch('report_workspace.current_capacity_month', return_value='2026-10')
        clock.start()
        self.addCleanup(clock.stop)

    def test_reference_rollover_414_plus_11_plus_11_is_436_and_non_recursive(self):
        reports={'daily':[
            {'Date':'2026-10-05','Received':31,'Completed':22,'Clarification':3,'Vendor Pending':1},
            {'Date':'2026-10-02','Received':414,'Completed':297,'Clarification':50,'Vendor Pending':30},
            {'Date':'2026-10-01','Received':323,'Completed':275,'Clarification':11,'Vendor Pending':11}], 'monthly':[]}
        saved=deepcopy(reports)
        result=capacity_report(reports, {'mode':'excel'})
        self.assertEqual([row['Received'] for row in result['daily']], [323,436,111])
        self.assertEqual(result['daily'][1]['Rollover Received'],22)
        self.assertEqual(result['monthly'][0]['Received'],870)
        self.assertEqual(reports,saved)
        self.assertEqual(capacity_report(reports, {'mode':'excel'}),result)

    def test_rollover_uses_previous_available_date_row_and_crosses_month_boundary(self):
        reports=sheet_reports({FULL:[order('A','Awaiting for Clarification',received='09/30/2026 09:00 AM'),
                                   order('B','Assign to ABS',received='09/30/2026 09:00 AM'),
                                   order('C',received='10/02/2026 09:00 AM')]})
        result=capacity_report(reports, {'selected_date':'2026-10-02'})
        self.assertEqual(result['daily'][0]['Received'],3)
        self.assertEqual(result['daily'][0]['Raw Received'],1)
        self.assertEqual(result['monthly'][1]['Received'],3)

    def test_in_house_order_counts_on_actual_completion_day_once(self):
        pending=order('P')
        before=capacity_report(sheet_reports({FULL:[pending]}), {'mode':'excel'})
        self.assertEqual(before['daily'][0]['In-House Pending'],1)
        completed=dict(pending, Status='Completed and Delivered', **{'Out Time':'10/03/2026 01:30 PM'})
        reports=sheet_reports({FULL:[completed,order('Q','Cancelled',completed='10/03/2026 02:00 PM')]})
        result=capacity_report(reports, {'mode':'excel'})
        self.assertEqual([(r['Date'],r['Received'],r['Completed']) for r in result['daily']],
                         [('2026-10-01',2,0),('2026-10-02',0,1)])
        self.assertEqual(result['monthly'][0]['Completed'],1)
        self.assertEqual(result['monthly'][0]['Capacity'],1400)
        self.assertEqual(reports['daily'][0]['Completed'],1)

    def test_existing_completion_day_moves_counts_without_double_counting(self):
        reports=sheet_reports({FULL:[order('A','Completed and Delivered',completed='10/02/2026 10:00 AM'),
                                   order('B','Completed and Delivered',received='10/02/2026 09:00 AM',completed='10/02/2026 11:00 AM'),
                                   order('C','Search In Progress',completed='10/02/2026 12:00 PM')]})
        result=capacity_report(reports, {'mode':'excel'})
        self.assertEqual([r['Completed'] for r in result['daily']], [0,2])
        self.assertEqual(sum(r['Completed'] for r in result['daily']),2)

    def test_completion_date_only_rows_serials_and_missing_date_fallback(self):
        rows=[order('A','Completed and Delivered',completed=str((datetime(2026,10,4,12)-datetime(1899,12,30)).total_seconds()/86400)),
              order('B','Completed and Delivered',completed='invalid'),
              order('C','Completed and Delivered')]
        result=capacity_report(sheet_reports({FULL:rows}), {'mode':'excel'})
        self.assertEqual([(r['Date'],r['Completed']) for r in result['daily']], [('2026-10-01',2),('2026-10-02',1)])
        self.assertEqual(result['missing_completion_date_count'],2)

    def test_completion_only_next_year_reconciles_monthly_and_pr_excel(self):
        rows=[order('A','Completed and Delivered',received='12/31/2026 09:00 AM',completed='01/02/2027 01:00 PM')]
        snapshot=imported_snapshot({'rows':rows,'columns':list(rows[0]),'files':[], 'created':'2026-12-31'})
        frames,report=report_frames(snapshot, {'mode':'excel','capacity_month':'2027-01'})
        self.assertEqual([(r['Date'],r['Received'],r['Completed']) for r in report['monthly']],
                         [('2026-12',1,0),('2027-01',0,1)])
        self.assertEqual(report['month'],'2027-01')
        self.assertEqual(frames['PR Excel'][3][0],'2027 YTD Total')
        self.assertEqual(frames['PR Excel'][5][:3],['2027-01-01',0,1])
        self.assertEqual(len(report['daily']),1)

    def test_live_daily_table_uses_current_month_and_keeps_previous_month_totals(self):
        reports=sheet_reports({FULL:[order('A','Awaiting for Clarification',received='08/20/2026 09:00 AM'),
                                   order('B','Assign to ABS',received='09/30/2026 09:00 AM'),
                                   order('C',received='10/01/2026 09:00 AM'),
                                   order('D',received='10/02/2026 09:00 AM')]})
        for mode in ('excel','tracker'):
            report=capacity_report(reports, {'mode':mode,'selected_date':'2026-09-30'})
            self.assertEqual(report['month'],'2026-10')
            self.assertEqual(report['scope_label'],'October 2026')
            self.assertEqual([row['Date'] for row in report['daily']],['2026-10-01','2026-10-02'])
            self.assertEqual([row['Date'] for row in report['monthly']],['2026-08','2026-09','2026-10'])
            self.assertEqual(report['daily'][0]['Rollover Received'],1)
            self.assertEqual(report['monthly'][0]['Received'],1)

    def test_sheet_frames_show_old_months_only_in_summary_and_october_days_in_detail(self):
        rows=[order('A',received='08/20/2026 09:00 AM'),order('B',received='09/30/2026 09:00 AM'),
              order('C',received='10/01/2026 09:00 AM'),order('D',received='10/02/2026 09:00 AM')]
        snapshot=imported_snapshot({'rows':rows,'columns':list(rows[0]),'files':[],'created':'2026-10-15'})
        frames,report=report_frames(snapshot,{'mode':'excel','selected_date':'2026-09-30'})
        values=frames['PR Excel']
        self.assertEqual([row[0] for row in values[1:4]],['2026-08','2026-09','2026-10'])
        self.assertEqual([row[0] for row in values[6:-1]],['2026-10-01','2026-10-02'])
        self.assertEqual(values[-1][1],2)
        self.assertEqual(values[4][1],4)

    def test_default_excel_has_only_october_details_and_explicit_month_export_is_preserved(self):
        rows=[order('A',received='09/30/2026 09:00 AM'),order('B',received='10/01/2026 09:00 AM')]
        snapshot=imported_snapshot({'rows':rows,'columns':list(rows[0]),'files':[],'created':'2026-10-15'})
        with tempfile.TemporaryDirectory() as folder:
            workspace=ReportWorkspace(PreviewStore(Path(folder)/'previews'))
            workspace.save(mode='excel',selected_date='2026-09-30')
            app=Flask(__name__)
            register_report_routes(app,workspace,threading.Lock(),lambda **kwargs:snapshot,lambda:None,lambda:None)
            client=app.test_client()
            for query,expected in (('', '2026-10-01'),('&month=2026-09', '2026-09-30')):
                response=client.get('/api/export/report?sheet=PR%20Excel'+query)
                self.assertEqual(response.status_code,200)
                book=load_workbook(BytesIO(response.data),data_only=True)
                sheet=book['PR Excel']
                self.assertEqual(sheet['A6'].value.date().isoformat(),expected)
                self.assertEqual(sheet['A6'].number_format,'dd-mm-yy')

    def test_completion_duplicate_archive_copy_counted_once(self):
        completed=order('A','Completed and Delivered',completed='10/02/2026 10:00 AM')
        reports={'daily':[{'Date':'2026-10-01','Received':2,'Completed':1,'Clarification':0,'Vendor Pending':0,
            'rows':[dict(order('A'),_month='2026-09'),dict(completed,_month='2026-10')]}], 'monthly':[]}
        days,_=capacity_days(reports)
        self.assertEqual(sum(day['Completed'] for day in days),1)
        self.assertEqual(days[-1]['Date'],'2026-10-02')

    def test_weekend_receipts_completions_and_pending_roll_into_friday_once(self):
        rows=[order('Friday clarification','Awaiting for Clarification',received='10/02/2026'),
              order('Friday vendor','Assign to ABS',received='10/02/2026'),
              order('Saturday','Completed and Delivered',received='10/03/2026',completed='10/03/2026'),
              order('Sunday','Awaiting for Clarification',received='10/04/2026'),
              order('Monday','Completed and Delivered',received='10/05/2026',completed='10/04/2026'),
              order('Tuesday',received='10/06/2026')]
        reports=sheet_reports({FULL:rows})
        original=deepcopy(reports)
        report=capacity_report(reports, {'mode':'excel'})
        self.assertEqual([(day['Date'],day['Raw Received'],day['Received'],day['Completed']) for day in report['daily']],
                         [('2026-10-02',4,4,2),('2026-10-05',1,4,0),('2026-10-06',1,1,0)])
        self.assertEqual(report['monthly'][0]['Capacity'],2100)
        friday=capacity_details(reports,'2026-10-02')
        groups={group['key']:group['rows'] for group in friday['groups']}
        self.assertEqual(len(groups['received']),4)
        self.assertEqual(len(groups['completed']),2)
        self.assertEqual({row['Source received date'] for row in groups['new']}, {'2026-10-02','2026-10-03','2026-10-04'})
        self.assertEqual({row['Capacity date'] for row in groups['new']}, {'2026-10-02'})
        monday=capacity_details(reports,'2026-10-05')
        self.assertEqual(monday['rollover_received'],3)
        self.assertEqual(len(next(group['rows'] for group in monday['groups'] if group['key']=='received')),4)
        self.assertEqual(reports,original)
        self.assertIn('2026-10-03',[day['Date'] for day in reports['daily']])

    def test_weekend_month_start_stays_in_previous_friday_month_in_summary_detail_and_export(self):
        rows=[order('Friday',received='10/30/2026'),
              order('Saturday','Completed and Delivered',received='10/31/2026',completed='11/01/2026'),
              order('Sunday',received='11/01/2026')]
        snapshot=imported_snapshot({'rows':rows,'columns':list(rows[0]),'files':[],'created':'2026-10-31'})
        frames,report=report_frames(snapshot, {'mode':'excel','capacity_month':'2026-10'})
        self.assertEqual([(day['Date'],day['Received'],day['Completed'],day['Capacity']) for day in report['monthly']],
                         [('2026-10',3,1,700)])
        self.assertEqual([day['Date'] for day in report['daily']], ['2026-10-30'])
        self.assertEqual(frames['PR Excel'][4][:3],['2026-10-30',3,1])
        groups={g['key']:g['rows'] for g in capacity_details(snapshot['reports'],'2026-10-30')['groups']}
        self.assertEqual({row['In-Time'] for row in groups['new']},{'10/30/2026','10/31/2026','11/01/2026'})
        self.assertEqual(capacity_report(snapshot['reports'],{'capacity_month':'2026-11'})['daily'],[])

    def test_weekend_mapping_handles_month_and_year_boundaries(self):
        for original,friday in [('2026-10-03','2026-10-02'),('2026-10-04','2026-10-02'),
                                ('2026-02-01','2026-01-30'),('2022-01-01','2021-12-31'),
                                ('2022-01-02','2021-12-31'),('2026-10-05','2026-10-05')]:
            with self.subTest(original=original):
                self.assertEqual(capacity_date(original),friday)

    def test_api_and_export_use_same_rollover_and_completion_counts(self):
        rows=[order('A','Awaiting for Clarification'),order('B','Assign to ABS'),
              order('C','Completed and Delivered',completed='10/02/2026 10:00 AM'),
              order('D',received='10/02/2026 09:00 AM')]
        snapshot=imported_snapshot({'rows':rows,'columns':list(rows[0]),'files':[], 'created':'2026-10-02'})
        with tempfile.TemporaryDirectory() as folder:
            workspace=ReportWorkspace(PreviewStore(Path(folder)/'previews'))
            workspace.save(mode='excel')
            app=Flask(__name__)
            register_report_routes(app,workspace,threading.Lock(),lambda **kwargs:snapshot,lambda:None,lambda:None)
            client=app.test_client()
            data=client.get('/api/capacity-report').json
            self.assertEqual([(r['Received'],r['Completed']) for r in data['daily']],[(3,0),(3,1)])
            book=load_workbook(BytesIO(client.get('/api/export/report?sheet=PR%20Excel').data),data_only=True)
            values=list(book['PR Excel'].values)
            self.assertEqual(values[4][1:3],(3,0))
            self.assertEqual(values[5][1:3],(3,1))
            self.assertEqual(values[6][1:3],(6,1))


if __name__=='__main__':
    unittest.main()
