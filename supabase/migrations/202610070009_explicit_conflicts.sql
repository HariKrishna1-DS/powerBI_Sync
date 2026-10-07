-- Business conflicts must not use serialization_failure: PostgREST may retry it
-- indefinitely. PT409 returns HTTP 409, requiring a fresh client-side review.
-- Recreate only these existing functions, preserving their signatures, owners,
-- privileges, SECURITY DEFINER and empty search_path. No rows are modified.
begin;
set local lock_timeout='10s';
do $migration$
declare item record; definition text; checked integer:=0;
begin
  for item in
    select p.oid,p.proname from pg_catalog.pg_proc p
    join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='public' and p.proname in (
      'tv_snapshot','tv_edit_order','tv_commit_capture','tv_ack_publication',
      'tv_seed_workspace','tv_activate_workspace','tv_reporting_state',
      'tv_change_reporting','tv_correct_sla','tv_apply_monthly')
  loop
    definition:=pg_catalog.pg_get_functiondef(item.oid);
    if position('errcode=''40001''' in definition)=0
       and position('errcode=''PT409''' in definition)=0 then
      raise exception 'Unexpected conflict function definition: %',item.proname;
    end if;
    execute replace(definition,'errcode=''40001''','errcode=''PT409''');
    checked:=checked+1;
  end loop;
  if checked<>10 then raise exception 'Apply migrations 001–008 before 009'; end if;
end $migration$;
notify pgrst,'reload schema';
commit;
