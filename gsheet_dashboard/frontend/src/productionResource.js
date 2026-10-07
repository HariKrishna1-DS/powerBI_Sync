import {api} from './workspaceUtils';
let inFlight=null, forced=false, snapshot=null, generation=0, controller=null;
export function invalidateProduction(){
  generation++;controller?.abort();controller=null;inFlight=null;forced=false;snapshot=null;
}
export function readProduction(refresh=false){
  if(inFlight)return refresh&&!forced?inFlight.then(()=>readProduction(true),()=>readProduction(true)):inFlight;
  const current=generation, params=new URLSearchParams();
  if(snapshot?.revision)params.set('revision',snapshot.revision);
  if(refresh)params.set('refresh','1');
  forced=refresh;controller=new AbortController();
  inFlight=api(`/api/live-sheets${params.size?`?${params}`:''}`,{signal:controller.signal}).then(data=>{
    if(current!==generation)throw new DOMException('Report source changed','AbortError');
    if(data.unchanged&&snapshot){const {unchanged,...metadata}=data;snapshot={...snapshot,...metadata};}else snapshot=data;
    return snapshot;
  }).finally(()=>{if(current===generation){inFlight=null;forced=false;controller=null;}});
  return inFlight;
}
