from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

from backup_protection import MAGIC
from cloud_backend.migration import Migration
from shared_backend import CloudError
from sheets_repository import INDEX_TITLE
from test_cloud_publication import ProjectionBook
from test_tracker_v2 import Sheet
from tracker_sync import FULL, REMAINING
from cloud_backend.publication import PROTOCOL, RECEIPT, digest
from sheets_writer import SHARED_TITLE, SHARED_ID


class MigrationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.workspace, self.worker = str(uuid.uuid4()), str(uuid.uuid4())
        self.book = ProjectionBook()
        headers = ['Order Number', 'Product', 'Status', 'Comments', 'Preview']
        self.book.sheets = [Sheet(FULL, 10, [headers, ['001', 'Full Title', 'Search In Progress', 'Keep', 'preview44']]),
            Sheet(REMAINING, 11, [headers]), Sheet(INDEX_TITLE, 12, [['Preview ID'], ['47']]),
            Sheet('Personal notes', 13, [['Unrelated']])]
        self.rows = [{'Order Number': '001', 'Product': 'Full Title', 'Status': 'Search In Progress',
            'Comments': 'Keep', 'Preview': 'preview44'}]
        self.status = {'mode': 'shadow', 'revision': 0, 'pending_captures': 0,
            'job': None, 'queue_scope': 'queue', 'spreadsheet': None, 'worker': None}
        self.rpc = Mock()
        self.calls = []
        self.lose_reply = False
        def call(name, body):
            self.calls.append((name, deepcopy(body)))
            if name == 'tv_workspace_status':
                return dict(self.status)
            if name == 'tv_seed_workspace':
                self.status['revision'] = 1
                return {'revision': 1, 'orders': len(body['p_rows']), 'next_sequence': body['p_next_sequence']}
            if name == 'tv_activate_workspace':
                self.status.update(mode='active', spreadsheet=self.book.id, worker=self.worker)
                if self.lose_reply:
                    self.lose_reply = False
                    raise CloudError('Lost activation reply', 'retry')
                return {'mode': 'active', 'revision': 1, 'spreadsheet': self.book.id, 'worker': self.worker}
            raise AssertionError(name)
        self.rpc.call.side_effect = call
        self.rpc.snapshot.return_value = {'revision': 1, 'orders': [{'data': self.rows[0]}]}
        for target, kwargs in (
            ('cloud_backend.migration.enabled', {'return_value': True}),
            ('cloud_backend.migration.protect', {'side_effect': lambda raw:MAGIC+raw}),
            ('cloud_backend.migration.unprotect', {'side_effect': lambda raw:raw[len(MAGIC):]})):
            helper = patch(target, **kwargs)
            helper.start()
            self.addCleanup(helper.stop)
        self.migration = Migration(self.rpc, self.book, self.root, 'queue')

    def test_preview_is_read_only_preserves_columns_and_recovers_shared_sequence(self):
        preview = self.migration.preview(self.workspace)
        self.assertEqual(preview['next_sequence'], 48)
        self.assertEqual(sum(item['orders'] for item in preview['counts']), 1)
        self.assertEqual(self.migration._load(preview['id'])['rows'], self.rows)
        self.assertEqual(self.migration.latest(self.workspace), preview)
        self.assertEqual(self.book.batches, [])
        self.assertNotIn('tables', preview)
        self.assertNotIn('rows', preview)

    def test_encryption_failure_prevents_seed_or_fence(self):
        with patch('cloud_backend.migration.protect', return_value=b'plaintext'):
            with self.assertRaisesRegex(ValueError, 'protect'):
                self.migration.preview(self.workspace)
        self.assertEqual(list(self.root.glob('*.tvmigration')), [])
        self.assertFalse(any(name == 'tv_seed_workspace' for name, _ in self.calls))

    def test_reserved_and_local_sequences_are_preserved_and_rechecked(self):
        self.book.sheets.append(Sheet(SHARED_TITLE, SHARED_ID,
            [['Protocol', 'Enabled', 'Next preview'], ['tv-tracker-shared-v2', 'stamp', '52']]))
        local = Mock()
        local.next_number.return_value = 50
        self.migration.local_store = local
        plan = self.migration.preview(self.workspace)
        self.assertEqual(plan['next_sequence'], 52)
        local.next_number.return_value = 54
        with self.assertRaisesRegex(CloudError, 'changed after review'):
            self.migration.activate(self.workspace, plan['id'], self.worker, True, True)
        self.assertFalse(any(name == 'tv_seed_workspace' for name, _ in self.calls))
        self.assertEqual(self.migration.preview(self.workspace)['next_sequence'], 54)

    def test_duplicate_orders_and_queue_mismatch_are_rejected(self):
        self.book.sheets[1].values.append(['001', 'Update', 'Available', '', 'preview44'])
        with self.assertRaisesRegex(ValueError, 'multiple'):
            self.migration.preview(self.workspace)
        self.status['queue_scope'] = 'other'
        with self.assertRaisesRegex(CloudError, 'queue'):
            self.migration.preview(self.workspace)

    def test_workbook_edits_after_review_preserve_snapshot_and_prevent_seed(self):
        plan = self.migration.preview(self.workspace)
        self.book.sheets[0].values[1][3] = 'Changed manually'
        with self.assertRaisesRegex(CloudError, 'changed after review'):
            self.migration.activate(self.workspace, plan['id'], self.worker, True, True)
        self.assertFalse(any(name == 'tv_seed_workspace' for name, _ in self.calls))
        self.assertEqual(self.migration._load(plan['id'])['rows'], self.rows)

    def test_lost_activation_response_reconciles_same_operation_after_restart(self):
        plan = self.migration.preview(self.workspace)
        self.lose_reply = True
        with patch('cloud_backend.migration.SheetsPublisher') as publisher:
            with self.assertRaises(CloudError):
                self.migration.activate(self.workspace, plan['id'], self.worker, True, True)
            publisher.return_value.bind.assert_called_once()
        restored = Migration(self.rpc, self.book, self.root, 'queue')
        with patch('cloud_backend.migration.SheetsPublisher') as publisher:
            result = restored.activate(self.workspace, plan['id'], self.worker, True, True)
            publisher.assert_not_called()
        self.assertEqual(result['state'], 'active')
        activations = [body for name, body in self.calls if name == 'tv_activate_workspace']
        self.assertEqual(activations[0], activations[1])
        self.assertEqual(sum(name == 'tv_seed_workspace' for name, _ in self.calls), 1)

    def test_confirmation_wrong_workspace_and_corruption_cannot_activate(self):
        plan = self.migration.preview(self.workspace)
        for reviewed, stopped in ((False, True), (True, False)):
            with self.assertRaises(ValueError):
                self.migration.activate(self.workspace, plan['id'], self.worker, reviewed, stopped)
        with self.assertRaises(ValueError):
            self.migration.activate(str(uuid.uuid4()), plan['id'], self.worker, True, True)
        value = self.migration._load(plan['id'])
        value['tables'][FULL][1][0] = 'Changed'
        self.migration._path(plan['id']).write_bytes(MAGIC+json.dumps(value).encode())
        with self.assertRaisesRegex(ValueError, 'integrity'):
            self.migration.activate(self.workspace, plan['id'], self.worker, True, True)

    def test_bound_baseline_resume_checks_receipt_and_visible_data_before_seed(self):
        plan = self.migration.preview(self.workspace)
        self.book.sheets += [Sheet(SHARED_TITLE, SHARED_ID, [['Protocol', 'Workspace', 'Spreadsheet'],
            [PROTOCOL, self.workspace, self.book.id]]), Sheet(RECEIPT, 100, [['Receipt'], [json.dumps({
            'workspace': self.workspace, 'spreadsheet': self.book.id, 'revision': 0,
            'digest': plan['digest'], 'tabs': sorted(self.migration._load(plan['id'])['tables'])})]])]
        self.book.sheets[0].values[1][3] = 'Edited after fencing'
        with self.assertRaisesRegex(CloudError, 'bound workbook differs'):
            self.migration.activate(self.workspace, plan['id'], self.worker, True, True)
        self.assertFalse(any(name == 'tv_seed_workspace' for name, _ in self.calls))
        self.book.sheets[0].values[1][3] = 'Keep'
        self.assertEqual(self.migration.activate(self.workspace, plan['id'], self.worker, True, True)['state'], 'active')

    def test_existing_publication_revision_cannot_be_reused_as_baseline(self):
        plan = self.migration.preview(self.workspace)
        self.book.sheets += [Sheet(SHARED_TITLE, SHARED_ID, [['Protocol', 'Workspace', 'Spreadsheet'],
            [PROTOCOL, self.workspace, self.book.id]]), Sheet(RECEIPT, 100, [['Receipt'], [json.dumps({
            'workspace': self.workspace, 'spreadsheet': self.book.id, 'revision': 2,
            'digest': digest(self.migration._load(plan['id'])['tables']), 'tabs': list(self.migration._load(plan['id'])['tables'])})]])]
        with self.assertRaisesRegex(CloudError, 'bound workbook differs'):
            self.migration.activate(self.workspace, plan['id'], self.worker, True, True)
        self.assertFalse(any(name == 'tv_seed_workspace' for name, _ in self.calls))

    def test_foreign_workbook_binding_blocks_before_seed(self):
        plan=self.migration.preview(self.workspace)
        self.book.sheets.append(Sheet(SHARED_TITLE,SHARED_ID,[['Protocol','Workspace','Spreadsheet'],
            [PROTOCOL,str(uuid.uuid4()),self.book.id]]))
        with self.assertRaisesRegex(CloudError,'different shared workspace'):
            self.migration.activate(self.workspace,plan['id'],self.worker,True,True)
        self.assertFalse(any(name=='tv_seed_workspace' for name,_ in self.calls))
