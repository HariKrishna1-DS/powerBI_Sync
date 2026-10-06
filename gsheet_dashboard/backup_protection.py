"""Windows-account protection for local recovery archives; no plaintext fallback."""
import ctypes
from ctypes import wintypes
import os

MAGIC = b'TVTRACKER-DPAPI-1\n'


def enabled():
    return os.environ.get('DATATRACE_DESKTOP') == '1'


def _transform(raw, decrypt=False):
    if os.name != 'nt':
        raise ValueError('Windows account encryption is required for local desktop backups.')
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('The recovery archive could not be unlocked by this Windows account.' if decrypt
                         else 'Windows could not protect the recovery archive. No history was removed.')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def protect(raw):
    if not enabled():
        return raw
    sealed = MAGIC + _transform(raw)
    if unprotect(sealed) != raw:
        raise ValueError('Encrypted archive verification failed.')
    return sealed


def unprotect(raw):
    return _transform(raw[len(MAGIC):], decrypt=True) if raw.startswith(MAGIC) else raw


def suffix():
    return '.tvbackup' if enabled() else '.zip'


def migrate_backups(folder):
    """Replace only app-owned ZIP archives after durable encryption/readback."""
    from workspace_backup import write_verified_backup
    result = {'protected': 0, 'failed': 0}
    if not enabled() or not folder.exists():
        return result
    for source in folder.glob('*.zip'):
        if not source.name.startswith(('before-delete-', 'before-update-', 'before-restore-', 'retention-')):
            continue
        try:
            if source.is_symlink() or source.resolve().parent != folder.resolve():
                raise ValueError('Backup path is outside the workspace.')
            raw = source.read_bytes()
            target = source.with_suffix('.tvbackup')
            if target.exists():
                if unprotect(target.read_bytes()) != raw:
                    raise ValueError('Existing encrypted backup differs.')
            else:
                write_verified_backup(target, protect(raw))
            if unprotect(target.read_bytes()) != raw:
                raise ValueError('Backup readback differs.')
            source.unlink()
            result['protected'] += 1
        except (OSError, ValueError):
            result['failed'] += 1
    return result
