from pathlib import Path
from copy import copy
from datetime import datetime
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from openpyxl import Workbook, load_workbook
from production_export import plan, proceed, discover, google_row


class ProductionExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.files={}
        for kind,title,product in [('full','Full Search','Full Title'),('co','C-O and Update','Update')]:
            p=self.root/f'TV Search Production Report {title} - November 2026.xlsx'
            w=Workbook();s=w.active
            s.append(['No','Date','Order number','State','County','Online/Gorund','Product','Status','SLA','Comments','Assignee','SLA Expiration','SLA'])
            s.append([1,'11/1/2026',kind+'-old','NJ','Ocean','Online',product,'Completed and delivered'])
            w.create_sheet('Escalations').append(['Keep this history'])
            w.save(p);w.close();self.files[kind]=p
        self.report={'preview_id':1,'preview_name':'preview1','rows':[
            {'Order Number':'full-old','Product':'Full Title','Status':'SearchFix'},
            {'Order Number':'new-full','Product':'Full Title','Status':'Search In Progress','St':'NJ','County':'Ocean','Online/ Ground':'Online','SLA Expiration':'11/12/2026 1:00 PM'},
            {'Order Number':'new-co','Product':'Update','Status':'Assign to ABS','Comment':'=not a formula'},
            {'Order Number':'new-co','Product':'Update','Status':'Assign to ABS'}], 'excluded_rows':[]}

    def tearDown(self): self.temp.cleanup()

    def test_routes_append_preserves_existing_and_is_idempotent(self):
        info,result=plan(self.root,self.report)
        self.assertEqual([r['missing'] for r in result['reports']],[1,1])
        backups=proceed(info,self.root/'exports'/'one')
        self.assertEqual(len(backups),2)
        for kind,p in self.files.items():
            w=load_workbook(p);s=w.active
            self.assertEqual(s.cell(2,8).value,'Completed and delivered')
            self.assertEqual(s.cell(3,3).value,'new-'+kind)
            self.assertEqual(s.cell(3,1).value,2)
            self.assertEqual(w['Escalations']['A1'].value,'Keep this history')
            if kind=='co':self.assertEqual(s.cell(3,10).data_type,'s')
            else:
                self.assertEqual(s.cell(3,9).value,datetime(2026,11,12))
                self.assertEqual(s.cell(3,9).number_format,'dd/mm/yyyy')
                self.assertEqual(s.cell(3,12).value,datetime(2026,11,12,13))
                self.assertEqual(s.cell(3,12).number_format,'mm/dd/yyyy hh:mm:ss AM/PM')
                self.assertEqual(s.cell(3,10).value,'New Orders')
                self.assertIsNone(s.cell(3,13).value)
            w.close()
        _,again=plan(self.root,self.report)
        self.assertEqual(sum(r['missing'] for r in again['reports']),0)

    def test_unfamiliar_products_require_explicit_route(self):
        self.report['rows'].append({'Order Number':'unknown','Product':'Custom Unmapped Product','Status':'SearchFix'})
        _,result=plan(self.root,self.report)
        self.assertEqual(result['unresolved'],['Custom Unmapped Product'])
        info,result=plan(self.root,self.report,{'Custom Unmapped Product':'co'})
        self.assertEqual(result['unresolved'],[])
        self.assertEqual(len(info['co']['additions']),2)

    def test_listed_products_default_to_co_including_truncated_and_full_labels(self):
        products=['Attorney Appro..','Bulk Two Owner','ClientReview','Home Builder L..',
            'New Owner','Quality Contro..','REO Full Title','Update Legal &..',
            'Attorney Approval','Home Builder Loan','Quality Control','Update Legal & Vesting']
        self.report['rows'] += [{'Order Number':f'co-extra-{index}','Product':product,'Status':'SearchFix'}
            for index,product in enumerate(products)]
        before={kind:path.read_bytes() for kind,path in self.files.items()}
        info,result=plan(self.root,self.report)
        self.assertEqual(result['unresolved'],[])
        self.assertEqual({row['Order Number'] for row in info['co']['additions']},
            {'new-co'} | {f'co-extra-{index}' for index in range(len(products))})
        self.assertEqual(len(info['full']['additions']),1)
        for kind,path in self.files.items():self.assertEqual(path.read_bytes(),before[kind])

    def test_explicit_product_override_still_wins(self):
        self.report['rows'].append({'Order Number':'client-review','Product':'ClientReview','Status':'SearchFix'})
        info,result=plan(self.root,self.report,{'ClientReview':'full'})
        self.assertEqual(result['unresolved'],[])
        self.assertIn('client-review',{row['Order Number'] for row in info['full']['additions']})

    def test_report_popup_orders_only_include_missing_rows_for_that_destination(self):
        info,result=plan(self.root,self.report)
        reports={item['kind']:item for item in result['reports']}
        self.assertEqual([row['Order Number'] for row in reports['full']['orders']],['new-full'])
        self.assertEqual([row['Order Number'] for row in reports['co']['orders']],['new-co'])
        for item in reports.values():self.assertEqual(len(item['orders']),item['missing'])
        self.assertNotIn('full-old',[row['Order Number'] for item in reports.values() for row in item['orders']])

    def test_proceed_writes_complete_eta_comments_and_real_excel_expiration(self):
        raw=self.report['rows'][2]
        raw['Comment']='Outbound correspondence created; ID=7968..'
        raw['ETA Comments']='ETA: Hello Team.&lt;br&gt;Please be informed that we requested the abstractor for review.&lt;br&gt;We will complete this order ASAP.'
        raw['SLA Expiration']='2026-11-09 23:07:11.312920'
        expected='ETA: Hello Team.\nPlease be informed that we requested the abstractor for review.\nWe will complete this order ASAP.'
        original=load_workbook(self.files['co'])
        old_values=[cell.value for cell in original.active[2]]
        original.active['L2'].number_format='m/d/yyyy h:mm:ss AM/PM'
        original.save(self.files['co']);original.close()
        info,result=plan(self.root,self.report)
        self.assertEqual(info['co']['additions'][0]['Comments'],expected)
        proceed(info,self.root/'exports'/'comments-date')
        book=load_workbook(self.files['co']);sheet=book.active
        self.assertEqual([cell.value for cell in sheet[2]],old_values)
        self.assertEqual(sheet['J3'].value,expected)
        self.assertEqual(copy(sheet['J3'].alignment),copy(sheet['J2'].alignment))
        self.assertEqual(copy(sheet['J3'].font),copy(sheet['J2'].font))
        self.assertEqual(sheet.row_dimensions[3].height,sheet.row_dimensions[2].height or sheet.sheet_format.defaultRowHeight)
        self.assertIsInstance(sheet['L3'].value,datetime)
        self.assertEqual(sheet['L3'].value.strftime('%m/%d/%Y %I:%M:%S %p'),'11/09/2026 11:07:11 PM')
        self.assertEqual(sheet['L3'].number_format,'mm/dd/yyyy hh:mm:ss AM/PM')
        self.assertEqual(sheet['I3'].value,datetime(2026,11,9))
        self.assertEqual(sheet['I3'].number_format,'dd/mm/yyyy')
        self.assertIsNone(sheet['M3'].value)
        book.close()

    def test_append_matches_normal_row_style_instead_of_enlarged_recent_rows(self):
        path=self.files['co']
        book=load_workbook(path);sheet=book.active
        from copy import copy
        from openpyxl.styles import Font
        sheet.row_dimensions[2].height=12
        for cell in sheet[2]:cell.font=Font(name='Calibri',size=10)
        sheet['B2'].number_format='dd-mm-yyyy'
        for r in (3,4):
            for c in range(1,sheet.max_column+1):sheet.cell(r,c)._style=copy(sheet.cell(2,c)._style)
            sheet.cell(r,3).value=f'older-{r}'
            sheet.cell(r,7).value='Update'
        sheet.row_dimensions[3].height=12
        sheet.row_dimensions[4].height=54
        book.save(path);book.close()
        self.report['rows'][2]['Arrival Date']='2026-11-10'
        info,_=plan(self.root,self.report)
        proceed(info,self.root/'exports'/'style-match')
        book=load_workbook(path);sheet=book.active
        self.assertEqual(sheet.row_dimensions[5].height,12)
        self.assertEqual(sheet['C5'].font.name,'Calibri')
        self.assertEqual(sheet['C5'].font.sz,10)
        self.assertEqual(sheet['B5'].value,datetime(2026,11,10))
        self.assertEqual(sheet['B5'].number_format,'dd-mm-yyyy')
        self.assertEqual(sheet.row_dimensions[4].height,54)
        book.close()

    def test_status_rules_extend_to_new_orders_without_changing_rules_or_other_sheets(self):
        from openpyxl.formatting.rule import FormulaRule,Rule
        from openpyxl.styles import PatternFill
        from production_export import append_rows
        from io import BytesIO
        path=self.files['co'];book=load_workbook(path);sheet=book.active
        statuses=[('Completed and Delivered','FFFF99'),('Cancelled','FF0000'),('Awaiting for Clarification','A66BD3')]
        for name,color in statuses:
            sheet.conditional_formatting.add('A2:M2',FormulaRule(formula=[f'$H2="{name}"'],fill=PatternFill('solid',fgColor=color)))
        sheet.conditional_formatting.add('C1:C1048576',Rule(type='duplicateValues'))
        sheet.conditional_formatting.add('K2:K2',FormulaRule(formula=['K2>0'],fill=PatternFill('solid',fgColor='00FF00')))
        book['Escalations'].conditional_formatting.add('A1:A3',Rule(type='duplicateValues'))
        book.save(path);book.close()
        data=append_rows(path,[google_row({'Order Number':'new-rule','Status':'Search In Progress','Product':'Update'})])
        book=load_workbook(BytesIO(data));sheet=book.active
        by_range={str(region.sqref):sheet.conditional_formatting[region] for region in sheet.conditional_formatting}
        self.assertEqual([rule.formula for rule in by_range['A2:M3']],[[f'$H2="{name}"'] for name,_ in statuses])
        self.assertEqual([rule.dxf.fill.fgColor.rgb for rule in by_range['A2:M3']],['00'+color for _,color in statuses])
        self.assertIn('C1:C1048576',by_range)
        self.assertIn('K2',by_range)
        self.assertEqual(str(next(iter(book['Escalations'].conditional_formatting)).sqref),'A1:A3')
        # Saving a later status edit retains the native rule and the new row's coverage.
        sheet['H3']='Completed and Delivered';stream=BytesIO();book.save(stream);book.close()
        reopened=load_workbook(stream);self.assertEqual(reopened.active['H3'].value,'Completed and Delivered')
        self.assertIn('A2:M3',[str(region.sqref) for region in reopened.active.conditional_formatting]);reopened.close()

    def test_external_change_prevents_writes(self):
        info,_=plan(self.root,self.report)
        original=self.files['full'].read_bytes()
        with self.files['co'].open('ab') as file:file.write(b'changed')
        with self.assertRaisesRegex(ValueError,'changed'):proceed(info,self.root/'exports'/'two')
        self.assertEqual(self.files['full'].read_bytes(),original)

    def test_second_replace_failure_restores_first(self):
        info,_=plan(self.root,self.report)
        original={k:p.read_bytes() for k,p in self.files.items()}
        import os
        real=os.replace
        calls=[]
        def fail_second(source,target):
            calls.append(target)
            if len(calls)==2:raise PermissionError('locked')
            return real(source,target)
        with patch('production_export.os.replace',side_effect=fail_second):
            with self.assertRaises(PermissionError):proceed(info,self.root/'exports'/'three')
        for kind,p in self.files.items():self.assertEqual(p.read_bytes(),original[kind])

    def test_missing_report_is_rejected(self):
        self.files['full'].unlink()
        with self.assertRaisesRegex(ValueError,'exactly one'):discover(self.root)

    def test_google_column_mapping(self):
        row=google_row({'Order Number':'ONE','Task Status':'SearchFix','St':'IL','Last User':'Person','Comment':'Note'})
        self.assertEqual((row['Status'],row['State'],row['Assignee'],row['Comments']),('SearchFix','IL','Person','Note'))

    def test_search_in_progress_comments_override_for_plan_and_export(self):
        from production_export import cell_value
        for status in ('Search in Progress','Search In Progress',' search IN progress '):
            raw={'Order Number':'SEARCH','Status':status,'ETA Comments':'[Int] - TV Auto Suspend'}
            self.assertEqual(google_row(raw)['Comments'],'New Orders')
            self.assertEqual(cell_value('Comments',{'Status':status,'Comments':'Old note'}),'New Orders')
        self.assertEqual(google_row({'Status':'SearchFix','Comments':'Keep note'})['Comments'],'Keep note')

    def test_api_requires_checked_plan_and_downloads_both_workbooks(self):
        from flask import Flask
        from types import SimpleNamespace
        from production_export import register_production_export
        settings={}
        store=SimpleNamespace(root=self.root/'previews',list=lambda:[{'id':1,'name':'preview1'}])
        workspace=SimpleNamespace(store=store,read=lambda:settings,save=lambda **values:settings.update(values))
        app=Flask(__name__)
        register_production_export(app,workspace,lambda preview_id:self.report)
        client=app.test_client()
        body={'folder':str(self.root),'preview_id':1}
        self.assertEqual(client.post('/api/production-report/proceed',json=body).status_code,409)
        check=client.post('/api/production-report/check',json=body)
        self.assertEqual(check.status_code,200)
        body['fingerprint']=check.json['fingerprint']
        result=client.post('/api/production-report/proceed',json=body)
        self.assertEqual(result.status_code,200)
        self.assertTrue(result.json['completed'])
        for file in result.json['downloads']:
            response=client.get(file['url'])
            self.assertEqual(response.status_code,200)
            self.assertIn(file['name'],response.headers['Content-Disposition'])
            response.close()
        again=client.post('/api/production-report/proceed',json=body)
        self.assertEqual(again.status_code,409)


if __name__=='__main__':unittest.main()
