"""Comparison categories and exports must reconcile with the selected SLA Status report."""
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from flask import Flask
from openpyxl import Workbook, load_workbook
from preview_store import PreviewStore
from report_workspace import ReportWorkspace, register_report_routes
from sla_compare import (compare_sla_with_production, export_comparison_excel,
                         read_production_file, update_order_production_status)


class SlaCompareTests(unittest.TestCase):
    def setUp(self):
        self.report = {'as_of': '2026-10-14', 'rows': [
            {'Order Number': number, 'Status': 'Search In Progress',
             'SLA Category': category, 'SLA Expiration': expiration}
            for number, category, expiration in [
                ('NEG-1', 'Negative SLA', '-2d'),
                ('NEG-2', 'Negative SLA', '-1h'),
                ('TODAY', 'Today SLA', '1d'),
                ('FUTURE', 'Future SLA', '2d'),
            ]], 'excluded_rows': [{'Order Number': 'EXCLUDED', 'Status': 'Cancelled'}]}
        self.production = [{'order_number': number, 'status': 'QC in Progress', 'prod_sla': expiry}
                           for number, expiry in [('NEG-1', '2099-01-01'), ('TODAY', '2000-01-01'),
                                                  ('FUTURE', ''), ('PROD-ONLY', '2000-01-01')]]

    def test_categories_and_negative_membership_match_sla_status_exactly(self):
        result = compare_sla_with_production(self.report, self.production)
        expected = {row['Order Number'] for row in self.report['rows'] if row['SLA Category'] == 'Negative SLA'}
        actual = {row['order_number'] for row in result['orders'] if row['sla_category'] == 'Negative SLA'}
        self.assertEqual(actual, expected)
        self.assertEqual(result['sla_summary']['totals']['Negative SLA'], 1)
        self.assertEqual(result['sla_summary']['totals']['Grand Total'], 3)
        self.assertEqual(result['sla_summary']['totals']['Not in SLA Queue'], 0)
        self.assertNotIn('Not in Production Report', {row['Status'] for row in result['sla_summary']['rows']})
        self.assertNotIn('EXCLUDED', {row['order_number'] for row in result['orders']})
        self.assertEqual(next(row for row in result['orders'] if row['order_number'] == 'NEG-2')['match_type'], 'sla_only')
        self.assertEqual(next(row for row in result['orders'] if row['order_number'] == 'PROD-ONLY')['sla_category'], 'Not in SLA Queue')

    def test_completed_excel_match_keeps_preview_status(self):
        self.production[0]['status'] = 'Completed and Delivered'
        result = compare_sla_with_production(self.report, self.production)
        order = next(row for row in result['orders'] if row['order_number'] == self.production[0]['order_number'])
        preview = next(row for row in self.report['rows'] if row['Order Number'] == order['order_number'])
        self.assertEqual(order['prod_status'], preview['Status'])
        self.assertEqual(order['imported_prod_status'], 'Completed and Delivered')
        self.assertEqual(order['match_type'], 'same_status')
        self.assertFalse(order['status_changed'])
        self.assertEqual(order['change_label'], 'Unchanged')
        self.assertFalse(any(row['Status'] == 'Completed and Delivered' for row in result['sla_summary']['rows']))
        self.assertEqual(self.production[0]['status'], 'Completed and Delivered')

    def test_summary_keeps_the_original_queue_scope_and_columns(self):
        self.production[0]['status'] = 'Typing in Progress'
        self.production[-1]['status'] = 'Typing in Progress'
        result = compare_sla_with_production(self.report, self.production)
        typing = next(row for row in result['sla_summary']['rows'] if row['Status'] == 'Typing in Progress')
        self.assertEqual(typing['Grand Total'], 1)
        self.assertEqual(typing['Negative SLA'], 1)
        self.assertEqual(typing['Not in SLA Queue'], 0)
        book = load_workbook(export_comparison_excel(result, table_scope='sla_summary'))
        headers = [cell.value for cell in book.active[4]]
        self.assertEqual(headers, ['Production Status', 'Future SLA', 'Negative SLA', 'Today SLA', 'Grand Total'])
        rows = list(book.active.iter_rows(min_row=5, values_only=True))
        exported = dict(zip(headers, next(row for row in rows if row[0] == 'Typing in Progress')))
        self.assertEqual(exported['Grand Total'], 1)
        popup_book = load_workbook(export_comparison_excel(result, table_scope='orders',
                                  filter_type='queue', prod_status='Typing in Progress'))
        self.assertEqual([row[0] for row in popup_book.active.iter_rows(min_row=5, values_only=True)], ['NEG-1'])

    def test_production_expirations_cannot_change_categories_or_exports(self):
        before = compare_sla_with_production(self.report, self.production)
        changed = deepcopy(self.production)
        for row in changed:
            row['prod_sla'] = '1900-01-01'
        self.assertEqual(compare_sla_with_production(self.report, changed), before)
        book = load_workbook(export_comparison_excel(before, table_scope='orders', category='Negative SLA'))
        rows = list(book.active.iter_rows(min_row=5, values_only=True))
        self.assertEqual({row[0] for row in rows}, {'NEG-1', 'NEG-2'})
        self.assertEqual({row[6] for row in rows}, {'-2d', '-1h'})

    def test_home_builders_from_sla_status_are_included_once_without_other_missing_orders(self):
        self.report['rows'][1]['Status'] = 'Home Builders'
        result = compare_sla_with_production(self.report, self.production)
        homes = next(row for row in result['sla_summary']['rows'] if row['Status'] == 'Home Builders')
        self.assertEqual(homes['Grand Total'], 1)
        self.assertEqual(homes['Negative SLA'], 1)
        order = next(row for row in result['orders'] if row['order_number'] == 'NEG-2')
        self.assertEqual(order['prod_status'], 'Home Builders')
        self.assertFalse(order['status_changed'])
        self.assertNotIn('Not in Production Report', {row['Status'] for row in result['sla_summary']['rows']})
        book = load_workbook(export_comparison_excel(result, table_scope='orders',
                             filter_type='summary', summary_status='Home Builders'))
        self.assertEqual([row[0] for row in book.active.iter_rows(min_row=5, values_only=True)], ['NEG-2'])
        matched = self.production + [{'order_number': 'NEG-2', 'status': 'QC in Progress'}]
        result = compare_sla_with_production(self.report, matched)
        self.assertEqual(result['sla_summary']['totals']['Grand Total'], 4)
        self.assertEqual(next(row for row in result['sla_summary']['rows'] if row['Status'] == 'Home Builders')['Grand Total'], 1)

    def test_duplicate_status_matches_the_queue_product_instead_of_last_workbook(self):
        self.report['rows'][0]['Product'] = 'Update Full Ti..'
        rows = [{'order_number': 'NEG-1', 'product': product, 'status': status, 'source_sheet': source}
                for product, status, source in [('Update', 'Waiting for Effective Date', 'C-O.xlsx'),
                                               ('Full Title', 'Completed and Delivered', 'Full.xlsx')]]
        for candidates in (rows, list(reversed(rows))):
            result = compare_sla_with_production(self.report, candidates)
            order = next(item for item in result['orders'] if item['order_number'] == 'NEG-1')
            self.assertEqual(order['prod_status'], 'Waiting for Effective Date')
            self.assertEqual(order['sla_category'], 'Negative SLA')

    def test_status_edits_keep_negative_membership_and_unmatched_orders(self):
        result = compare_sla_with_production(self.report, self.production)
        update_order_production_status(result, 'NEG-1', 'Completed and Delivered')
        self.assertEqual(result['sla_summary']['totals']['Negative SLA'], 1)
        self.assertEqual({o['order_number'] for o in result['orders'] if o['sla_category'] == 'Negative SLA'}, {'NEG-1', 'NEG-2'})

    def test_blank_status_is_not_reported_as_a_status_movement(self):
        self.production[0]['status'] = ''
        result = compare_sla_with_production(self.report, self.production)
        order = next(row for row in result['orders'] if row['order_number'] == 'NEG-1')
        self.assertFalse(order['status_changed'])
        self.assertEqual(order['match_type'], 'same_status')

    def test_order_numbers_preserve_punctuation_like_sla_status(self):
        self.report['rows'][1]['Order Number'] = 'NEG1'
        result = compare_sla_with_production(self.report, self.production)
        self.assertEqual(result['metrics']['total_sla'], 4)
        self.assertEqual(result['sla_summary']['totals']['Negative SLA'], 1)

    def test_excel_and_csv_ignore_expiration_and_eta_columns(self):
        book = Workbook()
        book.active.append(['Order Number', 'Product', 'Status', 'SLA Expiration', 'ETA'])
        book.active.append(['NEG-1', 'Full Title', 'QC in Progress', '2099-01-01', '2000-01-01'])
        stream = BytesIO()
        book.save(stream)
        csv = b'Order Number,Product,Status,SLA Expiration,ETA\nNEG-1,Full Title,QC in Progress,2099-01-01,2000-01-01\n'
        for content, name in [(stream.getvalue(), 'production.xlsx'), (csv, 'production.csv')]:
            with self.subTest(name=name):
                parsed = read_production_file(content, filename=name)
                self.assertEqual(parsed[0]['prod_sla'], '')
                result = compare_sla_with_production(self.report, parsed)
                self.assertEqual(result['sla_summary']['totals']['Negative SLA'], 1)

    def test_api_uses_the_same_selected_preview_as_sla_status(self):
        with tempfile.TemporaryDirectory() as folder:
            store = PreviewStore(Path(folder) / 'previews')
            rows = [{'Order Number': 'NEG-1', 'Status': 'Search In Progress', 'SLA Expiration': '-2d', 'SLA Expiration Overdue': True},
                    {'Order Number': 'NEG-2', 'Status': 'Search In Progress', 'SLA Expiration': '-1h'},
                    {'Order Number': 'TODAY', 'Status': 'Search In Progress', 'SLA Expiration': '1d'}]
            columns = list(rows[0])
            store.restore(1, columns, rows, created='2026-10-14T12:00:00Z')
            store.restore(2, columns, [dict(rows[0], **{'Order Number': 'OTHER-PREVIEW'})], created='2026-10-15T12:00:00Z')
            workspace = ReportWorkspace(store)
            workspace.save(mode='tracker', sla_preview_id=1)
            from report_workspace import read_report_files
            from test_pdf_report_workspace import excel, row
            workspace.save(imported=read_report_files([('old.xlsx', excel([row('NEG-1', 'Cancelled')]))]))
            app = Flask(__name__)
            register_report_routes(app, workspace, threading.Lock(), Mock(return_value={}),
                                   Mock(side_effect=RuntimeError('offline')), lambda: None)
            client = app.test_client()
            csv = b'Order Number,Product,Status,SLA Expiration\nNEG-1,Full Title,QC in Progress,2099-01-01\nTODAY,Full Title,QC in Progress,2000-01-01\n'
            response = client.post('/api/sla-compare', data={'file': (BytesIO(csv), 'production.csv')})
            self.assertEqual(response.status_code, 200)
            comparison = response.json
            status = client.get('/api/sla-status').json
            refreshed = client.get('/api/sla-compare').json
            self.assertEqual(refreshed['source_files'], 'production.csv')
            self.assertEqual(refreshed['orders'], comparison['orders'])
            restarted = Flask('restarted')
            register_report_routes(restarted, workspace, threading.Lock(), Mock(return_value={}),
                                   Mock(side_effect=RuntimeError('offline')), lambda: None)
            restored = restarted.test_client().get('/api/sla-compare').json
            self.assertEqual(restored['source_files'], 'production.csv')
            self.assertEqual(restored['orders'], comparison['orders'])
            self.assertNotIn('sla_comparison_report', workspace.public())
            self.assertEqual(comparison['selected_preview_id'], status['preview_id'])
            self.assertEqual(comparison['sla_summary']['totals']['Negative SLA'], 1)
            self.assertEqual({o['order_number'] for o in comparison['orders'] if o['sla_category'] == 'Negative SLA'},
                             {o['Order Number'] for o in status['rows'] if o['SLA Category'] == 'Negative SLA'})
            switched = client.get('/api/sla-compare?preview_id=2').json
            self.assertEqual({o['order_number'] for o in switched['orders'] if o['sla_category'] == 'Negative SLA'}, {'OTHER-PREVIEW'})
            active = client.get('/api/sla-compare?preview_id=1').json
            order = next(row for row in active['orders'] if row['order_number'] == 'NEG-1')
            edit = {'preview_id': 1, 'order_number': 'NEG-1', 'expiration': '2026-10-17T14:30',
                    'expected_revision': order['sla_revision']}
            invalid = client.post('/api/sla-compare/expiration', json=dict(edit, expiration='not a date'))
            self.assertEqual(invalid.status_code, 400)
            saved = client.post('/api/sla-compare/expiration', json=edit)
            self.assertEqual(saved.status_code, 200, saved.json)
            updated = next(row for row in saved.json['result']['orders'] if row['order_number'] == 'NEG-1')
            self.assertEqual(updated['sla_expiration'], '2026-10-17 14:30:00')
            self.assertEqual(updated['sla_category'], 'Future SLA')
            shared = client.get('/api/sla-status?preview_id=1').json
            shared_row = next(row for row in shared['rows'] if row['Order Number'] == 'NEG-1')
            self.assertEqual(shared_row['SLA Expiration'], updated['sla_expiration'])
            self.assertEqual(shared_row['SLA Category'], updated['sla_category'])
            self.assertEqual(store.get(1)['rows'][0]['SLA Expiration'], '-2d')
            self.assertEqual(store.get(2)['rows'][0]['SLA Expiration'], '-2d')
            self.assertEqual(client.post('/api/sla-compare/expiration', json=edit).status_code, 409)
            imported_before = workspace.read()['imported']
            cleared = client.post('/api/sla-compare?clear=1&preview_id=1')
            self.assertEqual(cleared.status_code, 200)
            self.assertFalse(cleared.json['has_production'])
            self.assertEqual(cleared.json['source_files'], '')
            self.assertFalse(client.get('/api/sla-compare').json['has_production'])
            self.assertEqual(workspace.read()['imported'], imported_before)
            self.assertEqual(len(store.list()), 2)
            after_clear = Flask('after_clear')
            register_report_routes(after_clear, workspace, threading.Lock(), Mock(return_value={}),
                                   Mock(side_effect=RuntimeError('offline')), lambda: None)
            after_client = after_clear.test_client()
            self.assertFalse(after_client.get('/api/sla-compare').json['has_production'])
            reuploaded = after_client.post('/api/sla-compare', data={'file': (BytesIO(csv), 'replacement.csv')})
            self.assertTrue(reuploaded.json['has_production'])
            self.assertEqual(after_client.get('/api/sla-compare').json['source_files'], 'replacement.csv')


if __name__ == '__main__':
    unittest.main()
