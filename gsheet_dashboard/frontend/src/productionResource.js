import {api} from './workspaceUtils';

// All production views share a single in-flight read. A queued explicit refresh
// follows an older ordinary read, so clicking Refresh always reaches the service.
let inFlight = null;
let forced = false;
let snapshot = null;

export function readProduction(refresh = false) {
  if (inFlight) return refresh && !forced ? inFlight.then(() => readProduction(true), () => readProduction(true)) : inFlight;
  const params = new URLSearchParams();
  if (snapshot?.revision) params.set('revision', snapshot.revision);
  if (refresh) params.set('refresh', '1');
  forced = refresh;
  inFlight = api(`/api/live-sheets${params.size ? `?${params}` : ''}`).then(data => {
    if (data.unchanged && snapshot) {
      const {unchanged, ...metadata} = data;
      snapshot = {...snapshot, ...metadata};
    } else snapshot = data;
    return snapshot;
  }).finally(() => { inFlight = null; forced = false; });
  return inFlight;
}
