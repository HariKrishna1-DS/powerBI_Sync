from copy import deepcopy
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from flask import Flask
from import_identity import upgrade_workbook_orders
from import_excel_changes import editable_frames, reconcile, preserve_sheet_edits
from preview_store import PreviewStore
from report_workspace import ReportWorkspace, read_report_files, combine_sources, imported_snapshot, report_frames, register_report_routes, publish_reports, all_products_date_filter
from sla_status import build_sla_status
from status_updates import rename_status
from tracker_sync import key
from test_pdf_report_workspace import ReportBook, excel, row


class ImportedWorkbookIdentityTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace=ReportWorkspace(PreviewStore(Path(self.folder.name)/'previews'))
        self.imported=read_report_files([
            ('full.xlsx',excel([row('A','Completed and Delivered',**{'Out Time':'10/02/2026','SLA Expiration':'10/20/2026'}),
                               row('B',**{'SLA Expiration':'10/20/2026'})])),
            ('other.xlsx',excel([row('A','Completed and Delivered',**{'Out Time':'10/03/2026','SLA Expiration':'10/20/2026'}),
                                row('C','Completed and Delivered',**{'Out Time':'10/05/2026','SLA Expiration':'10/20/2026'}),
                                row('A','Completed and Delivered',**{'Out Time':'10/04/2026','SLA Expiration':'10/20/2026'})]))])
        self.workspace.save(mode='excel',cloud_reset=True,imported=self.imported,files=self.imported['files'],row_count=4)

    def snapshot(self, **kwargs):
        return imported_snapshot(self.workspace.read()['imported'])

    def test_same_number_is_normal_in_both_files_in_every_report(self):
        self.assertEqual(len(self.imported['rows']),4)
        self.assertEqual(len({key(record) for record in self.imported['rows']}),4)
        self.assertEqual(len(self.imported['duplicate_orders']),1)
        self.assertEqual(self.imported['duplicate_orders'][0]['Earlier file'],'other.xlsx')
        snapshot=self.snapshot()
        frames,capacity=report_frames(snapshot, {'mode':'excel','capacity_month':'2026-10'})
        self.assertEqual(len(frames['All Products'])-1,4)
        self.assertEqual([cells[0] for cells in frames['All Products'][1:]],[1,2,3,4])
        self.assertEqual(sum(period['Received'] for period in snapshot['reports']['daily']),4)
        self.assertEqual(sum(period['Received'] for period in snapshot['reports']['monthly']),4)
        self.assertEqual(sum(period['Raw Received'] for period in capacity['daily']),4)
        self.assertEqual(sum(period['Completed'] for period in capacity['daily']),3)
        self.assertEqual(build_sla_status(snapshot)['totals']['Grand Total'],4)
        public=self.workspace.public()
        self.assertEqual((public['duplicate_row_count'],public['source_overlap_count']),(1,1))
        self.assertEqual(public['source_overlap_orders'][0]['Order Number'],'A')
        self.assertEqual(public['source_overlap_orders'][0]['Replacement row'],4)
        self.assertEqual([(file['rows'],file['orders']) for file in public['imports']],[(2,2),(3,2)])

    def test_source_file_routes_every_product_and_saved_membership_cannot_move_it(self):
        imported=read_report_files([
            ('TV Search Production Report Full Search - October 2026.xlsx',excel([row('F',Product='Update')])),
            ('TV Search Production Report C-O and Update - October 2026.xlsx',excel([row('C',Product='Full Title')]))])
        imported['view_members']={'Full Title':[key(imported['rows'][1])],'Remaining Products':[key(imported['rows'][0])]}
        snapshot=imported_snapshot(imported)
        self.assertEqual([record['Order Number'] for record in snapshot['sheets']['Full Title']['rows']],['F'])
        self.assertEqual([record['Order Number'] for record in snapshot['sheets']['Remaining Products']['rows']],['C'])
        baseline=editable_frames(snapshot,{'mode':'excel'})
        full=baseline['Full_Search_OCT_2026'];other=baseline['Remaining_Search_OCT_2026']
        self.assertEqual(full[1][full[0].index('Order Number')],'F')
        self.assertEqual(other[1][other[0].index('Order Number')],'C')
        remote=deepcopy(baseline)
        remote['All Products'][2][remote['All Products'][0].index('Product')]='Full Title'
        updated,events=reconcile(imported,baseline,remote)
        self.assertEqual(len(events),1)
        self.assertEqual([record['Order Number'] for record in imported_snapshot(updated)['sheets']['Full Title']['rows']],['F'])

    def test_received_date_precedes_later_in_time_without_changing_source_timestamps(self):
        imported=read_report_files([('full.xlsx',excel([
            row('A',Date='10/13/2026',**{'In-Time':'10/14/2026 06:12:35 AM'}),
            row('B',Date='10/10/2026',**{'In-Time':'10/13/2026'}),
            row('C',Date='invalid',**{'In-Time':'10/13/2026'})]))])
        original=deepcopy(imported)
        snapshot=imported_snapshot(imported)
        frames,capacity=report_frames(snapshot,{'mode':'excel','capacity_month':'2026-10'})
        self.assertEqual({period['Date']:period['Received'] for period in snapshot['reports']['daily']},
                         {'2026-10-13':2,'2026-10-10':1})
        self.assertEqual({day['Date']:day['Raw Received'] for day in capacity['daily']},
                         {'2026-10-09':1,'2026-10-13':2})
        self.assertEqual(imported,original)
        filtered=all_products_date_filter(1,frames['All Products'],'2026-10-13')['setBasicFilter']['filter']
        self.assertEqual(list(filtered['criteria']),[str(frames['All Products'][0].index('Date'))])
        # A real completion on the 14th must still be reported on that day.
        imported['rows'][0].update(Status='Completed and Delivered',**{'Out Time':'10/14/2026'})
        capacity=report_frames(imported_snapshot(imported),{'mode':'excel','capacity_month':'2026-10'})[1]
        last=capacity['daily'][-1]
        self.assertEqual((last['Date'],last['Raw Received'],last['Completed']),('2026-10-14',0,1))

    def test_google_sheet_round_trip_and_manual_edit_keep_both_copies(self):
        baseline=editable_frames(self.snapshot(),{'mode':'excel'})
        unchanged,events=reconcile(self.imported,baseline,deepcopy(baseline))
        self.assertFalse(events)
        self.assertEqual(len(unchanged['rows']),4)
        remote=deepcopy(baseline)
        values=remote['All Products'];headers=values[0]
        for cells in values[1:]:
            if cells[headers.index('Order Number')]=='A' and cells[headers.index('Source workbook')]=='other.xlsx':
                cells[headers.index('Status')]='Cancelled'
        updated,events=reconcile(self.imported,baseline,remote)
        copies={record['Source workbook']:record['Status'] for record in updated['rows'] if record['Order Number']=='A'}
        self.assertEqual(copies,{'full.xlsx':'Completed and Delivered','other.xlsx':'Cancelled'})
        self.assertEqual(len(events),1)
        for kind in ('missing','blank'):
            bad=deepcopy(baseline);values=bad['All Products'];index=values[0].index('Source workbook')
            if kind=='missing':
                for cells in values:cells.pop(index)
            else:values[1][index]=''
            with self.assertRaisesRegex(ValueError,'Source workbook'):
                reconcile(self.imported,baseline,bad)

    def test_date_editor_targets_selected_workbook_and_rejects_ambiguous_number(self):
        app=Flask(__name__)
        register_report_routes(app,self.workspace,threading.Lock(),self.snapshot,lambda:None,lambda:None)
        client=app.test_client()
        self.assertEqual(client.get('/api/order-details?order=A&mode=excel').status_code,409)
        editor=client.get('/api/order-details?order=A&mode=excel&source_workbook=full.xlsx').json
        self.assertNotIn('Source workbook',editor['editable_columns'])
        with patch('threading.Thread.start'):
            response=client.post('/api/order-details',json={'order_number':'A','mode':'excel','month':'',
                'source_workbook':editor['source_workbook'],'version':editor['version'],
                'report_date':'2026-10-01','changes':{'Status':'Cancelled'}})
        self.assertEqual(response.status_code,200,response.json)
        copies={record['Source workbook']:record['Status'] for record in self.workspace.read()['imported']['rows'] if record['Order Number']=='A'}
        self.assertEqual(copies,{'full.xlsx':'Cancelled','other.xlsx':'Completed and Delivered'})

    def test_status_rename_checks_workbook_records_independently(self):
        snapshot=self.snapshot()
        selected=[key(record) for record in snapshot['sheets']['Overview']['rows'] if record['Status']=='Completed and Delivered']
        self.assertEqual(len(selected),3)
        with self.assertRaisesRegex(ValueError,'changed since'):
            rename_status(self.workspace,None,snapshot,'Completed and Delivered','Cancelled',['A','C'])
        self.assertEqual(rename_status(self.workspace,None,snapshot,'Completed and Delivered','Cancelled',selected),3)
        self.assertEqual(sum(record['Status']=='Cancelled' for record in self.workspace.read()['imported']['rows']),3)

    def test_old_global_dataset_restores_other_copy_and_preserves_owner_edits(self):
        original=deepcopy(self.imported)
        legacy=deepcopy(self.imported)
        legacy.pop('order_identity')
        winning={record['Order Number']:record for source in legacy['sources'] for record in source['rows']}
        legacy['rows']=list(deepcopy(winning).values())
        next(record for record in legacy['rows'] if record['Order Number']=='A')['Client']='Saved client'
        updated=upgrade_workbook_orders(legacy)
        copies={record['Source workbook']:record for record in updated['rows'] if record['Order Number']=='A'}
        self.assertEqual(len(updated['rows']),4)
        self.assertEqual(copies['other.xlsx']['Client'],'Saved client')
        self.assertNotEqual(copies['full.xlsx'].get('Client'),'Saved client')
        self.assertEqual(self.imported,original)
        self.workspace.save(imported=legacy,row_count=3)
        reopened=ReportWorkspace(self.workspace.store)
        self.assertEqual(reopened.public()['row_count'],4)
        self.assertTrue(list((Path(self.folder.name)/'backups').glob('before-update-*.zip')))
        self.assertTrue(reopened.read()['cloud_reset'])

    def test_replacing_one_file_resets_only_that_workbooks_records(self):
        previous=deepcopy(self.imported)
        for record in previous['rows']:
            if record['Order Number']=='A':record['Client']='Saved '+record['Source workbook']
        snapshot=imported_snapshot(previous)
        previous['view_members']={label:[key(record) for record in snapshot['sheets'][label]['rows']] for label in ('Full Title','Remaining Products')}
        replacement=read_report_files([('full.xlsx',excel([row('A',Client='New full'),row('B')]))])
        next_import=combine_sources([replacement['sources'][0],self.imported['sources'][1]])
        updated=preserve_sheet_edits(previous,next_import,['full.xlsx'])
        copies={record['Source workbook']:record.get('Client') for record in updated['rows'] if record['Order Number']=='A'}
        self.assertEqual(copies,{'full.xlsx':'New full','other.xlsx':'Saved other.xlsx'})

    def test_publishing_replaces_old_rows_and_the_product_views_partition_only_imports(self):
        book=ReportBook()
        for title in ('All Products','Full_Search_OCT_2026','Remaining_Search_OCT_2026'):
            sheet=book.add(title,[row('OLD-'+str(index)) for index in range(15)])
            book.props[sheet.id]={'gridProperties':{'rowCount':12436,'columnCount':30}}
        book.values_batch_clear=Mock()
        with tempfile.TemporaryDirectory() as root:
            publish_reports(book,self.snapshot(),{'mode':'excel'},root)
        counts={}
        for title in ('All Products','Full_Search_OCT_2026','Remaining_Search_OCT_2026'):
            values=book.worksheet(title).get_all_values();column=values[0].index('Order Number')
            records=[cells[column] for cells in values[1:] if len(cells)>column and cells[column]]
            counts[title]=len(records)
            self.assertFalse(any(str(number).startswith('OLD-') for number in records))
        self.assertEqual(counts['All Products'],4)
        self.assertEqual(counts['Full_Search_OCT_2026']+counts['Remaining_Search_OCT_2026'],4)
        ranges=book.values_batch_clear.call_args.kwargs['body']['ranges']
        self.assertTrue(any(value.startswith("'All Products'!A6:") and value.endswith('12436') for value in ranges))


if __name__=='__main__':unittest.main()
