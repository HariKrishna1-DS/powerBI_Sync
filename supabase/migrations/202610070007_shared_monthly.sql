-- Reviewed canonical monthly imports/rollovers share optimistic revision and receipts.
begin;
create table tv_tracker.monthly_periods (
  workspace_id uuid not null references tv_tracker.workspaces(id),
  month text not null check(month ~ '^\d{4}-(0[1-9]|1[0-2])$'),
  primary key(workspace_id,month)
);
alter table tv_tracker.monthly_periods enable row level security;
revoke all on tv_tracker.monthly_periods from public,anon,authenticated;
alter function tv_tracker.report_context(uuid) rename to report_context_v1;
create function tv_tracker.report_context(w uuid) returns jsonb language sql security definer set search_path='' as $$
  select tv_tracker.report_context_v1(w)||jsonb_build_object('periods',coalesce(
    (select jsonb_agg(month order by month) from tv_tracker.monthly_periods where workspace_id=w),'[]'::jsonb));
$$;
revoke all on function tv_tracker.report_context(uuid),tv_tracker.report_context_v1(uuid) from public,anon,authenticated;

create function public.tv_apply_monthly(p_workspace uuid,p_operation uuid,p_plan uuid,p_revision bigint,
  p_kind text,p_month text,p_rows jsonb,p_periods jsonb)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; prior tv_tracker.orders; item jsonb;
  b jsonb; r jsonb; period text;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','monthly','plan',p_plan,'revision',p_revision,'action',p_kind,
    'month',p_month,'rows',p_rows,'periods',p_periods);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Monthly operation changed' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_plan is null or p_kind is null or p_kind not in ('setup','import','rollover')
    or p_month is null or p_month !~ '^\d{4}-(0[1-9]|1[0-2])$' or p_month<='2026-09'
    or p_rows is null or jsonb_typeof(p_rows)<>'array' or jsonb_array_length(p_rows)>100000
    or p_periods is null or jsonb_typeof(p_periods)<>'array' or jsonb_array_length(p_periods) not between 1 and 120
    or octet_length(b::text)>50000000 then
    raise exception 'Invalid reviewed monthly plan' using errcode='22023'; end if;
  if p_revision is distinct from w.revision or exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace) then
    raise exception 'Production changed or the worker is processing; refresh the preview' using errcode='40001'; end if;
  if p_kind='setup' and p_rows<>'[]'::jsonb then raise exception 'Setup cannot edit orders' using errcode='22023'; end if;
  if (select count(*)<>count(distinct x->>'order_key') from jsonb_array_elements(p_rows) x) then
    raise exception 'Duplicate monthly identities' using errcode='22023'; end if;
  for item in select value from jsonb_array_elements(p_rows) loop
    if jsonb_typeof(item)<>'object' or jsonb_typeof(item->'data') is distinct from 'object'
      or jsonb_typeof(item->'data'->'Order Number') is distinct from 'string'
      or length(trim(item->'data'->>'Order Number')) not between 1 and 200
      or item->'data'->>'Order Number' ~ '[^ -~]'
      or item->>'order_key' is distinct from lower(trim(item->'data'->>'Order Number'))
      or item->'data'->>'Reporting Month' is null or item->'data'->>'Reporting Month' !~ '^\d{4}-(0[1-9]|1[0-2])$'
      or item->'data'->>'Reporting Month'<='2026-09'
      or exists(select 1 from jsonb_each(item->'data') c where jsonb_typeof(c.value) not in ('string','number','boolean','null')) then
      raise exception 'Invalid canonical monthly row' using errcode='22023'; end if;
    select * into prior from tv_tracker.orders where workspace_id=p_workspace and order_key=item->>'order_key' for update;
    if found then
      if (item->>'version')::bigint is distinct from prior.version then
        raise exception 'An order changed after the preview' using errcode='40001'; end if;
      if prior.data->>'Reporting Month'<='2026-09' then
        raise exception 'Archived orders cannot be changed' using errcode='22023'; end if;
    elsif item->>'version' is not null or p_kind<>'import' then
      raise exception 'Missing canonical order; refresh the preview' using errcode='40001';
    end if;
    if p_kind='rollover' and exists(select 1 from jsonb_each(prior.data) c where c.key not in ('No','Reporting Month','Carried From')
        and item->'data'->c.key is distinct from c.value) then
      raise exception 'Rollover may only change month ownership' using errcode='22023'; end if;
  end loop;
  for period in select value#>>'{}' from jsonb_array_elements(p_periods) loop
    if period is null or period !~ '^\d{4}-(0[1-9]|1[0-2])$' or period<='2026-09' then
      raise exception 'Invalid monthly period' using errcode='22023'; end if;
    insert into tv_tracker.monthly_periods values(p_workspace,period) on conflict do nothing;
  end loop;
  for item in select value from jsonb_array_elements(p_rows) loop
    insert into tv_tracker.orders(workspace_id,order_key,data) values(p_workspace,item->>'order_key',item->'data')
      on conflict(workspace_id,order_key) do update set data=excluded.data,version=tv_tracker.orders.version+1;
  end loop;
  update tv_tracker.workspaces set revision=revision+1 where id=p_workspace returning revision into w.revision;
  r:=jsonb_build_object('state','pending','revision',w.revision,'updated_count',jsonb_array_length(p_rows));
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;
revoke all on function public.tv_apply_monthly(uuid,uuid,uuid,bigint,text,text,jsonb,jsonb) from public,anon,authenticated;
grant execute on function public.tv_apply_monthly(uuid,uuid,uuid,bigint,text,text,jsonb,jsonb) to authenticated;
commit;
