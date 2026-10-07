-- Report imports and targets share the same revision/worker boundary as orders.
-- Imports are separate datasets; they never imply queue completion.
begin;
create table tv_tracker.report_settings (
  workspace_id uuid primary key references tv_tracker.workspaces(id),
  source text not null default 'tracker' check(source in ('tracker','import')),
  import_id uuid,
  default_capacity integer default 700 check(default_capacity between 0 and 1000000),
  default_extended integer default 750 check(default_extended between 0 and 1000000),
  check(default_capacity is null or default_extended is null or default_extended>=default_capacity)
);
create table tv_tracker.report_imports (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  id uuid not null,
  dataset jsonb not null,
  created_at timestamptz not null default now(),
  primary key(workspace_id,id)
);
alter table tv_tracker.report_settings add foreign key(workspace_id,import_id)
  references tv_tracker.report_imports(workspace_id,id);
create table tv_tracker.capacity_targets (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  day date not null,
  capacity integer check(capacity between 0 and 1000000),
  extended integer check(extended between 0 and 1000000),
  primary key(workspace_id,day),
  check(capacity is null or extended is null or extended>=capacity)
);
alter table tv_tracker.report_settings enable row level security;
alter table tv_tracker.report_imports enable row level security;
alter table tv_tracker.capacity_targets enable row level security;
revoke all on tv_tracker.report_settings,tv_tracker.report_imports,tv_tracker.capacity_targets from public,anon,authenticated;

create function tv_tracker.report_context(w uuid)
returns jsonb language sql security definer set search_path='' as $$
  select jsonb_build_object('preferences',jsonb_build_object(
    'source',coalesce(s.source,'tracker'),'import_id',s.import_id,
    'default_capacity',case when s.workspace_id is null then 700 else s.default_capacity end,
    'default_extended',case when s.workspace_id is null then 750 else s.default_extended end),
    'targets',coalesce((select jsonb_object_agg(t.day::text,jsonb_build_object('capacity',t.capacity,'extended',t.extended))
      from tv_tracker.capacity_targets t where t.workspace_id=w),'{}'::jsonb),
    'dataset',case when s.source='import' then i.dataset else null end,
    'imports',coalesce((select jsonb_agg(jsonb_build_object('id',r.id,'created',r.created_at,
      'count',jsonb_array_length(r.dataset->'rows'),'files',r.dataset->'files') order by r.created_at desc,r.id)
      from tv_tracker.report_imports r where r.workspace_id=w),'[]'::jsonb))
  from (select w as id) base left join tv_tracker.report_settings s on s.workspace_id=base.id
  left join tv_tracker.report_imports i on i.workspace_id=w and i.id=s.import_id;
$$;

create function public.tv_reporting_state(p_workspace uuid,p_revision bigint default null)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces;
begin
  perform tv_tracker.require_member(p_workspace);
  select * into w from tv_tracker.workspaces where id=p_workspace for share;
  if p_revision is not null and p_revision<>w.revision then
    raise exception 'Report revision changed' using errcode='40001'; end if;
  return tv_tracker.report_context(p_workspace)||jsonb_build_object('revision',w.revision,'published_revision',w.published_revision);
end $$;

