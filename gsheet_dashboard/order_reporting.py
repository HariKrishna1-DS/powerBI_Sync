"""Status automation and capture-level daily order reporting."""
from datetime import datetime

import pandas as pd

from datatrace_sync import apply_status_rules, sla_result, parse_report_datetime
from preview_store import PreviewStore, compare
from reporting_dates import arrival_date, reporting_date

COMPLETED = 'Completed and Delivered'
AUTOMATIC_RULES = [{'source': 'Workflow Suspended', 'target': 'Awaiting for Clarification'}]


def automatic_sync_frame(latest, previous=None, keys=None, ignore=None, store=None, reports=None):
    day = reporting_date(latest)
    columns = list(latest['columns'])
    rows = list(latest['rows'])
    completed_orders = set()
    valid_completed_ids = None
    all_daily_missing = {}

    if store is not None:
        reports = daily_orders(store) if reports is None else reports
        for r in reversed(reports):
            for oid in r['missing_ids']:
                all_daily_missing[oid] = r['Date']
        valid_completed_ids = set(all_daily_missing.keys())

        # For the active reporting day of latest preview:
        day_report = next((r for r in reports if r['Date'] == day), None)
        if day_report:
            completed_orders = set(day_report['missing_ids'])
            columns = list(dict.fromkeys(columns + day_report['columns']))
            present = {str(row.get('Order Number', '')).strip() for row in rows} - {''}
            for r in day_report['rows']:
                oid = str(r.get('Order Number', '')).strip()
                if oid in completed_orders and oid not in present:
                    rows.append(r)
    elif previous is not None:
        comparison = compare(previous, latest, keys, ignore)
        if 'Order Number' not in latest['columns'] or 'Order Number' not in previous['columns']:
            raise ValueError('Order Number is required in both previews for automatic completion.')
        completed_orders = {str(row.get('Order Number', '')).strip()
                            for row in comparison['unmatched_rows']
                            if row['Comparison Status'] == 'Missing'} - {''}
        columns = list(dict.fromkeys(columns + previous['columns']))
        # Missing rows must remain in the uploaded reports to show their completion.
        present = {str(row.get('Order Number', '')).strip() for row in rows} - {''}
        rows += [row for row in previous['rows']
                 if str(row.get('Order Number', '')).strip() in completed_orders - present]
        valid_completed_ids = set(completed_orders)
        all_daily_missing = {oid: day for oid in completed_orders}

    frame = apply_status_rules(pd.DataFrame(rows, columns=columns).fillna(''), AUTOMATIC_RULES, reporting_date=day)
    if completed_orders:
        mask = frame['Order Number'].astype(str).str.strip().isin(completed_orders)
        for column in ('Task Status', 'Status'):
            if column in frame.columns:
                frame.loc[mask, column] = COMPLETED
        frame.loc[mask, 'Out Time'] = day
        if 'Is Available' in frame.columns:
            frame.loc[mask, 'Is Available'] = False
    frame.attrs['reporting_date'] = day
    frame.attrs['capture_date'] = datetime.fromisoformat(latest['created']).astimezone().date().isoformat()
    frame.attrs['original_capture'] = {'columns': list(latest['columns']), 'rows': latest['rows']}
    frame.attrs['valid_completed_ids'] = valid_completed_ids
    frame.attrs['completion_dates'] = all_daily_missing
    return frame, sorted(completed_orders)


def completion_history(store, latest_id):
    dates = {}
    reports = daily_orders(store)
    for report in reversed(reports):
        for identity in report['missing_ids']:
            dates[identity] = report['Date']
    return dates


