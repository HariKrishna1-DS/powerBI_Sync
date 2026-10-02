"""Local React dashboard API. The server deliberately starts with no seed data."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
import socket
from io import BytesIO
from pathlib import Path
import threading
import time as clock
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_file, send_from_directory
import pandas as pd
from openpyxl.worksheet.table import Table, TableStyleInfo

from datatrace_sync import run_sync, sync_workbook, apply_status_rules, build_synced_workbook_stream, target_worksheet
from reporting_dates import reporting_date
from preview_store import PreviewStore, compare
from order_reporting import automatic_sync_frame, daily_orders, monthly_orders, AUTOMATIC_RULES, completion_history
from sync_config import BASE_DIR, TARGET_GSHEET_URL
from sla_comments import sla_key, sla_status
from indian_clock import IndianClock

IST = timezone(timedelta(hours=5, minutes=30), 'IST')
SETTINGS_SHEET = '__DataTrace_Config'
from tracker_sync import TRACKERS, HEADERS, FULL, REMAINING, records, read_trackers, sheet_reports, sync_trackers, read_pass_report


def workbook(frame, name):
    stream = BytesIO()
    with pd.ExcelWriter(stream, engine='openpyxl') as writer:
        frame.to_excel(writer, sheet_name=name, index=False)
        ws = writer.sheets[name]
        for row in ws:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
        if not frame.empty:
            table = Table(displayName=name, ref=ws.dimensions)
            table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
            ws.add_table(table)
        ws.freeze_panes = 'A2'
    stream.seek(0)
    return stream


def create_app(root=None, runner=None, syncer=None, start_scheduler=False, time_source=None):
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
    store = PreviewStore(root or BASE_DIR / 'previews')
    runner = runner or run_sync
    syncer = syncer or sync_workbook
    indian_clock = time_source or IndianClock()
    app.extensions['indian_clock'] = indian_clock
    gate = threading.Lock()
    state_lock = threading.Lock()
    schedule_lock = threading.Lock()
    state = {'running': False, 'stage': 'Ready', 'action': None, 'result': None, 'run_id': 0}
    schedule_path = store.root.parent / 'sync_schedule.json'
    cloud_schedule_loaded = False
    preview_recovery_lock = threading.Lock()
    snapshot_lock = threading.Lock()
    snapshot_cache = {'checked': float('-inf'), 'signature': None, 'snapshot': None}

    def invalidate_snapshot():
        with snapshot_lock:
            snapshot_cache['checked'] = float('-inf')
            snapshot_cache['signature'] = None

    def reporting_snapshot():
        # Job status stays live; only immutable preview data and derived reports are cached.
        with snapshot_lock:
            if snapshot_cache['snapshot'] is not None and clock.monotonic() - snapshot_cache['checked'] < 2:
                return snapshot_cache['snapshot']
            previews = store.list()
            signature = tuple((p['id'], p['created'], p['source'], p['row_count']) for p in previews)
            if signature != snapshot_cache['signature']:
                history = store.history()
                previews = [{'id': p['id'], 'name': p['name'], 'created': p['created'],
                             'source': p['source'], 'row_count': len(p['rows'])}
                            for p in sorted(history, key=lambda p: p['id'], reverse=True)]
                reports = daily_orders(store, history=history)
                snapshot_cache['snapshot'] = (previews, history, reports)
                snapshot_cache['signature'] = tuple((p['id'], p['created'], p['source'], p['row_count']) for p in previews)
            snapshot_cache['checked'] = clock.monotonic()
            return snapshot_cache['snapshot']

    def recover_latest_preview():
        if root is not None or reporting_snapshot()[0]:
            return
        with preview_recovery_lock:
            if store.list():
                return
            try:
                book, _ = target_worksheet()
                values = book.worksheet('Sheet1').get_all_values()
                if values and 'Preview' in values[0]:
                    columns = [c for c in values[0] if c not in ('Preview', 'Preview Timestamp')]
                    grouped = {}
                    for row in records(values):
                        match = re.fullmatch(r'preview([1-9]\d*)', row.get('Preview', ''))
                        if match:
                            grouped.setdefault(int(match[1]), []).append(row)
                    for number, rows in grouped.items():
                        when = rows[0].get('Preview Timestamp', '')
                        created = datetime.fromisoformat(when).replace(tzinfo=IST).isoformat() if when else None
                        original = [{c: row.get(c, '') for c in columns} for row in rows if row.get('Order Number')]
                        store.restore(number, columns, original, created=created)
                        store.mark_synced(number)
                invalidate_snapshot()
            except Exception:
                app.logger.exception('Could not recover previews from raw Google Sheet history')

    def load_schedule():
        nonlocal cloud_schedule_loaded
        default = {'enabled': False, 'time': '09:00', 'times': ['09:00'], 'last_triggered_date': None, 'triggered_today': [], 'timezone': 'Asia/Kolkata'}
        if os.environ.get('RENDER') and not cloud_schedule_loaded:
            try:
                book, _ = target_worksheet()
                from gspread.exceptions import WorksheetNotFound
                try:
                    sheet = book.worksheet(SETTINGS_SHEET)
                except WorksheetNotFound:
                    sheet = None
                if sheet:
                    value = sheet.acell('A1').value
                    if value:
                        saved = json.loads(value)
                        if isinstance(saved, dict):
                            schedule_path.write_text(json.dumps(saved), encoding='utf-8')
                cloud_schedule_loaded = True
            except Exception:
                app.logger.exception('Could not load AutoLogin schedule from Google Sheets')
        try:
            saved = json.loads(schedule_path.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                default.update({key: saved.get(key, default[key]) for key in default if key in saved})
                if 'times' in saved and isinstance(saved['times'], list):
                    times = [str(t).strip() for t in saved['times'] if str(t).strip()]
                    default['times'] = sorted(list(dict.fromkeys(times))) if times else ['09:00']
                    default['time'] = default['times'][0]
                elif 'time' in saved and saved['time']:
                    default['times'] = [str(saved['time']).strip()]
                    default['time'] = default['times'][0]
        except (OSError, ValueError):
            pass
        default['timezone'] = 'Asia/Kolkata'
        return default

    def save_schedule(schedule):
        nonlocal cloud_schedule_loaded
        times = schedule.get('times', [])
        if not isinstance(times, list) or not times:
            if schedule.get('time'):
                times = [str(schedule['time']).strip()]
            else:
                times = ['09:00']
        times = sorted(list(dict.fromkeys([str(t).strip() for t in times if str(t).strip()])))
        schedule['times'] = times
        schedule['time'] = times[0] if times else '09:00'
        schedule_path.write_text(json.dumps(schedule, indent=2), encoding='utf-8')
        if os.environ.get('RENDER'):
            book, _ = target_worksheet()
            from gspread.exceptions import WorksheetNotFound
            try:
                sheet = book.worksheet(SETTINGS_SHEET)
            except WorksheetNotFound:
                sheet = book.add_worksheet(title=SETTINGS_SHEET, rows=2, cols=2)
            sheet.update_acell('A1', json.dumps(schedule))
            cloud_schedule_loaded = True

    def prepare_sync(preview_id=None, previous_id=None, keys=None, ignore=None, remaining_products=None):
        previews, history, reports = reporting_snapshot()
        if not previews:
            raise ValueError('Capture or import a preview before syncing Google Sheets.')
        by_id = {p['id']: p for p in history}
        selected_preview = by_id[int(preview_id) if preview_id is not None else previews[0]['id']]
        if previous_id is None:
            previous_id = next((item['id'] for item in previews if item['id'] < selected_preview['id']), None)
        if previous_id is not None and int(previous_id) >= selected_preview['id']:
            raise ValueError('The previous preview must be older than the selected preview.')
        previous_preview = by_id[int(previous_id)] if previous_id is not None else None
        frame, completed_orders = automatic_sync_frame(selected_preview, previous_preview, keys, ignore,
                                                       store=store, reports=reports)
        frame.attrs['preview_name'] = selected_preview['name']
        frame.attrs['preview_id'] = selected_preview['id']
        frame.attrs['sync_time'] = datetime.now(IST).isoformat()
        if remaining_products is not None:
            frame.attrs['selected_products'] = remaining_products
            try:
                (BASE_DIR / 'remaining_products.json').write_text(json.dumps(remaining_products, indent=2), encoding='utf-8')
            except Exception:
                pass
        return frame, selected_preview, completed_orders, previous_id

    def begin_sync(trigger='manual', preview_id=None, previous_id=None, keys=None, ignore=None, remaining_products=None):
        def work():
            gate.acquire()  # Queue behind an extraction or another sync; do not drop previews.
            with state_lock:
                state.update(running=True, action='sync', stage='Preparing Google Sheets sync', result=None,
                             run_id=state['run_id'] + 1)
            try:
                frame, selected_preview, completed_orders, prior_id = prepare_sync(preview_id, previous_id, keys, ignore, remaining_products)
                with state_lock:
                    state['stage'] = f"Syncing {selected_preview['name']} to Google Sheets"
                worksheets = upload_sync(frame)
                result = {'action': 'sync', 'trigger': trigger, 'error': None,
                          'google_sheet': 'success', 'preview_id': selected_preview['id'],
                          'preview_name': selected_preview['name'], 'rows': len(frame),
                          'worksheets': worksheets, 'stage': 'Finished'}
                result['status_rules'] = AUTOMATIC_RULES
                result['completed_orders'] = len(completed_orders)
                result['previous_id'] = prior_id
                result['pass_report'] = frame.attrs.get('pass_report', {})
                with state_lock:
                    state.update(result=result, stage='Finished')
            except Exception as exc:
                app.logger.exception('Google Sheets sync failed')
                with state_lock:
                    state.update(stage='Sync failed', result={'action': 'sync', 'trigger': trigger,
                                 'google_sheet': 'failed', 'error': str(exc)})
            finally:
                with state_lock:
                    state['running'] = False
                gate.release()
        threading.Thread(target=work, daemon=True).start()
        return True

    def upload_sync(frame):
        def progress(stage):
            with state_lock:
                state['stage'] = stage
        # Process pending snapshots chronologically before the selected capture.
        # This also handles previews saved by an external extraction process.
        for number in store.pending_syncs():
            if number < frame.attrs['preview_id']:
                prior, _ = automatic_sync_frame(store.get(number), store=store)
                upload_one(prior, progress)
        return upload_one(frame, progress)

    def upload_one(frame, progress):
        for attempt in range(3):
            try:
                result = syncer(frame, on_progress=progress) if syncer is sync_workbook else syncer(frame)
                store.mark_synced(frame.attrs['preview_id'])
                invalidate_snapshot()
                return result
            except Exception as exc:
                if attempt == 2:
                    store.mark_failed(frame.attrs['preview_id'], str(exc))
                    raise
                progress(f'Sync failed; retrying ({attempt + 2}/3). Preview is saved.')
                clock.sleep(2 ** attempt)

    def begin_scheduled_capture():
        if not gate.acquire(blocking=False):
            return False
        with state_lock:
            state.update(running=True, action='extract', stage='Scheduled extraction (IST)',
                         result=None, run_id=state['run_id'] + 1)

        def work():
            saved_preview = None
            try:
                prior_ids = {item['id'] for item in store.list()}
                def progress(result):
                    with state_lock:
                        state.update(stage=result.get('stage', 'Extracting queue'))
                result = runner(on_progress=progress)
                if result.get('error'):
                    raise RuntimeError(result['error'])
                preview_id = result.get('preview_id')
                if preview_id is None or preview_id in prior_ids:
                    raise RuntimeError('Extraction did not save a new preview; Google Sheets were not changed.')
                saved_preview = store.get(preview_id)
                invalidate_snapshot()
                frame, preview, completed, previous_id = prepare_sync(preview_id)
                with state_lock:
                    state.update(action='sync', stage=f"Syncing {preview['name']} to Google Sheets")
                worksheets = upload_sync(frame)
                with state_lock:
                    state.update(stage='Finished', result={
                        'action': 'sync', 'trigger': 'schedule', 'error': None,
                        'google_sheet': 'success', 'preview_id': preview['id'],
                        'preview_name': preview['name'], 'rows': len(frame),
                        'worksheets': worksheets, 'completed_orders': len(completed),
                        'previous_id': previous_id})
            except Exception as exc:
                app.logger.exception('Scheduled extraction/sync failed')
                with state_lock:
                    state.update(stage='Scheduled run failed', result={'action': 'sync',
                                 'trigger': 'schedule', 'error': str(exc),
                                 'preview_name': saved_preview['name'] if saved_preview else None})
            finally:
                with state_lock:
                    state['running'] = False
                gate.release()
        threading.Thread(target=work, daemon=True).start()
        return True

    def schedule_tick(now=None):
        now = now or indian_clock.now()
        if now is None:
            return False
        now = now.astimezone(IST)
        with schedule_lock:
            schedule = load_schedule()
            if not schedule['enabled']:
                return False
            today = now.date().isoformat()
            triggered = schedule.get('triggered_today', []) if schedule.get('last_triggered_date') == today else []
            due = [t for t in schedule['times'] if t <= now.strftime('%H:%M') and t not in triggered]
            if not due or not begin_scheduled_capture():
                return False
            schedule.update(last_triggered_date=today, triggered_today=triggered + due)
            save_schedule(schedule)
            return True

    app.extensions['schedule_tick'] = schedule_tick

    @app.before_request
    def same_origin():
        if request.method in ('POST', 'DELETE'):
            origin = request.headers.get('Origin')
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error='Cross-origin writes are not allowed.'), 403

    @app.after_request
    def no_cache(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(ValueError)
    def invalid(exc):
        return jsonify(error=str(exc)), 422

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(413)
    def too_large(exc):
        return jsonify(error='The file exceeds the 20 MB upload limit.'), 413

    @app.get('/api/state')
    def get_state():
        recover_latest_preview()
        previews, _, daily_reports = reporting_snapshot()
        with state_lock:
            job = dict(state)
        with schedule_lock:
            schedule = load_schedule()
        remaining_products = []
        try:
            path = BASE_DIR / 'remaining_products.json'
            if path.exists():
                remaining_products = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
        daily_completed_ids = list(dict.fromkeys(oid for r in daily_reports for oid in r['missing_ids']))
        return jsonify(previews=previews, job=job, schedule=schedule, clock=indian_clock.snapshot(), sheet_url=TARGET_GSHEET_URL, failed_syncs=store.failed_syncs(),
                       remaining_products=remaining_products,
                       daily_completed_ids=daily_completed_ids,
                       capabilities={'status_rules': True, 'automatic_statuses': True})

    @app.get('/api/remaining-products')
    def get_remaining_products():
        try:
            path = BASE_DIR / 'remaining_products.json'
            if path.exists():
                return jsonify(products=json.loads(path.read_text(encoding='utf-8')))
        except Exception:
            pass
        return jsonify(products=[])

    @app.post('/api/remaining-products')
    def save_remaining_products():
        body = request.get_json(silent=True) or {}
        products = body.get('products') if body.get('products') is not None else body.get('remaining_products')
        if not isinstance(products, list):
            raise ValueError('products must be a list.')
        (BASE_DIR / 'remaining_products.json').write_text(json.dumps(products, indent=2), encoding='utf-8')
        return jsonify(saved=True, products=products)

    @app.get('/api/daily-orders')
    def get_daily_orders():
        try:
            book, sheet_rows, _ = read_sla_sheets()
            trackers = {t: [r for r in sheet_rows if r['_sheet'] == t] for t in TRACKERS}
            return jsonify(rows=sheet_reports(trackers, read_pass_report(book, store))['daily'], selected_date=None)
        except Exception as exc:
            return jsonify(error=f'Google Sheet unavailable: {exc}'), 502

    def read_sla_sheets():
        book, _ = target_worksheet()
        sheet_rows, headers = [], {}
        for title in TRACKERS:
            values = book.worksheet(title).get_all_values()
            headers[title] = values[0] if values else []
            if values:
                sheet_rows.extend(dict(dict(zip(values[0], row)), _sheet=title, _sheet_row=index)
                                  for index, row in enumerate(values[1:], start=2))
        return book, sheet_rows, headers

    def monthly_report(sheet_rows=None, corrections=None):
        return monthly_orders(store, sheet_rows, history=reporting_snapshot()[1], corrections=corrections)

    @app.get('/api/monthly-orders')
    def get_monthly_orders():
        recover_latest_preview()
        try:
            book, sheet_rows, _ = read_sla_sheets()
            trackers = {t: [r for r in sheet_rows if r['_sheet'] == t] for t in TRACKERS}
            rows = sheet_reports(trackers, read_pass_report(book, store))['monthly']
        except Exception as exc:
            app.logger.warning('Could not refresh monthly SLA from Google Sheets: %s', exc)
            return jsonify(error=f'Google Sheet unavailable: {exc}'), 502
        return jsonify(rows=rows, sla_error=None)

    @app.post('/api/sla-comments')
    @app.post('/api/sla-comments/bulk')
    def update_sla_comment():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError('An SLA update is required.')
        bulk = request.path.endswith('/bulk')
        orders = body.get('orders') if bulk else [body]
        if not isinstance(orders, list) or not 1 <= len(orders) <= 10000:
            raise ValueError('Select between 1 and 10,000 orders to update.')
        status = body.get('status')
        if status not in ('On Time', 'Missing'):
            raise ValueError('Choose On Time or Missing.')
        selection = {}
        for order in orders:
            if not isinstance(order, dict):
                raise ValueError('Each selection must identify an SLA order.')
            identity, completion = order.get('order_number'), order.get('completion_date')
            expected = order.get('expected_status')
            if not isinstance(identity, str) or not identity.strip() or len(identity) > 512:
                raise ValueError('A valid order number is required.')
            identity = identity.strip()
            if not isinstance(completion, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', completion):
                raise ValueError('A completion date is required.')
            datetime.strptime(completion, '%Y-%m-%d')
            if expected not in ('On Time', 'Missing'):
                raise ValueError('Each selection must include its current SLA status.')
            key = (identity, completion)
            if key in selection:
                raise ValueError('Each order and completion date must be selected only once.')
            selection[key] = expected
        if not gate.acquire(blocking=False):
            return jsonify(error='A sync or extraction is running. Save the SLA change after it finishes.'), 409
        try:
            try:
                book, sheet_rows, headers = read_sla_sheets()
            except Exception:
                app.logger.exception('Could not read sheets before SLA edit')
                return jsonify(error='Could not check Google Sheets. Your change has not been saved. Please retry.'), 502
            corrections = store.sla_corrections()
            reports = monthly_report(sheet_rows, corrections)
            current = {(row['Order Number'], row['completion_date']): row['Free Site']
                       for report in reports for row in report['sla_rows']}
            for key, expected in selection.items():
                if key not in current:
                    return jsonify(error=f'Order {key[0]} is no longer in this SLA report. No changes were saved. Refresh the report before editing.'), 409
                if current[key] not in (expected, status):
                    return jsonify(error='An SLA status changed since you selected it. No changes were saved. Refresh the report and try again.'), 409
            matching = [row for row in sheet_rows if sla_key(row) in selection]
            if any('Free Site' not in headers[row['_sheet']] for row in matching):
                return jsonify(error='The matching Google Sheet is missing its Free Site column. Restore the column before saving.'), 409
            if matching:
                from gspread.utils import rowcol_to_a1
                updates = [{'range': f"'{row['_sheet']}'!{rowcol_to_a1(row['_sheet_row'], headers[row['_sheet']].index('Free Site') + 1)}",
                            'values': [[status]]} for row in matching]
                # Read back one column span per tab, keeping URLs small even for
                # thousands of selected cells spread over both product tabs.
                spans = {}
                for row in matching:
                    spans.setdefault(row['_sheet'], set()).add(row['_sheet_row'])
                ranges = []
                for title, indices in spans.items():
                    column = headers[title].index('Free Site') + 1
                    start, end = rowcol_to_a1(min(indices), column), rowcol_to_a1(max(indices), column)
                    ranges.append(f"'{title}'!{start}" + (f':{end}' if start != end else ''))
                try:
                    book.values_batch_update({'valueInputOption': 'RAW', 'data': updates})
                    verification = book.values_batch_get(ranges).get('valueRanges', [])
                    if len(verification) != len(ranges):
                        raise RuntimeError('SLA readback did not match the requested status.')
                    for indices, item in zip(spans.values(), verification):
                        values = item.get('values', [])
                        first = min(indices)
                        for index in indices:
                            offset = index - first
                            if offset >= len(values) or not values[offset] or sla_status(values[offset][0]) != status:
                                raise RuntimeError('SLA readback did not match the requested status.')
                except Exception:
                    app.logger.exception('Could not confirm SLA cell update')
                    return jsonify(error='The Google Sheets save could not be confirmed. Refresh the report before retrying.'), 502
            try:
                if bulk:
                    store.save_sla_corrections([(number, date, status) for number, date in selection])
                else:
                    store.save_sla_correction(identity, completion, status)
            except Exception:
                app.logger.exception('Could not persist SLA correction')
                message = ('Google Sheets was updated, but the history save failed. Retry Save to keep the correction in the database.'
                           if matching else 'The history save failed. Your change has not been saved. Please retry.')
                return jsonify(error=message), 503
            corrections.update({key: status for key in selection})
            for row in matching:
                row['Free Site'] = status
            message = (f'Order {identity} saved as {status} in Google Sheets and report history.' if matching else
                       f'Order {identity} saved as {status} in report history. This order is not in the current Google Sheet; the correction will apply when it is synced again.')
            if bulk:
                sheet_count = len({sla_key(row) for row in matching})
                history_count = len(selection) - sheet_count
                message = f'{len(selection)} {"order" if len(selection) == 1 else "orders"} saved as {status} in report history.'
                if sheet_count:
                    message += f' {sheet_count} also updated in Google Sheets.'
                if history_count:
                    message += f' {history_count} historical {"order" if history_count == 1 else "orders"} will use the correction when synced again.'
            return jsonify(saved=True, updated_count=len(selection), rows=monthly_report(sheet_rows, corrections), message=message)
        finally:
            gate.release()

    @app.get('/api/live-sheets')
    def get_live_sheets():
        try:
            book, _ = target_worksheet()
            trackers = read_trackers(book)
            sheets = {title: {'columns': list(dict.fromkeys(HEADERS + [c for r in rows for c in r])), 'rows': rows}
                      for title, rows in trackers.items()}
            combined = [r for rows in trackers.values() for r in rows]
            sheets['All Products'] = {'columns': HEADERS, 'rows': combined}
            # Stable UI labels point to the two renamed authoritative tracker tabs.
            sheets['Full Title'] = sheets[FULL]
            sheets['Remaining Products'] = sheets[REMAINING]
            previews = store.list()
            return jsonify(preview_name=previews[0]['name'] if previews else None, sheets=sheets)
        except Exception as exc:
            return jsonify(error=str(exc)), 502

    @app.post('/api/extract')
    def extract():
        if not gate.acquire(blocking=False):
            return jsonify(error='An extraction is already running.'), 409
        with state_lock:
            state.update(running=True, action='extract', stage='Starting fresh extraction', result=None,
                         run_id=state['run_id'] + 1)

        def progress(result):
            with state_lock:
                state.update(stage=result['stage'], result=result)

        def work():
            try:
                result = runner(on_progress=progress)
                if result.get('error'):
                    raise RuntimeError(result['error'])
                preview_id = result.get('preview_id')
                if not preview_id:
                    raise RuntimeError('Extraction did not save a preview.')
                invalidate_snapshot()
                frame, saved, _, _ = prepare_sync(preview_id)
                worksheets = upload_sync(frame)
                result.update(action='sync', google_sheet='success', worksheets=worksheets,
                              pass_report=frame.attrs.get('pass_report'), error=None)
                with state_lock:
                    state.update(result=result, stage='Finished')
            except Exception as exc:
                app.logger.exception('Extraction failed')
                with state_lock:
                    state.update(stage='Failed', result={'error': str(exc)})
            finally:
                invalidate_snapshot()
                with state_lock:
                    state['running'] = False
                gate.release()
        threading.Thread(target=work, daemon=True).start()
        return jsonify(accepted=True), 202

    @app.post('/api/sync')
    def sync_latest():
        body = request.get_json(silent=True) or {}
        preview_id = body.get('preview')
        if preview_id is None:
            raise ValueError('Select a preview before syncing Google Sheets.')
        preview_id = int(preview_id)
        if preview_id < 1:
            raise ValueError('Select a valid preview before syncing Google Sheets.')
        if body.get('previous') is not None and int(body['previous']) >= preview_id:
            raise ValueError('The previous preview must be older than the selected preview.')
        if not begin_sync('manual', preview_id, body.get('previous'), body.get('keys'), body.get('ignore'), body.get('remaining_products')):
            return jsonify(error='An extraction or sync is already running.'), 409
        return jsonify(accepted=True), 202

    @app.post('/api/sync-schedule')
    def update_schedule():
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get('enabled'))
        raw_times = body.get('times')
        if raw_times is None:
            raw_time = str(body.get('time', '')).strip()
            raw_times = [raw_time] if raw_time else []
        elif isinstance(raw_times, str):
            raw_times = [raw_times]

        validated_times = []
        for t_str in raw_times:
            t_str = str(t_str).strip()
            if not t_str:
                continue
            try:
                validated_times.append(datetime.strptime(t_str, '%H:%M').strftime('%H:%M'))
            except ValueError as exc:
                raise ValueError(f'Invalid sync time: "{t_str}". Use HH:MM format.') from exc

        if not validated_times:
            validated_times = ['09:00']
        validated_times = sorted(list(dict.fromkeys(validated_times)))

        now = indian_clock.now()
        if enabled and now is None:
            return jsonify(error='Indian time is still synchronizing. Try saving the schedule again shortly.'), 503
        with schedule_lock:
            current = load_schedule()
            changed = current['enabled'] != enabled or current.get('times') != validated_times
            current.update(enabled=enabled, times=validated_times, time=validated_times[0])
            if (changed or enabled) and now is not None:
                already_triggered = current.get('triggered_today', []) if current.get('last_triggered_date') == now.date().isoformat() else []
                current['last_triggered_date'] = now.date().isoformat()
                current['triggered_today'] = sorted(set(already_triggered + [t for t in validated_times if t < now.strftime('%H:%M')]))
            save_schedule(current)
        if enabled:
            schedule_tick()
        return jsonify(current)

    @app.get('/api/previews/<int:number>')
    def preview(number):
        return jsonify(store.get(number))

    @app.delete('/api/previews/<int:number>')
    def delete_preview(number):
        store.delete(number)
        invalidate_snapshot()
        return jsonify(deleted=number)

    @app.post('/api/import')
    def import_file():
        upload = request.files.get('file')
        if not upload or not upload.filename:
            raise ValueError('Select a CSV or XLSX file.')
        suffix = Path(upload.filename).suffix.lower()
        try:
            if suffix == '.csv':
                frame = pd.read_csv(upload, dtype=str, keep_default_na=False, encoding='utf-8-sig')
            elif suffix == '.xlsx':
                frame = pd.read_excel(upload, dtype=str, keep_default_na=False, engine='openpyxl')
            else:
                raise ValueError('Only CSV and XLSX files are supported.')
        except Exception as exc:
            raise ValueError('Cannot read this file. Use a valid UTF-8 CSV or XLSX workbook with headers.') from exc
        saved = store.save(frame, source=Path(upload.filename).name)
        invalidate_snapshot()
        begin_sync('import', saved['id'])
        return jsonify(saved), 201

    @app.get('/api/previews/<int:number>/download/<kind>')
    def download(number, kind):
        preview = store.get(number)
        if kind not in ('csv', 'xlsx'):
            raise ValueError('Unsupported download format.')
        if kind == 'xlsx':
            return export_google_sheets()
        else:
            frame = apply_status_rules(pd.DataFrame(preview['rows'], columns=preview['columns']), [])
            stream = BytesIO(frame.to_csv(index=False).encode('utf-8-sig'))
            return send_file(stream, as_attachment=True, download_name=f'preview{number}.csv')

    @app.get('/api/export/google-sheets')
    def export_google_sheets():
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current extraction or sync to finish before exporting.'), 409
        try:
            book, _ = target_worksheet()
            stream = BytesIO()
            preview_name = 'GoogleSheets'
            short_names = {FULL: 'Full Title', REMAINING: 'Remaining Products'}
            worksheets = book.worksheets()
            too_long = [w.title for w in worksheets if len(w.title) > 31]
            if too_long and request.args.get('short_names') != 'true':
                return jsonify(error='Excel limits tab names to 31 characters. Confirm exporting the tracker tabs as Full Title and Remaining Products.',
                               requires_short_names=True, proposed_names=short_names), 409
            from openpyxl.styles import PatternFill, Font
            from tracker_formatting import foreground
            from datatrace_sync import status_color
            with pd.ExcelWriter(stream, engine='openpyxl') as writer:
                for sheet in worksheets:
                    values = sheet.get_all_values()
                    title = short_names.get(sheet.title, sheet.title)
                    if len(title) > 31:
                        raise ValueError(f'Choose a shorter export name for {sheet.title}.')
                    pd.DataFrame(values).to_excel(writer, sheet_name=title, index=False, header=False)
                    ws = writer.sheets[title]
                    for row in ws:
                        for cell in row:
                            if isinstance(cell.value, str):
                                cell.data_type = 's'
                    if values and 'Status' in values[0]:
                        status_index = values[0].index('Status')
                        for cells in ws.iter_rows(min_row=2):
                            color = status_color(cells[status_index].value)
                            for cell in cells:
                                fill = color
                                cell.fill = PatternFill('solid', fgColor=fill.lstrip('#'))
                                cell.font = Font(color=foreground(fill).lstrip('#'))
                    ws.freeze_panes = 'A2'
            stream.seek(0)
            return send_file(stream, as_attachment=True, download_name='Production_data.xlsx')
        except Exception as exc:
            return jsonify(error=f'Google Sheets export failed: {exc}'), 502
        finally:
            gate.release()

    @app.post('/api/compare')
    def comparison():
        body = request.get_json()
        previous, latest = store.get(int(body['previous'])), store.get(int(body['latest']))
        result = compare(previous, latest, ['Order Number'], body.get('ignore'))
        if body.get('download'):
            frame = pd.DataFrame(result['rows'], columns=result['columns'])
            frame['Previous Preview'] = previous['name']
            frame['Latest Preview'] = latest['name']
            return send_file(workbook(frame, 'DataTraceChanges'), as_attachment=True,
                             download_name=f"{previous['name']}_to_{latest['name']}_changes.xlsx")
        return jsonify(result)

    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path='index.html'):
        return send_from_directory(BASE_DIR / 'frontend' / 'dist', path)

    if start_scheduler:
        def schedule_loop():
            try:
                sync_trackers()
            except Exception as exc:
                app.logger.exception('Default tracker initialization failed')
                with state_lock:
                    state.update(stage='Google Sheets setup needs attention', result={'error': str(exc)})
            while True:
                try:
                    # Saved but unsynced previews survive restarts and wait for the lock.
                    for preview_id in store.pending_syncs():
                        frame, _, _, _ = prepare_sync(preview_id)
                        with gate:
                            with state_lock:
                                state.update(running=True, action='sync', stage=f'Syncing preview{preview_id}', run_id=state['run_id'] + 1)
                            try:
                                worksheets = upload_sync(frame)
                                with state_lock:
                                    state.update(stage='Finished', result={'action': 'sync', 'google_sheet': 'success',
                                        'preview_name': frame.attrs['preview_name'], 'rows': len(frame),
                                        'worksheets': worksheets, 'pass_report': frame.attrs.get('pass_report')})
                            finally:
                                with state_lock:
                                    state['running'] = False
                    schedule_tick()
                except Exception as exc:
                    app.logger.exception('Automatic sync failed; preview retained')
                    with state_lock:
                        state.update(stage='Automatic sync needs attention', result={'error': str(exc)})
                clock.sleep(15)
        threading.Thread(target=schedule_loop, daemon=True).start()

    return app


def main():
    import os
    parser = argparse.ArgumentParser()
    default_host = os.environ.get('HOST', '0.0.0.0' if (os.environ.get('RENDER') or os.environ.get('PORT')) else '127.0.0.1')
    default_port = int(os.environ.get('PORT', 8510))
    parser.add_argument('--host', type=str, default=default_host)
    parser.add_argument('--port', type=int, default=default_port)
    args = parser.parse_args()
    from waitress import serve
    host = args.host
    port = args.port
    if host == '127.0.0.1':
        while port < args.port + 20:
            with socket.socket() as probe:
                try:
                    probe.bind((host, port))
                    break
                except OSError:
                    port += 1
        else:
            raise RuntimeError('No free dashboard port. Choose another port with --port.')
    print(f'DataTrace Workspace: http://{host}:{port}', flush=True)
    serve(create_app(start_scheduler=True), host=host, port=port, threads=8)


if __name__ == '__main__':
    main()
