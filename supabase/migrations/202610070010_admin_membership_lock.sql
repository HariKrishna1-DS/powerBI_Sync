-- Full-access managers use the existing owner role. Preserve all grants and data.
-- Serialize membership authority with its change, including competing removals.
begin;
create or replace function public.tv_set_member(p_workspace uuid,p_operation uuid,p_user uuid,p_role text)
returns jsonb language plpgsql security definer set search_path='' as $$
declare old tv_tracker.operations; b jsonb; r jsonb;
begin
  perform 1 from tv_tracker.workspaces where id=p_workspace for update;
  -- Recheck inside the workspace lock: a concurrent admin removal must not
  -- authorize another membership change or leave the workspace without an admin.
  perform tv_tracker.require_member(p_workspace,array['owner']);
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
commit;
