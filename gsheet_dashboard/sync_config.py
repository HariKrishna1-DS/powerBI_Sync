import json
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')
CONFIG = json.loads((BASE_DIR / 'sync_config.json').read_text(encoding='utf-8'))
SPREADSHEET_ID = CONFIG['spreadsheet_id']
WORKSHEET_GID = int(CONFIG['worksheet_gid'])
TARGET_GSHEET_URL = f'https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid={WORKSHEET_GID}'
QUEUE_URL = os.getenv('DATATRACE_QUEUE_URL', CONFIG['queue_url'])
FULL_TRACKER_TITLE = CONFIG.get('full_tracker_title', 'TV_Search_Production_Report_Full_Search_-_September_2026')
REMAINING_TRACKER_TITLE = CONFIG.get('remaining_tracker_title', 'TV_Search_Production_Report_C-O_and_Update_-_September_2026')
TRACKER_TITLES = (FULL_TRACKER_TITLE, REMAINING_TRACKER_TITLE)
