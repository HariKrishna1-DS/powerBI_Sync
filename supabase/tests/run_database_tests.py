"""Apply all migrations to a fresh database in the isolated QA container."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

root = Path(__file__).resolve().parents[2]
container = (root / '.desktop-build/supabase-qa-container.txt').read_text().strip()
if not re.fullmatch(r'tvtracker-db-qa-[a-f0-9]{10}', container):
    raise RuntimeError('Expected the isolated Tv Tracker QA container')
database = 'qa_' + uuid.uuid4().hex
command = ['docker', 'exec', '-i', container, 'psql', '-XAtq', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres']
subprocess.run(command, input=f'create database {database};', text=True, check=True, timeout=30)
bootstrap = (root / 'supabase/tests/bootstrap.sql').read_text()
# Roles belong to the container cluster and may already exist from a prior run.
bootstrap = re.sub(r'create role ([a-z_]+)([^;]*);',
    lambda m: f"do $$begin if not exists(select 1 from pg_roles where rolname='{m[1]}') then {m[0]} end if; end$$;", bootstrap, flags=re.I)
subprocess.run(command + ['-d', database], input=bootstrap, text=True, check=True, timeout=30)
for migration in sorted((root / 'supabase/migrations').glob('*.sql')):
    subprocess.run(command + ['-d', database], input=migration.read_text(), text=True, check=True, timeout=60)
result = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'supabase/tests', '-p', 'test_*.py'],
    cwd=root, env=dict(os.environ, TVTRACKER_QA_DATABASE=database), timeout=180)
if result.returncode:
    sys.exit(result.returncode)

# Exercise PostgreSQL recovery on disposable synthetic records as well as the
# local-profile backup tests. This does not back up the hosted production project.
manifest_query = """
select jsonb_build_object(
  'tables', (select jsonb_agg(jsonb_build_array(c.relname,c.relrowsecurity,
      (select jsonb_agg(a::text order by a::text) from unnest(
        coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) a)) order by c.relname)
    from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
    where n.nspname='tv_tracker' and c.relkind='r'),
  'functions', (select jsonb_agg(jsonb_build_array(p.proname,
      pg_catalog.pg_get_functiondef(p.oid),
      (select jsonb_agg(a::text order by a::text) from unnest(
        coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) a)) order by p.proname,p.oid::regprocedure::text)
    from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid=p.pronamespace
    where n.nspname='tv_tracker' or (n.nspname='public' and p.proname like 'tv_%'))
);
"""


def manifest(target):
    schema = subprocess.run(command + ['-d', target], input=manifest_query, text=True,
        capture_output=True, check=True, timeout=30).stdout.strip()
    # Every shared table is included, including retry receipts and fixed worker
    # job tokens; ordering by JSON text makes the comparison independent of OIDs.
    tables = subprocess.run(command + ['-d', target], input="select tablename from pg_catalog.pg_tables "
        "where schemaname='tv_tracker' order by tablename;", text=True,
        capture_output=True, check=True, timeout=30).stdout.splitlines()
    records = []
    for table in tables:
        if not re.fullmatch(r'[a-z_]+', table):
            raise RuntimeError('Unexpected QA table name')
        digest = subprocess.run(command + ['-d', target], input=f"select md5(coalesce("
            f"jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text)::text,'[]')) from tv_tracker.{table} t;",
            text=True, capture_output=True, check=True, timeout=30).stdout.strip()
        records.append((table, digest))
    return schema, records


before = manifest(database)
backup = subprocess.run(['docker', 'exec', container, 'pg_dump', '-Fc', '-U', 'postgres', '-d', database],
    capture_output=True, check=True, timeout=60).stdout
if not backup:
    raise RuntimeError('QA PostgreSQL backup is empty')
restored = 'qa_restore_' + uuid.uuid4().hex
subprocess.run(command, input=f'create database {restored};', text=True, check=True, timeout=30)
subprocess.run(['docker', 'exec', '-i', container, 'pg_restore', '--exit-on-error', '-U', 'postgres', '-d', restored],
    input=backup, check=True, timeout=60)
after = manifest(restored)
if before != after:
    # Only QA object names and changed field positions are reported. ACL item
    # ordering is normalized because pg_restore can emit grants in a new order.
    first, second = json.loads(before[0]), json.loads(after[0])
    for category in ('tables', 'functions'):
        old, new = {item[0]: item for item in first[category]}, {item[0]: item for item in second[category]}
        for name in sorted(set(old) | set(new)):
            if old.get(name) != new.get(name):
                print(f'QA restore difference: {category}/{name}', flush=True)
    for table, digest in before[1]:
        if dict(after[1]).get(table) != digest:
            print(f'QA restore record difference: {table}', flush=True)
    raise RuntimeError('Restored QA records, RPC definitions or access controls differ')
print('PASS: synthetic PostgreSQL backup restored all shared records, RPCs and table permissions.', flush=True)
restored_tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'supabase/tests', '-p', 'test_*.py'],
    cwd=root, env=dict(os.environ, TVTRACKER_QA_DATABASE=restored), timeout=180)
sys.exit(restored_tests.returncode)
