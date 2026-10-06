"""Desktop-only pilot actions. Production routing is deliberately not switched."""
import uuid
from flask import jsonify, request

from shared_backend import CloudError, CloudOutbox, SupabaseRpc
from cloud_backend.transport import OwnerWorkerRpc
from cloud_backend.worker import ShadowWorker


def register_shared_routes(app, store, gate, maintenance):
    @app.post('/api/desktop/shared/action')
    def shared_action():
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or body.get('action') not in ('inspect', 'submit', 'drain', 'worker'):
            return jsonify(error='Choose a valid shared workspace action.'), 422
        if maintenance.is_set() or not gate.acquire(blocking=False):
            return jsonify(error='Wait for the current workspace operation to finish.'), 409
        try:
            workspace = str(uuid.UUID(body.get('workspace', '')))
            config = body.get('config', {})
            access = request.headers.get('X-TV-Cloud-Access', '')
            if not access or len(access) > 16384:
                return jsonify(error='Sign in to the shared workspace first.'), 401
            rpc = SupabaseRpc(config.get('url', ''), config.get('publishableKey', ''), lambda: access)
            # Authorization and current mode come from the server, not local form fields.
            memberships = rpc.call('tv_list_workspaces', {})
            member = next((row for row in memberships if row.get('id') == workspace), None)
            if member is None:
                return jsonify(error='This account does not have access to that workspace.'), 403
            if member.get('mode') != 'shadow':
                return jsonify(error='This migration pilot only operates on validation workspaces.'), 409
            action = body['action']
            outbox = CloudOutbox(store)
            result = {}
            if action == 'submit':
                if member['role'] not in ('owner', 'editor'):
                    return jsonify(error='An editor or owner account is required to submit captures.'), 403
                if type(body.get('preview_id')) is not int:
                    return jsonify(error='Choose a saved capture.'), 422
                preview = store.get(body['preview_id'])
                outbox.enqueue(workspace, preview, member['queue_scope'])
            if action in ('submit', 'drain'):
                outbox.resume_auth(workspace)
                result['accepted'] = outbox.drain_one(workspace, rpc)
            if action == 'worker':
                if member['role'] != 'owner':
                    return jsonify(error='Only the workspace owner can run the office worker.'), 403
                worker_rpc = OwnerWorkerRpc(config['url'], config['publishableKey'], lambda: access)
                worker = ShadowWorker(worker_rpc, store.root.parent / 'shared-worker' / workspace)
                result['worker'] = worker.step(workspace)
            snapshot = rpc.snapshot(workspace)
            result.update(revision=snapshot['revision'], orders=len(snapshot['orders']),
                published_revision=snapshot['published_revision'], mode=snapshot['mode'], uploads=outbox.status(workspace))
            return jsonify(result)
        except CloudError as exc:
            return jsonify(error=str(exc), kind=exc.kind), 401 if exc.kind == 'auth' else 503 if exc.kind == 'retry' else 409
        except (ValueError, KeyError, TypeError, AttributeError):
            return jsonify(error='The shared workspace request or response could not be validated.'), 422
        finally:
            gate.release()
