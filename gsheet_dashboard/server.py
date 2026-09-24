"""Local React dashboard API. The server deliberately starts with no seed data."""
import argparse
from datetime import datetime
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

from datatrace_sync import run_sync, sync_workbook
from preview_store import PreviewStore, compare
from sync_config import BASE_DIR, TARGET_GSHEET_URL


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
        default = {'enabled': False, 'time': '09:00', 'last_triggered_date': None}
        try:
            saved = json.loads(schedule_path.read_text(encoding='utf-8'))
            if isinstance(saved, dict):
                default.update({key: saved.get(key, default[key]) for key in default})
        except (OSError, ValueError):
            pass
        return default

    def save_schedule(schedule):
        schedule_path.write_text(json.dumps(schedule, indent=2), encoding='utf-8')

    def begin_sync(trigger='manual', preview_id=None):
        if not store.list():
            raise ValueError('Capture or import a preview before syncing Google Sheets.')
        if preview_id is not None:
            store.get(int(preview_id))
        if not gate.acquire(blocking=False):
            return False
        with state_lock:
            state.update(running=True, action='sync', stage='Syncing latest preview', result=None,
                         run_id=state['run_id'] + 1)

        def work():
            try:
                selected_preview = store.get(int(preview_id)) if preview_id is not None else store.get(store.list()[0]['id'])
                frame = pd.DataFrame(selected_preview['rows'], columns=selected_preview['columns'])
                worksheets = syncer(frame)
                result = {'action': 'sync', 'trigger': trigger, 'error': None,
                          'google_sheet': 'success', 'preview_id': selected_preview['id'],
                          'preview_name': selected_preview['name'], 'rows': len(frame),
                          'worksheets': worksheets, 'stage': 'Finished'}
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
        return jsonify(previews=store.list(), job=job, schedule=schedule, sheet_url=TARGET_GSHEET_URL)

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
        if not begin_sync('manual', preview_id):
            return jsonify(error='An extraction or sync is already running.'), 409
        return jsonify(accepted=True), 202

    @app.post('/api/sync-schedule')
    def update_schedule():
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get('enabled'))
        sync_time = str(body.get('time', '')).strip()
        try:
            datetime.strptime(sync_time, '%H:%M')
        except ValueError as exc:
            raise ValueError('Choose a valid daily sync time.') from exc
        with schedule_lock:
            current = load_schedule()
            changed = current['enabled'] != enabled or current['time'] != sync_time
            current.update(enabled=enabled, time=sync_time)
            if changed:
                current['last_triggered_date'] = None
            save_schedule(current)
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
        store.get(number)
        if kind not in ('csv', 'xlsx'):
            raise ValueError('Unsupported download format.')
        return send_from_directory(store.root, f'preview{number}.{kind}', as_attachment=True)

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
                now = datetime.now().astimezone()
                with schedule_lock:
                    schedule = load_schedule()
                    due = (schedule['enabled'] and now.strftime('%H:%M') >= schedule['time']
                           and schedule['last_triggered_date'] != now.date().isoformat())
                    if due:
                        schedule['last_triggered_date'] = now.date().isoformat()
                        save_schedule(schedule)
                if due:
                    try:
                        begin_sync('schedule')
                    except Exception:
                        app.logger.exception('Scheduled Google Sheets sync could not start')
        threading.Thread(target=schedule_loop, daemon=True).start()

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8510)
    args = parser.parse_args()
    from waitress import serve
    port = args.port
    while port < args.port + 20:
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', port))
                break
            except OSError:
                port += 1
    else:
        raise RuntimeError('No free dashboard port. Choose another port with --port.')
    print(f'DataTrace Workspace: http://localhost:{port}', flush=True)
    serve(create_app(start_scheduler=True), host='127.0.0.1', port=port, threads=8)


if __name__ == '__main__':
    main()
