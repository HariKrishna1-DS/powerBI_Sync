// Deterministic synthetic data shared by UI tests and the isolated design preview.
export function workspaceFixture(count=240) {
  const products=['Full Title','Current Owner','Update','Full Search'];
  const statuses=['Search In Progress','Search Completed','Awaiting for Clarification','Search In Progress','Assigned'];
  const rows=Array.from({length:count},(_,i)=>({'Order Number':`TV-${62000+i}`,Product:products[i%4],Status:statuses[i%5],Client:['Northstar Title & Escrow','Pacific Coast Settlement Services','Meridian National Title'][i%3],Assignee:['Alex Morgan','Jordan Lee','Sam Taylor'][i%3],'Online/ Ground':i%4?'Online':'Ground','In-Time':'10/05/2026 09:30 AM','Order Date':'10/05/2026',County:['Los Angeles','Maricopa','Orange'][i%3]}));
  const columns=Object.keys(rows[0]);
  const previews=[{id:32,name:'preview32',created:'2026-10-05T05:30:00Z',row_count:count},{id:31,name:'preview31',created:'2026-10-05T03:30:00Z',row_count:count-12},{id:30,name:'September final • consolidated production review',created:'2026-09-30T12:00:00Z',row_count:count-24}];
  const report={Month:'2026-10',MonthLabel:'October 2026',Previews:['preview31','preview32'],columns,rows,'Month Orders':count,'Completed Orders':48,'Unchanged':144,'Awaiting for Clarification':48,'SLA On Time':40,'SLA Missed':8,completed_ids:rows.filter((_,i)=>i%5===1).map(r=>r['Order Number']),sla_rows:rows.filter((_,i)=>i%5===1).slice(0,8).map((r,i)=>({...r,'Product Group':'Full Title','In Time':'2026-10-05 09:30','Out Time':'2026-10-05 11:30','SLA Expiration':'2026-10-05 13:30','Free Site':'Yes',completion_date:'2026-10-05','System SLA':i%4?'On Time':'Missing','Final SLA':i%4?'On Time':'Missing',Comments:''}))};
  const daily=[{Date:'2026-10-05',Previews:['preview31','preview32'],columns,rows,'Today Orders':count,'Not in latest preview':8,'Newly Orders':20,'Unchanged':212,'Awaiting for Clarification':48,new_ids:rows.slice(0,20).map(r=>r['Order Number']),missing_ids:rows.slice(-8).map(r=>r['Order Number']),unchanged_ids:rows.slice(20,-8).map(r=>r['Order Number'])}];
  function response(path,body={}) {
    if(path==='/api/state')return {previews,remaining_products:['Current Owner','Update'],pending_sync:0,job:{running:false,stage:'Ready',run_id:1},schedule:{enabled:false,times:['09:00','13:00','17:30']},clock:{synchronized:true,epoch_ms:1791178200000}};
    if(path.startsWith('/api/previews/')){const preview=previews.find(p=>p.id===Number(path.split('/')[3]));return {...preview,columns,rows:rows.slice(0,preview?.row_count||0)};}
    if(path==='/api/live-sheets')return {updated_at:'2026-10-05T05:32:00Z',sheets:{Overview:{columns,rows},'Full Title':{columns,rows:rows.filter(r=>['Full Title','Full Search'].includes(r.Product))},'Remaining Products':{columns,rows:rows.filter(r=>['Current Owner','Update'].includes(r.Product))}}};
    if(path==='/api/monthly-orders')return {rows:[report],updated_at:'2026-10-05T05:32:00Z'};
    if(path==='/api/daily-orders')return {rows:daily,selected_date:'2026-10-05',updated_at:'2026-10-05T05:32:00Z'};
    if(path==='/api/compare')return {previous:'preview31',latest:'preview32',method:'Matched by Order Number',record_columns:[...columns,'Comparison Status'],record_counts:{matched:228,missing:8,newly_added:20,unchanged:212},matched_rows:rows.slice(0,30).map(r=>({...r,'Comparison Status':'Unchanged'})),unmatched_rows:rows.slice(-8).map(r=>({...r,'Comparison Status':'Missing'})),added_columns:[],removed_columns:[]};
    if(path==='/api/order-history')return {events:previews.slice(0,2).map(p=>({preview_id:p.id,preview_name:p.name,created:p.created,status:'Search In Progress'}))};
    if(path==='/api/activity')return {operations:[{id:1,kind:'sync',status:'completed',started:'2026-10-05T05:32:00Z'},{id:2,kind:'capture',status:'completed',started:'2026-10-05T05:30:00Z'}]};
    if(path==='/api/sync-reports')return {report:{preview_name:'preview32',changes:[{'Order Number':'TV-62001',Action:'Updated','Old Status':'Assigned','New Status':'Search In Progress'}]}};
    if(path==='/api/sync-schedule')return body;
    if(path==='/api/remaining-products')return {saved:true,products:body.remaining_products};
    return {rows:[],operations:[]};
  }
  return {rows,columns,previews,report,response};
}
