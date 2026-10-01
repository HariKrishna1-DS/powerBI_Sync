"""Optional Neon integration checks, isolated in a disposable schema."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
import psycopg
from psycopg import sql

from migrate_to_neon import migrate
from preview_store import PreviewStore


@unittest.skipUnless(os.getenv('NEON_TEST_URL'), 'Set NEON_TEST_URL to run Neon integration checks')
class NeonStorageTests(unittest.TestCase):
    def setUp(self):
        self.url = os.environ['NEON_TEST_URL']
        self.schema = 'neon_test_' + uuid4().hex
        self.original_connect = psycopg.connect
        with self.original_connect(self.url) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
        self.addCleanup(self.drop_schema)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env_patch = patch.dict(os.environ, {'DATABASE_URL': self.url})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        self.connection_patch = patch.object(PreviewStore, 'schema', self.schema)
        self.connection_patch.start()
        self.addCleanup(self.connection_patch.stop)

    def drop_schema(self):
        with self.original_connect(self.url) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))

    def test_roundtrip_restore_and_sequence_after_delete(self):
        store = PreviewStore(self.root, database_url=self.url)
        frame = pd.DataFrame([{'Order Number': '001', 'Unicode': '₹', 'Blank': None}])
        first = store.save(frame)
        self.assertEqual(first['rows'][0]['Order Number'], '001')
        self.assertEqual(first['rows'][0]['Blank'], '')
        store.restore(27, first['columns'], first['rows'])
        self.assertEqual(store.save(frame)['id'], 28)
        store.delete(28)
        store.restore(27, first['columns'], first['rows'])
        self.assertEqual(store.save(frame)['id'], 29)
        store.delete(first['id'])
        with self.assertRaises(KeyError):
            store.get(first['id'])

    def test_migration_is_repeatable_and_conflicts_roll_back(self):
        local = PreviewStore(self.root, database_url='')
        frame = pd.DataFrame([{'Order Number': '001'}, {'Order Number': '001'}])
        first = local.save(frame)
        migrate(self.root)
        migrate(self.root)
        remote = PreviewStore(self.root, database_url=self.url)
        self.assertEqual(remote.get(first['id']), first)
        self.assertEqual(len(remote.list()), 1)
        local.save(frame)
        conflicting = remote.save(pd.DataFrame([{'Order Number': 'different'}]))
        local.save(frame)
        with self.assertRaises(RuntimeError):
            migrate(self.root)
        self.assertEqual(remote.get(conflicting['id']), conflicting)
        self.assertEqual(len(remote.list()), 2)

    def test_sla_correction_roundtrip_and_update(self):
        store = PreviewStore(self.root, database_url=self.url)
        store.save_sla_correction('001', '2026-09-30', 'On Time')
        reopened = PreviewStore(self.root, database_url=self.url)
        self.assertEqual(reopened.sla_corrections(), {('001', '2026-09-30'): 'On Time'})
        reopened.save_sla_correction('001', '2026-09-30', 'Missed')
        self.assertEqual(store.sla_corrections(), {('001', '2026-09-30'): 'Missed'})

    def test_bulk_sla_corrections_persist_together(self):
        store = PreviewStore(self.root, database_url=self.url)
        store.save_sla_corrections([('001', '2026-09-30', 'On Time'), ('002', '2026-09-30', 'Missed')])
        reopened = PreviewStore(self.root, database_url=self.url)
        self.assertEqual(reopened.sla_corrections(), {('001', '2026-09-30'): 'On Time', ('002', '2026-09-30'): 'Missed'})
        with self.assertRaises(ValueError):
            reopened.save_sla_corrections([('001', '2026-09-30', 'Missed'), ('002', 'invalid', 'On Time')])
        self.assertEqual(store.sla_corrections()[('001', '2026-09-30')], 'On Time')


if __name__ == '__main__':
    unittest.main()
