import unittest
from io import BytesIO
from openpyxl import load_workbook
from new_order_report import NEW_ORDER_COLUMNS, production_record
from sla_compare import compare_sla_with_production, export_comparison_excel

class NewOrderReportTests(unittest.TestCase):
    def test_new_queue_fields_and_workbook_column_alignment(self):
        source={'Order Number':'NEW-1','Status':'Search In Progress','Arrival Time':'2026-11-10 12:30:00',
            'TraceQ ID':'TRACE-1','St':'NJ','Online/ Ground':'Online','Last User':'Owner',
            'ETA':'11/12/2026','SLA Expiration*':'2026-11-11 14:30:00','Comment':'Keep comment',
            'Typer':'Typer','Review/QC':'QC','review':'Review','Clarification Requested':'Yes','Expense':0}
        row=production_record(source, source['Status'])
        self.assertEqual(list(row),NEW_ORDER_COLUMNS)
        self.assertEqual(len(row),25)
        self.assertEqual(NEW_ORDER_COLUMNS[17], 'Typer')
        self.assertEqual(row['TraceQ Id'],'TRACE-1')
        self.assertEqual(row['Assignee'],'Owner')
        self.assertEqual(row['ETA'],'11/12/2026')
        self.assertEqual(row['SLA Expiration'],'2026-11-11 14:30:00')
        self.assertEqual(row['Expense'],0)
        self.assertEqual(row['Date'],'11/10/2026')
        self.assertEqual(row['Process date'],'')
        source['SLA Category']='Today SLA'
        result=compare_sla_with_production({'as_of':'2026-11-10','rows':[source]},[{'order_number':'OTHER','status':'QC in Progress'}])
        self.assertEqual(result['orders'][0]['production_report'],row)
        book=load_workbook(export_comparison_excel(result,table_scope='orders',filter_type='sla_only'))
        sheet=book.active
        self.assertEqual([cell.value for cell in sheet[1]],NEW_ORDER_COLUMNS)
        self.assertEqual(sheet.max_row,2)
        self.assertEqual(sheet['C2'].value,'NEW-1')
        self.assertEqual(sheet['R2'].value,'Typer')
        self.assertEqual(sheet['W2'].value.hour,14)
        self.assertEqual(sheet['K2'].value.day,12)
        self.assertIsNone(sheet['A2'].value)
    def test_full_eta_comments_take_precedence_and_keep_readable_line_breaks(self):
        source={'Order Number':'ETA-1','Status':'SearchFix','SLA Category':'Today SLA',
            'Comment':'Outbound correspondence created; ID=7968..',
            'ETA Comments':'ETA: Hello Team.&lt;br&gt;Please be informed that we requested the abstractor for review.&lt;br&gt;We will complete the order ASAP.'}
        expected='ETA: Hello Team.\nPlease be informed that we requested the abstractor for review.\nWe will complete the order ASAP.'
        result=compare_sla_with_production({'rows':[source]},[{'order_number':'OTHER','status':'QC in Progress'}])
        row=next(row for row in result['orders'] if row['match_type']=='sla_only')
        self.assertEqual(row['eta_comments'],expected)
        self.assertEqual(row['production_report']['Comments'],expected)
        ws=load_workbook(export_comparison_excel(result,table_scope='orders',filter_type='sla_only')).active
        self.assertEqual(ws['L2'].value,expected)
        self.assertTrue(ws['L2'].alignment.wrap_text)
        ws=load_workbook(export_comparison_excel(result,table_scope='orders')).active
        headers=[cell.value for cell in ws[4]]
        self.assertEqual(headers[-1],'ETA Comments')
        self.assertEqual(ws.cell(5,len(headers)).value,expected)

    def test_missing_fields_are_blank_and_text_cannot_become_formula(self):
        result={'orders':[{'order_number':'NEW-1','match_type':'sla_only','sla_status':'SearchFix',
            'production_report':{'Comments':'=1+1'}}]}
        ws=load_workbook(export_comparison_excel(result,table_scope='orders',filter_type='new')).active
        self.assertEqual(ws['C2'].value,'NEW-1')
        self.assertEqual(ws['L2'].value,'=1+1')
        self.assertEqual(ws['L2'].data_type,'s')
        self.assertIsNone(ws['K2'].value)
        self.assertIsNone(ws['W2'].value)

if __name__=='__main__':unittest.main()
