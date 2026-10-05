"""Offline, disposable workspace benchmark. Never opens the user's profile or Sheets."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.desktop-build' / 'deps'), str(ROOT / 'gsheet_dashboard')]
from preview_store import PreviewStore
from production_cache import ProductionCache
from server import create_app
from tracker_sync import sheet_reports, FULL, REMAINING


def measure(action, count=7):
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        action()
        samples.append((time.perf_counter() - started) * 1000)
    return {'median_ms': round(statistics.median(samples), 2), 'max_ms': round(max(samples), 2), 'samples': count}


def run():
    rows = [{'Order Number': f'TEST-{i:06}', 'Product': 'Full Title', 'Status': 'Search In Progress',
             'Date': '10/05/2026', 'In-Time': '10/05/2026 09:00 AM', 'Client': f'Client {i % 30}',
             'County': f'County {i % 75}', 'Assignee': f'Team {i % 15}', 'Out Time': '', 'Free Site': ''}
            for i in range(7000)]
    with tempfile.TemporaryDirectory(prefix='tv-tracker-benchmark-') as folder:
        root = Path(folder)
        store = PreviewStore(root / 'previews')
        for number in range(1, 36):
            store.restore(number, list(rows[0]), rows[:350], created=f'2026-10-05T{number//6:02}:{number%6*10:02}:00Z')
        started = time.perf_counter()
        app = create_app(store.root, time_source=Mock(snapshot=lambda: {}, now=lambda: None))
        client = app.test_client()
        startup = (time.perf_counter() - started) * 1000
        cache = ProductionCache(root / 'production-cache.json', 'benchmark')
        loader = lambda: {'sheets': {'Overview': {'columns': list(rows[0]), 'rows': rows}}}
        first = cache.get(loader)
        reports = lambda: sheet_reports({FULL: rows, REMAINING: []}, {})
        report = reports()
        return {'dataset': {'orders': len(rows), 'captures': 35, 'rows_per_capture': 350},
                'local_app_creation_ms': round(startup, 2),
                'status_poll': measure(lambda: client.get('/api/state')),
                'capture_load': measure(lambda: client.get('/api/previews/35')),
                'warm_cache': measure(lambda: cache.get(loader)),
                'unchanged_cache': measure(lambda: cache.get(loader, known_revision=first.get('revision'))),
                'cache_full_bytes': len(json.dumps(cache.get(loader)).encode()),
                'cache_unchanged_bytes': len(json.dumps(cache.get(loader, known_revision=first.get('revision'))).encode()),
                'reporting': measure(reports, 3),
                'report_sha256': hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = json.dumps(run(), indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding='utf-8')
    print(result)
