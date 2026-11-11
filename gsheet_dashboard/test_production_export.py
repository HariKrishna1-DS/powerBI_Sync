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

    def test_status_changes_use_sla_compare_snapshot(self):
        book=load_workbook(self.files['full']);book.active.cell(2,8).value='Assign to ABS';book.save(self.files['full']);book.close()
        snapshot=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}]
        info,result=plan(self.root,self.report,comparison_rows=snapshot)
        full=next(r for r in result['reports'] if r['kind']=='full')
        self.assertEqual(full['status_changed'],1)
        self.assertEqual(full['changed_orders'][0]['PreviousStatus'],'Assign to ABS')
        self.assertEqual(full['changed_orders'][0]['Status'],'SearchFix')
        proceed(info,self.root/'changed-export')
        book=load_workbook(self.files['full'])
        self.assertEqual(book.active.cell(2,8).value,'SearchFix')
        book.close()

    def test_status_changes_exclude_production_only_labels(self):
        self.report['summary']=[{'Status':'Assign to ABS'},{'Status':'Search In Progress'},
                                {'Status':'Awaiting for Clarification'},{'Status':'SearchFix'}]
        snapshot=[{'order_number':'full-old','status':'QC in Progress','product':'Full Title'}]
        info,result=plan(self.root,self.report,comparison_rows=snapshot)
        self.assertEqual(sum(file['status_changed'] for file in result['reports']),0)
        proceed(info,self.root/'excluded-qc')
        book=load_workbook(self.files['full'])
        self.assertEqual(book.active.cell(2,8).value,'Completed and delivered')
        book.close()

    def test_status_changes_take_queue_value_for_shared_statuses_only(self):
        book=load_workbook(self.files['full']);book.active.cell(2,8).value='Search In Progress';book.save(self.files['full']);book.close()
        self.report['rows'][0]['Status']='Assign to ABS'
        self.report['summary']=[{'Status':'Assign to ABS'},{'Status':'Search In Progress'}]
        snapshot=[{'order_number':'full-old','status':'Search in Progress','product':'Full Title'}]
        info,result=plan(self.root,self.report,comparison_rows=snapshot)
        full=next(file for file in result['reports'] if file['kind']=='full')
        self.assertEqual(full['status_changed'],1)
        self.assertEqual(full['changed_orders'][0]['Status'],'Assign to ABS')
        self.assertEqual(full['changed_orders'][0]['PreviousStatus'],'Search In Progress')
        proceed(info,self.root/'shared-status')
        book=load_workbook(self.files['full'])
        self.assertEqual(book.active.cell(2,8).value,'Assign to ABS')
        book.close()

    def test_selected_summary_is_authoritative_over_excluded_statuses(self):
        self.report['summary']=[{'Status':'Assign to ABS'},{'Status':'Search In Progress'}]
        snapshot=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}]
        _,result=plan(self.root,self.report,comparison_rows=snapshot)
        # SearchFix is in raw rows, but not in this selected summary.
        self.assertEqual(sum(file['status_changed'] for file in result['reports']),0)

    def tearDown(self): self.temp.cleanup()

    def test_planned_status_selection_is_staged_and_applied_on_proceed(self):
        book=load_workbook(self.files['full']);book.active.cell(2,8).value='Assign to ABS';book.save(self.files['full']);book.close()
        original=self.files['full'].read_bytes()
        snapshot=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}]
        _,before=plan(self.root,self.report,comparison_rows=snapshot)
        overrides={'full-old':'Awaiting for Clarification','new-co':'Typing in Progress'}
        info,result=plan(self.root,self.report,comparison_rows=snapshot,status_overrides=overrides)
        self.assertNotEqual(result['fingerprint'],before['fingerprint'])
        self.assertEqual(self.files['full'].read_bytes(),original)
        self.assertEqual(self.report['rows'][0]['Status'],'SearchFix')
        self.assertEqual(info['full']['changes'][0]['Status'],'Awaiting for Clarification')
        proceed(info,self.root/'status-selections')
        book=load_workbook(self.files['full']);self.assertEqual(book.active.cell(2,8).value,'Awaiting for Clarification');book.close()
        book=load_workbook(self.files['co']);self.assertEqual(book.active.cell(3,8).value,'Typing in Progress');book.close()

    def test_override_cannot_reopen_protected_or_unlisted_order(self):
        for overrides in ({'full-old':'Search In Progress'},{'not-listed':'SearchFix'},{'new-co':''},{'new-co':'x'*257}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):plan(self.root,self.report,status_overrides=overrides)

    def test_completed_destination_is_protected_even_when_saved_comparison_is_active(self):
        snapshot=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}]
        for status in ('Completed and delivered',' COMPLETED AND DELIVERED ','Completed & Delivered','Completed'):
            with self.subTest(status=status):
                book=load_workbook(self.files['full']);book.active.cell(2,8).value=status;book.save(self.files['full']);book.close()
                info,result=plan(self.root,self.report,comparison_rows=snapshot)
                self.assertEqual(next(file for file in result['reports'] if file['kind']=='full')['changed_orders'],[])
                self.assertEqual(info['full']['changes'],[])

    def test_writer_never_overwrites_completed_destination_from_supplied_changes(self):
        from production_export import append_rows
        from io import BytesIO
        book=load_workbook(self.files['full'])
        # Duplicate order occurrences must not allow the completed row to reopen.
        book.active.append([2,'11/1/2026','full-old','NJ','Ocean','Online','Full Title','Assign to ABS'])
        book.save(self.files['full']);book.close()
        stream=append_rows(self.files['full'],[],[{'Order Number':'full-old','Status':'Search In Progress'}])
        book=load_workbook(BytesIO(stream))
        self.assertEqual(book.active.cell(2,8).value,'Completed and delivered')
        self.assertEqual(book.active.cell(3,8).value,'Assign to ABS')
        book.close()

    def test_need_to_assign_orders_are_excluded_from_status_change_plan(self):
        snapshot=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}]
        for status in ('Need to Assign','Need to assign ABS','  NEED TO ASSIGN ABS  '):
            with self.subTest(status=status):
                book=load_workbook(self.files['full']);book.active.cell(2,8).value=status;book.save(self.files['full']);book.close()
                info,result=plan(self.root,self.report,comparison_rows=snapshot)
                self.assertEqual(next(file for file in result['reports'] if file['kind']=='full')['status_changed'],0)
                self.assertEqual(info['full']['changes'],[])

    def test_writer_preserves_need_to_assign_even_with_explicit_update(self):
        from production_export import append_rows
        from io import BytesIO
        book=load_workbook(self.files['full']);book.active.cell(2,8).value='Need to assign ABS';book.save(self.files['full']);book.close()
        data=append_rows(self.files['full'],[],[{'Order Number':'full-old','Status':'Search In Progress'}])
        book=load_workbook(BytesIO(data))
        self.assertEqual(book.active.cell(2,8).value,'Need to assign ABS')
        book.close()

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
        self.assertEqual(sum(r['status_changed'] for r in again['reports']),0)

    def test_unfamiliar_products_require_explicit_route(self):
        self.report['rows'].append({'Order Number':'unknown','Product':'Custom Unmapped Product','Status':'SearchFix'})
        _,result=plan(self.root,self.report)
        self.assertEqual(result['unresolved'],['Custom Unmapped Product'])
        info,result=plan(self.root,self.report,{'Custom Unmapped Product':'co'})
        self.assertEqual(result['unresolved'],[])
        self.assertEqual(len(info['co']['additions']),2)

    def test_listed_products_default_to_co_including_truncated_and_full_labels(self):
        products=['Attorney Appro..','Bulk Two Owner','ClientReview','Home Builder L..','Home Builder U..','Home Builder Update',
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
        originals={kind:path.read_bytes() for kind,path in self.files.items()}
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
        restore=result.json['revert']
        self.assertTrue(restore['token'])
        # The checkpoint is discovered from durable backups after a fresh config read.
        self.assertEqual(client.get('/api/production-report').json['revert']['token'],restore['token'])
        reverted=client.post('/api/production-report/revert',json={'folder':str(self.root),'token':restore['token']})
        self.assertEqual(reverted.status_code,200,reverted.json)
        for kind,path in self.files.items():self.assertEqual(path.read_bytes(),originals[kind])
        self.assertIsNone(client.get('/api/production-report').json['revert'])
        self.assertEqual(client.post('/api/production-report/revert',json={'folder':str(self.root),'token':restore['token']}).status_code,409)

    def checkpoint(self):
        from production_export import revert_checkpoint
        import json
        info,_=plan(self.root,self.report)
        output=self.root/'exports'/('a'*32)
        proceed(info,output)
        (output/'files.json').write_text(json.dumps({kind:path.name for kind,path in self.files.items()}))
        return revert_checkpoint(self.root,self.root/'exports')

    def test_revert_blocks_later_manual_edits(self):
        from production_export import revert_excel
        checkpoint=self.checkpoint()
        original=self.files['full'].read_bytes()
        with self.files['co'].open('ab') as file:file.write(b'manual edit')
        changed=self.files['co'].read_bytes()
        with self.assertRaisesRegex(ValueError,'changed after Proceed'):revert_excel(checkpoint)
        self.assertEqual(self.files['full'].read_bytes(),original)
        self.assertEqual(self.files['co'].read_bytes(),changed)

    def test_failed_revert_restores_both_updated_files(self):
        from production_export import revert_excel
        import os
        checkpoint=self.checkpoint()
        updated={kind:path.read_bytes() for kind,path in self.files.items()}
        real=os.replace
        calls=[]
        def fail_second(source,target):
            calls.append(target)
            if len(calls)==2:raise PermissionError('locked')
            return real(source,target)
        with patch('production_export.os.replace',side_effect=fail_second):
            with self.assertRaises(PermissionError):revert_excel(checkpoint)
        for kind,path in self.files.items():self.assertEqual(path.read_bytes(),updated[kind])

    def test_revert_restores_status_changes_and_removes_added_orders(self):
        from production_export import revert_excel
        import json
        book=load_workbook(self.files['full']);book.active.cell(2,8).value='Assign to ABS';book.save(self.files['full']);book.close()
        originals={kind:path.read_bytes() for kind,path in self.files.items()}
        info,_=plan(self.root,self.report,comparison_rows=[{'order_number':'full-old','status':'Assign to ABS','product':'Full Title'}])
        output=self.root/'exports'/('b'*32)
        proceed(info,output)
        (output/'files.json').write_text(json.dumps({kind:path.name for kind,path in self.files.items()}))
        from production_export import revert_checkpoint
        revert_excel(revert_checkpoint(self.root,self.root/'exports'))
        for kind,path in self.files.items():self.assertEqual(path.read_bytes(),originals[kind])


if __name__=='__main__':unittest.main()
