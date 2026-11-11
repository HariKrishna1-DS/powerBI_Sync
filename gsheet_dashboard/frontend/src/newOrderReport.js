export function plainComment(value){
  let text=String(value??'');
  for(let pass=0;pass<2&&/<\/?[a-z][^>]*>|&(?:#\d+|#x[0-9a-f]+|[a-z]+);/i.test(text);pass++){
    const template=document.createElement('template');template.innerHTML=text;
    template.content.querySelectorAll('br').forEach(node=>node.replaceWith('\n'));
    template.content.querySelectorAll('p,div,li').forEach(node=>node.append('\n'));
    text=template.content.textContent;
  }
  return text.replace(/\r\n?/g,'\n').trim();
}
export const NEW_ORDER_COLUMNS=['No','Date','Order Number','TraceQ Id','State','County','Client','Online/Ground','Product','Status','ETA','Comments','Assignee','Searcher','Clarification Requested','Shift','Process date','Typer','Review/QC','Expense','In-Time','Out Time','SLA Expiration','Free site','review'];
export function newOrderRecord(order){
  const fallback={'No':'','Date':order.arrival_date||order.in_time||'','Order Number':order.order_number,'TraceQ Id':order.traceq_id,'State':order.state,'County':order.county,'Client':order.client,'Online/Ground':order.online_ground,'Product':order.product,'Comments':order.queue_comments||'','Assignee':order.assignee,'Searcher':order.searcher,'Typer':order.typer,'In-Time':order.in_time,'Out Time':order.out_time};
  const record={...fallback,...order.production_report,'Status':order.sla_status,'SLA Expiration':order.sla_expiration};
  record.Comments=plainComment(order.eta_comments||record.Comments);
  const iso=String(record.Date||'').match(/^(\d{4})-(\d{2})-(\d{2})/);
  if(iso)record.Date=`${Number(iso[2])}/${Number(iso[3])}/${iso[1]}`;
  else {const date=String(record.Date||'').match(/^(\d{1,2}\/\d{1,2}\/\d{4})/);if(date)record.Date=date[1];}
  return Object.fromEntries(NEW_ORDER_COLUMNS.map(column=>[column,record[column]??'']));
}
export function newOrdersTsv(orders){
  const clean=value=>{const text=String(value??'').replace(/[\t\r\n]+/g,' ');return /^[=+@]/.test(text)?"'"+text:text;};
  return orders.map(order=>{const record=newOrderRecord(order);return NEW_ORDER_COLUMNS.map(column=>clean(record[column])).join('\t');}).join('\r\n');
}
