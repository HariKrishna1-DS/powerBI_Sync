begin;
alter table tv_tracker.captures add column processed_revision bigint;
create function tv_tracker.capture_revision() returns trigger language plpgsql set search_path='' as $$
begin
  if new.state='processed' and old.state='queued' then
    select revision into new.processed_revision from tv_tracker.workspaces where id=new.workspace_id;
  end if;
  return new;
end $$;
create trigger capture_revision before update of state on tv_tracker.captures
for each row execute function tv_tracker.capture_revision();
create or replace function public.tv_operation(p_workspace uuid,p_operation uuid)
returns jsonb language plpgsql security definer set search_path='' as $$
declare result jsonb;
begin
  perform tv_tracker.require_member(p_workspace);
  select o.result || jsonb_build_object('processing_state',c.state,'report',c.report,
    'processed_revision',c.processed_revision,'published',
    c.state='processed' and c.processed_revision is not null and w.published_revision>=c.processed_revision) into result
    from tv_tracker.operations o join tv_tracker.workspaces w on w.id=o.workspace_id
    left join tv_tracker.captures c on c.workspace_id=o.workspace_id and c.operation_id=o.id
    where o.workspace_id=p_workspace and o.id=p_operation;
  return result;
end $$;
commit;
