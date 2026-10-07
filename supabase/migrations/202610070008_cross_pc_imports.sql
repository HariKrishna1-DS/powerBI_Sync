-- Preserve the existing authenticated permissions and validated import contract.
begin;
create or replace function public.tv_save_report_import(p_workspace uuid,p_operation uuid,p_import uuid,p_dataset jsonb)
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
  -- A content-addressed import may arrive from another PC with another operation ID.
  -- Reuse identical immutable data; never replace a dataset under an existing identity.
  if exists(select 1 from tv_tracker.report_imports where workspace_id=p_workspace and id=p_import and dataset<>p_dataset) then
    raise exception 'Import identity already has different content' using errcode='23505';
  end if;
  insert into tv_tracker.report_imports(workspace_id,id,dataset) values(p_workspace,p_import,p_dataset) on conflict do nothing;
  r:=jsonb_build_object('id',p_import,'count',jsonb_array_length(p_dataset->'rows'));
  insert into tv_tracker.operations values(p_workspace,p_operation,auth.uid(),b,r,now());
  return r;
end $$;

commit;
