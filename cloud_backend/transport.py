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
