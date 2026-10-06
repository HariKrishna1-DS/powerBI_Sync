import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backup_protection import MAGIC, protect, unprotect, migrate_backups
from preview_store import PreviewStore
from workspace_backup import save_safety_backup, restore_backup, make_backup


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI acceptance')
class ProtectionTests(unittest.TestCase):
    def test_windows_protected_backup_restores_and_detects_damage(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DATATRACE_DESKTOP': '1'}):
            store = PreviewStore(Path(folder) / 'previews')
            saved = save_safety_backup(store, 'before-update')
            raw = saved.read_bytes()
            self.assertTrue(raw.startswith(MAGIC))
            self.assertTrue(unprotect(raw).startswith(b'PK'))
            restore_backup(store, raw)
            damaged = bytearray(raw)
            damaged[-1] ^= 1
            with self.assertRaises(ValueError):
                restore_backup(store, bytes(damaged))

    def test_migration_preserves_original_on_failure_and_verifies_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DATATRACE_DESKTOP': '1'}):
            root = Path(folder)
            original = root / 'before-update-fixture.zip'
            original.write_bytes(b'archive data')
            with patch('workspace_backup.os.fsync', side_effect=OSError('full')):
                self.assertEqual(migrate_backups(root)['failed'], 1)
            self.assertTrue(original.exists())
            self.assertEqual(migrate_backups(root)['protected'], 1)
            self.assertFalse(original.exists())
            self.assertEqual(unprotect(original.with_suffix('.tvbackup').read_bytes()), b'archive data')
            self.assertEqual(migrate_backups(root)['protected'], 0)

    def test_encryption_failure_never_returns_plaintext(self):
        with patch.dict(os.environ, {'DATATRACE_DESKTOP': '1'}), patch('backup_protection._transform', side_effect=ValueError('unavailable')):
            with self.assertRaises(ValueError):
                protect(b'private data')

    def test_portable_container_includes_cloud_archives_without_source_windows_binding(self):
        from cloud_retention import archive, plan, decode
        from test_cloud_retention import Book
        from io import BytesIO
        from zipfile import ZipFile
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'DATATRACE_DESKTOP': '1'}):
            store = PreviewStore(Path(folder) / 'source' / 'previews')
            book = Book()
            result = archive(book, store.root.parent / 'cloud-archives', plan(book)['fingerprint'])
            exported = make_backup(store).getvalue()
            name = 'cloud-archives/' + result['archive']
            with ZipFile(BytesIO(exported)) as zipped:
                self.assertFalse(zipped.read(name).startswith(MAGIC))
                decode(zipped.read(name))
            other = PreviewStore(Path(folder) / 'destination' / 'previews')
            restore_backup(other, exported)
            restored = (other.root.parent / name).read_bytes()
            self.assertTrue(restored.startswith(MAGIC))
            self.assertEqual(decode(restored)['workbook'], book.id)
