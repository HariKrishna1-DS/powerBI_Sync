import React, {useState} from 'react';
import {Columns3, RotateCcw} from 'lucide-react';
import {useWorkspacePreference} from './useWorkspacePreference';
import './tableLayout.css';

const defaults = {mode:'compact', hidden:[], widths:{}, pinIdentifier:true, wrap:false};
const valid = value => value && ['compact','all','custom'].includes(value.mode) &&
  Array.isArray(value.hidden) && value.hidden.length <= 100 && value.hidden.every(v=>typeof v==='string'&&v.length<=256) &&
  value.widths && typeof value.widths==='object' && !Array.isArray(value.widths) && Object.keys(value.widths).length<=100 &&
  Object.entries(value.widths).every(([key,width])=>key.length<=256&&Number.isInteger(width)&&width>=120&&width<=400) &&
  typeof value.pinIdentifier==='boolean' && typeof value.wrap==='boolean';

export function useTableLayout(columns) {
  const [layout,save,ready,error]=useWorkspacePreference('tableLayout','tv-tracker-table-layout',defaults,valid);
  const [saving,setSaving]=useState(false);
  const compact=['Order Number','Product','Status',...['Received Date','Order Date','Date','Assignee','Client'].filter(c=>columns.includes(c)).slice(0,2)].filter(c=>columns.includes(c));
  const visible=(layout.mode==='compact'?compact:columns).filter(c=>c==='Order Number'||layout.mode!=='custom'||!layout.hidden.includes(c));
  async function update(patch){
    if(saving||!ready)return;
    setSaving(true);
    try{await save({...layout,...patch});}catch{}finally{setSaving(false);}
  }
  return {layout,visible,compact,update,ready:ready&&!saving,error};
}

export function TableLayoutControls({columns,preferences}) {
  const {layout,visible,update,ready,error}=preferences;
  return <details className="table-layout-control" onKeyDown={event=>{if(event.key==='Escape'){event.currentTarget.open=false;event.currentTarget.querySelector('summary')?.focus();}}}>
    <summary><Columns3 size={15}/>Columns & layout</summary>
    <section className="table-layout-panel" aria-label="Table layout preferences">
      <div className="table-layout-heading"><div><strong>Make this table yours</strong><p>Saved on this computer. Exports always include every column.</p></div><button type="button" className="text-button" disabled={!ready} onClick={()=>update(defaults)}><RotateCcw size={14}/>Reset layout</button></div>
      <div className="table-layout-options"><label><input type="checkbox" checked={layout.pinIdentifier} disabled={!ready} onChange={event=>update({pinIdentifier:event.target.checked})}/>Keep order number in view</label><label><input type="checkbox" checked={layout.wrap} disabled={!ready} onChange={event=>update({wrap:event.target.checked})}/>Wrap cell text</label></div>
      <div className="column-options">{columns.map(column=><div className="column-option" key={column}><label><input type="checkbox" aria-label={`Show ${column}`} checked={visible.includes(column)} disabled={!ready||column==='Order Number'||(visible.length===1&&visible.includes(column))} onChange={event=>{const shown=new Set(visible);event.target.checked?shown.add(column):shown.delete(column);update({mode:'custom',hidden:columns.filter(c=>!shown.has(c))});}}/><span>{column}</span></label><select aria-label={`Width for ${column}`} disabled={!ready} value={layout.widths[column]||180} onChange={event=>update({widths:{...layout.widths,[column]:Number(event.target.value)}})}>{[120,180,240,320,400].map(width=><option key={width} value={width}>{width} px</option>)}</select></div>)}</div>
      {error&&<p role="alert" className="field-help">{error}</p>}
    </section>
  </details>;
}
