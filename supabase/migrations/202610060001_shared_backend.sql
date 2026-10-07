-- No production data is imported by this migration.
begin;
create schema if not exists tv_tracker;
revoke all on schema tv_tracker from public, anon, authenticated;

create table tv_tracker.workspaces (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 1 and 100),
  queue_scope text not null check (length(queue_scope) between 1 and 2048),
  mode text not null default 'shadow' check (mode in ('shadow','active')),
  revision bigint not null default 0,
  next_sequence bigint not null default 1,
  last_capture_at timestamptz,
  last_capture_id uuid,
  published_revision bigint not null default 0,
  created_at timestamptz not null default now()
);
create table tv_tracker.members (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  user_id uuid not null references auth.users(id),
  role text not null check (role in ('owner','editor','viewer')),
  primary key (workspace_id,user_id)
);
create table tv_tracker.operations (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  id uuid not null,
  actor uuid not null references auth.users(id),
  body jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (workspace_id,id)
);
create table tv_tracker.captures (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references tv_tracker.workspaces(id),
  operation_id uuid not null,
  sequence bigint not null,
  captured_at timestamptz not null,
  received_at timestamptz not null default now(),
  payload jsonb not null,
  state text not null default 'queued' check (state in ('queued','processed','review')),
  report jsonb,
  unique(workspace_id,sequence),
  unique(workspace_id,operation_id),
  foreign key (workspace_id,operation_id) references tv_tracker.operations(workspace_id,id)
);
create table tv_tracker.orders (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  order_key text collate "C" not null,
  version bigint not null default 1,
  data jsonb not null check (jsonb_typeof(data)='object'),
  updated_at timestamptz not null default now(),
  primary key (workspace_id,order_key)
);
create table tv_tracker.jobs (
  workspace_id uuid primary key references tv_tracker.workspaces(id),
  token uuid not null,
  kind text not null check (kind in ('capture','publish')),
  capture_id uuid references tv_tracker.captures(id),
  revision bigint not null,
  started_at timestamptz not null default now()
);
create table tv_tracker.job_receipts (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  token uuid not null,
  kind text not null check (kind in ('capture','publish')),
  body_hash text not null,
  result jsonb not null,
  completed_at timestamptz not null default now(),
  primary key (workspace_id,token)
);
create index captures_pending on tv_tracker.captures(workspace_id,sequence) where state='queued';
alter table tv_tracker.workspaces enable row level security;
alter table tv_tracker.members enable row level security;
alter table tv_tracker.operations enable row level security;
alter table tv_tracker.captures enable row level security;
alter table tv_tracker.orders enable row level security;
alter table tv_tracker.jobs enable row level security;
alter table tv_tracker.job_receipts enable row level security;
revoke all on all tables in schema tv_tracker from public, anon, authenticated;

create function tv_tracker.require_member(w uuid, roles text[] default array['owner','editor','viewer'])
returns void language plpgsql security definer set search_path='' as $$
begin
  if auth.uid() is null or not exists(select 1 from tv_tracker.members m
      where m.workspace_id=w and m.user_id=auth.uid() and m.role=any(roles)) then
    raise exception 'Workspace access denied' using errcode='42501';
  end if;
end $$;

create function public.tv_create_workspace(p_workspace uuid,p_name text,p_queue_scope text)
returns uuid language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces;
begin
  if auth.uid() is null then raise exception 'Sign in required' using errcode='42501'; end if;
  insert into tv_tracker.workspaces(id,name,queue_scope) values(p_workspace,trim(p_name),trim(p_queue_scope)) on conflict(id) do nothing;
  if found then
    insert into tv_tracker.members values(p_workspace,auth.uid(),'owner');
  else
    perform tv_tracker.require_member(p_workspace,array['owner']);
    select * into w from tv_tracker.workspaces where id=p_workspace;
    if w.name is distinct from trim(p_name) or w.queue_scope is distinct from trim(p_queue_scope) then
      raise exception 'Workspace ID already has different content' using errcode='23505';
    end if;
  end if;
  return p_workspace;
end $$;

