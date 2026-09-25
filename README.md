# DataTrace Workspace & PowerBI Sync

DataTrace Workspace is a local web application and automation suite designed for extracting title queue data from TitleVision, generating structured previews, synchronizing data with Google Sheets, and providing exports for Power BI reporting.

## 🚀 Overview

- **TitleVision Queue Extraction**: Automated headless/headed browser scraping using Node.js & Puppeteer.
- **Local Preview Store**: Immutable SQLite & Excel/CSV preview history tracking all extraction runs and user imports.
- **Google Sheets Synchronization**: Sync the configured primary tab (currently Sheet1), All Products, Full Title, Remaining Products, and Status Report using Google Sheets API (`gspread`).
- **Power BI Integration**: Direct consumption of structured Excel tables (`DataTraceQueue`, `DataTraceChanges`) for reporting and dashboards.
- **Streamlit & React Web Applications**:
  - React/Vite local workspace UI (`http://localhost:8510`)
  - Streamlit analytics dashboard (`http://localhost:8501`)

---

## 🛠️ Architecture & Tech Stack

| Layer | Component / Tool | Responsibility |
| --- | --- | --- |
| **Frontend UI** | React + Vite + Lucide + Recharts | Fast interactive dashboard for filtering, visual breakdowns, preview comparison, & manual sync triggers |
| **Analytics UI** | Streamlit + Plotly | Interactive analytics dashboard with KPI cards and visualizations |
| **Backend API** | Python (Flask, Waitress) | Local application service for extraction management, previews, diffing, and sync scheduling |
| **Automation** | Node.js + Puppeteer | Headless browser engine for TitleVision portal login, pagination, and queue extraction |
| **Data Storage** | SQLite, openpyxl, pandas | Numbered snapshot storage, CSV/XLSX file generation, and diff tracking |
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
- Extraction saves previews locally; it does not automatically upload them.
- Manual sync updates the configured primary tab, **All Products**, **Full Title**, **Remaining Products**, and **Status Report**.
- Select an original **Status_1** and replacement **Status_2**, then click **+** for each rule. **Sync Filters** and **Sync preview to Sheets** upload the selected preview with those replacements.
- Status colors extend across complete data rows, and Google Sheets column filters are enabled. Status values are read back before success is reported.
- Rules are saved per preview in browser local storage. Different browsers or ports do not share them. Original saved previews remain unchanged.
- Search and dropdown slicers filter the displayed data; they do not restrict which rows are uploaded.
- Optional daily automated local trigger to push the latest preview snapshot.
- The scheduler runs only while the backend is running and uploads the original preview; it does not receive browser-local status replacement rules.
- All five overview metrics share one line, with horizontal scrolling on narrow screens.

### 📈 Diff & Comparison Engine
- Compare any two snapshot previews for added, removed, or modified task records.
- Custom key matching rules and field-level change exports (`DataTraceChanges` table for Power BI).

### 📈 Power BI Integration
- Direct Excel import via table `DataTraceQueue` (`queue_data_sheet2.xlsx`).
- Pre-configured field types (Date, Text identifiers, Booleans, SLA Status, Queue Age Hours).

---

## 🧪 Running Tests

```powershell
# Python unit tests
.\.venv\Scripts\python.exe -m unittest discover -s gsheet_dashboard -p "test_*.py" -v

# Frontend build & Playwright E2E tests
cd gsheet_dashboard\frontend
npm.cmd run build
npx.cmd playwright test
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
6. *(Optional)* Add a **Persistent Disk** mounted at `/app/gsheet_dashboard/previews` so your saved data previews persist across app restarts.

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
port 8511 and needs a dashboard there. The workspace suite's empty-state test expects
no saved previews, so the full suite is not suitable unchanged for a populated live
workspace. Status-rule tests mock API writes and do not update the live sheet.
