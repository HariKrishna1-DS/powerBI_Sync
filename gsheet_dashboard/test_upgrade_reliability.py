from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from operation_journal import OperationJournal
from preview_store import PreviewStore
from production_cache import ProductionCache
from server import compact_job, create_app
from sheet_reads import read_values
from workspace_backup import restore_backup


class UpgradeReliabilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def cache(self):
        return ProductionCache(self.root / 'production-cache.json', 'test-sheet')

    def test_unchanged_reads_are_small_and_external_edits_change_revision(self):
        cache = self.cache()
        row = {'Order Number': '001', 'Status': 'Available'}
        loader = Mock(side_effect=lambda: {'sheets': {'Overview': {'rows': [dict(row)]}}, 'reports': {'daily': []}})
        first = cache.get(loader)
        small = cache.get(loader, known_revision=first['revision'])
        self.assertTrue(small['unchanged'])
        self.assertNotIn('sheets', small)
        self.assertNotIn('reports', small)
        self.assertEqual(loader.call_count, 1)
        row['Status'] = 'Awaiting for Clarification'
        cache.invalidate()
        changed = cache.get(loader, known_revision=first['revision'])
        self.assertNotIn('unchanged', changed)
        self.assertNotEqual(first['revision'], changed['revision'])
        self.assertEqual(changed['sheets']['Overview']['rows'][0]['Status'], row['Status'])
        changed['sheets']['Overview']['rows'].clear()
        self.assertEqual(len(cache.get(loader)['sheets']['Overview']['rows']), 1)

    def test_offline_and_recovery_metadata_arrives_even_when_rows_are_unchanged(self):
        cache = self.cache()
        first = cache.get(lambda: {'sheets': {'Overview': {'rows': []}}})
        offline = cache.get(Mock(side_effect=OSError('offline')), force=True, known_revision=first['revision'])
        self.assertTrue(offline['offline'])
        self.assertTrue(offline['unchanged'])
        self.assertEqual(first['updated_at'], offline['updated_at'])
        recovered = cache.get(lambda: {'sheets': {'Overview': {'rows': []}}}, force=True, known_revision=first['revision'])
        self.assertFalse(recovered['offline'])
        self.assertTrue(recovered['unchanged'])

    def test_successful_live_read_is_current_even_if_disk_cache_write_fails(self):
        cache = self.cache()
        with patch.object(Path, 'write_text', side_effect=OSError('disk full')):
            value = cache.get(lambda: {'sheets': {'Overview': {'rows': [{'Order Number': 'A'}]}}})
        self.assertFalse(value['offline'])
        self.assertIn('offline copy could not be saved', value['cache_warning'])
        self.assertEqual(value['sheets']['Overview']['rows'][0]['Order Number'], 'A')

    def test_concurrent_forced_reads_share_one_load(self):
        cache = self.cache()
        entered, release = threading.Event(), threading.Event()
        def load():
            entered.set()
            release.wait(3)
            return {'sheets': {}}
        loader = Mock(side_effect=load)
        with ThreadPoolExecutor(max_workers=4) as pool:
            first = pool.submit(cache.get, loader, True)
            self.assertTrue(entered.wait(1))
            others = [pool.submit(cache.get, loader, True) for _ in range(3)]
            time.sleep(.05)
            release.set()
            values = [future.result(3) for future in [first, *others]]
        self.assertEqual(loader.call_count, 1)
        self.assertEqual(len({value['updated_at'] for value in values}), 1)

    def test_status_summary_preserves_counts_without_order_contents(self):
        report = {'scanned': 10000, 'changes': [{'Order Number': str(i)} for i in range(10000)],
                  'not_in_latest': ['A','B'], 'ambiguous': [{'Order Number': 'C'}], 'unprocessed': 4}
        original = {'running': False, 'result': {'preview_name': 'preview1', 'pass_report': report}}
        small = compact_job(original)['result']['pass_report']
        self.assertEqual(small['not_in_latest_count'], 2)
        self.assertEqual(small['ambiguous_count'], 1)
        self.assertEqual(small['unprocessed_count'], 4)
        self.assertLess(len(json.dumps(small)), 250)
        self.assertEqual(len(original['result']['pass_report']['changes']), 10000)

    def test_delete_makes_restorable_backup_and_preserves_numbering_and_receipts(self):
        store = PreviewStore(self.root / 'previews')
        store.restore(8, ['Order Number'], [{'Order Number':'001'}])
        store.mark_synced(8, {'added': 1})
        client = create_app(store.root).test_client()
        response = client.delete('/api/previews/8')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.list(), [])
        restore_backup(store, (self.root / 'backups' / response.json['recovery_backup']).read_bytes())
        self.assertEqual(store.get(8)['rows'][0]['Order Number'], '001')
        self.assertEqual(store.pending_count(), 0)

    def test_delete_aborts_when_recovery_copy_cannot_be_saved(self):
        store = PreviewStore(self.root / 'previews')
        store.restore(1, ['Order Number'], [{'Order Number':'001'}])
        client = create_app(store.root).test_client()
        with patch('workspace_backup.save_safety_backup', side_effect=OSError('disk full')):
            self.assertEqual(client.delete('/api/previews/1').status_code, 503)
        self.assertEqual(store.get(1)['rows'][0]['Order Number'], '001')

    def test_schedule_summary_separates_failure_attempt_and_last_success(self):
        store = PreviewStore(self.root / 'previews')
        client = create_app(store.root).test_client()
        journal = OperationJournal(store)
        journal.finish(journal.begin('scheduled_capture'), {})
        success = journal.scheduled_summary()['last_success']
        journal.finish(journal.begin('scheduled_capture'), {'error':'network timeout'})
        schedule = client.get('/api/state?light=1').json['schedule']
        self.assertEqual(schedule['last_success'], success)
        self.assertEqual(schedule['last_status'], 'failed')
        self.assertEqual(schedule['last_error_code'], 'connection')

    def test_batch_reads_preserve_order_formatted_values_and_blank_cells(self):
        class Book:
            def values_batch_get(self, ranges, params):
                self.ranges, self.params = ranges, params
                return {'valueRanges': [{'values':[['ID','Date'],['001','10/05/2026'],['002']]}, {}]}
        book = Book()
        result = read_values(book, [Mock(title="O'Brien"), Mock(title='Empty')])
        self.assertEqual(book.ranges, ["'O''Brien'", "'Empty'"])
        self.assertEqual(book.params['valueRenderOption'], 'FORMATTED_VALUE')
        self.assertEqual(result, [[['ID','Date'],['001','10/05/2026'],['002','']], []])

    def test_partial_batch_read_fails_instead_of_misassigning_data(self):
        class Book:
            def values_batch_get(self, ranges, params):
                return {'valueRanges': []}
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            read_values(Book(), [Mock(title='Production')])

    def test_schedule_restart_and_resume_keep_one_attempt_for_missed_times(self):
        store = PreviewStore(self.root / 'previews')
        (self.root / 'sync_schedule.json').write_text(json.dumps({'enabled':True,'times':['09:00','13:00','17:00']}))
        runner = Mock(return_value={'error':'network unavailable'})
        app = create_app(store.root, runner=runner, time_source=Mock(snapshot=lambda:{}, now=lambda:None))
        noon = datetime(2026,10,5,10,30,tzinfo=timezone.utc)  # 16:00 IST, two missed times
        self.assertTrue(app.extensions['schedule_tick'](noon))
        client = app.test_client()
        for _ in range(100):
            if not client.get('/api/state').json['job']['running']:
                break
            time.sleep(.01)
        self.assertEqual(runner.call_count, 1)
        restarted = create_app(store.root, runner=runner, time_source=Mock(snapshot=lambda:{}, now=lambda:None))
        self.assertFalse(restarted.extensions['schedule_tick'](noon))
        self.assertEqual(runner.call_count, 1)
        schedule = restarted.test_client().get('/api/state').json['schedule']
        self.assertEqual(schedule['triggered_today'], ['09:00','13:00'])
        self.assertEqual(schedule['last_status'], 'failed')

    def test_diagnostics_measure_templates_without_leaking_order_ids_or_queries(self):
        store = PreviewStore(self.root / 'previews')
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'test-token'}):
            client = create_app(store.root).test_client()
        headers = {'X-DataTrace-Token':'test-token'}
        client.get('/api/previews/9876?password=secret-test',headers=headers)
        result = client.get('/api/desktop/diagnostics',headers=headers)
        self.assertIn('/api/previews/<int:number>', result.json['request_metrics'])
        self.assertEqual(result.json['request_metrics']['/api/previews/<int:number>']['errors'], 1)
        self.assertNotIn('9876', result.get_data(as_text=True))
        self.assertNotIn('secret-test', result.get_data(as_text=True))

    def test_revision_api_keeps_legacy_callers_full_and_refreshes_changed_data(self):
        from test_production_sync import Book
        book = Book([[{'Order Number':'A','Product':'Full Title','Status':'Available','Date':'10/05/2026'}],[]])
        with patch.dict(os.environ, {'DATATRACE_DESKTOP':'1','DATATRACE_DESKTOP_TOKEN':'test-token'}):
            client = create_app(self.root / 'previews').test_client()
        headers = {'X-DataTrace-Token':'test-token'}
        with patch('server.target_worksheet', return_value=(book,book.sheets[0])) as read, patch('server.read_pass_report',return_value={}):
            first = client.get('/api/live-sheets',headers=headers).json
            self.assertIn('sheets', first)
            self.assertIn('reports', first)
            small = client.get('/api/live-sheets',query_string={'revision':first['revision']},headers=headers).json
            self.assertTrue(small['unchanged'])
            self.assertNotIn('sheets', small)
            self.assertEqual(read.call_count, 1)
            full = client.get('/api/live-sheets',headers=headers).json
            self.assertEqual(full['sheets'], first['sheets'])
            self.assertEqual(full['reports'], first['reports'])
            client.get('/api/live-sheets?refresh=1',headers=headers)
            self.assertEqual(read.call_count, 2)

    def test_malformed_offline_cache_does_not_prevent_online_recovery(self):
        (self.root/'production-cache.json').write_text('[]')
        value = self.cache().get(lambda:{'sheets':{}})
        self.assertFalse(value['offline'])

    def test_light_poll_preserves_full_sync_report_for_existing_callers(self):
        store = PreviewStore(self.root/'previews')
        row = {'Order Number':'A','Product':'Full Title','Task Name':'Search','Task Status':'Available'}
        store.restore(1, list(row), [row])
        report = {'scanned':1,'added':0,'updated':1,'unchanged':0,'changes':[{'Order Number':'A'}],
                  'not_in_latest':['B'],'ambiguous':[],'unprocessed':3}
        def syncer(frame):
            frame.attrs['pass_report'] = report
            store.stage_sync_report(1, 'fixture-digest', report)
            store.commit_sync_report(1, 'fixture-digest')
            return ['Production']
        client = create_app(store.root, syncer=syncer, time_source=Mock(snapshot=lambda:{}, now=lambda:None)).test_client()
        self.assertEqual(client.post('/api/sync',json={'preview':1}).status_code,202)
        for _ in range(100):
            state = client.get('/api/state').json
            if not state['job']['running']:
                break
            time.sleep(.01)
        self.assertEqual(state['job']['result']['pass_report'],report)
        light = client.get('/api/state?light=1').json['job']['result']['pass_report']
        self.assertEqual(light['not_in_latest_count'],1)
        self.assertEqual(light['unprocessed_count'],3)
        self.assertNotIn('changes',light)
        self.assertEqual(client.get('/api/sync-reports').json['report']['changes'],report['changes'])


if __name__ == '__main__':
    unittest.main()
