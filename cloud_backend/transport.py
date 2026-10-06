"""Owner-scoped worker RPC names; no Supabase administrator key required."""
from shared_backend import SupabaseRpc


class OwnerWorkerRpc(SupabaseRpc):
    def call(self, name, body):
        names = {'tv_claim_job': 'tv_worker_claim_job',
                 'tv_commit_capture': 'tv_worker_commit_capture',
                 'tv_ack_publication': 'tv_worker_ack_publication'}
        if name not in names:
            raise ValueError('Unsupported worker operation.')
        return super().call(names[name], body)


class OfficeWorkerRpc(OwnerWorkerRpc):
    def __init__(self, url, api_key, access_token, worker, **kwargs):
        super().__init__(url, api_key, access_token, **kwargs)
        self.worker = worker

    def call(self, name, body):
        if name == 'tv_claim_job':
            return SupabaseRpc.call(self, 'tv_office_claim_job', dict(body, p_worker=self.worker))
        return super().call(name, body)
