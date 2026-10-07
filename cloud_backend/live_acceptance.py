"""Authenticated synthetic checks. Never reads/writes the production workbook."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import uuid

from shared_backend import SupabaseRpc
from cloud_backend.transport import OwnerWorkerRpc
from cloud_backend.worker import ShadowWorker


def run(settings):
    config, token = settings['config'], settings['accessToken']
    def client():
        return SupabaseRpc(config['url'], config['publishableKey'], lambda: token)
    rpc = client()
    workspace = str(uuid.uuid4())
    scope = 'synthetic-acceptance-' + workspace
    assert rpc.call('tv_create_workspace', {'p_workspace': workspace,
        'p_name': 'Tv Tracker synthetic acceptance', 'p_queue_scope': scope}) == workspace
    base = datetime.now(timezone.utc) - timedelta(minutes=5)
    operations = [str(uuid.uuid4()) for _ in range(4)]
    def submit(index):
        row = {'Order Number': 'TV-CLOUD-QA-001', 'Product': 'Full Title',
               'Status': 'Search In Progress', 'In-Time': '10/01/2026 09:00 AM'}
        body = {'p_workspace': workspace, 'p_operation': operations[index],
            'p_captured_at': (base + timedelta(seconds=index)).isoformat(),
            'p_payload': {'columns': list(row), 'rows': [row], 'queue_scope': scope,
                'metadata': {'kind': 'portal', 'complete': True, 'expected_rows': 1, 'actual_rows': 1}}}
        transport = client()
        first = transport.call('tv_submit_capture', body)
        assert transport.call('tv_submit_capture', body) == first
        return first
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(submit, range(4)))
    assert sorted(row['sequence'] for row in receipts) == [1, 2, 3, 4]
    with tempfile.TemporaryDirectory() as folder:
        worker = ShadowWorker(OwnerWorkerRpc(config['url'], config['publishableKey'], lambda: token), folder)
        results = [worker.step(workspace) for _ in range(4)]
        assert all(row['state'] in ('processed', 'review') for row in results)
        assert worker.step(workspace)['state'] == 'idle'
    snapshot = rpc.snapshot(workspace)
    assert len(snapshot['orders']) == 1
    for operation in operations:
        assert rpc.call('tv_operation', {'p_workspace': workspace, 'p_operation': operation})['processing_state'] in ('processed', 'review')
    result = {'workspace': workspace, 'four_concurrent_logical_clients': True,
        'duplicate_submissions_idempotent': True, 'owner_worker_processed': True,
        'canonical_orders': 1, 'revision': snapshot['revision'], 'production_modified': False}
    (Path(__file__).resolve().parents[1] / '.desktop-build/shared-live-acceptance.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        run(json.load(sys.stdin))
    except Exception as error:
        # Upstream responses and tokens must not enter diagnostic files.
        print('Shared acceptance failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(1)
