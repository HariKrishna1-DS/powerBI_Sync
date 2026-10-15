"""Create a source archive without credentials, captures, or user workbooks."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = json.loads((ROOT / 'desktop' / 'package.json').read_text(encoding='utf-8'))['version']
OUTPUT = ROOT / 'release' / VERSION / f'Tv-Tracker-{VERSION}-source.zip'
EXCLUDE_DIRS = {'.git', '.venv', 'venv', 'env', 'ENV', 'node_modules', '__pycache__', '.pytest_cache',
                '.test-deps', '.desktop-build', '.codex', '.agents', 'release', 'test-results',
                'playwright-report', 'test-output', 'previews', 'dist', 'logs', 'backups', 'connection-backups',
                '.npm-cache', '.cache', 'extractor-diagnostics', 'scratch', 'runtime-data', 'output', 'cloud-archives', 'default_trackers'}
EXCLUDE_SUFFIXES = {'.zip', '.log', '.pyc', '.pyo', '.xlsx', '.csv', '.sqlite', '.sqlite3', '.db', '.pem', '.key', '.tvbackup', '.tvcloud'}
EXCLUDE_NAMES = {'secrets.toml', 'sync_schedule.json', 'sync_status.json', 'production-cache.json', 'desktop-ui-results.json'}


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with zipfile.ZipFile(OUTPUT, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for directory, folders, files in os.walk(ROOT):
            folders[:] = sorted(name for name in folders if name not in EXCLUDE_DIRS and not name.startswith('previews-before-restore-'))
            for name in sorted(files):
                file = Path(directory) / name
                lower = name.lower()
                if file.is_symlink() or lower == '.git' or file.suffix.lower() in EXCLUDE_SUFFIXES or lower in EXCLUDE_NAMES:
                    continue
                if lower.startswith('.env') and lower != '.env.example':
                    continue
                if 'service_account' in lower or lower.startswith(('queue_data', 'settings.vault')) or lower.endswith('.vault') or lower == 'local state':
                    continue
                relative = file.relative_to(ROOT).as_posix()
                data = file.read_bytes()
                hashes[relative] = hashlib.sha256(data).hexdigest()
                archive.writestr(f'Tv-Tracker/{relative}', data)
        archive.writestr('Tv-Tracker/SOURCE_MANIFEST.json', json.dumps({
            'version': VERSION, 'created_utc': datetime.now(timezone.utc).isoformat(),
            'description': 'Tv Tracker desktop source. No user data or baseline workbooks.', 'sha256': hashes,
        }, indent=2))
    with zipfile.ZipFile(OUTPUT) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Source archive integrity check failed.')
        for name, digest in hashes.items():
            if hashlib.sha256(archive.read(f'Tv-Tracker/{name}')).hexdigest() != digest:
                raise RuntimeError(f'Source verification failed: {name}')
    print(f'{OUTPUT}\n{len(hashes)} source files; {OUTPUT.stat().st_size / 1048576:.1f} MB; integrity verified')


if __name__ == '__main__':
    main()
