"""Authenticated monthly maintenance routes; destructive work requires its preview token."""
from datetime import datetime
import json
import time
from flask import jsonify, request, send_file

from monthly_production import (ARCHIVE, BASES, apply_plan, import_plan, migration_plan,
    monthly_workbook, preserve_formulas, read_import, rollover_plan, snapshot, tab_identity, tab_name, new_plan)


def register_monthly_routes(app, store, gate, maintenance, production_cache, load_snapshot, get_book):
    def initialize():
        with store.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS monthly_operations (id TEXT PRIMARY KEY, created REAL NOT NULL, status TEXT NOT NULL, plan_json TEXT NOT NULL, result_json TEXT)')

    initialize()

    def public(plan):
        return {key: value for key, value in plan.items() if key not in ('writes', 'fingerprint', 'formula_cells')}

    def save(plan):
        initialize()  # Restoring an older workspace is supported.
        with store.connect() as db:
            db.execute("DELETE FROM monthly_operations WHERE status='preview' AND created < ?", (time.time()-86400,))
            db.execute('INSERT INTO monthly_operations VALUES (?,?,?,?,?)', (plan['id'], plan['created'], 'preview', json.dumps(plan), None))
        return public(plan)

    def acquire():
        return not maintenance.is_set() and gate.acquire(blocking=False)

    @app.post('/api/monthly-maintenance/preview', endpoint='monthly_maintenance_preview')
    def preview():
        if not acquire():
            return jsonify(error='Wait for the current operation to finish.'), 409
        try:
            body = request.form if request.files else (request.get_json(silent=True) or {})
            kind, month = body.get('kind'), body.get('month', '2026-10')
            book, _ = get_book()
            before = snapshot(book)
            if kind == 'setup':
                plan = migration_plan(before, month)
            elif kind == 'rollover':
                plan = rollover_plan(before, month)
            elif kind == 'import':
                uploads = []
                for field, base in zip(('full_search', 'co_update'), BASES):
                    file = request.files.get(field)
                    if file:
                        if not file.filename.lower().endswith('.xlsx'):
                            raise ValueError('Production imports require .xlsx workbooks.')
                        uploads.append((base, file.filename.replace('\\', '/').split('/')[-1], read_import(file.read(), base)))
                if not uploads:
                    raise ValueError('Select at least one production workbook.')
                plan = import_plan(before, uploads, month)
            else:
                raise ValueError('Choose setup, import or rollover.')
            return jsonify(save(preserve_formulas(plan, before)))
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        except Exception:
            app.logger.exception('Monthly preview failed')
            return jsonify(error='Could not preview the monthly operation. Check the workbook, connection and Sheet permissions. No production data was changed.'), 502
        finally:
            gate.release()

    @app.post('/api/monthly-maintenance/apply', endpoint='monthly_maintenance_apply')
    def apply():
        body = request.get_json(silent=True) or {}
        if body.get('confirmed') is not True or not isinstance(body.get('id'), str):
            return jsonify(error='Review and confirm a saved preview before changing production data.'), 422
        if not acquire():
            return jsonify(error='Wait for the current operation to finish.'), 409
        try:
            initialize()
            with store.connect() as db:
                row = db.execute('SELECT status,plan_json,result_json FROM monthly_operations WHERE id=?', (body['id'],)).fetchone()
            if not row:
                return jsonify(error='Preview not found. Generate a new preview.'), 404
            if row[0] == 'applied':
                return jsonify(json.loads(row[2]))
            plan = json.loads(row[1])
            from tracker_sync import sync_lock
            with sync_lock(store.root):
                book, _ = get_book()
                result = dict(public(plan), **apply_plan(book, plan))
            with store.connect() as db:
                db.execute("UPDATE monthly_operations SET status='applied',result_json=? WHERE id=?", (json.dumps(result), plan['id']))
            production_cache.invalidate()
            return jsonify(result)
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        except Exception:
            app.logger.exception('Monthly apply could not be confirmed')
            production_cache.invalidate()
            return jsonify(error='The operation could not be confirmed. Keep this preview and retry its confirmation; the saved receipt prevents duplicate moves.'), 502
        finally:
            gate.release()

    @app.get('/api/monthly-maintenance', endpoint='monthly_maintenance_history')
    def history():
        initialize()
        with store.connect() as db:
            rows = db.execute('SELECT status,plan_json,result_json FROM monthly_operations ORDER BY created DESC LIMIT 30').fetchall()
        return jsonify(operations=[dict(public(json.loads(plan)), status=status,
            result=json.loads(result) if result else None) for status, plan, result in rows])

    @app.get('/api/export/monthly', endpoint='monthly_excel_export')
    def export():
        from monthly_production import month_key
        from tracker_sync import tracker_sources
        if not acquire():
            return jsonify(error='Wait for the current operation before exporting.'), 409
        try:
            month = month_key(request.args.get('month', ''))
            report_workspace = app.extensions.get('report_workspace')
            if report_workspace and report_workspace.preferences()['source'] == 'import':
                from report_publishing import export_reports
                value = report_workspace.imported_snapshot()
                value['reports']['daily'] = [r for r in value['reports']['daily'] if r['Date'].startswith(month)]
                value['reports']['monthly'] = [r for r in value['reports']['monthly'] if r['Month'] == month]
                rows = [r for report in value['reports']['monthly'] for r in report['rows']]
                if not rows:
                    return jsonify(error=f'No imported orders are available for {month}.'), 404
                for label in ('Overview', 'All Products'):
                    value['sheets'][label]['rows'] = rows
                return send_file(export_reports(value, report_workspace.capacity(value)), as_attachment=True,
                                 download_name=f'Tv-Tracker-Imported-{month}.xlsx')
            # One live read supplies both detail and totals; no stale-summary/live-detail mix.
            book, _ = get_book()
            sources = tracker_sources(book)
            from monthly_production import decode
            from tracker_sync import sheet_reports
            reports = sheet_reports({s.title if tab_identity(s.title) else base: decode(values)
                                     for base, s, values in sources}, store.latest_sync_report())['monthly']
            report = next((r for r in reports if r['Month'] == month), None)
            if not report or not report['rows']:
                return jsonify(error=f'No production orders are available for {month}.'), 404
            stream, filename = monthly_workbook(report, [(base, s.title, values) for base, s, values in sources])
            return send_file(stream, as_attachment=True, download_name=filename,
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        except ValueError as exc:
            return jsonify(error=str(exc)), 422
        except Exception:
            app.logger.exception('Monthly export failed')
            return jsonify(error='Could not export the selected month. Check the Google Sheets connection and retry.'), 502
        finally:
            gate.release()

    checked = [None]
    def auto_preview():
        """At the boundary (or next launch), prepare counts; never bypass consent."""
        now = time.monotonic()
        if (checked[0] is not None and now-checked[0] < 3600) or not acquire():
            return
        checked[0] = now
        try:
            from tracker_sync import IST
            month = datetime.now(IST).strftime('%Y-%m')
            book, _ = get_book()
            before = snapshot(book)
            if before and all(tab_identity(title) for title in before) and month > ARCHIVE:
                from tracker_sync import HEADERS, sync_lock
                opening = new_plan(before, 'open_month')
                opening['writes'] = {tab_name(base, month): [HEADERS] for base in BASES if tab_name(base, month) not in before}
                if opening['writes']:
                    # Creating missing empty tabs never removes or overwrites production rows.
                    opening['automatic'] = True
                    opening['counts'] = [{'target': title, 'added': 0} for title in opening['writes']]
                    save(opening)
                    with sync_lock(store.root):
                        result = dict(public(opening), **apply_plan(book, opening))
                    with store.connect() as db:
                        db.execute("UPDATE monthly_operations SET status='applied',result_json=? WHERE id=?", (json.dumps(result), opening['id']))
                    production_cache.invalidate()
                    before = snapshot(book)
            periods = sorted({tab_identity(t)[1] for t in before if tab_identity(t) and ARCHIVE < tab_identity(t)[1] < month})
            initialize()
            with store.connect() as db:
                pending = [json.loads(r[0]) for r in db.execute("SELECT plan_json FROM monthly_operations WHERE status='preview'")]
            for period in periods:
                if any(p.get('month') == period and time.time()-p['created'] < 1800 for p in pending):
                    continue
                plan = rollover_plan(before, period)
                if plan['moves']:
                    plan['automatic'] = True
                    save(preserve_formulas(plan, before))
        except Exception:
            app.logger.exception('Automatic rollover preview deferred until next connection')
        finally:
            gate.release()
    return auto_preview
