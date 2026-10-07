"""Reviewed monthly plans operate on one canonical revision, never client Sheets."""
from datetime import datetime
import json
import re
import uuid

from monthly_production import (BASES, ARCHIVE, month_key, local_datetime, tab_name,
    tab_identity, encode, extend_headers, import_plan, rollover_plan, read_import)
from production_rules import full_title
from production_timing import sla_result
from shared_backend import CloudError
from tracker_sync import HEADERS, key


class SharedMonthly:
    def __init__(self, runtime):
        self.runtime = runtime

    def preview(self, kind, month, files):
        self.runtime.authorize_capture()
        month_key(month)
        if month <= ARCHIVE:
            raise ValueError('September 2026 is archived and cannot be changed.')
        saved = self.runtime.rpc.snapshot(self.runtime.selection['id'])
        context = self.runtime.report_state(saved['revision'])
        if context['preferences']['source'] != 'tracker':
            raise ValueError('Select Tracker report before changing canonical monthly orders.')
        original = {item['order_key']: item for item in saved['orders']}
        groups = {}
        for item in original.values():
            row = dict(item['data'])
            period = row.get('Reporting Month')
            if not period:
                arrival = local_datetime(row.get('In-Time') or row.get('Date'))
                if not arrival:
                    raise ValueError('An order has no valid reporting month or arrival date. Review it before monthly maintenance.')
                period = arrival.strftime('%Y-%m')
            month_key(period)
            title = tab_name(BASES[0] if full_title(row) else BASES[1], period)
            groups.setdefault(title, []).append(row)
        data = {title: {'values': encode(rows, extend_headers(HEADERS, rows))} for title, rows in groups.items()}
        for base in BASES:
            data.setdefault(tab_name(base, month), {'values': [HEADERS]})
        if kind == 'setup':
            plan = {'kind': kind, 'writes': {}, 'counts': [{'target': tab_name(base, month), 'added': 0} for base in BASES],
                'reviews': [], 'moves': []}
        elif kind == 'rollover':
            plan = rollover_plan(data, month)
        elif kind == 'import':
            uploads = []
            for field, base in zip(('full_search', 'co_update'), BASES):
                file = files.get(field)
                if not file:
                    continue
                if not file.filename.lower().endswith('.xlsx'):
                    raise ValueError('Production imports require .xlsx workbooks.')
                source = read_import(file.read(), base)
                # Last-row-wins is unsafe for a shared canonical import.
                if any('Duplicate Order Number' in r['Reason'] or 'Missing Order Number' in r['Reason'] for r in source['reviews']):
                    raise ValueError('Resolve missing or duplicate order numbers in the workbook before importing.')
                uploads.append((base, file.filename.replace('\\', '/').split('/')[-1], source))
            if not uploads:
                raise ValueError('Select at least one production workbook.')
            all_keys = [key(row) for _, _, source in uploads for row in source['rows']]
            if len(all_keys) != len(set(all_keys)):
                raise ValueError('An order occurs in both workbooks. Resolve product ownership before importing.')
            plan = import_plan(data, uploads, month)
        else:
            raise ValueError('Choose setup, import or rollover.')
        changes, periods = {}, {month}
        from monthly_production import decode
        for title, values in plan['writes'].items():
            _, period = tab_identity(title)
            periods.add(period)
            for raw in decode(values):
                row = dict(raw, **{'Reporting Month': period})
                identity = key(row)
                if not identity or len(identity) > 200 or re.search(r'[^ -~]', row['Order Number']):
                    raise ValueError('An imported order has an unsupported identity.')
                old = original.get(identity)
                if kind == 'import':
                    row['Free Site'], _ = sla_result(row)
                # Display numbering is recomputed by the publisher, not canonical data.
                row.pop('No', None)
                previous = dict(old['data']) if old else None
                if previous:
                    previous.pop('No', None)
                if row != previous:
                    changes[identity] = {'order_key': identity, 'version': old['version'] if old else None, 'data': row}
        plan.update(id=uuid.uuid4().hex, kind=kind, created=datetime.now().timestamp(), month=month,
            shared=True, workspace=self.runtime.selection['id'], revision=saved['revision'],
            changes=list(changes.values()), periods=sorted(periods))
        plan.pop('writes', None)
        if len(json.dumps(plan).encode()) > 50_000_000:
            raise ValueError('The monthly plan exceeds the supported 50 MB size.')
        return plan

    def apply(self, plan):
        self.runtime.authorize_capture()
        if not plan.get('shared') or plan.get('workspace') != self.runtime.selection['id']:
            raise ValueError('This preview belongs to a different backend or workspace. Generate a fresh preview.')
        receipt = self.runtime.requests.perform(self.runtime.rpc, 'tv_apply_monthly', {
            'p_workspace': plan['workspace'], 'p_plan': str(uuid.UUID(plan['id'])), 'p_revision': plan['revision'],
            'p_kind': plan['kind'], 'p_month': plan['month'], 'p_rows': plan['changes'], 'p_periods': plan['periods']})
        if receipt.get('state') != 'pending' or receipt.get('revision') != plan['revision'] + 1 or receipt.get('updated_count') != len(plan['changes']):
            raise CloudError('The monthly save could not be verified. Keep and retry this same preview.', 'retry')
        self.runtime.cache.invalidate()
        self.runtime.reporting = None
        return receipt
