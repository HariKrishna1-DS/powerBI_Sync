import json
import os
from pathlib import Path
from dotenv import load_dotenv

ASSET_DIR = Path(__file__).resolve().parent
BASE_DIR = Path(os.environ.get('DATATRACE_DATA_DIR', str(ASSET_DIR))).resolve()
BASE_DIR.mkdir(parents=True, exist_ok=True)
if os.environ.get('DATATRACE_DESKTOP') != '1':
    load_dotenv(BASE_DIR / '.env')
CONFIG = json.loads((ASSET_DIR / 'sync_config.json').read_text(encoding='utf-8'))
SPREADSHEET_ID = os.environ.get('DATATRACE_SPREADSHEET_ID', CONFIG['spreadsheet_id'])
WORKSHEET_GID = int(CONFIG['worksheet_gid'])
TARGET_GSHEET_URL = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid={WORKSHEET_GID}'
QUEUE_URL = os.getenv('DATATRACE_QUEUE_URL', CONFIG['queue_url'])
FULL_TRACKER_TITLE = os.environ.get('DATATRACE_FULL_TRACKER', CONFIG.get('full_tracker_title', 'TV_Search_Production_Report_Full_Search'))
REMAINING_TRACKER_TITLE = os.environ.get('DATATRACE_REMAINING_TRACKER', CONFIG.get('remaining_tracker_title', 'TV_Search_Production_Report_C-O_and_Update'))
# Upgrade only the shipped legacy names; preserve user-defined tracker names.
if FULL_TRACKER_TITLE == 'TV_Search_Production_Report_Full_Search_-_September_2026':
    FULL_TRACKER_TITLE = 'TV_Search_Production_Report_Full_Search'
if REMAINING_TRACKER_TITLE == 'TV_Search_Production_Report_C-O_and_Update_-_September_2026':
    REMAINING_TRACKER_TITLE = 'TV_Search_Production_Report_C-O_and_Update'
TRACKER_TITLES = (FULL_TRACKER_TITLE, REMAINING_TRACKER_TITLE)
if BASE_DIR != ASSET_DIR and not (BASE_DIR / 'remaining_products.json').exists():
    (BASE_DIR / 'remaining_products.json').write_bytes((ASSET_DIR / 'remaining_products.json').read_bytes())
