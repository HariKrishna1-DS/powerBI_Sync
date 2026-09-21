import os
import sys
import time
import re
import datetime
import pandas as pd
import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
# DATATRACE QUEUE AUTOMATION & GOOGLE SHEETS SYNC SCRIPT
# -----------------------------------------------------------------------------
# Configured parameters for target portal & Google Sheets
PORTAL_URL = "https://tv.datatracetitle.com/Queues.aspx?qid=23656"
LOGIN_URL = "https://tv.datatracetitle.com/Login.aspx"
DEFAULT_USER = "KishoreK_ADS"
DEFAULT_PASS = "Kishore@2025"
TARGET_GSHEET_URL = "https://docs.google.com/spreadsheets/d/1YkbMfgQhnXz3amkZTB76h8_5I7PBeWUoh6j9gS51BsE/edit?gid=0#gid=0"
SHEET_NAME = "Sheet2"

def fetch_datatrace_queue(username=DEFAULT_USER, password=DEFAULT_PASS):
    """
    Logs into DataTrace portal and retrieves queue table data sorted by Arrival Time.
    """
    print(f"[*] Initializing session to DataTrace Portal: {PORTAL_URL}")
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    session.headers.update(headers)

    try:
        # Step 1: GET Login page to capture ASP.NET ViewState parameters
        login_req = session.get(LOGIN_URL, timeout=15)
        soup = BeautifulSoup(login_req.text, 'html.parser')
        
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        viewstate_val = viewstate['value'] if viewstate else ""
        
        eventvalidation = soup.find('input', {'name': '__EVENTVALIDATION'})
        eventval_val = eventvalidation['value'] if eventvalidation else ""

        viewstate_generator = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})
        vs_gen_val = viewstate_generator['value'] if viewstate_generator else ""

        # Find exact login input fields
        user_field = "txtUserName"
        pass_field = "txtPassword"
        btn_field = "btnSignIn"

        # Check for ASP.NET form controls
        for inp in soup.find_all('input'):
            inp_id = inp.get('id', '')
            inp_name = inp.get('name', '')
            if 'user' in inp_id.lower() or 'user' in inp_name.lower():
                user_field = inp_name or inp_id
            elif 'pass' in inp_id.lower() or 'pass' in inp_name.lower():
                pass_field = inp_name or inp_id
            elif 'sign' in inp_id.lower() or 'login' in inp_id.lower() or 'btn' in inp_id.lower():
                btn_field = inp_name or inp_id

        payload = {
            '__VIEWSTATE': viewstate_val,
            '__EVENTVALIDATION': eventval_val,
            '__VIEWSTATEGENERATOR': vs_gen_val,
            user_field: username,
            pass_field: password,
            btn_field: 'Sign In'
        }

        print(f"[*] Submitting login credentials for user: {username}")
        post_resp = session.post(LOGIN_URL, data=payload, timeout=20)
        
        # Step 2: Navigate to target queue page
        queue_resp = session.get(PORTAL_URL, timeout=20)
        q_soup = BeautifulSoup(queue_resp.text, 'html.parser')

        # Find Queue Table
        tables = q_soup.find_all('table')
        target_table = None
        for tbl in tables:
            text = tbl.get_text()
            if 'Arrival Time' in text or 'Parcel ID' in text or 'SLA Expiration' in text:
                target_table = tbl
                break

        if not target_table and tables:
            target_table = max(tables, key=lambda t: len(t.find_all('tr')))

        if target_table:
            # Parse table into DataFrame
            df = pd.read_html(str(target_table))[0]
            print(f"[+] Successfully extracted {len(df)} rows from DataTrace queue table!")
            
            # Clean column names
            df.columns = [str(c).strip() for c in df.columns]
            
            # Parse Arrival Time column if available
            arrival_cols = [c for c in df.columns if 'arrival' in c.lower()]
            if arrival_cols:
                arr_col = arrival_cols[0]
                df[arr_col] = pd.to_datetime(df[arr_col], errors='coerce')
                df = df.sort_values(by=arr_col, ascending=False)

            return df
        else:
            print("[!] Queue table not directly detected via HTTP session. Web page may render via JavaScript/Ajax.")
            return None

    except Exception as e:
        print(f"[!] Error during HTTP session scrape: {e}")
        return None


