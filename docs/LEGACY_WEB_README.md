# DataTrace Workspace & PowerBI Sync

DataTrace Workspace is a local web application and automation suite designed for extracting title queue data from TitleVision, generating structured previews, synchronizing data with Google Sheets, and providing exports for Power BI reporting.

## 🚀 Overview

- **TitleVision Queue Extraction**: Automated headless/headed browser scraping using Node.js & Puppeteer.
- **Preview Store**: Append-only Google Sheets history, plus a local SQLite retry index and numbered Excel/CSV snapshots. No remote database is required.
- **Google Sheets Synchronization**: Automatically reconcile both named production tracker tabs, preserve manual cells and missing orders, and refresh all report views using the Google Sheets API (`gspread`).
- **Editable SLA Comments**: In Monthly report, filter SLA orders by On Time/Missed or Full Title/Remaining Products. Choose **Edit** for one order, or check multiple orders, choose **Bulk SLA status**, and click **Update selected**. The header checkbox selects the current page; **Select all matching orders** includes every page of the current filter. Selections carry across pages and clear when filters change. The order table, totals, percentages, and chart update together. Matching master tracker cells are updated and verified in a batch. Reports read those Sheet values; cached local corrections never supply production data. A new preview recalculates derived Free Site values.
- **Power BI Integration**: Use the Google Sheets production export for production reporting. Raw `DataTraceQueue` snapshots and `DataTraceChanges` comparisons remain available for inspection.
- **Streamlit & React Web Applications**:
  - React/Vite local workspace UI (`http://localhost:8510`)
  - Streamlit analytics dashboard (`http://localhost:8501`)

---

## 🛠️ Architecture & Tech Stack

| Layer | Component / Tool | Responsibility |
| --- | --- | --- |
| **Frontend UI** | React + Vite + Lucide + Recharts | Google Sheets production reporting, audit logs, preview comparison, and automatic sync with a retry control |
| **Analytics UI** | Streamlit + Plotly | Interactive analytics dashboard with KPI cards and visualizations |
| **Backend API** | Python (Flask, Waitress) | Local application service for extraction management, previews, diffing, and sync scheduling |
| **Automation** | Node.js + Puppeteer | Headless browser engine for TitleVision portal login, pagination, and queue extraction |
| **Data Storage** | Google Sheets, local SQLite retry cache, openpyxl, pandas | Numbered snapshot storage, CSV/XLSX file generation, and diff tracking |
| **Integrations** | Google Sheets API, Power BI | Automated cloud sync & BI ready data structures |

---

## 📋 Prerequisites

- **Python**: `3.10+`
- **Node.js**: `v22.12+`
- **Windows OS**

---

## ⚡ Quick Start

> [!IMPORTANT]
> All commands below must be executed from the repository root directory (`C:\Users\Harikrishna\Desktop\powerBI_Sync`). If your shell is in a subdirectory like `gsheet_dashboard\frontend`, return to root with `cd ..\..` first.

### 1. Environment & Dependencies Setup

From the repository root directory:

```powershell
# Install Python dependencies
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r gsheet_dashboard\requirements.txt

# Install Node.js dependencies
npm.cmd --prefix gsheet_dashboard install
npm.cmd --prefix gsheet_dashboard\frontend install
```

### 2. Configuration

Create `gsheet_dashboard/.env` based on `gsheet_dashboard/.env.example`:

```ini
DATATRACE_USERNAME=your_username
DATATRACE_PASSWORD=your_password
DATATRACE_QUEUE_URL=https://... (optional)
DATATRACE_HEADLESS=true
```

Place your Google Cloud Service Account JSON credentials at `gsheet_dashboard/service_account.json` and grant **Editor** access on your target Google Sheet.

`gsheet_dashboard/sync_config.json` selects the spreadsheet and worksheet. The
`GOOGLE_SERVICE_ACCOUNT_JSON` environment setting can override the credential path;
relative paths resolve inside `gsheet_dashboard`. Keep credentials and `.env` private.

### 3. Launch Application

**Option A: Windows Launcher**
Double-click or run:
```powershell
.\gsheet_dashboard\run.bat
```

