-- An office worker uses the owner's encrypted Auth session, not a project-wide
-- service-role key. Editors/viewers cannot call the canonical commit boundary.
begin;
create function public.tv_worker_claim_job(p_workspace uuid,p_token uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  return public.tv_claim_job(p_workspace,p_token);
end $$;
create function public.tv_worker_commit_capture(p_workspace uuid,p_token uuid,p_rows jsonb,p_report jsonb,p_review boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  return public.tv_commit_capture(p_workspace,p_token,p_rows,p_report,p_review);
end $$;
create function public.tv_worker_ack_publication(p_workspace uuid,p_token uuid,p_revision bigint)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  return public.tv_ack_publication(p_workspace,p_token,p_revision);
end $$;
revoke all on function public.tv_worker_claim_job(uuid,uuid),public.tv_worker_commit_capture(uuid,uuid,jsonb,jsonb,boolean),
  public.tv_worker_ack_publication(uuid,uuid,bigint) from public,anon,authenticated;
grant execute on function public.tv_worker_claim_job(uuid,uuid),public.tv_worker_commit_capture(uuid,uuid,jsonb,jsonb,boolean),
  public.tv_worker_ack_publication(uuid,uuid,bigint) to authenticated;
commit;
