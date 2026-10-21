import React, {Children,Fragment,cloneElement,isValidElement,useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {Filter,X} from 'lucide-react';
import {matches,str} from './workspaceUtils';
import './columnFilters.css';

export function useColumnFilters(rows,columns) {
  const [filters,setFilters]=useState({});
  const names=columns.filter(Boolean);
  const active=useMemo(()=>Object.fromEntries(Object.entries(filters).filter(([column])=>names.includes(column))),[filters,columns]);
  const filteredRows=useMemo(()=>Object.keys(active).length?rows.filter(row=>matches(row,active)):rows,[rows,active]);
  return {sourceRows:rows,rows:filteredRows,filters:active,state:filters,clear:()=>setFilters({}),restore:value=>setFilters(value&&typeof value==='object'&&!Array.isArray(value)?value:{}),
    apply:(column,filter)=>setFilters(previous=>{const next={...previous};if(filter)next[column]=filter;else delete next[column];return next;})};
}

function FilterMenu({column,controls,anchor,onClose}) {
  const popup=useRef(null),searchInput=useRef(null),selectAll=useRef(null);
  const current=controls.filters[column]||{};
  const options=useMemo(()=>{
    const counts=new Map();
    for(const row of controls.sourceRows)if(matches(row,controls.filters,column)){
      const value=str(row[column]);counts.set(value,(counts.get(value)||0)+1);
    }
    return [...counts].sort(([a],[b])=>a.localeCompare(b,undefined,{numeric:true}));
  },[controls.sourceRows,controls.filters,column]);
  const [search,setSearch]=useState(''),[selected,setSelected]=useState(()=>current.values||options.map(([value])=>value));
  const [operator,setOperator]=useState(current.operator||'none'),[query,setQuery]=useState(current.query||''),[end,setEnd]=useState(current.end||'');
  const shown=options.filter(([value])=>(value||'(Blanks)').toLowerCase().includes(search.trim().toLowerCase()));
  const selectedSet=new Set(selected),checked=shown.filter(([value])=>selectedSet.has(value)).length;
  const [position,setPosition]=useState({left:12,top:12});
  useLayoutEffect(()=>{
    const bounds=anchor.getBoundingClientRect(),height=Math.min(480,window.innerHeight-24),width=Math.min(320,window.innerWidth-24);
    setPosition({left:Math.max(12,Math.min(bounds.right-width,window.innerWidth-width-12)),
      top:Math.max(12,Math.min(bounds.bottom+6,window.innerHeight-height-12)),width,maxHeight:height});
    popup.current?.showPopover?.();searchInput.current?.focus();
  },[anchor]);
  useEffect(()=>{if(selectAll.current)selectAll.current.indeterminate=checked>0&&checked<shown.length;},[checked,shown.length]);
  useEffect(()=>{
    const outside=event=>{if(!popup.current?.contains(event.target)&&!anchor.contains(event.target))onClose(false);};
    const keys=event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();onClose(true);}};
    const reposition=event=>{if(!popup.current?.contains(event.target)){
      const bounds=anchor.getBoundingClientRect(),height=Math.min(480,window.innerHeight-24),width=Math.min(320,window.innerWidth-24);
      setPosition({left:Math.max(12,Math.min(bounds.right-width,window.innerWidth-width-12)),
        top:Math.max(12,Math.min(bounds.bottom+6,window.innerHeight-height-12)),width,maxHeight:height});
    }};
    document.addEventListener('pointerdown',outside,true);document.addEventListener('keydown',keys,true);
    window.addEventListener('resize',reposition);window.addEventListener('scroll',reposition,true);
    return()=>{document.removeEventListener('pointerdown',outside,true);document.removeEventListener('keydown',keys,true);window.removeEventListener('resize',reposition);window.removeEventListener('scroll',reposition,true);};
  },[anchor,onClose]);
  function apply(){
    const values=(search.trim()?shown.map(([value])=>value):options.map(([value])=>value)).filter(value=>selectedSet.has(value));
    const filter={operator,query,end,...(values.length===options.length?{}:{values})};
    controls.apply(column,operator==='none'&&!filter.values?null:filter);onClose(true);
  }
  return createPortal(<div ref={popup} popover="manual" role="dialog" aria-label={`${column} filter`} className="workspace-column-menu" style={position}>
    <div className="column-menu-title"><strong>{column}</strong><button type="button" className="icon-button" aria-label="Close column filter" onClick={()=>onClose(true)}><X size={16}/></button></div>
    <label className="column-menu-condition">Condition<select aria-label="Filter condition" value={operator} onChange={event=>setOperator(event.target.value)}>{[['none','Any value'],['contains','Contains'],['excludes','Does not contain'],['equals','Equals'],['blank','Is blank'],['notblank','Is not blank'],['gt','Greater than / after'],['lt','Less than / before'],['between','Between']].map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
    {!['none','blank','notblank'].includes(operator)&&<input aria-label="Condition value" placeholder="Value, number or date" value={query} onChange={event=>setQuery(event.target.value)}/>}
    {operator==='between'&&<input aria-label="Condition end value" placeholder="End value" value={end} onChange={event=>setEnd(event.target.value)}/>}
    <input ref={searchInput} aria-label="Search filter values" placeholder="Search values" value={search} onChange={event=>setSearch(event.target.value)}/>
    <label className="column-menu-check"><input ref={selectAll} type="checkbox" checked={shown.length>0&&checked===shown.length} onChange={event=>setSelected(previous=>{const next=new Set(previous);for(const [value] of shown)event.target.checked?next.add(value):next.delete(value);return [...next];})}/><span>Select All</span></label>
    <div className="column-menu-values" role="group" aria-label={`${column} values`}>{shown.map(([value,count])=><label className="column-menu-check" key={value}><input type="checkbox" aria-label={value||'(Blanks)'} checked={selectedSet.has(value)} onChange={event=>setSelected(previous=>event.target.checked?[...previous,value]:previous.filter(item=>item!==value))}/><span title={value}>{value||'(Blanks)'}</span><small>{count.toLocaleString()}</small></label>)}{!shown.length&&<p className="muted">No matching values.</p>}</div>
    <div className="column-menu-actions"><button type="button" className="primary" onClick={apply}>Apply</button><button type="button" className="secondary" onClick={()=>{controls.apply(column,null);onClose(true);}}>Clear filter</button></div>
  </div>,anchor.closest('dialog')||document.body);
}