create function public.tv_list_workspaces()
returns jsonb language sql security definer set search_path='' as $$
  select coalesce(jsonb_agg(jsonb_build_object('id',w.id,'name',w.name,'queue_scope',w.queue_scope,
    'mode',w.mode,'role',m.role,'revision',w.revision,'published_revision',w.published_revision) order by w.name,w.id),'[]'::jsonb)
  from tv_tracker.workspaces w join tv_tracker.members m on w.id=m.workspace_id where m.user_id=auth.uid();
$$;

create function public.tv_set_member(p_workspace uuid,p_operation uuid,p_user uuid,p_role text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare old tv_tracker.operations; b jsonb; r jsonb;
begin
  perform tv_tracker.require_member(p_workspace,array['owner']);
  perform 1 from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','member','user',p_user,'role',p_role);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_user is null or p_user=auth.uid()
      or (p_role is not null and p_role not in ('owner','editor','viewer')) then
    raise exception 'Use a valid role for another registered workspace member' using errcode='22023'; end if;
  if p_role is null then
    delete from tv_tracker.members where workspace_id=p_workspace and user_id=p_user;
  else
    insert into tv_tracker.members values(p_workspace,p_user,p_role)
      on conflict(workspace_id,user_id) do update set role=excluded.role;
  end if;
  r:=jsonb_build_object('user',p_user,'role',p_role);
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;

create function public.tv_submit_capture(p_workspace uuid,p_operation uuid,p_captured_at timestamptz,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; b jsonb; r jsonb; c uuid;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','capture','captured_at',p_captured_at,'payload',p_payload);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_captured_at is null or p_captured_at>now()+interval '5 minutes'
      or p_payload is null or jsonb_typeof(p_payload)<>'object'
      or jsonb_typeof(p_payload->'rows') is distinct from 'array'
      or jsonb_typeof(p_payload->'columns') is distinct from 'array'
      or (p_payload->'metadata'->'complete') is distinct from 'true'::jsonb
      or (p_payload->>'queue_scope') is distinct from w.queue_scope then
    raise exception 'A complete capture of the configured queue is required' using errcode='22023';
  end if;
  if jsonb_array_length(p_payload->'rows') not between 1 and 10000 or octet_length(p_payload::text)>10000000
      or not (p_payload->'columns' ? 'Order Number') then
    raise exception 'Capture size or headers are invalid; empty captures require review' using errcode='22023';
  end if;
  if (p_payload->'metadata'->>'kind') is distinct from 'portal'
      or (p_payload->'metadata'->'expected_rows') is distinct from to_jsonb(jsonb_array_length(p_payload->'rows'))
      or (p_payload->'metadata'->'actual_rows') is distinct from to_jsonb(jsonb_array_length(p_payload->'rows')) then
    raise exception 'Portal row-count evidence must match the complete capture' using errcode='22023'; end if;
  if exists(select 1 from jsonb_array_elements(p_payload->'rows') x
      where jsonb_typeof(x)<>'object' or jsonb_typeof(x->'Order Number') is distinct from 'string'
        or length(trim(x->>'Order Number')) not between 1 and 200 or (x->>'Order Number') ~ '[^ -~]')
      or (select count(*)<>count(distinct lower(trim(x->>'Order Number'))) from jsonb_array_elements(p_payload->'rows') x) then
    raise exception 'Missing or duplicate order identities require review' using errcode='22023';
  end if;
  c:=gen_random_uuid();
  r:=jsonb_build_object('capture_id',c,'sequence',w.next_sequence,'state','accepted');
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  insert into tv_tracker.captures(id,workspace_id,operation_id,sequence,captured_at,payload)
    values(c,p_workspace,p_operation,w.next_sequence,p_captured_at,p_payload);
  update tv_tracker.workspaces set next_sequence=next_sequence+1 where id=p_workspace;
  return r;
end $$;

create function public.tv_snapshot(p_workspace uuid,p_revision bigint default null,p_after text default '')
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; items jsonb; cursor_key text; n integer;
begin
  perform tv_tracker.require_member(p_workspace);
  select * into w from tv_tracker.workspaces where id=p_workspace for share;
  if p_revision is not null and p_revision<>w.revision then raise exception 'Snapshot revision changed' using errcode='40001'; end if;
  select coalesce(jsonb_agg(to_jsonb(o) - 'workspace_id' order by o.order_key),'[]'::jsonb), max(o.order_key),count(*)
    into items,cursor_key,n from (select * from tv_tracker.orders where workspace_id=p_workspace and order_key>p_after order by order_key limit 500) o;
  return jsonb_build_object('revision',w.revision,'published_revision',w.published_revision,'mode',w.mode,
    'orders',items,'next_cursor',case when n=500 then cursor_key else null end);
end $$;

create function public.tv_operation(p_workspace uuid,p_operation uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
  perform tv_tracker.require_member(p_workspace);
  select o.result || jsonb_build_object('processing_state',c.state,'report',c.report) into result
    from tv_tracker.operations o left join tv_tracker.captures c on c.workspace_id=o.workspace_id and c.operation_id=o.id
    where o.workspace_id=p_workspace and o.id=p_operation;
  return result;
end $$;

create function public.tv_edit_order(p_workspace uuid,p_operation uuid,p_order_key text,p_version bigint,p_patch jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare old tv_tracker.operations; b jsonb; r jsonb; v bigint;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  perform 1 from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','edit','key',p_order_key,'version',p_version,'patch',p_patch);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_patch is null or p_patch='{}'::jsonb or jsonb_typeof(p_patch)<>'object' or octet_length(p_patch::text)>16000
      or exists(select 1 from jsonb_each(p_patch) kv where kv.key not in ('Comments','Assignee','Searcher','Shift','Review/QC','review') or jsonb_typeof(kv.value)<>'string') then
    raise exception 'Only manual text fields can be edited here' using errcode='22023';
  end if;
  if exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace) then raise exception 'Workspace processing is in progress; retry this edit' using errcode='40001'; end if;
  update tv_tracker.orders set data=data||p_patch,version=version+1,updated_at=now()
    where workspace_id=p_workspace and order_key=p_order_key and version=p_version returning version into v;
  if not found then raise exception 'Order changed; review the latest version' using errcode='40001'; end if;
  update tv_tracker.workspaces set revision=revision+1 where id=p_workspace;
  r:=jsonb_build_object('order_key',p_order_key,'version',v);
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;

-- Worker access is granted only to the server role. A token is never taken over on a timer.
create function public.tv_claim_job(p_workspace uuid,p_token uuid)
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
    'previous',previous,'orders',rows,'last_capture_at',w.last_capture_at,'queue_scope',w.queue_scope,'mode',w.mode);
end $$;

create function public.tv_commit_capture(p_workspace uuid,p_token uuid,p_rows jsonb,p_report jsonb,p_review boolean default false)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; j tv_tracker.jobs; c tv_tracker.captures; item jsonb; k text;
  receipt tv_tracker.job_receipts; body_hash text; result jsonb;
begin
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  body_hash:=encode(sha256(convert_to(jsonb_build_object('rows',p_rows,'report',p_report,'review',p_review)::text,'UTF8')),'hex');
  select * into receipt from tv_tracker.job_receipts where workspace_id=p_workspace and token=p_token;
  if found then
    if receipt.kind<>'capture' or receipt.body_hash<>body_hash then raise exception 'Job token already has different content' using errcode='23505'; end if;
    return receipt.result;
  end if;
  select * into j from tv_tracker.jobs where workspace_id=p_workspace and token=p_token and kind='capture';
  if not found or j.revision<>w.revision then raise exception 'Job ownership or revision changed' using errcode='40001'; end if;
  select * into c from tv_tracker.captures where id=j.capture_id;
  if p_review is null or p_rows is null or jsonb_typeof(p_rows)<>'array' or p_report is null or jsonb_typeof(p_report)<>'object' then
    raise exception 'Invalid capture result' using errcode='22023'; end if;
  if jsonb_array_length(p_rows)>100000 or octet_length(p_rows::text)>50000000
      or octet_length(p_report::text)>10000000 or (p_review and p_rows<>'[]'::jsonb)
      or exists(select 1 from jsonb_array_elements(p_rows) x where jsonb_typeof(x)<>'object'
        or jsonb_typeof(x->'Order Number') is distinct from 'string'
        or length(trim(x->>'Order Number')) not between 1 and 200 or (x->>'Order Number') ~ '[^ -~]')
      or (select count(*)<>count(distinct lower(trim(x->>'Order Number'))) from jsonb_array_elements(p_rows) x) then
    raise exception 'Invalid or duplicate canonical orders' using errcode='22023'; end if;
  if not p_review then
    if w.last_capture_at is not null and c.captured_at<=w.last_capture_at then raise exception 'Late capture requires review' using errcode='22023'; end if;
    for item in select value from jsonb_array_elements(p_rows) loop
      k:=lower(trim(item->>'Order Number'));
      if jsonb_typeof(item)<>'object' or coalesce(k,'')='' then raise exception 'Invalid canonical order' using errcode='22023'; end if;
      insert into tv_tracker.orders(workspace_id,order_key,data) values(p_workspace,k,item)
      on conflict(workspace_id,order_key) do update set data=excluded.data,version=tv_tracker.orders.version+1,updated_at=now()
      where tv_tracker.orders.data is distinct from excluded.data;
    end loop;
    update tv_tracker.workspaces set revision=revision+1,last_capture_at=c.captured_at,last_capture_id=c.id where id=p_workspace;
  end if;
  update tv_tracker.captures set state=case when p_review then 'review' else 'processed' end,report=p_report where id=c.id;
  result:=jsonb_build_object('state',case when p_review then 'review' else 'processed' end,'revision',w.revision+case when p_review then 0 else 1 end);
  insert into tv_tracker.job_receipts(workspace_id,token,kind,body_hash,result) values(p_workspace,p_token,'capture',body_hash,result);
  delete from tv_tracker.jobs where workspace_id=p_workspace and token=p_token;
  return result;
end $$;

create function public.tv_ack_publication(p_workspace uuid,p_token uuid,p_revision bigint)
returns jsonb language plpgsql security definer set search_path='' as $$
declare receipt tv_tracker.job_receipts; result jsonb;
begin
  perform 1 from tv_tracker.workspaces where id=p_workspace for update;
  select * into receipt from tv_tracker.job_receipts where workspace_id=p_workspace and token=p_token;
  if found then
    if receipt.kind<>'publish' or receipt.body_hash is distinct from p_revision::text then raise exception 'Job token already has different content' using errcode='23505'; end if;
    return receipt.result;
  end if;
  if not exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace and token=p_token and kind='publish' and revision=p_revision) then
    raise exception 'Publication ownership changed' using errcode='40001'; end if;
  update tv_tracker.workspaces set published_revision=p_revision where id=p_workspace and revision=p_revision;
  if not found then raise exception 'Publication revision changed' using errcode='40001'; end if;
  result:=jsonb_build_object('state','published','revision',p_revision);
  insert into tv_tracker.job_receipts(workspace_id,token,kind,body_hash,result) values(p_workspace,p_token,'publish',p_revision::text,result);
  delete from tv_tracker.jobs where workspace_id=p_workspace and token=p_token;
  return result;
end $$;

revoke all on all functions in schema tv_tracker from public,anon,authenticated;
revoke all on function public.tv_create_workspace(uuid,text,text),public.tv_list_workspaces(),public.tv_set_member(uuid,uuid,uuid,text),public.tv_submit_capture(uuid,uuid,timestamptz,jsonb),
  public.tv_snapshot(uuid,bigint,text),public.tv_operation(uuid,uuid),public.tv_edit_order(uuid,uuid,text,bigint,jsonb),
  public.tv_claim_job(uuid,uuid),public.tv_commit_capture(uuid,uuid,jsonb,jsonb,boolean),public.tv_ack_publication(uuid,uuid,bigint)
  from public,anon,authenticated;
grant execute on function public.tv_create_workspace(uuid,text,text),public.tv_list_workspaces(),public.tv_set_member(uuid,uuid,uuid,text),public.tv_submit_capture(uuid,uuid,timestamptz,jsonb),
  public.tv_snapshot(uuid,bigint,text),public.tv_operation(uuid,uuid),public.tv_edit_order(uuid,uuid,text,bigint,jsonb) to authenticated;
grant execute on function public.tv_claim_job(uuid,uuid),public.tv_commit_capture(uuid,uuid,jsonb,jsonb,boolean),public.tv_ack_publication(uuid,uuid,bigint) to service_role;
commit;
