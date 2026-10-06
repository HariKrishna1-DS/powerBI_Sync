"""Report-source routes; staged imports never enter queue/completion history."""
import threading
from flask import jsonify, request, send_file

from report_workspace import ReportWorkspace


def register_report_routes(app, store, gate, maintenance, tracker_snapshot, get_book, spreadsheet_id):
    workspace = ReportWorkspace(store)
    publish_lock = threading.Lock()

    def snapshot(force=False, known_revision=None):
        prefs = workspace.preferences()
        if prefs['source'] == 'import':
            result = workspace.imported_snapshot()
            if result['revision'] == known_revision:
                result = {k: v for k, v in result.items() if k not in ('sheets', 'reports')}
                result['unchanged'] = True
        else:
            result = tracker_snapshot(force=force, known_revision=known_revision)
            result['source_mode'] = 'tracker'
        result['report_preferences'] = prefs
        return result

    def publish_current():
        from report_publishing import publish_reports
        workspace.update(publish_status='publishing', publish_error='')
        try:
            value = snapshot(force=True)
            if value.get('offline'):
                raise ValueError('Reconnect before publishing tracker reports. The saved offline copy will not overwrite live Sheets.')
            book, _ = get_book()
            result = publish_reports(book, value, workspace.capacity(value))
            workspace.update(publish_status='published', publish_error='', published=result)
            return result
        except Exception:
            workspace.update(publish_status='failed', publish_error='Reports are available locally. Sheets publishing failed; check the connection and designated writer, then retry.')
            raise

    def queue_publish(gate_owned=False):
        if not publish_lock.acquire(blocking=False):
            raise ValueError('Report publishing is already running.')
        if maintenance.is_set() or (not gate_owned and not gate.acquire(blocking=False)):
            publish_lock.release()
            raise ValueError('Wait for the current operation before changing the report source.')
        workspace.update(publish_status='publishing', publish_error='')

        def run():
            try:
                publish_current()
            except Exception:
                app.logger.exception('Report publishing failed')
            finally:
                gate.release()
                publish_lock.release()
        threading.Thread(target=run, daemon=True).start()

    def json_body():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValueError('Send a JSON object containing the report settings.')
        return value

    @app.get('/api/reporting')
    def settings():
        return jsonify(preferences=workspace.preferences(), imports=workspace.imports())

    @app.get('/api/reporting/storage')
    def storage():
        from workspace_retention import storage_status
        return jsonify(storage_status(store))

    @app.post('/api/reporting/archive')
    def archive():
        from workspace_retention import archive_history
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before archiving.'), 409
        try:
            result = archive_history(store, workspace.preferences().get('import_id'))
            workspace.update()
            return jsonify(result)
        finally:
            gate.release()

    @app.post('/api/reporting/protect-backups')
    def protect_backups():
        from backup_protection import migrate_backups, enabled
        if not enabled():
            raise ValueError('Open the desktop app to protect local recovery archives.')
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before protecting backups.'), 409
        try:
            return jsonify(migrate_backups(store.root.parent / 'backups'))
        finally:
            gate.release()

    @app.get('/api/reporting/cloud-history')
    def cloud_history():
        from cloud_retention import plan, FILE
        book, _ = get_book()
        result = plan(book)
        result['archives'] = sorted(p.name for p in (store.root.parent / 'cloud-archives').glob('*.tvcloud') if FILE.fullmatch(p.name))
        return jsonify(result)

    @app.post('/api/reporting/cloud-history')
    def archive_cloud_history():
        from cloud_retention import archive
        body = json_body()
        if not isinstance(body.get('fingerprint'), str):
            raise ValueError('Preview the cloud archive plan first.')
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before archiving cloud history.'), 409
        try:
            book, _ = get_book()
            return jsonify(archive(book, store.root.parent / 'cloud-archives', body['fingerprint']))
        finally:
            gate.release()

    @app.post('/api/reporting/cloud-history/restore')
    def restore_cloud_history():
        from cloud_retention import restore, FILE
        name = json_body().get('archive')
        if not isinstance(name, str) or not FILE.fullmatch(name):
            raise ValueError('Select a valid cloud recovery archive.')
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before restoring cloud history.'), 409
        try:
            book, _ = get_book()
            return jsonify(restore(book, (store.root.parent / 'cloud-archives' / name).read_bytes()))
        finally:
            gate.release()

    @app.get('/api/reporting/archive/<name>')
    def download_archive(name):
        import re
        if not re.fullmatch(r'retention-\d{8}-\d{6}-\d{6}\.(zip|tvbackup)', name):
            raise ValueError('Select a valid retention archive.')
        return send_file(store.root.parent / 'backups' / name, as_attachment=True, download_name=name)

    @app.post('/api/reporting/import')
    def import_files():
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before importing reports.'), 409
        try:
            files = request.files.getlist('files')
            result = workspace.save_import([(file.filename, file.read()) for file in files])
            return jsonify(result)
        finally:
            gate.release()

    @app.post('/api/reporting/source')
    def source():
        if publish_lock.locked() or maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before changing the report source.'), 409
        handed_off = False
        try:
            body = json_body()
            mode = body.get('source')
            if mode not in ('tracker', 'import'):
                raise ValueError('Choose Tracker report or Import Excel report.')
            if mode == 'import':
                if not isinstance(body.get('import_id'), str) or not body['import_id']:
                    raise ValueError('Select a validated Excel import.')
                workspace.imported_snapshot(body.get('import_id'))
            workspace.update(source=mode, import_id=body.get('import_id') if mode == 'import' else workspace.preferences()['import_id'], publish_status='pending', published=None)
            queue_publish(gate_owned=True)
            handed_off = True
        finally:
            if not handed_off:
                gate.release()
        return jsonify(preferences=workspace.preferences()), 202

    @app.post('/api/reporting/publish')
    def publish():
        queue_publish()
        return jsonify(preferences=workspace.preferences()), 202

    @app.get('/api/reporting/capacity')
    def capacity():
        value = snapshot()
        return jsonify(**workspace.capacity(value), preferences=workspace.preferences(),
                       source=value['source'], offline=value.get('offline', False), updated_at=value.get('updated_at'))

    @app.post('/api/reporting/capacity')
    def set_capacity():
        if publish_lock.locked() or maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current operation before saving targets.'), 409
        handed_off = False
        try:
            body = json_body()
            workspace.set_targets(body.get('date', ''), body.get('capacity'), body.get('extended'))
            queue_publish(gate_owned=True)
            handed_off = True
        finally:
            if not handed_off:
                gate.release()
        return jsonify(saved=True), 202

    @app.get('/api/reporting/day-link')
    def day_link():
        prefs = workspace.preferences()
        published = prefs.get('published') or {}
        date = request.args.get('date')
        if prefs['publish_status'] != 'published' or date not in published.get('daily_dates', []):
            raise ValueError('Publish the current report to Google Sheets before opening this date.')
        row = published['daily_dates'].index(date) + 2
        return jsonify(url=f'https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={published["daily_gid"]}&range=A{row}:I{row}')

    @app.get('/api/reporting/export')
    def export():
        from report_publishing import export_reports
        value = snapshot()
        return send_file(export_reports(value, workspace.capacity(value)), as_attachment=True,
                         download_name='Tv-Tracker-Reports.xlsx')

    app.extensions['report_workspace'] = workspace
    app.extensions['publish_reports'] = publish_current
    return snapshot