**Option B: React Web Workspace**
```powershell
npm.cmd --prefix gsheet_dashboard\frontend run build
.\.venv\Scripts\python.exe gsheet_dashboard\server.py
```
Open [http://localhost:8510](http://localhost:8510) in your browser.

If port 8510 is occupied, open the free port printed by the server. For normal use,
keep one backend running to avoid duplicate daily schedulers. After Python code
changes, restart the backend. After frontend changes, rebuild and refresh the page.
An old backend can continue serving new frontend files; restart it to load sync changes.

**Option C: Streamlit Analytics Dashboard**
```powershell
.\.venv\Scripts\python.exe -m streamlit run gsheet_dashboard/streamlit_app.py
```
Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📊 Features & Capabilities

### 🔍 Automated Extraction & Previews
- Performs authenticated login and multi-page queue extractions from TitleVision.
- Saves snapshots sequentially (`previews/preview1.xlsx`, `preview2.xlsx`, etc.) alongside SQLite metadata index.
- Manual CSV/XLSX uploads are automatically integrated as new saved previews.

### 🔄 Google Sheets Sync
- Every extraction, import, and scheduled capture automatically syncs. Failed previews remain saved and are retried while the backend runs.
- Google Sheets is the source for Overview, Data sheets, Daily Orders, Monthly report, Changes, and production exports. Reports show a connection error when Sheets is unavailable.
- The two master tabs use the full September 2026 production tracker names, configurable in `sync_config.json`. Legacy tracker tabs are migrated by title and headers; unrelated tabs are preserved.
- Orders match by trimmed, case-insensitive Order Number. New orders append. Existing manual fields and formulas are preserved. Missing orders keep their existing status and Out Time.
- New orders start as Search In Progress, except workflow-suspended orders, which become Awaiting for Clarification. Existing statuses only follow the documented two mapping rules. Queue disappearance never means completion.
- Snapshots append to raw Sheet1 and All Products history, with a fingerprint index in `__DataTrace_Previews`. All synced captures can be recovered from Google Sheets.
- One atomic batch commits tracker updates, history, reports, and the audit receipt. A host-wide writer lock and receipt verification protect concurrent jobs and retries.
- SLA countdowns use the capture timestamp. Completed orders use real Out Time values, including the time of day. Ambiguous dates are flagged; open orders retain a blank Free Site.
- Daily/monthly totals include every retained tracker order. SLA completions are grouped by actual Out Time. Status colors and On Time/Missing colors are applied to Sheets and `Production_data.xlsx` exports.
- Changes shows the Google Sheets sync log. Compare previews separately inspects raw saved captures.

The reconciled rules and conflict resolutions are documented in [TV Search sync specification](docs/TV_Search_Sync_Prompt.md).
Run one backend writer per spreadsheet. Scheduled jobs run while the backend runs; use a persistent disk to preserve unsynced captures across hosting restarts. Synced history lives in Google Sheets.

### 📈 Diff & Comparison Engine
- Compare any two snapshot previews for added, removed, or modified task records.
- Custom key matching rules and field-level change exports (`DataTraceChanges` table for Power BI).

### 📈 Power BI Integration
- Use `Production_data.xlsx` from Export for retained production totals. The `DataTraceQueue` table contains a raw queue snapshot, not the production source.
- Pre-configured field types (Date, Text identifiers, Booleans, SLA Status, Queue Age Hours).

---

## 🧪 Running Tests

```powershell
# Python unit tests
.\.venv\Scripts\python.exe -m unittest discover -s gsheet_dashboard -p "test_*.py" -v

# Frontend build & Playwright E2E tests
cd gsheet_dashboard\frontend
npm.cmd run build
npx.cmd playwright test --config playwright.production.config.js
```

---

## 📁 Repository Structure

```text
powerBI_Sync/
├── PROJECT_ARCHITECTURE.md       # Architectural deep-dive & diagrams
├── README.md                     # Root project documentation
├── docs/                         # Architecture & workflow diagrams
└── gsheet_dashboard/             # Main application codebase
    ├── app.py / server.py        # Flask API backend service
    ├── streamlit_app.py          # Streamlit analytics dashboard
    ├── datatrace_sync.py         # Scraping & Google Sheets sync pipeline
    ├── preview_store.py          # SQLite & preview file storage manager
    ├── scrape_datatrace.js       # Node.js Puppeteer scraping script
    ├── frontend/                 # React/Vite UI application source code
    ├── SYNC_SETUP.md             # Detailed sync configuration guide
    └── run.bat                   # One-click Windows launcher
```

---

## ☁️ Deploying to Render

This project includes a pre-configured [`Dockerfile`](file:///c:/Users/Harikrishna/Desktop/powerBI_Sync/Dockerfile) and [`render.yaml`](file:///c:/Users/Harikrishna/Desktop/powerBI_Sync/render.yaml) Blueprint to run both Python and Node.js Puppeteer (Headless Chromium) seamlessly on [Render.com](https://render.com).

### Option 1: Automatic Deploy via Render Blueprint (Recommended)
1. Push your repository code to GitHub (`https://github.com/HariKrishna1-DS/powerBI_Sync`).
2. Log in to [Render Dashboard](https://dashboard.render.com/) and click **New + > Blueprint**.
3. Connect your GitHub repository. Render will automatically detect [`render.yaml`](file:///c:/Users/Harikrishna/Desktop/powerBI_Sync/render.yaml).
4. Fill in the environment variables when prompted (`DATATRACE_USERNAME`, `DATATRACE_PASSWORD`, `GOOGLE_SERVICE_ACCOUNT_JSON`).
5. Click **Apply**.

### Option 2: Manual Web Service Setup
1. Create a **New Web Service** on Render.
2. Connect your GitHub repository.
3. Select **Docker** as the Runtime.
4. Set the **Dockerfile Path** to `./Dockerfile`.
5. Under **Environment Variables**, add:
   - `DATATRACE_USERNAME` = `your_username`
   - `DATATRACE_PASSWORD` = `your_password`
   - `DATATRACE_HEADLESS` = `true`
   - `GOOGLE_SERVICE_ACCOUNT_JSON` = contents of your `service_account.json`
6. The included free-service blueprint recovers synced history from Google Sheets. Render persistent disks require a paid service; unsynced local previews are lost on ephemeral-host restarts. To preserve failed captures across restarts, use a persistent local backend or explicitly configure a paid service with a disk at `/app/gsheet_dashboard/previews`. See [Render persistent disk documentation](https://render.com/docs/disks).

---

## 📄 License & Notes

DataTrace Workspace is designed as a local web application running on Windows endpoints. No external AI inference or third-party cloud analytics tools are used at runtime.

## Render Chromium launch errors

If extraction reports `Failed to launch the browser process: Code: 1`, inspect
the Render logs for Chromium's underlying error. The Docker image uses Node 22,
system Chromium at `/usr/bin/chromium`, and these runtime settings:

```text
DATATRACE_HEADLESS=true
PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium
DATATRACE_CHROME_NO_SANDBOX=true
```

The no-sandbox setting is limited to Linux containers that explicitly enable it;
local desktop runs keep their normal sandbox. Disabling Chromium's sandbox reduces
browser isolation, so use this container only with the intended trusted portal.
Linux launches also use disk-backed temporary storage instead of small `/dev/shm`.

After pushing the updated Dockerfile and scraper support files, rebuild and deploy
the service in Render. The image build runs `node gsheet_dashboard/check_browser.cjs`
without portal credentials and must print `Chromium check passed`. The same command
can diagnose browser startup in a running container. The Docker build excludes local
credentials, dependencies, and previews; provide credentials through Render secrets.

## Folder and File Review

Checked against the current project on September 25, 2026. No files were deleted
during this review. Regenerable files may still be needed while the app is running.

### Keep for the application

| Folder or file | Purpose and recommendation |
| --- | --- |
| `gsheet_dashboard/` | Main application. Keep. |
| `server.py`, `app.py`, `datatrace_sync.py`, `preview_store.py`, `scrape_datatrace.js` inside `gsheet_dashboard/` | Backend, compatibility entry point, sync, preview storage, and extraction code. Keep. |
| `gsheet_dashboard/sync_config.py`, `sync_config.json`, `.env` | App configuration. Keep. |
| `gsheet_dashboard/service_account.json` | Default live Google Sheets credential. Keep securely unless deliberately using an override. |
| `gsheet_dashboard/requirements.txt`, both `package.json` and `package-lock.json` files | Dependency installation/version information. Keep. |
| `gsheet_dashboard/run.bat` | Windows launcher. Keep. |
| `gsheet_dashboard/frontend/src/`, `index.html`, `vite.config.js` | React source and build configuration. Keep for maintenance and rebuilding. |
| `gsheet_dashboard/frontend/dist/` | Built dashboard served by Python. Required to run the React app; can be regenerated with the frontend build command. |
| `.venv/` | Python dependencies used by the launcher. Keep for everyday use; recreatable through setup. |
| `gsheet_dashboard/node_modules/` | Extraction dependencies. Keep for extraction; recreate with `npm.cmd --prefix gsheet_dashboard install`. |
| `gsheet_dashboard/frontend/node_modules/` | Needed for frontend builds, development, and tests; recreate with `npm.cmd --prefix gsheet_dashboard/frontend install`. |
| `.git/`, `.gitignore` | Version history and exclusions. Keep for project development even though the app does not need Git to run. |

### Preserve your data

| Folder or file | Purpose and recommendation |
| --- | --- |
| `gsheet_dashboard/previews/` | Saved data: `previews.sqlite` plus numbered CSV/XLSX exports. Keep and back up together. Deleting this folder loses history; use the dashboard to delete individual previews. |
| `gsheet_dashboard/queue_data_sheet2.csv`, `queue_data_sheet2.xlsx` | Latest exports used by Streamlit and potentially Power BI. Keep if reports depend on them. Future extraction can regenerate them, but not restore their previous contents. |
| `gsheet_dashboard/sync_schedule.json` (when created) | Daily schedule settings. Keep if scheduling is configured. |
| `gsheet_dashboard/sync_status.json` | Last extraction status, not the saved-preview database. Generated again by extraction. |

### Optional or cleanup candidates

| Folder or file | Required? |
| --- | --- |
| `__pycache__/`, `*.pyc`, `.pytest_cache/` if present | Regenerable Python caches. Safe to remove while the app is stopped. |
| `gsheet_dashboard/frontend/test-results/`, `playwright-report/` if present | Generated test screenshots/reports. Safe to remove when no tests are running. |
| `dashboard-status.*.log`, `dashboard-8510.*.log`, `dashboard-8511.*.log` | Temporary troubleshooting logs. Already absent at this review. If recreated, remove after the writing process has stopped. |
| `docs/`, `PROJECT_ARCHITECTURE.md`, `project-architecture-streamlit-text-links.png` | Documentation and diagrams, optional at runtime. Keep for reference; deleting `docs/` breaks architecture diagram links. |
| `.streamlit/`, `gsheet_dashboard/.streamlit/` | Optional Streamlit theme/server settings. Not used by the React app; keep if using Streamlit. |
| `gsheet_dashboard/streamlit_app.py` | Optional analytics interface, separate from the React dashboard. |
| `gsheet_dashboard/scratch/` | Standalone sheet-inspection scripts, not imported by the application. Optional troubleshooting tools. |
| `gsheet_dashboard/update_row_colors.py` | Optional maintenance utility. Normal sync already colors rows. Running this utility without `--verify-only` writes formatting to the live sheet. |
| `gsheet_dashboard/test_*.py`, `test_scraper.cjs`, `frontend/tests/`, `frontend/playwright.config.js` | Development tests. Keep for regression checks; unlike test reports, these are source files. |
| Root `service_account.json.json` | Not the default credential used by the app. Check environment overrides or external use before removing it; treat it as a private credential/backup, not cache. |

For simple cleanup, remove only caches and old test results/logs. Keep the main app,
dependencies, built frontend, previews, and credentials unless deliberately rebuilding
or retiring the corresponding feature.

### Test environment notes

Playwright's default base URL is port 8510. The status-rule test explicitly uses
port 8520 by default (override with `DASHBOARD_TEST_URL`) and needs a dashboard there. The workspace suite's empty-state test expects
no saved previews, so the full suite is not suitable unchanged for a populated live
workspace. Status-rule tests mock API writes and do not update the live sheet.