create function public.tv_save_report_import(p_workspace uuid,p_operation uuid,p_import uuid,p_dataset jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare old tv_tracker.operations; b jsonb; r jsonb;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  perform 1 from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','report-import','id',p_import,'dataset',p_dataset);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_import is null or p_operation is null or p_dataset is null or jsonb_typeof(p_dataset)<>'object'
    or jsonb_typeof(p_dataset->'rows') is distinct from 'array'
    or jsonb_typeof(p_dataset->'columns') is distinct from 'array'
    or jsonb_typeof(p_dataset->'files') is distinct from 'array' then
    raise exception 'A validated report dataset is required' using errcode='22023'; end if;
  if jsonb_array_length(p_dataset->'rows') not between 1 and 100000
    or octet_length(p_dataset::text)>50000000 or jsonb_array_length(p_dataset->'columns') not between 4 and 200
    or jsonb_array_length(p_dataset->'files') not between 1 and 20
    or not (p_dataset->'columns' ?& array['Order Number','Product','Status'])
    or not (p_dataset->'columns' ?| array['Date','In-Time'])
    or exists(select 1 from jsonb_array_elements(p_dataset->'columns') c where jsonb_typeof(c)<>'string' or length(c#>>'{}') not between 1 and 200)
    or (select count(*)<>count(distinct c) from jsonb_array_elements(p_dataset->'columns') c)
    or exists(select 1 from jsonb_array_elements(p_dataset->'rows') x where jsonb_typeof(x)<>'object'
      or jsonb_typeof(x->'Order Number') is distinct from 'string' or length(trim(x->>'Order Number')) not between 1 and 200
      or (x->>'Order Number') ~ '[^ -~]' or coalesce(trim(x->>'Product'),'')='' or coalesce(trim(x->>'Status'),'')='')
    or (select count(*)<>count(distinct lower(trim(x->>'Order Number'))) from jsonb_array_elements(p_dataset->'rows') x) then
    raise exception 'Report size, columns or order identities need review' using errcode='22023'; end if;
  -- No unchecked cell objects/arrays can reach a Sheets projection.
  if exists(select 1 from jsonb_array_elements(p_dataset->'rows') x cross join lateral jsonb_each(x) c
      where jsonb_typeof(c.value) not in ('string','number','boolean','null') or not (p_dataset->'columns' ? c.key)) then
    raise exception 'Report cells must match the validated columns' using errcode='22023'; end if;
  insert into tv_tracker.report_imports(workspace_id,id,dataset) values(p_workspace,p_import,p_dataset);
  r:=jsonb_build_object('id',p_import,'count',jsonb_array_length(p_dataset->'rows'));
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;

create function public.tv_change_reporting(p_workspace uuid,p_operation uuid,p_revision bigint,p_action text,p_change jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; b jsonb; r jsonb; d date; c integer; e integer; mode text; import_identity uuid;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','report-change','revision',p_revision,'action',p_action,'change',p_change);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_action not in ('source','capacity','publish') or p_action is null
    or p_change is null or jsonb_typeof(p_change)<>'object' then
    raise exception 'Use a valid report change' using errcode='22023'; end if;
  if p_revision is distinct from w.revision or exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace) then
    raise exception 'Report changed or the office worker is processing; refresh before retrying' using errcode='40001'; end if;
  insert into tv_tracker.report_settings(workspace_id) values(p_workspace) on conflict do nothing;
  if p_action='source' then
    mode:=p_change->>'source';
    if mode is null or mode not in ('tracker','import') or exists(select 1 from jsonb_object_keys(p_change) k where k not in ('source','import_id')) then
      raise exception 'Choose a report source' using errcode='22023'; end if;
    import_identity:=nullif(p_change->>'import_id','')::uuid;
    if mode='import' and (import_identity is null or not exists(select 1 from tv_tracker.report_imports where workspace_id=p_workspace and id=import_identity)) then
      raise exception 'Select an import belonging to this workspace' using errcode='22023'; end if;
    update tv_tracker.report_settings set source=mode,import_id=case when mode='import' then import_identity else import_id end where workspace_id=p_workspace;
  elsif p_action='capacity' then
    if not (p_change ?& array['date','capacity','extended']) or exists(select 1 from jsonb_object_keys(p_change) k where k not in ('date','capacity','extended'))
      or jsonb_typeof(p_change->'date') is distinct from 'string' then
      raise exception 'Choose a date and both capacity targets' using errcode='22023'; end if;
    if jsonb_typeof(p_change->'capacity') not in ('number','null') or jsonb_typeof(p_change->'extended') not in ('number','null')
      or coalesce(p_change->>'capacity','0') !~ '^\d+$' or coalesce(p_change->>'extended','0') !~ '^\d+$' then
      raise exception 'Capacity must be a whole number or blank' using errcode='22023'; end if;
    c:=(p_change->>'capacity')::integer; e:=(p_change->>'extended')::integer;
    if c not between 0 and 1000000 or e not between 0 and 1000000 or e<c then
      raise exception 'Invalid capacity range' using errcode='22023'; end if;
    if p_change->>'date'='default' then
      update tv_tracker.report_settings set default_capacity=c,default_extended=e where workspace_id=p_workspace;
    else
      if p_change->>'date' !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'Use a YYYY-MM-DD date' using errcode='22023'; end if;
      d:=(p_change->>'date')::date;
      insert into tv_tracker.capacity_targets values(p_workspace,d,c,e)
        on conflict(workspace_id,day) do update set capacity=excluded.capacity,extended=excluded.extended;
    end if;
  elsif p_change<>'{}'::jsonb then
    raise exception 'Publish takes no settings' using errcode='22023';
  end if;
  update tv_tracker.workspaces set revision=revision+1 where id=p_workspace returning revision into w.revision;
  r:=jsonb_build_object('revision',w.revision,'state','pending');
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;

-- Existing owner/office wrappers call this function, with their original access checks.
create or replace function public.tv_claim_job(p_workspace uuid,p_token uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; j tv_tracker.jobs; c tv_tracker.captures; previous jsonb; rows jsonb; receipt jsonb;
begin
  if p_token is null then raise exception 'Job token required' using errcode='22023'; end if;
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  if not found then raise exception 'Workspace not found' using errcode='22023'; end if;
  select result into receipt from tv_tracker.job_receipts where workspace_id=p_workspace and token=p_token;
  if found then return jsonb_build_object('completed',true,'result',receipt); end if;
  select * into j from tv_tracker.jobs where workspace_id=p_workspace;
  if found and j.token<>p_token then return jsonb_build_object('busy',true); end if;
  if j.token is null then
    if w.mode='active' and w.revision>w.published_revision then
      insert into tv_tracker.jobs(workspace_id,token,kind,revision) values(p_workspace,p_token,'publish',w.revision) returning * into j;
    else
      select * into c from tv_tracker.captures where workspace_id=p_workspace and state='queued' order by sequence limit 1;
      if not found then return null; end if;
      insert into tv_tracker.jobs(workspace_id,token,kind,capture_id,revision) values(p_workspace,p_token,'capture',c.id,w.revision) returning * into j;
    end if;
  end if;
  select * into c from tv_tracker.captures where id=j.capture_id;
  select to_jsonb(p) into previous from tv_tracker.captures p where p.id=w.last_capture_id;
  select coalesce(jsonb_agg(jsonb_build_object('order_key',o.order_key,'version',o.version,'data',o.data) order by o.order_key),'[]'::jsonb)
    into rows from tv_tracker.orders o where o.workspace_id=p_workspace;
  return jsonb_build_object('job',to_jsonb(j),'capture',case when c.id is null then null else to_jsonb(c) end,
    'previous',previous,'orders',rows,'last_capture_at',w.last_capture_at,'queue_scope',w.queue_scope,'mode',w.mode,
    'report_context',tv_tracker.report_context(p_workspace));
end $$;
revoke all on function tv_tracker.report_context(uuid) from public,anon,authenticated;
revoke all on function public.tv_reporting_state(uuid,bigint),public.tv_save_report_import(uuid,uuid,uuid,jsonb),
  public.tv_change_reporting(uuid,uuid,bigint,text,jsonb) from public,anon,authenticated;
grant execute on function public.tv_reporting_state(uuid,bigint),public.tv_save_report_import(uuid,uuid,uuid,jsonb),
  public.tv_change_reporting(uuid,uuid,bigint,text,jsonb) to authenticated;
commit;
