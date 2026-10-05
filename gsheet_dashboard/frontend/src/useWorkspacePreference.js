import {useEffect, useRef, useState} from 'react';

// The engine port changes on restart, so native preferences belong to the desktop vault.
export function useWorkspacePreference(key, localKey, fallback, valid) {
  const native = !!window.desktop?.getPreferences;
  const changed = useRef(false);
  const [ready,setReady] = useState(!native);
  const [error,setError] = useState('');
  const [value,setValue] = useState(()=>{
    if(native)return fallback;
    try {
      const raw=localStorage.getItem(localKey);
      let stored;try{stored=JSON.parse(raw);}catch{stored=raw;}
      return valid(stored)?stored:fallback;
    } catch{return fallback;}
  });
  useEffect(()=>{
    if(!native)return;
    let active=true;
    window.desktop.getPreferences().then(saved=>{
      if(active&&!changed.current&&valid(saved[key]))setValue(saved[key]);
    }).catch(()=>{if(active)setError('Saved preferences could not be loaded.');})
      .finally(()=>{if(active)setReady(true);});
    return()=>{active=false;};
  },[key,native]);
  async function save(next){
    changed.current=true;
    try {
      if(native)await window.desktop.savePreferences({[key]:next});
      else localStorage.setItem(localKey,JSON.stringify(next));
      setValue(next);setError('');
    } catch {
      setError('This preference could not be saved. Check local storage and retry.');
      throw Error('The preference could not be saved.');
    }
  }
  return [value,save,ready,error];
}
