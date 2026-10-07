-- Owner-reviewed baseline and fixed office-worker destination. No implicit cutover.
begin;
alter table tv_tracker.workspaces add column spreadsheet_id text;
alter table tv_tracker.workspaces add column worker_id uuid;
alter table tv_tracker.workspaces add column baseline_hash text;
create unique index workspace_publication_destination on tv_tracker.workspaces(spreadsheet_id) where mode='active';

create function public.tv_seed_workspace(p_workspace uuid,p_operation uuid,p_rows jsonb,p_next_sequence bigint)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; b jsonb; r jsonb; item jsonb; h text;
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  if p_operation is null or p_rows is null or jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows)>100000
    or octet_length(p_rows::text)>50000000 or p_next_sequence is null or p_next_sequence<1 then
    raise exception 'Invalid migration baseline' using errcode='22023'; end if;
  if exists(select 1 from jsonb_array_elements(p_rows) x where jsonb_typeof(x)<>'object'
    or jsonb_typeof(x->'Order Number') is distinct from 'string'
    or length(trim(x->>'Order Number')) not between 1 and 200 or (x->>'Order Number') ~ '[^ -~]')
    or (select count(*)<>count(distinct lower(trim(x->>'Order Number'))) from jsonb_array_elements(p_rows) x) then
    raise exception 'Invalid or duplicate baseline identities' using errcode='22023'; end if;
  h:=encode(sha256(convert_to(p_rows::text,'UTF8')),'hex');
  b:=jsonb_build_object('kind','seed','hash',h,'next_sequence',p_next_sequence);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Migration operation changed' using errcode='23505'; end if;
    return old.result;
  end if;
  if w.mode<>'shadow' or w.revision<>0 or exists(select 1 from tv_tracker.captures where workspace_id=p_workspace)
    or exists(select 1 from tv_tracker.orders where workspace_id=p_workspace)
    or exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace) then
    raise exception 'Baseline needs an empty validation workspace' using errcode='40001'; end if;
  for item in select value from jsonb_array_elements(p_rows) loop
    insert into tv_tracker.orders(workspace_id,order_key,data) values(p_workspace,lower(trim(item->>'Order Number')),item);
  end loop;
  update tv_tracker.workspaces set revision=1,baseline_hash=h,next_sequence=p_next_sequence where id=p_workspace;
  r:=jsonb_build_object('revision',1,'orders',jsonb_array_length(p_rows),'hash',h,'next_sequence',p_next_sequence);
  insert into tv_tracker.operations(workspace_id,id,actor,body,result) values(p_workspace,p_operation,auth.uid(),b,r);
  return r;
end $$;

create function public.tv_activate_workspace(p_workspace uuid,p_operation uuid,p_revision bigint,p_spreadsheet text,p_worker uuid,p_legacy_stopped boolean)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; b jsonb; r jsonb;
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  if p_operation is null or p_worker is null or p_spreadsheet is null or p_spreadsheet !~ '^[A-Za-z0-9_-]{20,150}$'
    or p_legacy_stopped is distinct from true or p_revision is null or p_revision<1 then
    raise exception 'Reviewed workbook, worker and stopped legacy writers required' using errcode='22023'; end if;
  b:=jsonb_build_object('kind','activate','revision',p_revision,'spreadsheet',p_spreadsheet,'worker',p_worker);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Activation operation changed' using errcode='23505'; end if;
    return old.result;
  end if;
  if w.mode<>'shadow' or w.revision<>p_revision or w.baseline_hash is null
    or exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace)
    or exists(select 1 from tv_tracker.captures where workspace_id=p_workspace and state='queued') then
    raise exception 'Migration revision or processing state changed' using errcode='40001'; end if;
  update tv_tracker.workspaces set mode='active',spreadsheet_id=p_spreadsheet,worker_id=p_worker where id=p_workspace;
  r:=jsonb_build_object('mode','active','revision',p_revision,'spreadsheet',p_spreadsheet,'worker',p_worker);
  insert into tv_tracker.operations(workspace_id,id,actor,body,result) values(p_workspace,p_operation,auth.uid(),b,r);
  return r;
end $$;

create function public.tv_workspace_status(p_workspace uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare r jsonb;
begin
  perform tv_tracker.require_member(p_workspace);
  select jsonb_build_object('id',w.id,'mode',w.mode,'revision',w.revision,'published_revision',w.published_revision,
    'spreadsheet',w.spreadsheet_id,'worker',w.worker_id,'baseline_hash',w.baseline_hash,
    'queue_scope',w.queue_scope,'pending_captures',(select count(*) from tv_tracker.captures c where c.workspace_id=w.id and c.state='queued'),
    'job',(select jsonb_build_object('kind',j.kind,'started_at',j.started_at,'revision',j.revision) from tv_tracker.jobs j where j.workspace_id=w.id))
    into r from tv_tracker.workspaces w where w.id=p_workspace;
  return r;
end $$;

create or replace function public.tv_worker_claim_job(p_workspace uuid,p_token uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  perform 1 from tv_tracker.workspaces where id=p_workspace and mode='shadow' for update;
  if not found then raise exception 'Use the designated office worker' using errcode='42501'; end if;
  return public.tv_claim_job(p_workspace,p_token);
end $$;

create function public.tv_office_claim_job(p_workspace uuid,p_token uuid,p_worker uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; r jsonb;
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  if w.mode<>'active' or w.worker_id is distinct from p_worker then
    raise exception 'Only the designated office worker may process this workspace' using errcode='42501'; end if;
  r:=public.tv_claim_job(p_workspace,p_token);
  if r is not null then r:=r||jsonb_build_object('spreadsheet',w.spreadsheet_id); end if;
  return r;
end $$;

revoke all on function public.tv_seed_workspace(uuid,uuid,jsonb,bigint),public.tv_activate_workspace(uuid,uuid,bigint,text,uuid,boolean),
  public.tv_workspace_status(uuid),public.tv_office_claim_job(uuid,uuid,uuid) from public,anon,authenticated;
grant execute on function public.tv_seed_workspace(uuid,uuid,jsonb,bigint),public.tv_activate_workspace(uuid,uuid,bigint,text,uuid,boolean),
  public.tv_workspace_status(uuid),public.tv_office_claim_job(uuid,uuid,uuid) to authenticated;
commit;