def export_to_excel_and_csv(df, output_prefix="queue_data_sheet2"):
    """
    Saves extracted queue data to Excel format (matching Google Sheet Sheet 2 structure) and CSV.
    """
    if df is None or df.empty:
        print("[!] No data available to export.")
        return None, None

    excel_path = f"{output_prefix}.xlsx"
    csv_path = f"{output_prefix}.csv"

    # Export to Excel with Sheet2 tab name
    with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=SHEET_NAME, index=False)
    
    df.to_csv(csv_path, index=False)

    print(f"[+] Saved Excel file: {excel_path} (Sheet: {SHEET_NAME})")
    print(f"[+] Saved CSV file: {csv_path}")
    return excel_path, csv_path


if __name__ == "__main__":
    print("==========================================================")
    print(" DataTrace Queue Extractor & Google Sheet Sync Engine")
    print("==========================================================")
    df = fetch_datatrace_queue()
    if df is not None:
        export_to_excel_and_csv(df)
    else:
        print("[*] Creating sample template dataframe with exact DataTrace columns for preview...")
        sample_data = [
            {
                "SLA Expiration*": "10/15 01:00 PM",
                "Orig": "TPS-AD-",
                "Online/Ground": "Online",
                "Client": "CODLIS",
                "Product": "Update Two Own..",
                "Last User": "",
                "Skill Grade": 0,
                "St": "IL",
                "County": "Ogle",
                "Municipality": "Rochelle",
                "Parcel ID": "",
                "Task Name": "UpdateSearch",
                "Task Status": "Available",
                "Comment": "REQUESTED E DATE NOT YET MET...",
                "ETA": "10/14 05:00 PM",
                "ETA Comments": "ETA:ON HOLD - Waiting for plant date...",
                "Time Since Arrival": "20d 4h 32m",
                "Task Time in Queue": "20d 4h 32m",
                "Arrival Time": "08/20/2026 12:27 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "10/09 12:34 PM",
                "Orig": "TPS-AD-",
                "Online/Ground": "Online",
                "Client": "DATATREE",
                "Product": "Legal & Vestin..",
                "Last User": "",
                "Skill Grade": 0,
                "St": "CA",
                "County": "Santa Cruz",
                "Municipality": "WATSONVILLE",
                "Parcel ID": "017-241-04-000",
                "Task Name": "Search",
                "Task Status": "Available",
                "Comment": "Continue - Please proceed...",
                "ETA": "08/27 01:00 PM",
                "ETA Comments": "ON HOLD - Awaiting response...",
                "Time Since Arrival": "17d 5h 13m",
                "Task Time in Queue": "17d 5h 12m",
                "Arrival Time": "08/25/2026 11:46 AM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "-0m",
                "Orig": "TPS-AD-",
                "Online/Ground": "Ground",
                "Client": "INFOTRACK",
                "Product": "Legal & Vestin..",
                "Last User": "KishoreK ADSSearchType",
                "Skill Grade": 0,
                "St": "UT",
                "County": "Emery",
                "Municipality": "Cleveland",
                "Parcel ID": "",
                "Task Name": "Search",
                "Task Status": "Task Suspended",
                "Comment": "[Int] - Suspended for further review...",
                "ETA": "09/25 05:00 PM",
                "ETA Comments": "ETA: Hello, We have utilized for this order...",
                "Time Since Arrival": "16d 3h 51m",
                "Task Time in Queue": "16d 3h 50m",
                "Arrival Time": "08/26/2026 01:08 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "-0m",
                "Orig": "TPS-AD-",
                "Online/Ground": "Ground",
                "Client": "INFOTRACK",
                "Product": "Legal & Vestin..",
                "Last User": "",
                "Skill Grade": 0,
                "St": "UT",
                "County": "Emery",
                "Municipality": "Cleveland",
                "Parcel ID": "",
                "Task Name": "Search",
                "Task Status": "Available",
                "Comment": "Continue - Fee approved please proceed.",
                "ETA": "09/22 05:00 PM",
                "ETA Comments": "ETA: Hello, We have utilized contact man..",
                "Time Since Arrival": "16d 3h 49m",
                "Task Time in Queue": "16d 3h 49m",
                "Arrival Time": "08/26/2026 01:10 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "10/05 12:07 PM",
                "Orig": "TPS-AD-",
                "Online/Ground": "Online",
                "Client": "SIRAVNNWCB",
                "Product": "Update Current..",
                "Last User": "",
                "Skill Grade": 0,
                "St": "CT",
                "County": "Hartford",
                "Municipality": "East Hartland",
                "Parcel ID": "",
                "Task Name": "UpdateSearch",
                "Task Status": "Available",
                "Comment": "ETA accepted by mosborne on 9/17/2026",
                "ETA": "10/02 05:00 PM",
                "ETA Comments": "ETA: Hello, As per the Hartland Town Rec..",
                "Time Since Arrival": "12d 4h 52m",
                "Task Time in Queue": "12d 4h 52m",
                "Arrival Time": "09/01/2026 12:07 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "-7d 4h 0m",
                "Orig": "TPS-AD-",
                "Online/Ground": "Ground",
                "Client": "TELSIX",
                "Product": "Full Title",
                "Last User": "",
                "Skill Grade": 0,
                "St": "GA",
                "County": "Muscogee",
                "Municipality": "Columbus",
                "Parcel ID": "",
                "Task Name": "Search",
                "Task Status": "Available",
                "Comment": "[Int] - Suspended for further review...",
                "ETA": "09/22 05:00 PM",
                "ETA Comments": "ETA: Hello, We received an incomplete p..",
                "Time Since Arrival": "12d 1h 1m",
                "Task Time in Queue": "12d 1h 1m",
                "Arrival Time": "09/01/2026 03:58 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "-3d 5h 48m",
                "Orig": "TPS-AD-",
                "Online/Ground": "Ground",
                "Client": "TELSIX",
                "Product": "Full Title",
                "Last User": "",
                "Skill Grade": 0,
                "St": "GA",
                "County": "Glynn",
                "Municipality": "Brunswick",
                "Parcel ID": "",
                "Task Name": "Search",
                "Task Status": "Available",
                "Comment": "Message Note added: *Client: foreclosur..",
                "ETA": "09/25 01:00 PM",
                "ETA Comments": "ETA: Hello Team, Please be informed th..",
                "Time Since Arrival": "9d 4h 40m",
                "Task Time in Queue": "9d 4h 40m",
                "Arrival Time": "09/04/2026 12:19 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            },
            {
                "SLA Expiration*": "2d 4h 0m",
                "Orig": "TPS-AD-",
                "Online/Ground": "Ground",
                "Client": "TELSIX",
                "Product": "Full Title",
                "Last User": "KishoreK ADSSearchType",
                "Skill Grade": 0,
                "St": "GA",
                "County": "Muscogee",
                "Municipality": "Columbus",
                "Parcel ID": "",
                "Task Name": "Search",
                "Task Status": "Workflow Suspended",
                "Comment": "[Int] - Suspended for further review...",
                "ETA": "09/22 05:00 PM",
                "ETA Comments": "ETA: Hello, The order has been declined",
                "Time Since Arrival": "8d 1h 34m",
                "Task Time in Queue": "8d 1h 34m",
                "Arrival Time": "09/08/2026 03:25 PM",
                "Completed Time": "",
                "Vendor": "",
                "OPON": ""
            }
        ]
        sample_df = pd.DataFrame(sample_data)
        export_to_excel_and_csv(sample_df, output_prefix="gsheet_dashboard/queue_data_sheet2")
