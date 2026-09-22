import requests
import re
import pandas as pd
import io

sheet_id = "1YkbMfgQhnXz3amkZTB76h8_5I7PBeWUoh6j9gS51BsE"
url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

r = requests.get(url, headers=headers)
print("HTML View Status:", r.status_code)

matches = re.findall(r'name:\s*"([^"]+)",\s*pageUrl:[^}]+?gid:\s*"([0-9]+)"', r.text)
print("\nDiscovered Tabs in Google Sheet:")
for name, gid in matches:
    print(f"  - Tab Name: '{name}' | GID: {gid}")
    export_u = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    res = requests.get(export_u, headers=headers)
    print(f"    Export Status: {res.status_code} | Bytes: {len(res.content)}")
    if len(res.content) > 0:
        try:
            df = pd.read_csv(io.BytesIO(res.content))
            print(f"    Rows: {len(df)} | Columns: {list(df.columns[:4])}")
        except Exception as e:
            print(f"    Parse error: {e}")
