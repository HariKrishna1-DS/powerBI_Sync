-- Explicit manual SLA corrections are versioned and tied to the recorded timing.
begin;
create function public.tv_correct_sla(p_workspace uuid,p_operation uuid,p_revision bigint,p_orders jsonb,p_status text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare w tv_tracker.workspaces; old tv_tracker.operations; b jsonb; r jsonb; selected jsonb; current tv_tracker.orders;
begin
  perform tv_tracker.require_member(p_workspace,array['owner','editor']);
  select * into w from tv_tracker.workspaces where id=p_workspace for update;
  b:=jsonb_build_object('kind','sla','revision',p_revision,'orders',p_orders,'status',p_status);
  select * into old from tv_tracker.operations where workspace_id=p_workspace and id=p_operation;
  if found then
    if old.actor<>auth.uid() or old.body<>b then raise exception 'Operation ID already has different content' using errcode='23505'; end if;
    return old.result;
  end if;
  if p_operation is null or p_status is null or p_status not in ('On Time','Missing')
    or p_orders is null or jsonb_typeof(p_orders)<>'array' then raise exception 'Choose a valid SLA correction' using errcode='22023'; end if;
  if jsonb_array_length(p_orders) not between 1 and 10000 or octet_length(p_orders::text)>4000000
    or exists(select 1 from jsonb_array_elements(p_orders) x where jsonb_typeof(x)<>'object'
      or jsonb_typeof(x->'order_key') is distinct from 'string' or jsonb_typeof(x->'version') is distinct from 'number'
      or jsonb_typeof(x->'completion_date') is distinct from 'string'
      or jsonb_typeof(x->'expected_status') is distinct from 'string'
      or x->>'completion_date' !~ '^\d{4}-\d{2}-\d{2}$'
      or x->>'expected_status' not in ('On Time','Missing') or not (x ? 'expected_status'))
    or (select count(*)<>count(distinct x->>'order_key') from jsonb_array_elements(p_orders) x) then
    raise exception 'Review SLA selections' using errcode='22023'; end if;
  if p_revision is distinct from w.revision or exists(select 1 from tv_tracker.jobs where workspace_id=p_workspace) then
    raise exception 'Report changed; refresh before correcting SLA' using errcode='40001'; end if;
  -- Validate every row before updating any; one stale selection rolls back the batch.
  for selected in select value from jsonb_array_elements(p_orders) loop
    select * into current from tv_tracker.orders where workspace_id=p_workspace and order_key=selected->>'order_key';
    if not found or current.version is distinct from (selected->>'version')::bigint
      or current.data->>'Free Site' is distinct from selected->>'expected_status'
      or lower(trim(current.data->>'Status')) is distinct from 'completed and delivered'
      or lower(coalesce(current.data->>'Completion Evidence','')) like 'inferred%'
      or coalesce(current.data->>'Out Time','') !~ '\d{1,2}:\d{2}'
      or coalesce(current.data->>'SLA Expiration','') !~ '\d{1,2}:\d{2}' then
      raise exception 'The selected order changed or lacks recorded SLA timing' using errcode='40001'; end if;
  end loop;
  for selected in select value from jsonb_array_elements(p_orders) loop
    update tv_tracker.orders set data=data||jsonb_build_object('Free Site',p_status,
      'SLA Override Status',p_status,'SLA Override Out Time',data->>'Out Time',
      'SLA Override Deadline',data->>'SLA Expiration','SLA Override Completion',selected->>'completion_date'),
      version=version+1,updated_at=now() where workspace_id=p_workspace and order_key=selected->>'order_key';
  end loop;
  update tv_tracker.workspaces set revision=revision+1 where id=p_workspace returning revision into w.revision;
  r:=jsonb_build_object('revision',w.revision,'state','pending','updated_count',jsonb_array_length(p_orders));
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;
revoke all on function public.tv_correct_sla(uuid,uuid,bigint,jsonb,text) from public,anon,authenticated;
grant execute on function public.tv_correct_sla(uuid,uuid,bigint,jsonb,text) to authenticated;
commit;