def daily_orders(store, preview_id=None, history=None):
    days = {}
    if history is None:
        history = store.history() if isinstance(store, PreviewStore) else [store.get(item['id']) for item in store.list()]
    captures = sorted(history, key=lambda item: (datetime.fromisoformat(item['created']), item['id']))
    if preview_id is not None:
        selected = next((item for item in captures if item['id'] == preview_id), None)
        if selected is None:
            raise KeyError('Preview not found.')
        cutoff = (datetime.fromisoformat(selected['created']), selected['id'])
        captures = [item for item in captures if (datetime.fromisoformat(item['created']), item['id']) <= cutoff]
    for preview in captures:
        day = reporting_date(preview)
        days.setdefault(day, []).append(preview)
    reports = []
    for day, previews in sorted(days.items(), reverse=True):
        orders, snapshots, columns = {}, [], []
        for preview in previews:
            columns = list(dict.fromkeys(columns + preview['columns']))
            current = {}
            for row in preview['rows']:
                identity = str(row.get('Order Number', '')).strip()
                if identity:
                    current[identity] = dict(row)
            snapshots.append(set(current))
            orders.update(current)
        unique = set(orders)
        missing = unique - snapshots[-1]
        arrivals = {identity: arrival_date(row) for identity, row in orders.items()}
        new = {identity for identity, date in arrivals.items() if date == day} if any(arrivals.values()) else unique - snapshots[0]
        unchanged = set.intersection(*snapshots)
        frame = apply_status_rules(pd.DataFrame(list(orders.values()), columns=columns).fillna(''), AUTOMATIC_RULES, reporting_date=day)
        rows = frame.to_dict('records')
        for row in rows:
            if str(row.get('Order Number', '')).strip() in missing:
                for column in ('Task Status', 'Status'):
                    if column in row:
                        row[column] = COMPLETED
                if 'Is Available' in row:
                    row['Is Available'] = False
                row['Out Time'] = day
        awaiting = sum(1 for row in rows if str(row.get('Task Status', row.get('Status', ''))).strip().casefold() in ('awaiting for clarification', 'workflow suspended'))
        reports.append({
            'Date': day, 'Previews': [p['name'] for p in previews],
            'Today Orders': len(unique),
            'Awaiting for Clarification': awaiting,
            'Missing (Completed Orders)': len(missing),
            'Newly Orders': len(new), 'Unchanged': len(unchanged),
            'columns': list(frame.columns), 'rows': rows,
            'missing_ids': sorted(missing), 'new_ids': sorted(new),
            'unchanged_ids': sorted(unchanged),
        })
    return reports


