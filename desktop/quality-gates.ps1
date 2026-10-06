param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
function Check-Exit([string]$stage) { if ($LASTEXITCODE -ne 0) { throw "$stage failed" } }
& $Python -m pip install --target .desktop-build/quality-tools ruff==0.11.13 pip-audit==2.9.0
Check-Exit 'Quality tooling installation'
$priorPath = $env:PYTHONPATH
try {
  $env:PYTHONPATH = "$pwd/.desktop-build/quality-tools"
  & $Python -m ruff check --select E9,F gsheet_dashboard/report_metrics.py gsheet_dashboard/report_workspace.py gsheet_dashboard/report_routes.py gsheet_dashboard/report_publishing.py gsheet_dashboard/sheets_writer.py gsheet_dashboard/workspace_backup.py gsheet_dashboard/workspace_retention.py gsheet_dashboard/redaction.py gsheet_dashboard/test_report_workspace.py gsheet_dashboard/test_report_safety.py
  Check-Exit 'Reporting lint'
  & $Python -m ruff check --select E9,F gsheet_dashboard/backup_protection.py gsheet_dashboard/cloud_retention.py gsheet_dashboard/test_backup_protection.py gsheet_dashboard/test_cloud_retention.py desktop/live-sheets-acceptance.py
  Check-Exit 'Recovery lint'
  & $Python -m ruff check --select E9,F gsheet_dashboard/sheets_transport.py gsheet_dashboard/test_sheets_quota.py gsheet_dashboard/production_cache.py gsheet_dashboard/sheet_reads.py
  Check-Exit 'Sheets transport lint'
  & $Python -m ruff check --select E9,F cloud_backend supabase/tests gsheet_dashboard/shared_backend.py gsheet_dashboard/test_shared_backend.py gsheet_dashboard/test_cloud_worker.py
  Check-Exit 'Shared backend lint'
  & $Python -m pip_audit -r desktop/requirements-build.lock --no-deps --disable-pip
  Check-Exit 'Python dependency audit'
} finally { $env:PYTHONPATH = $priorPath }
foreach ($folder in @('desktop', 'desktop/extractor', 'gsheet_dashboard/frontend')) {
  & npm.cmd --prefix $folder audit --omit=dev --audit-level=high
  Check-Exit "$folder production dependency audit"
}
Get-ChildItem -LiteralPath desktop -Filter *.cjs | ForEach-Object {
  & node --check $_.FullName
  Check-Exit "$($_.Name) syntax"
}
