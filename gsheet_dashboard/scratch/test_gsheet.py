import requests
import re
import pandas as pd
import io

sheet_id = "1YkbMfgQhnXz3amkZTB76h8_5I7PBeWUoh6j9gS51BsE"

urls_to_test = [
    ("export format=csv gid=14789859", f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=14789859"),
    ("export format=csv gid=0", f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid=0"),
    ("export format=csv default", f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"),
    ("gviz sheet=Sheet2", f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Sheet2"),
    ("gviz sheet=Sheet 2", f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=Sheet%202"),
    ("gviz gid=14789859", f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid=14789859"),
]

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Cache-Control": "no-cache"
}

print("=== TESTING GOOGLE SHEET URL ENDPOINTS ===")
for label, u in urls_to_test:
    try:
        r = requests.get(u, headers=headers, timeout=10)
        print(f"\n[+] Testing: {label}")
        print(f"    URL: {u}")
        print(f"    Status: {r.status_code}")
        print(f"    Content-Type: {r.headers.get('Content-Type')}")
        print(f"    Content-Length: {len(r.content)} bytes")
        if r.status_code == 200:
            if "html" in r.headers.get('Content-Type', '').lower():
                print("    [!] Response is HTML (Private/Restricted Sheet or Login required)")
            else:
                try:
                    df = pd.read_csv(io.BytesIO(r.content))
                    print(f"    [SUCCESS] Parsed DataFrame shape: {df.shape}")
                    print(f"    Columns: {list(df.columns[:5])}")
                    if not df.empty:
                        print(f"    First row sample:\n{df.iloc[0].to_dict()}")
                except Exception as e:
                    print(f"    [!] Failed to parse CSV: {e}")
    except Exception as ex:
        print(f"    [!] Request error: {ex}")