def monthly_orders(store, sheet_rows=None, history=None, corrections=None):
    from sla_comments import sla_entry, sla_key, sla_status
    months = {}
    monthly_completions = {}
    previous_rows = {}
    if history is None and corrections is None and isinstance(store, PreviewStore):
        history, corrections = store.history(include_sla_corrections=True)
    if history is None:
        history = store.history() if isinstance(store, PreviewStore) else [store.get(item['id']) for item in store.list()]
    if corrections is None:
        corrections = store.sla_corrections() if isinstance(store, PreviewStore) else {}
    captures = sorted(history, key=lambda item: (datetime.fromisoformat(item['created']), item['id']))
    for preview in captures:
        day = reporting_date(preview)
        month_key = day[:7] if len(day) >= 7 else datetime.fromisoformat(preview['created']).astimezone().strftime('%Y-%m')
        months.setdefault(month_key, []).append((day, preview))
        current_rows = {str(row.get('Order Number', '')).strip(): dict(row)
                        for row in preview['rows'] if str(row.get('Order Number', '')).strip()}
        # Use the first capture where an order disappears, including across days.
        completed = [dict(row, **{'Out Time': day}) for identity, row in previous_rows.items()
                     if identity not in current_rows and not str(row.get('Out Time', '')).strip()]
        adjusted = apply_status_rules(pd.DataFrame(preview['rows'], columns=preview['columns']).fillna(''),
                                      AUTOMATIC_RULES, reporting_date=day)
        adjusted_rows = adjusted.to_dict('records')
        for row in adjusted_rows:
            identity = str(row.get('Order Number', '')).strip()
            prior_out = previous_rows.get(identity, {}).get('Out Time', '')
            if (parse_report_datetime(prior_out) and row.get('Out Time')
                    and not current_rows.get(identity, {}).get('Out Time')):
                row['Out Time'] = prior_out
        completed.extend(adjusted_rows)
        for row in completed:
            out = parse_report_datetime(row.get('Out Time', ''))
            identity = str(row.get('Order Number', '')).strip()
            if out and identity:
                bucket = monthly_completions.setdefault(out.strftime('%Y-%m'), {})
                # Repeated captures must not move a completion to a later day.
                bucket.setdefault(identity, sla_entry(row, corrections.get(sla_key(row), sla_result(row))))
        previous_rows = {str(row.get('Order Number', '')).strip(): row for row in adjusted_rows}

    # Live sheet values override saved captures for matching orders. A cleared Free Site
    # cell removes the old classification rather than leaving the snapshot's value behind.
    for index, row in enumerate(sheet_rows or []):
        out = parse_report_datetime(row.get('Out Time', ''))
        status = sla_status(row.get('Free Site'))
        identity = str(row.get('Order Number', '')).strip() or f'sheet-row-{index}'
        for bucket in monthly_completions.values():
            bucket.pop(identity, None)
        if out and status:
            monthly_completions.setdefault(out.strftime('%Y-%m'), {})[identity] = sla_entry(row, status)

    reports = []
    for month_key, day_previews in sorted(months.items(), reverse=True):
        orders, snapshots, columns = {}, [], []
        day_previews_sorted = sorted(day_previews, key=lambda dp: (dp[0], datetime.fromisoformat(dp[1]['created']), dp[1]['id']))
        previews = [p for _, p in day_previews_sorted]
        days = sorted(list({day for day, _ in day_previews_sorted}))
        last_day = days[-1] if days else f"{month_key}-01"

        for preview in previews:
            columns = list(dict.fromkeys(columns + preview['columns']))
            current = {}
            for row in preview['rows']:
                identity = str(row.get('Order Number', '')).strip()
                if identity:
                    current[identity] = dict(row)
            snapshots.append(set(current))
            orders.update(current)

        unique = set(orders)
        missing = unique - snapshots[-1] if snapshots else set()
        arrivals = {identity: arrival_date(row) for identity, row in orders.items()}
        new = {identity for identity, date in arrivals.items() if date and date.startswith(month_key)} if any(arrivals.values()) else (unique - snapshots[0] if snapshots else set())
        unchanged = set.intersection(*snapshots) if snapshots else set()

        frame = apply_status_rules(pd.DataFrame(list(orders.values()), columns=columns).fillna(''), AUTOMATIC_RULES, reporting_date=last_day)
        rows = frame.to_dict('records')
        for row in rows:
            if str(row.get('Order Number', '')).strip() in missing:
                for column in ('Task Status', 'Status'):
                    if column in row:
                        row[column] = COMPLETED
                if 'Is Available' in row:
                    row['Is Available'] = False
                row['Out Time'] = last_day
        awaiting = sum(1 for row in rows if str(row.get('Task Status', row.get('Status', ''))).strip().casefold() in ('awaiting for clarification', 'workflow suspended'))

        try:
            month_label = datetime.strptime(month_key, '%Y-%m').strftime('%B %Y')
        except ValueError:
            month_label = month_key

        sla_rows = sorted(monthly_completions.get(month_key, {}).values(),
                          key=lambda row: (row['completion_date'], row['Order Number']), reverse=True)
        on_time = sum(row['Free Site'] == 'On Time' for row in sla_rows)
        missed_sla = sum(row['Free Site'] == 'Missed' for row in sla_rows)
        reports.append({
            'Month': month_key,
            'MonthLabel': month_label,
            'Date': month_key,
            'Previews': [p['name'] for p in previews],
            'Days': days,
            'Month Orders': len(unique),
            'Today Orders': len(unique),
            'Awaiting for Clarification': awaiting,
            'Missing (Completed Orders)': len(missing),
            'Completed Orders': len(missing),
            'SLA On Time': on_time,
            'SLA Missed': missed_sla,
            'sla_rows': sla_rows,
            'Newly Orders': len(new),
            'Unchanged': len(unchanged),
            'columns': list(frame.columns),
            'rows': rows,
            'missing_ids': sorted(missing),
            'new_ids': sorted(new),
            'unchanged_ids': sorted(unchanged),
        })
    return reports

