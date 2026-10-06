const {execFileSync} = require('node:child_process');
function processTreeMetrics(pid) {
  if (process.platform !== 'win32') return {available: false, reason: 'Windows process-tree sampler'};
  if (!Number.isSafeInteger(pid) || pid <= 0) throw Error('A process ID is required.');
  const script = `$items=Get-CimInstance Win32_Process; $ids=[System.Collections.Generic.HashSet[int]]::new(); [void]$ids.Add(${pid}); do {$changed=$false; foreach($p in $items){if($ids.Contains([int]$p.ParentProcessId) -and $ids.Add([int]$p.ProcessId)){$changed=$true}}}while($changed); @($items | Where-Object {$ids.Contains([int]$_.ProcessId)} | Select-Object Name,ProcessId,WorkingSetSize) | ConvertTo-Json -Compress`;
  const raw = execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', script], {encoding: 'utf8', windowsHide: true, timeout: 15000});
  const parsed = JSON.parse(raw), processes = Array.isArray(parsed) ? parsed : [parsed];
  return {available: true, processes: processes.map(p => ({name: p.Name, pid: p.ProcessId, workingSetMB: Math.round(Number(p.WorkingSetSize) / 1048576)})),
    totalWorkingSetMB: Math.round(processes.reduce((n, p) => n + Number(p.WorkingSetSize), 0) / 1048576),
    includesPython: processes.some(p => /datatrace-engine|python/i.test(p.Name))};
}
module.exports = {processTreeMetrics};
