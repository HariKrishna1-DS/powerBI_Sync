"""Local React dashboard API. The server deliberately starts with no seed data."""
import argparse
from collections import deque
from datetime import datetime, timedelta, timezone
import json
import os
import re
import socket
import hmac
from io import BytesIO
from pathlib import Path
import threading
import time as clock
from urllib.parse import urlparse

from flask import Flask, g, jsonify, request, send_file, send_from_directory
import pandas as pd
from openpyxl.worksheet.table import Table, TableStyleInfo

from datatrace_sync import run_sync, sync_workbook, target_worksheet, CaptureCancelled
from reporting_dates import reporting_date
from preview_store import PreviewStore, compare
from order_reporting import automatic_sync_frame, daily_orders, monthly_orders, AUTOMATIC_RULES, completion_history
from sync_config import BASE_DIR, ASSET_DIR, SPREADSHEET_ID, TARGET_GSHEET_URL, TRACKER_TITLES
from production_cache import ProductionCache
from operation_journal import OperationJournal
from request_metrics import RequestMetrics
from tracker_sync import read_tracker_rows, read_preview_history, tracker_sources, TRACKERS, FULL, REMAINING, HEADERS, sheet_reports, read_pass_report
from indian_clock import IndianClock
from sla_comments import sla_key, sla_status

IST = timezone(timedelta(hours=5, minutes=30), 'IST')
SETTINGS_SHEET = '__DataTrace_Config'


def compact_job(job):
    """Keep polling small; the full immutable report remains available from sync-reports."""
    result = job.get('result')
    if not result or not isinstance(result.get('pass_report'), dict):
        return job
    report = result['pass_report']
    summary = {key: value for key, value in report.items() if isinstance(value, (str, int, float, bool)) or value is None}
    for key in ('not_in_latest', 'ambiguous', 'unprocessed'):
        value = report.get(key, 0)
        summary[key + '_count'] = len(value) if isinstance(value, list) else value if isinstance(value, int) else 0
    return dict(job, result=dict(result, pass_report=summary))


def color_export_sheet(ws, values):
    from openpyxl.styles import PatternFill, Font
    from datatrace_sync import status_color
    from tracker_formatting import foreground
    if not values:
        return
    headers = values[0]
    status_column = next((headers.index(name) for name in ('Status', 'Task Status') if name in headers), None)
    if status_column is None:
        return
    styles = {}
    # Indexing ws[number] recalculates max_column by scanning every populated
    # cell for every row. Explicit bounds keep large archive exports linear.
    rows = ws.iter_rows(min_row=2, max_row=len(values), max_col=len(headers))
    for cells, output_row in zip(values[1:], rows):
        color = status_color(cells[status_column] if len(cells) > status_column else '')
        if color not in styles:
            styles[color] = (PatternFill('solid', fgColor=color.lstrip('#').upper()),
                             Font(color=foreground(color).lstrip('#').upper()))
        fill, font = styles[color]
        for cell in output_row:
            cell.fill = fill
            cell.font = font


