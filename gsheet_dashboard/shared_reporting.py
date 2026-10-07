"""Use shared report sources/targets without touching Google on client PCs."""
import hashlib
import json
import uuid

from report_workspace import read_workbooks, validate_targets
from shared_backend import CloudError


class SharedReportWorkspace:
    def __init__(self, runtime):
        self.runtime = runtime

    def preferences(self):
        return self.runtime.cached_preferences()

    def imports(self):
        return self.runtime.report_state()['imports']

    def save_import(self, uploads, choices=None):
        self.runtime.authorize_capture()
        dataset = read_workbooks(uploads, choices)
        fingerprint = hashlib.sha256(json.dumps(dataset,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        identity = str(uuid.uuid5(uuid.UUID(self.runtime.selection['id']),fingerprint))
        result = self.runtime.requests.perform(self.runtime.rpc,'tv_save_report_import', {
            'p_workspace':self.runtime.selection['id'],'p_import':identity,'p_dataset':dataset})
        if result.get('id')!=identity or result.get('count')!=len(dataset['rows']):
            raise CloudError('The shared import receipt could not be verified. Retry uses the same identity.', 'retry')
        return dict(result,digest=fingerprint,**{k:dataset[k] for k in ('files','skipped','duplicates_removed','conflicts_resolved')})

    def imported_snapshot(self, identity=None):
        value = self.runtime.snapshot(force=True)
        if value.get('source_mode')!='import' or (identity and value.get('import_id')!=identity):
            raise ValueError('Select this import as the shared report source before exporting it.')
        return value

    def capacity(self, snapshot):
        return snapshot['capacity']

    def set_targets(self, date, capacity, extended, revision):
        validate_targets(date,capacity,extended)
        return self.runtime.report_change('capacity', {'date':date,'capacity':capacity,'extended':extended},revision)
