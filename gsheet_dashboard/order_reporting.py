"""Google Sheet based reporting and immutable capture preparation."""
import pandas as pd

COMPLETED = 'Completed and Delivered'
AUTOMATIC_RULES = [{'source': 'WorkflowSuspended = True', 'target': 'Awaiting for Clarification'},
                   {'source': 'Search / Available', 'target': 'Search In Progress'}]

def automatic_sync_frame(latest, previous=None, keys=None, ignore=None, store=None, reports=None):
    frame = pd.DataFrame(latest['rows'], columns=latest['columns']).fillna('')
    frame.attrs.update(preview_name=latest['name'], preview_id=latest['id'],
                       preview_created=latest['created'],
                       original_capture=dict(latest))
    if store is not None:
        frame.attrs['store_root'] = str(store.root)
    return frame, []

def completion_history(store, latest_id):
    return {}

def daily_orders(store=None, preview_id=None, history=None, sheet_rows=None):
    from tracker_sync import sheet_reports, FULL, REMAINING
    if sheet_rows is None:
        raise ValueError('Google Sheets tracker rows are required for production reporting.')
    trackers = {t: [r for r in sheet_rows if (r.get('_tracker') or r.get('_sheet') or (FULL if str(r.get('Product', '')).strip().casefold() in ('full title', 'full search') else REMAINING)) == t] for t in (FULL, REMAINING)}
    return sheet_reports(trackers)['daily']

def monthly_orders(store=None, sheet_rows=None, history=None, corrections=None):
    from tracker_sync import sheet_reports, FULL, REMAINING
    if sheet_rows is None:
        raise ValueError('Google Sheets tracker rows are required for production reporting.')
    trackers = {t: [r for r in sheet_rows if (r.get('_tracker') or r.get('_sheet') or (FULL if str(r.get('Product', '')).strip().casefold() in ('full title', 'full search') else REMAINING)) == t] for t in (FULL, REMAINING)}
    return sheet_reports(trackers)['monthly']