def production_export_frames(book, store=None, sources=None):
    from datatrace_sync import status_report_frame
    from monthly_production import decode, tab_identity, arrival_sort, encode
    sources = tracker_sources(book) if sources is None else sources
    if not sources:
        return {}
    frames = {sheet.title: encode(arrival_sort(decode(values)), values[0]) if values else [] for _, sheet, values in sources}
    trackers = {sheet.title if tab_identity(sheet.title) else title: decode(values) for title, sheet, values in sources}
    rows = [row for values in trackers.values() for row in values if row.get('Order Number')]
    reports = sheet_reports(trackers, read_pass_report(book, store))
    status = status_report_frame(pd.DataFrame(rows, columns=list(dict.fromkeys(HEADERS + [c for row in rows for c in row]))))
    frames['Status Report'] = [list(status.columns)] + status.fillna('').values.tolist()
    for title, kind, period in (('Daily Orders', 'daily', 'Date'), ('Monthly report', 'monthly', 'Month')):
        columns = [period, 'Today Orders' if kind == 'daily' else 'Month Orders', 'Completed Orders', 'Not in latest preview', 'Awaiting for Clarification', 'SLA On Time', 'SLA Missed']
        frames[title] = [columns] + [[row.get(c, '') for c in columns] for row in reports[kind]]
    return frames


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
    metrics = RequestMetrics()

    @app.before_request
    def begin_request_timing():
        g.request_started = clock.perf_counter()

    @app.after_request
    def finish_request_timing(response):
        if request.url_rule:
            metrics.record(request.url_rule.rule, (clock.perf_counter() - g.request_started) * 1000, response.status_code)
        return response
    desktop_mode = os.environ.get('DATATRACE_DESKTOP') == '1'
    desktop_token = os.environ.get('DATATRACE_DESKTOP_TOKEN', '')
    if desktop_mode and not desktop_token:
        raise RuntimeError('Desktop authentication is required.')
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
    store = PreviewStore(root or BASE_DIR / 'previews')
    from report_workspace import ReportWorkspace
    report_workspace = ReportWorkspace(store)
    journal = OperationJournal(store)
    cancel_capture = threading.Event()
    runner = runner or (lambda on_progress: run_sync(on_progress=on_progress, auto_sync=False, cancel_event=cancel_capture))
    syncer = syncer or sync_workbook
    indian_clock = time_source or IndianClock()
    app.extensions['indian_clock'] = indian_clock
    sync_queue, queued_ids = deque(), set()
    queue_lock = threading.Lock()
    worker_active = False
    gate = threading.Lock()
    import_lock = threading.Lock()
    state_lock = threading.Lock()
    schedule_lock = threading.Lock()
    state = {'running': False, 'stage': 'Ready', 'action': None, 'result': None, 'run_id': 0}
    schedule_path = store.root.parent / 'sync_schedule.json'
    cloud_schedule_loaded = False
    preview_recovery_lock = threading.Lock()
    snapshot_lock = threading.Lock()
    snapshot_cache = {'checked': float('-inf'), 'signature': None, 'snapshot': None}
    recovery_checked = float('-inf')
    connection_retry_after = float('-inf')
    scheduler_stop = threading.Event()
    maintenance = threading.Event()
    app.extensions['stop_scheduler'] = scheduler_stop
    production_cache = ProductionCache(store.root.parent / 'production-cache.json', '|'.join((SPREADSHEET_ID, *TRACKER_TITLES)))
    app.extensions['production_cache'] = production_cache

    import secrets
    local_settings_token = secrets.token_urlsafe(32)

    @app.before_request
    def local_settings_security():
        if not request.path.startswith('/api/local/'):
            return
        if (desktop_mode or os.environ.get('RENDER') or
                request.remote_addr not in ('127.0.0.1', '::1') or
                urlparse(request.host_url).hostname not in ('127.0.0.1', 'localhost', '::1')):
            return jsonify(error='Connections can only be managed from this computer.'), 403
        origin = request.headers.get('Origin')
        if (origin and origin != request.host_url.rstrip('/')) or request.headers.get('Sec-Fetch-Site') == 'cross-site':
            return jsonify(error='Open settings from the local workspace.'), 403
        request.max_content_length = 128 * 1024
        if request.method != 'GET' and (not request.is_json or not hmac.compare_digest(
                request.headers.get('X-Settings-Token', ''), local_settings_token)):
            return jsonify(error='Reopen Connections & settings and try again.'), 403

    @app.get('/api/local/settings')
    def get_local_settings():
        import local_settings
        import sync_config
        return jsonify(**local_settings.public(local_settings.current(sync_config)), csrfToken=local_settings_token)

    @app.post('/api/local/settings')
    def save_local_settings():
        nonlocal recovery_checked, cloud_schedule_loaded, connection_retry_after
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current capture or sync to finish before saving connections.'), 409
        try:
            with state_lock:
                if state['running'] or queued_ids:
                    return jsonify(error='Wait for queued syncs to finish before saving connections.'), 409
            import importlib
            import sys
            import local_settings
            import sync_config
            import datatrace_sync
            import tracker_sync
            import monthly_production
            import sheets_repository
            previous_spreadsheet = sync_config.SPREADSHEET_ID
            settings = local_settings.validate(request.get_json(), local_settings.current(sync_config))
            local_settings.save(BASE_DIR, settings)
            importlib.reload(sync_config)
            # These modules retain imported connection constants; update them together
            # while capture/sync work is excluded, then discard connection-specific caches.
            for module in (sys.modules[__name__], datatrace_sync, tracker_sync, monthly_production, sheets_repository):
                for name in ('SPREADSHEET_ID', 'TARGET_GSHEET_URL', 'WORKSHEET_GID', 'TRACKER_TITLES',
                             'FULL_TRACKER_TITLE', 'REMAINING_TRACKER_TITLE'):
                    if hasattr(module, name):
                        setattr(module, name, getattr(sync_config, name))
            for module in (sys.modules[__name__], tracker_sync):
                module.FULL, module.REMAINING = sync_config.TRACKER_TITLES
                module.TRACKERS = sync_config.TRACKER_TITLES
            monthly_production.BASES = sync_config.TRACKER_TITLES
            production_cache.identity = '|'.join((sync_config.SPREADSHEET_ID, *sync_config.TRACKER_TITLES))
            production_cache.reload()
            if settings['spreadsheetId'] != previous_spreadsheet:
                report_workspace.save(cloud_baseline=None, cloud_reset=True, synced_at=None,
                                      cloud_refresh_error=None)
            recovery_checked, cloud_schedule_loaded = float('-inf'), False
            connection_retry_after = float('-inf')
            invalidate_snapshot()
            return jsonify(**local_settings.public(settings), csrfToken=local_settings_token)
        finally:
            gate.release()

    @app.post('/api/local/check-connection')
    def check_local_connection():
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current capture or sync to finish before testing the connection.'), 409
        try:
            book, _ = target_worksheet()
            titles = {sheet.title for sheet in book.worksheets()}
            missing = [title for title in TRACKER_TITLES if title not in titles]
            return jsonify(connected=True, title=book.title, missingTrackers=missing)
        except Exception as exc:
            return jsonify(error=str(exc)), 502
        finally:
            gate.release()

    def finish_operation(number):
        if number is not None:
            try:
                journal.finish(number, state.get('result'))
            except Exception:
                app.logger.exception('Could not finish the local operation receipt')
                state.update(stage='Local receipt needs attention', result={
                    **(state.get('result') or {}),
                    'error': 'The operation finished but its local activity receipt could not be saved. Check free disk space before continuing.'})

    @app.get('/api/activity')
    def activity():
        return jsonify(operations=journal.list())

    @app.get('/api/order-history')
    def order_history():
        number = request.args.get('order', '').strip()
        if not number or len(number) > 512:
            raise ValueError('A valid order number is required.')
        with store.connect() as db:
            rows = db.execute("WITH recent AS (SELECT id,created,rows_json FROM previews ORDER BY id DESC LIMIT 100) "
                              "SELECT recent.id,recent.created,group_concat(DISTINCT json_extract(item.value,'$.Status')) "
                              "FROM recent,json_each(recent.rows_json) item "
                              "WHERE lower(trim(CAST(json_extract(item.value,'$.\"Order Number\"') AS TEXT)))=lower(?) "
                              "GROUP BY recent.id,recent.created ORDER BY recent.id DESC", (number,)).fetchall()
        return jsonify(events=[{'preview_id': row[0], 'preview_name': f'preview{row[0]}',
                                'created': row[1], 'status': row[2]} for row in rows], capture_limit=100)

    @app.get('/api/desktop/diagnostics')
    def diagnostics():
        # An allowlist deliberately excludes logs, paths, URLs, account identifiers and order contents.
        with state_lock:
            active = bool(state['running'])
        return jsonify(format='tv-tracker-diagnostics', version=1, created=journal.now(),
                       captures=len(store.list()), pending_sync=store.pending_count(),
                       failed_syncs=len(store.failed_syncs()), active_operation=active,
                       schedule={'timezone': 'Asia/Kolkata', 'catch_up': 'one run for all missed times today'},
                       operations=journal.list(), request_metrics=metrics.snapshot())

    @app.before_request
    def desktop_security():
        if desktop_mode and not hmac.compare_digest(request.headers.get('X-DataTrace-Token', ''), desktop_token):
            return jsonify(error='Open this workspace in DataTrace Studio.'), 401
        if request.path.startswith('/api/desktop/') and not desktop_mode:
            return jsonify(error='This action is available in the desktop app.'), 404
        if maintenance.is_set() and request.path not in ('/api/health', '/api/desktop/shutdown'):
            return jsonify(error='The local workspace is being restored. Try again in a moment.'), 503
        if request.path == '/api/desktop/restore':
            request.max_content_length = 100 * 1024 * 1024

    @app.after_request
    def response_security(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        if desktop_mode:
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/api/health')
    def health():
        with state_lock:
            return jsonify(ready=True, running=state['running'] or bool(queued_ids), stage=state['stage'], desktop=desktop_mode)

    @app.post('/api/desktop/shutdown')
    def shutdown_desktop():
        options = request.get_json(silent=True) or {}
        force = bool(options.get('force'))
        if force and options.get('backup'):
            return jsonify(error='An update backup requires an idle workspace.'), 422
        if not force and not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current capture or sync to finish before installing or quitting.'), 409
        with state_lock:
            if (state['running'] or queued_ids) and not force:
                gate.release()
                return jsonify(error='A job is running.'), 409
            maintenance.set()
        if options.get('backup'):
            try:
                from workspace_backup import make_backup
                stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
                destination = store.root.parent / 'backups' / f'before-update-{stamp}.zip'
                destination.parent.mkdir(exist_ok=True)
                temporary = destination.with_suffix('.tmp')
                temporary.write_bytes(make_backup(store).getvalue())
                temporary.replace(destination)
            except Exception:
                maintenance.clear()
                gate.release()
                return jsonify(error='The update backup could not be saved. Check free disk space and retry.'), 503
        scheduler_stop.set()
        callback = app.config.get('DESKTOP_SHUTDOWN')
        if callback:
            threading.Timer(0.15, callback).start()
        return jsonify(stopping=True)

    @app.get('/api/desktop/backup')
    def desktop_backup():
        from workspace_backup import make_backup
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current job before backing up.'), 409
        try:
            return send_file(make_backup(store), as_attachment=True, download_name='DataTrace-backup.zip', mimetype='application/zip')
        finally:
            gate.release()

    @app.post('/api/desktop/restore')
    def desktop_restore():
        from workspace_backup import restore_backup
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current job before restoring.'), 409
        try:
            maintenance.set()
            with import_lock:
                safety = restore_backup(store, request.get_data())
                journal.__init__(store)
                report_workspace.__init__(store)
            invalidate_snapshot()
            production_cache.reload()
            production_cache.invalidate()
            return jsonify(restored=True, safety_backup=safety)
        finally:
            maintenance.clear()
            gate.release()

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
                history = None
                reports = []
                snapshot_cache['snapshot'] = (previews, history, reports)
                snapshot_cache['signature'] = tuple((p['id'], p['created'], p['source'], p['row_count']) for p in previews)
            snapshot_cache['checked'] = clock.monotonic()
            return snapshot_cache['snapshot']

    def recover_latest_preview(required=False):
        nonlocal recovery_checked
        if root is not None or reporting_snapshot()[0] or (desktop_mode and not required):
            return
        with preview_recovery_lock:
            if not required and clock.monotonic() - recovery_checked < 60:
                return
            recovery_checked = clock.monotonic()
            if store.list():
                return
            try:
                book, primary = target_worksheet()
                for preview in read_preview_history(book):
                    store.restore(preview['id'], preview['columns'], preview['rows'], preview['source'], created=preview['created'])
                    store.mark_synced(preview['id'], {'recovered': True})
                invalidate_snapshot()
            except Exception as exc:
                app.logger.exception('Could not recover latest preview from Google Sheets')
                if required:
                    if desktop_mode and not (SPREADSHEET_ID and os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')):
                        raise RuntimeError('Open Connections & settings, enter your spreadsheet URL, import the service-account JSON key, and Save settings. Sharing the Sheet alone does not configure this app.') from exc
                    detail = (str(exc) if isinstance(exc, RuntimeError) else
                              f'Cloud preview history could not be read ({type(exc).__name__}).')
                    raise RuntimeError(f'Could not recover existing preview numbers from Google Sheets. {detail} '
                                       'No new capture was created.') from exc

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
        temporary = schedule_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(schedule, indent=2), encoding='utf-8')
        temporary.replace(schedule_path)
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
        selected_preview = store.get(int(preview_id) if preview_id is not None else previews[0]['id'])
        if previous_id is None:
            previous_id = next((item['id'] for item in previews if item['id'] < selected_preview['id']), None)
        if previous_id is not None and int(previous_id) >= selected_preview['id']:
            raise ValueError('The previous preview must be older than the selected preview.')
        previous_preview = store.get(int(previous_id)) if previous_id is not None else None
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
        nonlocal worker_active
        preview_id = int(preview_id) if preview_id is not None else None

        def work():
            operation_id = None
            while not scheduler_stop.is_set():
                if gate.acquire(timeout=0.2):
                    break
            else:
                return
            with state_lock:
                state.update(running=True, action='sync', stage='Preparing Google Sheets sync', result=None,
                             run_id=state['run_id'] + 1)
            try:
                operation_id = journal.begin('sync')
                frame, selected_preview, completed_orders, prior_id = prepare_sync(preview_id, previous_id, keys, ignore, remaining_products)
                with state_lock:
                    state['stage'] = f"Syncing {selected_preview['name']} to Google Sheets"
                drain_earlier_previews(frame.attrs['preview_id'], retry_failed=trigger == 'manual')
                worksheets = upload_sync(frame)
                result = {'action': 'sync', 'trigger': trigger, 'error': None,
                          'google_sheet': 'success', 'preview_id': selected_preview['id'],
                          'preview_name': selected_preview['name'], 'rows': len(frame),
                          'worksheets': worksheets, 'pass_report': frame.attrs.get('pass_report'), 'stage': 'Finished'}
                result['status_rules'] = AUTOMATIC_RULES
                result['completed_orders'] = len(completed_orders)
                result['previous_id'] = prior_id
                with state_lock:
                    state.update(result=result, stage='Finished')
            except Exception as exc:
                app.logger.exception('Google Sheets sync failed')
                with state_lock:
                    state.update(stage='Sync failed', result={'action': 'sync', 'trigger': trigger,
                                 'google_sheet': 'failed', 'error': str(exc)})
            finally:
                with state_lock:
                    finish_operation(operation_id)
                    state['running'] = False
                    gate.release()
        def drain_queue():
            nonlocal worker_active
            while True:
                with queue_lock:
                    if not sync_queue or scheduler_stop.is_set():
                        sync_queue.clear()
                        queued_ids.clear()
                        worker_active = False
                        return
                    number, task = sync_queue.popleft()
                try:
                    task()
                finally:
                    with queue_lock:
                        queued_ids.discard(number)

        with queue_lock:
            if preview_id in queued_ids:
                return trigger != 'manual'
            if len(sync_queue) >= 100:
                return False  # The capture stays durable for the scheduler to pick up.
            queued_ids.add(preview_id)
            sync_queue.append((preview_id, work))
            if not worker_active:
                worker_active = True
                threading.Thread(target=drain_queue, daemon=True).start()
        return True

    def upload_sync(frame):
        def progress(stage):
            with state_lock:
                state['stage'] = stage
        number = frame.attrs['preview_id']
        for attempt in range(3):
            try:
                if scheduler_stop.is_set():
                    raise RuntimeError('Sync interrupted; the capture remains saved.')
                worksheets = syncer(frame, on_progress=progress) if syncer is sync_workbook else syncer(frame)
                store.mark_synced(number, frame.attrs.get('pass_report', {}))
                invalidate_snapshot()
                production_cache.invalidate()
                if syncer is sync_workbook and report_workspace.read().get('enabled'):
                    app.extensions['publish_active_reports']()
                return worksheets
            except Exception as exc:
                # Validation/conflict errors need intervention, not automatic retries.
                if isinstance(exc, (ValueError, KeyError)) or attempt == 2 or scheduler_stop.is_set():
                    store.mark_failed(number, str(exc))
                    raise
                progress(f'Sync failed; retrying ({attempt + 2}/3). Preview is saved.')
                scheduler_stop.wait(2 ** attempt)

    def drain_earlier_previews(preview_id, retry_failed=False):
        failures = {row['preview_id'] for row in store.failed_syncs()}
        for number in store.unsynced_ids():
            if number >= preview_id:
                break
            if number in failures and not retry_failed:
                raise ValueError(f'preview{number} needs retry before newer captures can sync. Use its Retry sync button.')
            frame, _, _, _ = prepare_sync(number)
            upload_sync(frame)

    def begin_scheduled_capture():
        if not gate.acquire(blocking=False):
            return False
        with state_lock:
            cancel_capture.clear()
            state.update(running=True, action='extract', stage='Scheduled extraction (IST)',
                         result=None, cancel_requested=False, run_id=state['run_id'] + 1)

        def work():
            saved_preview = None
            operation_id = None
            try:
                operation_id = journal.begin('scheduled_capture')
                recover_latest_preview(required=True)
                prior_ids = {item['id'] for item in store.list()}
                def progress(result):
                    with state_lock:
                        state.update(stage='Cancelling extraction…' if cancel_capture.is_set() else result.get('stage', 'Extracting queue'))
                with import_lock:
                    result = runner(on_progress=progress)
                if result.get('cancelled'):
                    raise CaptureCancelled()
                if result.get('error'):
                    raise RuntimeError(result['error'])
                preview_id = result.get('preview_id')
                if preview_id is None or preview_id in prior_ids:
                    raise RuntimeError('Extraction did not save a new preview; Google Sheets were not changed.')
                saved_preview = store.get(preview_id)
                invalidate_snapshot()
                frame, preview, completed, previous_id = prepare_sync(preview_id)
                with state_lock:
                    if cancel_capture.is_set():
                        raise CaptureCancelled()
                    state.update(action='sync', stage=f"Syncing {preview['name']} to Google Sheets")
                drain_earlier_previews(frame.attrs['preview_id'])
                worksheets = upload_sync(frame)
                with state_lock:
                    state.update(stage='Finished', result={
                        'action': 'sync', 'trigger': 'schedule', 'error': None,
                        'google_sheet': 'success', 'preview_id': preview['id'],
                        'preview_name': preview['name'], 'rows': len(frame),
                        'worksheets': worksheets, 'pass_report': frame.attrs.get('pass_report'), 'completed_orders': len(completed),
                        'previous_id': previous_id})
            except CaptureCancelled:
                with state_lock:
                    state.update(stage='Extraction cancelled', result={'cancelled': True, 'error': None,
                        'saved_locally': bool(saved_preview), 'preview_id': saved_preview['id'] if saved_preview else None,
                        'preview_name': saved_preview['name'] if saved_preview else None})
            except Exception as exc:
                app.logger.exception('Scheduled extraction/sync failed')
                with state_lock:
                    state.update(stage='Capture saved; Sheets sync needs retry' if saved_preview else 'Scheduled run failed', result={'action': 'sync',
                                 'trigger': 'schedule', 'error': str(exc),
                                 'saved_locally': bool(saved_preview),
                                 'preview_name': saved_preview['name'] if saved_preview else None})
            finally:
                with state_lock:
                    finish_operation(operation_id)
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
        with queue_lock:
            job['running'] = job['running'] or bool(queued_ids)
        with schedule_lock:
            schedule = load_schedule()
        schedule.update(journal.scheduled_summary())
        if request.args.get('light') == '1':
            job = compact_job(job)
        remaining_products = []
        try:
            path = BASE_DIR / 'remaining_products.json'
            if path.exists():
                remaining_products = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
        daily_completed_ids = []
        return jsonify(previews=previews, job=job, schedule=schedule, clock=indian_clock.snapshot(), failed_syncs=store.failed_syncs(), sheet_url=TARGET_GSHEET_URL,
                       remaining_products=remaining_products, report_workspace=report_workspace.public(),
                       daily_completed_ids=daily_completed_ids,
                       pending_sync=store.pending_count(),
                       capabilities={'status_rules': True, 'automatic_statuses': True, 'desktop': desktop_mode,
                                     'google_configured': bool(SPREADSHEET_ID and os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'))})

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
            snapshot = production_snapshot()
            workspace_status = report_workspace.read()
            return jsonify(rows=snapshot['reports']['daily'],
                           **{key: workspace_status.get(key) for key in ('selected_date', 'highlighted_date', 'publication_state', 'sync_error')},
                           **{key: snapshot.get(key) for key in ('source', 'mode', 'statuses', 'offline', 'updated_at')})
        except Exception as exc:
            return jsonify(error=f'Could not read Google Sheets daily orders: {exc}'), 502

    def read_sla_sheets():
        book, _ = target_worksheet()
        rows = read_tracker_rows(book)
        from tracker_sync import canonical_headers
        headers = {sheet.title: canonical_headers(values[0]) if values else [] for _, sheet, values in tracker_sources(book)}
        return book, rows, headers

    def monthly_report(sheet_rows=None, corrections=None):
        if sheet_rows is None:
            raise ValueError('Google Sheets tracker rows are required for production reporting.')
        trackers = {title: [dict(r) for r in sheet_rows if r.get('_tracker', r.get('_sheet')) == title] for title in TRACKERS}
        return sheet_reports(trackers, store.latest_sync_report())['monthly']

    @app.get('/api/monthly-orders')
    def get_monthly_orders():
        try:
            snapshot = production_snapshot()
            return jsonify(rows=snapshot['reports']['monthly'], sla_error=None,
                           **{key: snapshot.get(key) for key in ('source', 'mode', 'statuses', 'offline', 'updated_at')})
        except Exception as exc:
            return jsonify(error=f'Could not read Google Sheets monthly orders: {exc}'), 502

    @app.post('/api/sla-comments')
    @app.post('/api/sla-comments/bulk')
    def update_sla_comment():
        if report_workspace.read()['mode'] == 'excel':
            return jsonify(error='Edit the source workbook and reimport it to change imported SLA values.'), 409
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError('An SLA update is required.')
        bulk = request.path.endswith('/bulk')
        orders = body.get('orders') if bulk else [body]
        if not isinstance(orders, list) or not 1 <= len(orders) <= 10000:
            raise ValueError('Select between 1 and 10,000 orders to update.')
        status = 'Missing' if body.get('status') == 'Missed' else body.get('status')
        if status not in ('On Time', 'Missing'):
            raise ValueError('Choose On Time or Missing.')
        selection = {}
        for order in orders:
            if not isinstance(order, dict):
                raise ValueError('Each selection must identify an SLA order.')
            identity, completion = order.get('order_number'), order.get('completion_date')
            expected = 'Missing' if order.get('expected_status') == 'Missed' else order.get('expected_status')
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
            from monthly_production import ARCHIVE
            if any(row.get('_month') and row['_month'] <= ARCHIVE for row in matching):
                return jsonify(error='September is archived. SLA changes cannot overwrite the archive.'), 409
            if any('Free Site' not in headers[row['_sheet']] for row in matching):
                return jsonify(error='The matching Google Sheet is missing its Free Site column. Restore the column before saving.'), 409
            if matching:
                from gspread.utils import rowcol_to_a1
                sheet_status = 'Missing' if status == 'Missed' else status
                updates = [{'range': f"'{row['_sheet']}'!{rowcol_to_a1(row['_sheet_row'], headers[row['_sheet']].index('Free Site') + 1)}",
                            'values': [[sheet_status]]} for row in matching]
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
                row['Free Site'] = 'Missing' if status == 'Missed' else status
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
            production_cache.invalidate()
            return jsonify(saved=True, updated_count=len(selection), rows=monthly_report(sheet_rows, corrections), message=message)
        finally:
            gate.release()

    def production_snapshot(force=False, known_revision=None, tracker_only=False):
        from report_workspace import imported_snapshot
        settings = report_workspace.read()
        if not tracker_only and settings['mode'] == 'excel' and settings.get('imported'):
            return dict(imported_snapshot(settings['imported']), data_revision=settings.get('data_revision'))
        def load():
            book, _ = target_worksheet()
            sheets, trackers, groups = {}, {}, {}
            from monthly_production import decode, tab_identity, arrival_sort, ARCHIVE
            from tracker_sync import canonical_headers
            for title, sheet, values in tracker_sources(book):
                identity = tab_identity(sheet.title)
                rows = [dict(r, _sheet=sheet.title, _tracker=title, _month=identity[1] if identity else '') for r in decode(values)]
                trackers[sheet.title if identity else title] = rows
                columns = canonical_headers(values[0]) if values else HEADERS
                sheets[sheet.title] = {'columns': columns, 'rows': arrival_sort(rows)}
                label = 'Full Title' if title == FULL else 'Remaining Products'
                group = groups.setdefault(label, {'columns': [], 'rows': []})
                group['columns'] = list(dict.fromkeys(group['columns'] + columns))
                # Archived rows remain available in Monthly reports; Orders shows current ownership.
                if not identity or identity[1] > ARCHIVE:
                    group['rows'].extend(rows)
            sheets.update(groups)
            for label in ('Full Title', 'Remaining Products'):
                sheets.setdefault(label, {'columns': HEADERS, 'rows': []})
                sheets[label]['rows'] = arrival_sort(sheets[label]['rows'])
            columns = list(dict.fromkeys(c for title in ('Full Title', 'Remaining Products') for c in sheets[title]['columns']))
            combined = arrival_sort(sheets['Full Title']['rows'] + sheets['Remaining Products']['rows'])
            sheets['Overview'] = sheets['All Products'] = {'columns': columns, 'rows': combined}
            audit = read_pass_report(book, store)
            reports = sheet_reports(trackers, audit)
            return dict(preview_name=audit.get('preview_name'), sheets=sheets, reports=reports, source='Google Sheets', offline=False)
        result = production_cache.get(load, force=force, known_revision=known_revision) if desktop_mode else load()
        if result.get('unchanged'):
            return result
        # Older desktop caches did not include reports. Derive them from their saved tracker rows.
        if 'reports' not in result:
            trackers = {title: result['sheets'][label]['rows'] for title, label in zip(TRACKERS, ('Full Title', 'Remaining Products'))}
            result['reports'] = sheet_reports(trackers, store.latest_sync_report())
        result['mode'] = 'tracker'
        result['data_revision'] = settings.get('data_revision')
        return result

    @app.get('/api/live-sheets')
    def get_live_sheets():
        recover_latest_preview()
        try:
            return jsonify(production_snapshot(force=request.args.get('refresh') == '1', known_revision=request.args.get('revision')))
        except RuntimeError as exc:
            return jsonify(error=str(exc)), 502
        except Exception as exc:
            return jsonify(error=f'Could not read Google Sheets: {exc}'), 502

    @app.get('/api/sync-reports')
    def sync_reports():
        report = store.latest_sync_report()
        return jsonify(report={key: value for key, value in report.items() if not key.startswith('_')}, source='Local sync history')

    @app.post('/api/desktop/check-connection')
    def check_connection():
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current capture or sync to finish before testing the connection.'), 409
        try:
            recover_latest_preview(required=True)
            result = production_snapshot(force=True)
            if result.get('offline'):
                return jsonify(error=result['sync_error']), 502
            previews = store.list()
            return jsonify(connected=True, orders=len(result['sheets']['Overview']['rows']), updated_at=result.get('updated_at'),
                           recovered_previews=len(previews), next_preview=max((p['id'] for p in previews), default=0) + 1)
        except Exception as exc:
            return jsonify(error=str(exc)), 502
        finally:
            gate.release()

    @app.post('/api/extract')
    def extract():
        with state_lock:
            if state['running']:
                return jsonify(error='A capture or queue sync is already running.'), 409
            cancel_capture.clear()
            state.update(running=True, action='extract', stage='Starting fresh extraction', result=None,
                         cancel_requested=False, run_id=state['run_id'] + 1)

        def progress(result):
            with state_lock:
                state.update(stage='Cancelling extraction…' if cancel_capture.is_set() else result['stage'], result=result)

        def work():
            saved = None
            operation_id = None
            owns_gate = False
            try:
                while not scheduler_stop.is_set():
                    if cancel_capture.is_set():
                        raise CaptureCancelled()
                    if gate.acquire(timeout=1):
                        owns_gate = True
                        break
                    with state_lock:
                        state['stage'] = 'Waiting for the current Sheets update before extracting'
                if not owns_gate:
                    raise RuntimeError('Application stopped before extraction could start.')
                operation_id = journal.begin('capture')
                recover_latest_preview(required=True)
                prior_ids = {item['id'] for item in store.list()}
                with import_lock:
                    result = runner(on_progress=progress)
                if result.get('cancelled'):
                    raise CaptureCancelled()
                if result.get('error'):
                    raise RuntimeError(result['error'])
                preview_id = result.get('preview_id')
                if preview_id is None or preview_id in prior_ids:
                    raise RuntimeError('Extraction did not save a new preview; existing data was retained.')
                saved = store.get(preview_id)
                invalidate_snapshot()
                frame, saved, _, _ = prepare_sync(preview_id)
                with state_lock:
                    if cancel_capture.is_set():
                        raise CaptureCancelled()
                    state.update(action='sync', stage=f"Syncing {saved['name']} to Google Sheets")
                drain_earlier_previews(frame.attrs['preview_id'])
                worksheets = upload_sync(frame)
                with state_lock:
                    state.update(result=dict(result, action='sync', google_sheet='success', worksheets=worksheets,
                                             pass_report=frame.attrs.get('pass_report')), stage='Finished')
            except CaptureCancelled:
                with state_lock:
                    state.update(stage='Extraction cancelled', result={'cancelled': True, 'error': None,
                        'saved_locally': bool(saved), 'preview_id': saved['id'] if saved else None,
                        'preview_name': saved['name'] if saved else None})
            except Exception as exc:
                app.logger.exception('Extraction failed')
                with state_lock:
                    state.update(stage='Capture saved; Sheets sync needs retry' if saved else 'Failed', result={'error': str(exc), 'google_sheet': 'failed',
                                 'saved_locally': bool(saved), 'rows': len(saved['rows']) if saved else 0,
                                 'preview_name': saved['name'] if saved else None,
                                 'preview_id': saved['id'] if saved else None})
            finally:
                invalidate_snapshot()
                with state_lock:
                    finish_operation(operation_id)
                    state['running'] = False
                    if owns_gate:
                        gate.release()
        threading.Thread(target=work, daemon=True).start()
        return jsonify(accepted=True), 202

    @app.post('/api/extract/cancel')
    def cancel_extraction():
        run_id = (request.get_json(silent=True) or {}).get('run_id')
        with state_lock:
            if not state['running'] or state['action'] != 'extract':
                return jsonify(error='No queue extraction is running.'), 409
            if run_id is not None and run_id != state['run_id']:
                return jsonify(error='That extraction has already finished. Refresh the current operation.'), 409
            cancel_capture.set()
            state.update(cancel_requested=True, stage='Cancelling extraction…')
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
        if not isinstance(raw_times, list) or len(raw_times) > 48:
            raise ValueError('Provide at most 48 scheduled times.')

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
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for extraction or sync to finish before deleting a preview.'), 409
        try:
            # Verify the ID before writing a backup, and fail closed if it cannot be saved.
            store.get(number)
            from workspace_backup import save_safety_backup
            try:
                backup = save_safety_backup(store, 'before-delete')
            except OSError:
                return jsonify(error='The recovery copy could not be saved. Check free disk space; the capture was not deleted.'), 503
            store.delete(number)
            invalidate_snapshot()
            return jsonify(deleted=number, recovery_backup=backup.name)
        finally:
            gate.release()

    @app.post('/api/import')
    def import_file():
        upload = request.files.get('file')
        if not upload or not upload.filename:
            raise ValueError('Select a CSV or XLSX file.')
        if not import_lock.acquire(blocking=False):
            return jsonify(error='Another capture or import is using the local workspace. Try again when it finishes.'), 409
        owns_gate = gate.acquire(blocking=False)
        if not owns_gate:
            with state_lock:
                can_queue = state['running'] and state['action'] == 'sync' and not maintenance.is_set()
            if not can_queue:
                import_lock.release()
                return jsonify(error='Wait for the current capture or maintenance operation before importing.'), 409
        try:
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
            can_sync = not desktop_mode or bool(SPREADSHEET_ID and os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON'))
            if can_sync:
                recover_latest_preview(required=True)
            saved = store.save(frame, source=Path(upload.filename).name)
            invalidate_snapshot()
        finally:
            if owns_gate:
                gate.release()
            import_lock.release()
        if can_sync:
            begin_sync('import', saved['id'])
        return jsonify(dict(saved, auto_sync=can_sync)), 201

    @app.get('/api/previews/<int:number>/download/<kind>')
    def download(number, kind):
        preview = store.get(number)
        if kind not in ('csv', 'xlsx'):
            raise ValueError('Unsupported download format.')
        frame = pd.DataFrame(preview['rows'], columns=preview['columns']).fillna('')
        if kind == 'xlsx':
            return send_file(workbook(frame, 'DataTraceQueue'), as_attachment=True, download_name=f'preview{number}.xlsx')
        stream = BytesIO(frame.to_csv(index=False).encode('utf-8-sig'))
        return send_file(stream, as_attachment=True, download_name=f'preview{number}.csv')

    @app.get('/api/export/google-sheets')
    def export_google_sheets():
        if not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current extraction or sync to finish before exporting.'), 409
        try:
            book, _ = target_worksheet()
            worksheets = [sheet for sheet in book.worksheets() if not sheet.title.startswith('__DataTrace_')]
            from tracker_sync import OLD_FULL, OLD_REMAINING
            short_names = {FULL: 'Full Title', REMAINING: 'Remaining Products'}
            if FULL == OLD_FULL.removesuffix('_-_September_2026'):
                short_names[OLD_FULL] = 'Full Title'
            if REMAINING == OLD_REMAINING.removesuffix('_-_September_2026'):
                short_names[OLD_REMAINING] = 'Remaining Products'
            titles = {sheet.title for sheet in worksheets}
            from monthly_production import tab_identity
            has_full = FULL in titles or (OLD_FULL in short_names and OLD_FULL in titles)
            has_remaining = REMAINING in titles or (OLD_REMAINING in short_names and OLD_REMAINING in titles)
            sources = tracker_sources(book) if (has_full and has_remaining) or any(tab_identity(t) for t in titles) else []
            proposed, used = {}, set()
            for sheet in sorted(worksheets, key=lambda sheet: sheet.title not in short_names):
                base = short_names.get(sheet.title, re.sub(r'[\\/*?:\[\]]', '_', sheet.title))[:31] or 'Sheet'
                name, index = base, 2
                while name.casefold() in used:
                    suffix = f' ({index})'
                    name = base[:31-len(suffix)] + suffix
                    index += 1
                used.add(name.casefold())
                proposed[sheet.title] = name
            renamed = {title: name for title, name in proposed.items() if title != name}
            if renamed and request.args.get('short_names') != 'true':
                return jsonify(error='Excel tab names have a 31-character limit. Confirm the proposed names for the exported copy.', requires_short_names=True, proposed_names=renamed), 409
            refreshed = production_export_frames(book, store, sources=sources)
            stream = BytesIO()
            with pd.ExcelWriter(stream, engine='openpyxl') as writer:
                for sheet in worksheets:
                    values = refreshed.get(sheet.title)
                    if values is None:
                        values = sheet.get_all_values()
                    name = proposed[sheet.title]
                    pd.DataFrame(values).to_excel(writer, sheet_name=name, index=False, header=False)
                    ws = writer.sheets[name]
                    for row in ws:
                        for cell in row:
                            if isinstance(cell.value, str):
                                cell.data_type = 's'
                    ws.freeze_panes = 'A2'
                    if sheet.title in TRACKERS or tab_identity(sheet.title) or sheet.title in (OLD_FULL, OLD_REMAINING):
                        from openpyxl.styles import Font, PatternFill, Border, Side
                        border = Border(**{side: Side(style='thin', color='000000') for side in ('left', 'right', 'top', 'bottom')})
                        for cells in ws:
                            for cell in cells:
                                cell.font = Font(color='000000', bold=cell.row == 1)
                                cell.fill = PatternFill('solid', fgColor='FFFFFF')
                                cell.border = border
                    color_export_sheet(ws, values)
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
        return send_from_directory(ASSET_DIR / 'frontend' / 'dist', path)

    from monthly_api import register_monthly_routes
    auto_monthly_preview = register_monthly_routes(app, store, gate, maintenance, production_cache, production_snapshot, lambda: target_worksheet())
    from report_workspace import register_report_routes
    app.extensions['publish_active_reports'] = register_report_routes(
        app, report_workspace, gate, production_snapshot, lambda: target_worksheet(), production_cache.invalidate)
    app.extensions['monthly_tick'] = auto_monthly_preview

    def resume_connection_sync():
        """Retry the oldest capture after its authentication/network failure clears."""
        nonlocal connection_retry_after
        if clock.monotonic() < connection_retry_after:
            return False
        unsynced = store.unsynced_ids()
        if not unsynced:
            return False
        failures = {row['preview_id']: row['error'] for row in store.failed_syncs()}
        error = failures.get(unsynced[0], '').casefold()
        if not any(message in error for message in (
                'google sheets authentication failed', 'google sheets connection failed',
                'google sheets access failed (transporterror)',
                'set google_service_account_json to a valid service account json',
                'open connections & settings to add your google sheet and service-account key')):
            return False
        if not gate.acquire(blocking=False):
            return False
        try:
            target_worksheet()
        except Exception:
            # A rejected key or unavailable network must not cause a write loop.
            connection_retry_after = clock.monotonic() + 300
            return False
        finally:
            gate.release()
        connection_retry_after = float('-inf')
        return begin_sync('retry', unsynced[0])

    app.extensions['resume_connection_sync'] = resume_connection_sync

    if start_scheduler:
        def schedule_loop():
            while not scheduler_stop.wait(15):
                try:
                    if desktop_mode and not (SPREADSHEET_ID and os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')):
                        continue
                    recover_latest_preview()
                    app.extensions['refresh_imported_reports']()
                    auto_monthly_preview()
                    if not schedule_tick():
                        pending = store.pending_syncs()
                        if pending:
                            begin_sync('retry', pending[0])
                        else:
                            resume_connection_sync()
                except Exception:
                    app.logger.exception('Scheduled capture could not start')
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
