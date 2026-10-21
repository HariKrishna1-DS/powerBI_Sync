import React, {useEffect,useMemo,useState} from 'react';
import {Search,LoaderCircle,X} from 'lucide-react';
import {api,str} from './workspaceUtils';
import {DataTable} from './WorkspaceViews';

export default function ReportOrderSearch({name,rows,columns=[],revision,disabled=false}) {
  const [search,setSearch]=useState(''),[result,setResult]=useState(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  const query=search.trim().toLowerCase();
  useEffect(()=>{
    if(rows||!query){setResult(null);setLoading(false);setError('');return;}
    const controller=new AbortController();
    setLoading(true);setResult(null);setError('');
    const timer=setTimeout(()=>{
      api(`/api/report-order-search?${new URLSearchParams({search:query})}`,{signal:controller.signal})
        .then(setResult).catch(error=>{if(error.name!=='AbortError')setError(error.message);})
        .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    },250);
    return()=>{clearTimeout(timer);controller.abort();};
  },[query,rows,revision]);
  const matches=useMemo(()=>{
    if(!rows||!query)return result?.rows||[];
    const exact=rows.filter(row=>str(row['Order Number']).trim().toLowerCase()===query);
    return exact.length?exact:rows.filter(row=>str(row['Order Number']).toLowerCase().includes(query));
  },[rows,query,result]);
  const detailColumns=useMemo(()=>{
    const names=new Set([...(rows?columns:result?.columns||[]),...matches.flatMap(row=>Object.keys(row))]);
    return [...new Set(['Order Number','Status','SLA Category','Out Time','Date','In-Time','Source workbook','Product',...names])]
      .filter(column=>names.has(column)&&!column.startsWith('_'));
  },[rows,columns,result,matches]);
  return <section className="report-order-search" aria-label={`${name} order search`}>
    <label className="report-order-search-label" htmlFor={`report-order-search-${name.replaceAll(' ','-')}`}>Search order number</label>
    <div className="search-input"><Search size={16}/><input id={`report-order-search-${name.replaceAll(' ','-')}`} type="text" aria-label={`Search ${name} orders`} placeholder="Enter an Order Number" value={search} disabled={disabled} onChange={event=>setSearch(event.target.value)}/>{search&&<button type="button" className="icon-button" aria-label={`Clear ${name} order search`} onClick={()=>setSearch('')}><X size={16}/></button>}</div>
    {query&&<div aria-live="polite">
      {loading?<p className="muted"><LoaderCircle size={16} className="spin"/> Searching orders…</p>:error?<p className="notice warning" role="alert">{error}</p>:(rows||result)&&<>
        <p className="report-context">{result?.total??matches.length} matching order{(result?.total??matches.length)===1?'':'s'}{result?.total>matches.length?` · first ${matches.length} shown`:''}</p>
        {matches.length?<DataTable rows={matches} columns={detailColumns} filters={{}} openFilter={()=>{}} filterable={false} name={`${name} search results`}/>:<p className="muted">No orders match this order number.</p>}
      </>}
    </div>}
  </section>;
}