export function ColumnFilterButton({column,controls}) {
  const button=useRef(null),[open,setOpen]=useState(false);
  const close=focus=>{setOpen(false);if(focus)button.current?.focus();};
  return <><button ref={button} type="button" className={`column-filter-trigger${controls.filters[column]?' active-filter':''}`} aria-label={`Filter column ${column}`} title={`Filter ${column}`} aria-haspopup="dialog" aria-expanded={open} onClick={()=>setOpen(value=>!value)}><Filter size={13}/></button>{open&&<FilterMenu column={column} controls={controls} anchor={button.current} onClose={close}/>}</>;
}

function elements(children){return Children.toArray(children).flatMap(child=>isValidElement(child)&&child.type===Fragment?elements(child.props.children):isValidElement(child)?[child]:[]);}
function textOf(node){return Children.toArray(node).map(child=>typeof child==='string'||typeof child==='number'?str(child):isValidElement(child)?textOf(child.props.children):'').join('');}

// Plain report tables share the same menu; paginated tables provide controls
// computed from their entire dataset, so filtering always happens before paging.
export function FilterableTable({children,controls,columnNames,...props}) {
  const parts=elements(children),head=parts.find(part=>part.type==='thead'),body=parts.find(part=>part.type==='tbody');
  const headings=elements(elements(head?.props.children)[0]?.props.children);
  const columns=columnNames||headings.map(th=>textOf(th.props.children).trim());
  const bodyRows=elements(body?.props.children);
  const records=useMemo(()=>controls?[]:bodyRows.map((row,index)=>Object.fromEntries([
    ['_filter_index',index],...elements(row.props.children).map((cell,i)=>[columns[i],str(cell.props.title??textOf(cell.props.children))])
  ])),[children,controls]);
  const local=useColumnFilters(records,columns),filters=controls||local;
  const indexes=new Set(local.rows.map(row=>row._filter_index));
  return <>{Object.keys(filters.filters).length>0&&<div className="workspace-table-filter-status"><span>{Object.keys(filters.filters).length} column filters · {filters.rows.length.toLocaleString()} of {filters.sourceRows.length.toLocaleString()} rows</span><button type="button" className="text-button" onClick={filters.clear}>Clear table filters</button></div>}
    <table {...props}>{parts.map(part=>part.type==='thead'?cloneElement(part,{},elements(part.props.children).map(row=>cloneElement(row,{},elements(row.props.children).map((th,index)=>cloneElement(th,{},<div className="workspace-filter-heading"><div className="workspace-heading-content">{th.props.children}</div>{columns[index]&&<ColumnFilterButton column={columns[index]} controls={filters}/>}</div>))))):part.type==='tbody'&&!controls?cloneElement(part,{},bodyRows.filter((_,index)=>indexes.has(index))):part)}</table>
  </>;
}
