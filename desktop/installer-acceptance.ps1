$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted') {
  throw 'Run installer acceptance only on a disposable GitHub-hosted Windows runner.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$version = (Get-Content desktop/package.json | ConvertFrom-Json).version
$env:BASELINE_VERSION = '2.7.2'
$baseline = Join-Path $env:RUNNER_TEMP 'tv-tracker-baseline'
$installation = Join-Path $env:RUNNER_TEMP 'tv-tracker-installed'
New-Item -ItemType Directory -Path $baseline -ErrorAction Stop | Out-Null
gh release download "v$env:BASELINE_VERSION" --repo HariKrishna1-DS/powerBI_Sync --pattern "Tv-Tracker-$env:BASELINE_VERSION-x64.exe" --pattern latest.yml --dir $baseline
if ($LASTEXITCODE -ne 0) { throw 'Baseline download failed' }
$env:TV_TRACKER_BASELINE_DIR = $baseline
node -e 'const fs=require("fs"),path=require("path"),c=require("crypto"),yaml=require("./desktop/node_modules/js-yaml");const d=process.env.TV_TRACKER_BASELINE_DIR,v=process.env.BASELINE_VERSION;const m=yaml.load(fs.readFileSync(path.join(d,"latest.yml"),"utf8"));const b=fs.readFileSync(path.join(d,`Tv-Tracker-${v}-x64.exe`));if(m.version!==v||m.sha512!==c.createHash("sha512").update(b).digest("base64"))throw Error("Baseline checksum mismatch");'
if ($LASTEXITCODE -ne 0) { throw 'Baseline integrity failed' }
$installer = Join-Path $baseline "Tv-Tracker-$env:BASELINE_VERSION-x64.exe"
$process = Start-Process -FilePath $installer -ArgumentList @('/S', "/D=$installation") -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw "Baseline installer failed: $($process.ExitCode)" }
$env:BASELINE_EXE = Join-Path $installation 'Tv Tracker.exe'
$env:DESKTOP_EXE = $env:BASELINE_EXE
$env:CANDIDATE_ASAR = "$projectRoot/release/$version/win-unpacked/resources/app.asar"
$env:TV_TRACKER_TEST_INSTALL = '1'
node desktop/upgrade-smoke.cjs
if ($LASTEXITCODE -ne 0) { throw 'Actual installer upgrade/recovery acceptance failed' }
