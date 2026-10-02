param([string]$Python = 'python', [switch]$DirectoryOnly)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
function Assert-Exit([string]$Stage) { if ($LASTEXITCODE -ne 0) { throw "$Stage failed ($LASTEXITCODE)." } }
& $Python -m pip install --target .desktop-build/deps --upgrade -r desktop/requirements-build.lock
Assert-Exit 'Python dependencies'
& npm.cmd --prefix desktop ci
Assert-Exit 'Desktop dependencies'
& npm.cmd --prefix desktop/extractor ci
Assert-Exit 'Extractor dependencies'
& npm.cmd --prefix gsheet_dashboard/frontend ci
Assert-Exit 'Frontend dependencies'
& npm.cmd --prefix gsheet_dashboard/frontend run build
Assert-Exit 'Frontend build'
& $Python desktop/build_backend.py
Assert-Exit 'Engine build'
if ($DirectoryOnly) { & npm.cmd --prefix desktop run pack } else { & npm.cmd --prefix desktop run dist }
Assert-Exit 'Desktop packaging'
