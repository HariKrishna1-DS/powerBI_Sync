"""Owner-reviewed migration; writes follow a durable, encrypted local snapshot."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from backup_protection import enabled, protect, unprotect, MAGIC
from cloud_backend.publication import SheetsPublisher, digest
from shared_backend import CloudError
from workspace_backup import write_verified_backup


class Migration:
    def __init__(self, rpc, book, directory, queue_scope, local_store=None):
        if not enabled():
            raise ValueError('Open the Windows desktop app to protect the migration snapshot.')
        self.rpc, self.book = rpc, book
        self.root, self.scope = Path(directory), queue_scope
        self.local_store = local_store

    def _path(self, plan):
        return self.root / (str(uuid.UUID(plan)) + '.tvmigration')

    def _save(self, plan):
        raw = json.dumps(plan, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        if len(raw) > 100_000_000:
            raise ValueError('Migration snapshot exceeds the supported 100 MB recovery size.')
        sealed = protect(raw)
        if not sealed.startswith(MAGIC) or unprotect(sealed) != raw:
            raise ValueError('Windows could not verify the protected migration snapshot.')
        write_verified_backup(self._path(plan['id']), sealed)

    def _load(self, identity):
        path = self._path(identity)
        if path.is_symlink() or path.stat().st_size > 101_000_000:
            raise ValueError('Invalid migration snapshot.')
        try:
            value = json.loads(unprotect(path.read_bytes()))
            valid = (isinstance(value,dict) and value.get('id') == identity and value.get('format') == 'tv-tracker-migration-1'
                and value.get('spreadsheet') == self.book.id and value.get('queue_scope') == self.scope
                and isinstance(value.get('tables'),dict) and isinstance(value.get('rows'),list)
                and isinstance(value.get('counts'),list) and type(value.get('next_sequence')) is int and value['next_sequence']>0
                and digest(value['tables']) == value.get('digest'))
            for field in ('id','workspace','seed_operation','activation_operation'):
                uuid.UUID(value[field])
        except (KeyError,TypeError,ValueError):
            valid = False
        if not valid:
            raise ValueError('The migration snapshot failed its integrity or destination check.')
        return value

    def _read(self):
        from tracker_sync import tracker_sources, FULL, REMAINING, OLD_FULL, OLD_REMAINING
        from monthly_production import tab_identity, decode
        from monthly_views import view_identity
        from sheets_repository import INDEX_TITLE
        from sheet_reads import read_values
        sources = tracker_sources(self.book)
        owned = {FULL, REMAINING, OLD_FULL, OLD_REMAINING, 'Full Title', 'Remaining Products',
            'All Products', 'Overview', 'Sheet1', 'Status Report', 'Daily Orders',
            'Monthly Orders', 'Monthly report', 'Capacity Report', 'Changes', 'Needs review', 'Preview History'}
        sheets = self.book.worksheets()
        selected = [s for s in sheets if s.title in owned or tab_identity(s.title) or view_identity(s.title)]
        if len(selected) > 200:
            raise ValueError('Archive old report tabs before migrating more than 200 tabs.')
        tables = dict(zip([s.title for s in selected], read_values(self.book, selected)))
        rows, counts = {}, []
        for base, sheet, _ in sources:
            values = tables[sheet.title]
            if not values or 'Order Number' not in values[0]:
                raise ValueError('Each production tracker needs an Order Number header.')
            count = 0
            for row in decode(values):
                number = str(row.get('Order Number', '')).strip()
                if not number or len(number) > 200 or re.search(r'[^ -~]', number):
                    raise ValueError('A production order has an unsupported or missing identity. Reconcile it before migration.')
                key = number.lower()
                if key in rows:
                    raise ValueError('An order occurs in multiple production rows. Reconcile month ownership before migration.')
                row['Order Number'] = number
                if tab_identity(sheet.title):
                    row['Reporting Month'] = tab_identity(sheet.title)[1]
                rows[key] = row
                count += 1
            counts.append({'tab': sheet.title, 'orders': count, 'tracker': base})
        if len(rows) > 100000 or len(json.dumps(list(rows.values())).encode()) > 50_000_000:
            raise ValueError('The baseline exceeds the supported 100,000-order / 50 MB size.')
        # Sequence is derived from every retained preview reference, not local IDs.
        ledger = next((s for s in sheets if s.title == INDEX_TITLE), None)
        sequence_values = list(tables.values())
        if ledger:
            sequence_values.append(read_values(self.book, [ledger])[0])
        sequence = self.local_store.next_number() if self.local_store is not None else 1
        from sheets_writer import SHARED_TITLE
        control = next((s for s in sheets if s.title == SHARED_TITLE), None)
        if control:
            marker = read_values(self.book, [control])[0]
            if len(marker) > 1 and marker[1][:1] == ['tv-tracker-shared-v2'] and (len(marker[0]) > 2 or len(marker[1]) > 2):
                try:
                    position = marker[0].index('Next preview')
                    reserved = str(marker[1][position])
                    if not re.fullmatch(r'[1-9]\d*', reserved):
                        raise ValueError('Invalid sequence')
                    sequence = max(sequence, int(reserved))
                except (ValueError, IndexError) as error:
                    raise ValueError('The shared preview counter is invalid. Reconcile it before migration.') from error
        for table in sequence_values:
            if not table:
                continue
            columns = [i for i, name in enumerate(table[0]) if name in ('Preview', 'Preview ID')]
            for row in table[1:]:
                for index in columns:
                    if index >= len(row):
                        continue
                    raw = str(row[index])
                    match = re.fullmatch(r'(?:preview)?([1-9]\d*)', raw)
                    if match:
                        sequence = max(sequence, int(match[1]) + 1)
        for sheet in sheets:
            match = re.fullmatch(r'preview([1-9]\d*)', sheet.title, re.I)
            if match:
                sequence = max(sequence, int(match[1]) + 1)
        return tables, [rows[key] for key in sorted(rows)], counts, sequence

    @staticmethod
    def _summary(plan):
        return {key: plan[key] for key in ('id', 'workspace', 'spreadsheet', 'created',
            'digest', 'counts', 'next_sequence', 'status_counts', 'state')}

    def latest(self, workspace):
        uuid.UUID(workspace)
        for path in sorted(self.root.glob('*.tvmigration'), key=lambda p:p.stat().st_mtime, reverse=True):
            try:
                plan = self._load(path.stem)
            except (ValueError, OSError):
                continue
            if plan['workspace'] == workspace:
                return self._summary(plan)
        return None

    def preview(self, workspace):
        uuid.UUID(workspace)
        status = self.rpc.call('tv_workspace_status', {'p_workspace': workspace})
        if status['mode'] != 'shadow' or status['revision'] != 0 or status['pending_captures'] or status['job']:
            raise CloudError('Migration needs an empty validation workspace. Do not use the synthetic acceptance workspace.')
        if status['queue_scope'] != self.scope:
            raise CloudError('The TitleVision queue differs from this workspace. Check Connections first.')
        tables, rows, counts, sequence = self._read()
        plan = {'format': 'tv-tracker-migration-1', 'id': str(uuid.uuid4()), 'workspace': workspace,
            'spreadsheet': self.book.id, 'queue_scope': self.scope, 'created': datetime.now(timezone.utc).isoformat(),
            'tables': tables, 'rows': rows, 'counts': counts, 'digest': digest(tables), 'next_sequence': sequence,
            'seed_operation': str(uuid.uuid4()), 'activation_operation': str(uuid.uuid4()), 'state': 'review',
            'status_counts': dict(Counter(row.get('Status', '') or '(Blank)' for row in rows))}
        self._save(plan)
        return self._summary(plan)

    def activate(self, workspace, identity, worker, reviewed=False, legacy_stopped=False):
        uuid.UUID(worker)
        if reviewed is not True or legacy_stopped is not True:
            raise ValueError('Review the snapshot and stop every old writer before activating.')
        plan = self._load(identity)
        if plan['workspace'] != workspace:
            raise ValueError('This migration snapshot belongs to another workspace.')
        if plan.get('worker') and plan['worker'] != worker:
            raise ValueError('The office-worker identity changed. Use the same PC to resume migration.')
        plan['worker'] = worker
        self._save(plan)
        status = self.rpc.call('tv_workspace_status', {'p_workspace': workspace})
        if status['queue_scope'] != self.scope:
            raise CloudError('The workspace queue changed. Migration was retained for review.', 'conflict')
        if status['mode'] != 'active':
            from cloud_backend.publication import PROTOCOL
            from sheets_writer import SHARED_TITLE
            existing = {s.title: s for s in self.book.worksheets()}
            # A lost response after fencing is resumed with the same durable plan.
            bound = False
            if SHARED_TITLE in existing:
                from sheet_reads import read_values
                marker = read_values(self.book, [existing[SHARED_TITLE]])[0]
                if len(marker)>1 and marker[1][:1]==[PROTOCOL] and marker[1][:3]!=[PROTOCOL,workspace,self.book.id]:
                    raise CloudError('The workbook is already bound to a different shared workspace. No baseline was imported.', 'conflict')
                bound = len(marker) > 1 and marker[1][:3] == [PROTOCOL, workspace, self.book.id]
            if not bound:
                tables, rows, _, sequence = self._read()
                if digest(tables) != plan['digest'] or rows != plan['rows'] or sequence != plan['next_sequence']:
                    raise CloudError('The workbook changed after review. Preserve the snapshot and reconcile before migration.', 'conflict')
            else:
                publisher = SheetsPublisher(self.book, workspace, self.book.id)
                receipt = publisher._receipt()
                if receipt['revision'] != 0 or receipt['digest'] != plan['digest'] or digest(publisher._read(sorted(plan['tables']))) != plan['digest']:
                    raise CloudError('The bound workbook differs from this reviewed baseline. Publishing remains paused.', 'conflict')
            seed = self.rpc.call('tv_seed_workspace', {'p_workspace': workspace, 'p_operation': plan['seed_operation'],
                'p_rows': plan['rows'], 'p_next_sequence': plan['next_sequence']})
            if seed.get('revision') != 1 or seed.get('orders') != len(plan['rows']) or seed.get('next_sequence') != plan['next_sequence']:
                raise CloudError('The baseline receipt could not be verified. Retry will reuse the same operation.', 'retry')
            snapshot = self.rpc.snapshot(workspace)
            if snapshot['revision'] != 1 or [row['data'] for row in snapshot['orders']] != plan['rows']:
                raise CloudError('The shared baseline differs from the reviewed workbook. Publishing remains paused.', 'conflict')
            SheetsPublisher(self.book, workspace, self.book.id).bind(sorted(plan['tables']), plan['digest'])
        elif status['spreadsheet'] != self.book.id or status['worker'] != worker:
            raise CloudError('This workspace is activated for a different destination or office PC.', 'conflict')
        receipt = self.rpc.call('tv_activate_workspace', {'p_workspace': workspace,
            'p_operation': plan['activation_operation'], 'p_revision': 1, 'p_spreadsheet': self.book.id,
            'p_worker': worker, 'p_legacy_stopped': True})
        if receipt != {'mode': 'active', 'revision': 1, 'spreadsheet': self.book.id, 'worker': worker}:
            raise CloudError('Activation could not be verified. Resume using the saved snapshot.', 'retry')
        plan['state'] = 'active'
        self._save(plan)
        return {**self._summary(plan), 'worker': worker}
