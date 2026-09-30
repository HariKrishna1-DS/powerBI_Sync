"""Local React dashboard API. The server deliberately starts with no seed data."""
import argparse
from datetime import datetime, timedelta, timezone
import json
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

IST = timezone(timedelta(hours=5, minutes=30), 'IST')


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


def create_app(root=None, runner=None, syncer=None, start_scheduler=False):
    app = Flask(__name__, static_folder=None)
    app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024
    store = PreviewStore(root or BASE_DIR / 'previews')
    runner = runner or run_sync
    syncer = syncer or sync_workbook
    gate = threading.Lock()
    state_lock = threading.Lock()
    schedule_lock = threading.Lock()
    state = {'running': False, 'stage': 'Ready', 'action': None, 'result': None, 'run_id': 0}
    schedule_path = store.root.parent / 'sync_schedule.json'

    def load_schedule():
        default = {'enabled': False, 'time': '09:00', 'times': ['09:00'], 'last_triggered_date': None, 'triggered_today': [], 'timezone': 'Asia/Kolkata'}
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

    def prepare_sync(preview_id=None, previous_id=None, keys=None, ignore=None, remaining_products=None):
        if not store.list():
            raise ValueError('Capture or import a preview before syncing Google Sheets.')
        selected_preview = store.get(int(preview_id)) if preview_id is not None else store.get(store.list()[0]['id'])
        if previous_id is None:
            previous_id = next((item['id'] for item in store.list() if item['id'] < selected_preview['id']), None)
        if previous_id is not None and int(previous_id) >= selected_preview['id']:
            raise ValueError('The previous preview must be older than the selected preview.')
        previous_preview = store.get(int(previous_id)) if previous_id is not None else None
        frame, completed_orders = automatic_sync_frame(selected_preview, previous_preview, keys, ignore, store=store)
        frame.attrs['completion_dates'] = completion_history(store, selected_preview['id'])
        frame.attrs['preview_name'] = selected_preview['name']
        frame.attrs['preview_id'] = selected_preview['id']
        frame.attrs['sync_time'] = datetime.now(IST).strftime('%Y-%m-%d %I:%M:%S %p IST')
        if remaining_products is not None:
            frame.attrs['selected_products'] = remaining_products
            try:
                (BASE_DIR / 'remaining_products.json').write_text(json.dumps(remaining_products, indent=2), encoding='utf-8')
            except Exception:
                pass
        return frame, selected_preview, completed_orders, previous_id

    def begin_sync(trigger='manual', preview_id=None, previous_id=None, keys=None, ignore=None, remaining_products=None):
        frame, selected_preview, completed_orders, previous_id = prepare_sync(preview_id, previous_id, keys, ignore, remaining_products)
        if not gate.acquire(blocking=False):
            return False
        with state_lock:
            state.update(running=True, action='sync', stage='Syncing latest preview', result=None,
                         run_id=state['run_id'] + 1)

        def work():
            try:
                worksheets = syncer(frame)
                result = {'action': 'sync', 'trigger': trigger, 'error': None,
                          'google_sheet': 'success', 'preview_id': selected_preview['id'],
                          'preview_name': selected_preview['name'], 'rows': len(frame),
                          'worksheets': worksheets, 'stage': 'Finished'}
                result['status_rules'] = AUTOMATIC_RULES
                result['completed_orders'] = len(completed_orders)
                result['previous_id'] = previous_id
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
                frame, preview, completed, previous_id = prepare_sync(preview_id)
                with state_lock:
                    state.update(action='sync', stage=f"Syncing {preview['name']} to Google Sheets")
                worksheets = syncer(frame)
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
        now = (now or datetime.now(IST)).astimezone(IST)
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
        daily_reports = daily_orders(store)
        daily_completed_ids = list(dict.fromkeys(oid for r in daily_reports for oid in r['missing_ids']))
        return jsonify(previews=store.list(), job=job, schedule=schedule, sheet_url=TARGET_GSHEET_URL,
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
        preview_id = request.args.get('preview_id', type=int)
        selected_date = reporting_date(store.get(preview_id)) if preview_id is not None else None
        return jsonify(rows=daily_orders(store, preview_id), selected_date=selected_date)

    @app.get('/api/monthly-orders')
    def get_monthly_orders():
        try:
            book, _ = target_worksheet()
            sheet_rows = []
            for title in ('Full Title', 'Remaining Products'):
                values = book.worksheet(title).get_all_values()
                if values:
                    sheet_rows.extend(dict(zip(values[0], row)) for row in values[1:])
            return jsonify(rows=monthly_orders(store, sheet_rows), sla_error=None)
        except Exception as exc:
            app.logger.warning('Could not refresh monthly SLA from Google Sheets: %s', exc)
            return jsonify(rows=monthly_orders(store), sla_error='Could not read the connected Google Sheet. Showing saved preview values.')

    @app.get('/api/live-sheets')
    def get_live_sheets():
        book, _ = target_worksheet()
        sheets = {}
        for title in ('All Products', 'Full Title', 'Remaining Products', 'Status Report'):
            values = book.worksheet(title).get_all_values()
            sheets[title] = {'columns': values[0], 'rows': [dict(zip(values[0], row)) for row in values[1:]]} if values else {'columns': [], 'rows': []}
        status = sheets['Status Report']
        names = {row.get('Preview', '') for row in status['rows'] if row.get('Preview', '')}
        return jsonify(preview_name=names.pop() if len(names) == 1 else None, sheets=sheets)

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
                with state_lock:
                    state.update(result=result, stage=result.get('stage', 'Finished'))
            except Exception as exc:
                app.logger.exception('Extraction failed')
                with state_lock:
                    state.update(stage='Failed', result={'error': str(exc)})
            finally:
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

        with schedule_lock:
            current = load_schedule()
            changed = current['enabled'] != enabled or current.get('times') != validated_times
            current.update(enabled=enabled, times=validated_times, time=validated_times[0])
            if changed or enabled:
                now = datetime.now(IST)
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
        return jsonify(store.save(frame, source=Path(upload.filename).name)), 201

    @app.get('/api/previews/<int:number>/download/<kind>')
    def download(number, kind):
        preview = store.get(number)
        if kind not in ('csv', 'xlsx'):
            raise ValueError('Unsupported download format.')
        if kind == 'xlsx':
            previous_id = next((item['id'] for item in store.list() if item['id'] < preview['id']), None)
            previous_preview = store.get(int(previous_id)) if previous_id is not None else None
            frame, _ = automatic_sync_frame(preview, previous_preview, store=store)
            frame.attrs['completion_dates'] = completion_history(store, preview['id'])
            frame.attrs['preview_name'] = preview['name']
            frame.attrs['preview_id'] = preview['id']
            remaining_products = None
            try:
                path = BASE_DIR / 'remaining_products.json'
                if path.exists():
                    remaining_products = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                pass
            stream = build_synced_workbook_stream(frame, preview_name=preview['name'], selected_products=remaining_products)
            return send_file(stream, as_attachment=True, download_name=f"{preview['name']}_GoogleSheets.xlsx")
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
            with pd.ExcelWriter(stream, engine='openpyxl') as writer:
                for sheet in book.worksheets():
                    values = sheet.get_all_values()
                    pd.DataFrame(values).to_excel(writer, sheet_name=sheet.title, index=False, header=False)
                    ws = writer.sheets[sheet.title]
                    for row in ws:
                        for cell in row:
                            if isinstance(cell.value, str):
                                cell.data_type = 's'
                    ws.freeze_panes = 'A2'
                    if sheet.title == 'Status Report' and values and 'Preview' in values[0]:
                        offset = values[0].index('Preview')
                        names = {r[offset] for r in values[1:] if len(r) > offset}
                        if len(names) == 1:
                            name = names.pop()
                            if name.startswith('preview') and name[7:].isdigit():
                                preview_name = name
            stream.seek(0)
            return send_file(stream, as_attachment=True, download_name=f'{preview_name}_GoogleSheets.xlsx')
        except Exception as exc:
            return jsonify(error=f'Google Sheets export failed: {exc}'), 502
        finally:
            gate.release()

    @app.post('/api/compare')
    def comparison():
        body = request.get_json()
        previous, latest = store.get(int(body['previous'])), store.get(int(body['latest']))
        result = compare(previous, latest, body.get('keys'), body.get('ignore'))
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
            while True:
                clock.sleep(15)
                try:
                    schedule_tick()
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
