"""New Orders follow the supplied C-O and Update production worksheet."""
import re
from html.parser import HTMLParser

NEW_ORDER_COLUMNS = ['No', 'Date', 'Order Number', 'TraceQ Id', 'State', 'County', 'Client',
    'Online/Ground', 'Product', 'Status', 'ETA', 'Comments', 'Assignee', 'Searcher',
    'Clarification Requested', 'Shift', 'Process date', 'Typer', 'Review/QC', 'Expense',
    'In-Time', 'Out Time', 'SLA Expiration', 'Free site', 'review']

class _CommentText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
    def handle_data(self, value): self.parts.append(value)
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='br': self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag.lower() in ('p','div','li'): self.parts.append('\n')


def plain_comment(value):
    text=str(value or '')
    for _ in range(2):
        if not re.search(r'<\/?[a-z][^>]*>|&(?:#\d+|#x[0-9a-f]+|[a-z]+);', text, re.I): break
        parser=_CommentText()
        parser.feed(text)
        text=''.join(parser.parts)
    text=re.sub(r'[^\S\n]+',' ',text.replace('\r\n','\n').replace('\r','\n'))
    return '\n'.join(line.strip() for line in text.split('\n')).strip()


def production_record(source, status=None):
    # Preserve case for Review/QC versus review; otherwise normalize header punctuation.
    normalized = {re.sub(r'[^a-z0-9]', '', str(k).casefold()): v for k,v in source.items()}
    def field(*names):
        for name in names:
            val = normalized.get(re.sub(r'[^a-z0-9]', '', name.casefold()))
            if val is not None and str(val).strip():
                return val
        return ''
    record = {column: field(column) for column in NEW_ORDER_COLUMNS}
    record.update({'No':'', 'Date':field('Date','Arrival Date','Arrival Time','In-Time'),
        'State':field('State','St'), 'Status':status if status is not None else field('Status','Task Status'),
        'Comments':plain_comment(field('ETA Comments','Comments','Comment')), 'Assignee':field('Assignee','Last User'),
        'In-Time':field('In-Time','Arrival Time'), 'Process date':field('Process date','Processed Date'),
        'SLA Expiration':field('SLA Expiration','SLA Expiration*')})
    value = str(record['Date'])
    iso = re.match(r'^(\d{4})-(\d{2})-(\d{2})', value)
    if iso: record['Date'] = f'{int(iso[2])}/{int(iso[3])}/{iso[1]}'
    else:
        date = re.match(r'^(\d{1,2}/\d{1,2}/\d{4})', value)
        if date: record['Date'] = date[1]
    return record

def comparison_record(order):
    source = {'Date':order.get('arrival_date') or order.get('in_time',''),
        'Order Number':order.get('order_number',''), 'TraceQ Id':order.get('traceq_id',''),
        'State':order.get('state',''), 'County':order.get('county',''), 'Client':order.get('client',''),
        'Online/Ground':order.get('online_ground',''), 'Product':order.get('product',''),
        'Comments':order.get('queue_comments',''), 'Assignee':order.get('assignee',''),
        'Searcher':order.get('searcher',''), 'Typer':order.get('typer',''),
        'In-Time':order.get('in_time',''), 'Out Time':order.get('out_time','')}
    source.update(order.get('production_report') or {})
    source['SLA Expiration'] = order.get('sla_expiration','')
    if order.get('eta_comments'): source['ETA Comments'] = order['eta_comments']
    return production_record(source, order.get('sla_status',''))
