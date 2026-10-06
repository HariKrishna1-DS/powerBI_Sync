"""Apply all migrations to a fresh database in the isolated QA container."""
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
sys.exit(result.returncode)
