# DataTrace Sync Setup

The extraction button and `python datatrace_sync.py` run the same pipeline:
browser login, queue pagination, CSV/Excel export, then Google Sheets replacement.
`sync_config.json` is the shared target configuration for spreadsheet
`1xjQ3yaDpMgvp3cRSQM-SfF8UBnbTcW_HWpZp_aN5-a8`, worksheet gid `0`.
The tab title is discovered by ID. Every successful sync replaces all values on
that tab, including stale rows. Other tabs and formatting are retained.
Keep manually maintained data on a separate tab.

## Requirements

1. Install Python 3.10+ and Node.js 22.12+.
2. From the repository root, run:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r gsheet_dashboard\requirements.txt
   npm.cmd --prefix gsheet_dashboard install
   ```

3. Create `gsheet_dashboard/.env` using `.env.example` as the template.
   Set `DATATRACE_USERNAME` and `DATATRACE_PASSWORD`.
   `DATATRACE_QUEUE_URL` optionally selects another queue.
4. In Google Cloud, enable the Google Sheets API, create a service account, and
   download its JSON key to `gsheet_dashboard/service_account.json`.
   Alternatively, set `GOOGLE_SERVICE_ACCOUNT_JSON` to an absolute path or inline JSON.
5. Share the target Sheet with the JSON file's `client_email` as **Editor**.
   Public sharing is not required for this target.

Credentials and `.env` are ignored by Git. Authentication reference:
https://docs.gspread.org/en/master/oauth2.html

## Run

```powershell
.\.venv\Scripts\python.exe gsheet_dashboard\datatrace_sync.py
npm.cmd --prefix gsheet_dashboard\frontend install
npm.cmd --prefix gsheet_dashboard\frontend run build
.\.venv\Scripts\python.exe gsheet_dashboard\server.py
```

Or launch `gsheet_dashboard/run.bat` and click **Run AutoLogin & Extract Queue**.
The React workspace opens at http://localhost:8510 (or the next free port printed
by the launcher). The former Streamlit UI and demo star schema have been removed.
The dashboard reports extraction status, row count, Sheets status and the last
successful sync time in UTC. Failed extraction never uploads old local files.
A failed Sheets write retains fresh local exports. The CLI exits nonzero on failure.
No recurring schedule is installed by this change.

Exports are `gsheet_dashboard/queue_data_sheet2.csv` and `.xlsx`.
Each new capture also saves immutable `previews/preview1.xlsx`, `preview2.xlsx`,
and so on, with matching CSV files and a SQLite history index. Imported CSV/XLSX
files are saved as new numbered previews too. Existing legacy queue files are
never loaded automatically. The UI starts empty until a capture or import.
Excel contains the named table **DataTraceQueue**.
The Node script produces intermediate JSON only; run the Python pipeline for
CSV/Excel and Sheets sync. Excel generation uses the existing Python openpyxl library.
Empty/unrecognized queues fail without replacing existing data; review the portal
manually if a legitimately empty queue should be cleared.
For interactive login, set `DATATRACE_HEADLESS=false`.
Portal login and pagination still require validation with your account.

## Power BI

Recommended: **Get Data > Excel**, select `queue_data_sheet2.xlsx`, then the named
**DataTraceQueue** table. CSV import is also supported. Set Parcel ID, OPON and
other identifiers to Text. Use the English (United States) locale for full dates.

| Field | Type / purpose |
| --- | --- |
| Arrival Time, Completed Time | Date/time when a full date is supplied |
| Arrival Date | Date; join to a calendar dimension |
| Client, Product, Task Name, Task Status, St, County, Municipality, Online/Ground, Vendor | Text dimensions |
| Parcel ID, OPON, Last User, Comment, ETA Comments | Text identifiers/details |
| Queue Age Hours | Decimal derived from portal Time Since Arrival |
| Is Available, Is Suspended | Boolean |
| SLA Status | Overdue for negative portal durations; otherwise Unknown |
| Sync Timestamp | UTC date/time of the extraction run |

ETA and SLA Expiration may contain yearless dates or durations. Keep them as text
until the portal year/timezone conventions are confirmed. Unknown SLA is not
on-time. Queue age and SLA fields are snapshot values.

```dax
Queue Tasks = COUNTROWS(DataTraceQueue)
Available Tasks = CALCULATE([Queue Tasks], DataTraceQueue[Is Available] = TRUE())
Overdue Tasks = CALCULATE([Queue Tasks], DataTraceQueue[SLA Status] = "Overdue")
Average Queue Age Hours = AVERAGE(DataTraceQueue[Queue Age Hours])
```

Use cards for counts, bars by Client/Status/State, a County matrix, and an arrival
date trend. This is a current queue snapshot, not a historical completion log.
Published Power BI reports reading local files require a refresh gateway.
Desktop reports can refresh directly from these exports.

## Preview comparison and filters

Select **Changes** to compare the selected capture against its predecessor, or
choose any two saved previews. Added/removed/modified counts refer to tasks;
the change table has one row per modified field (an entire row for additions/removals).
Matching defaults to a complete unique OPON or Task ID, then a unique composite
of Arrival Time, Parcel ID, Task Name, Client and Product. If no reliable key is
available, a multiset comparison preserves duplicates and reports additions/removals.
Select custom **Matching columns** to identify updates in those datasets. Invalid
or duplicate keys are rejected rather than pairing unrelated tasks.

Elapsed queue durations, Queue Age Hours and Sync Timestamp are ignored by default;
change the **Ignored columns** selection to include them. Schema changes are shown
separately. **Power BI changes.xlsx** downloads the named `DataTraceChanges` table;
load it into Power BI with Get Data > Excel. Actual Power BI embedding/publishing
requires a separate Power BI account/report integration and is not configured here.

Click a column header to list its unique values and counts, select values, search,
or apply text/numeric/date conditions. Conditions combine across columns with AND.
Use ISO dates (YYYY-MM-DD) for date bounds. Filters affect both charts and the table.
Unique-value lists can be printed or downloaded. Filtered CSV exports include all
matching rows, not just the current page; the original preview downloads remain intact.

Charts support bar, horizontal bar, line, area, pie and donut. Choose any grouping
column, adjust spacing, and scroll horizontally or vertically for larger datasets.
Cartesian charts also have a draggable range selector when there are many categories.

Each extraction launches a new browser process. The run button is disabled only
while a job is active and becomes available after success or failure. A browser
refresh reconnects to an active job. Job status is in memory; numbered captures
remain on disk after server restarts. Keep one server instance running per workspace.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s gsheet_dashboard -p "test_*.py" -v
cd gsheet_dashboard\frontend
npm.cmd run build
npx.cmd playwright test
```

Browser tests use isolated API fixtures; they do not seed the real workspace or
contact DataTrace/Google. Actual portal login still requires configured credentials.
