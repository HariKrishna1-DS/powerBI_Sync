# ⚡ Google Sheets Live-Sync Streamlit Dashboard

A production-ready, custom Python Streamlit dashboard that connects to any Google Sheet link and automatically syncs data and visualizations in real-time.

---

## 🚀 Quick Start (Windows)

### Option 1: One-Click Launcher
Double-click `run.bat` inside the `gsheet_dashboard/` directory.  
It will automatically verify your environment, install dependencies, and open the dashboard in your web browser.

### Option 2: Command Line Launcher
From the repository root:
```powershell
# 1. Activate your virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Run the Streamlit application
streamlit run gsheet_dashboard\app.py
```

---

## 📋 How to Share Your Google Sheet

To let the dashboard read data from your Google Sheet in real time:

1. Open your Google Sheet in your web browser.
2. Click the **Share** button in the top-right corner.
3. Under **General access**, change the dropdown from **Restricted** to **Anyone with the link**.
4. Set the role to **Viewer**.
5. Click **Copy link**.
6. In the Streamlit dashboard sidebar:
   - Paste the link into the **Google Sheet Share Link** box.
   - The dashboard instantly parses the Sheet ID and tab `gid`, fetches the CSV stream, and builds your KPIs and charts!

---

## ✨ Features

- **Real-Time Live-Syncing**: Select auto-refresh frequency (5s, 10s, 30s, 60s, or Manual) powered by `@st.fragment(run_every=...)` to pull edits without flickering the whole application.
- **Connection Telemetry Bar**: Shows live status badge, last sync timestamp, total records count, and incremental changes (`+N` rows added).
- **Dynamic KPI Cards**: Automatic calculation of sum, average, min, and max for all detected numeric columns.
- **Interactive Visualization Studio**:
  - 📊 **Bar Charts**: Group and aggregate categorical dimensions by sums or averages.
  - 📈 **Trend / Line Charts**: Sequence or time-series tracking with multi-series coloring.
  - 🍩 **Proportion Donut Charts**: Relative market share and category breakdowns.
  - 📉 **Distribution Histograms**: Binned frequency distributions with marginal boxplots.
  - ⚡ **Scatter Plots**: Multi-variable correlation analysis.
  - 🛠️ **Custom Chart Studio**: Build your own visualizations choosing any axes and color parameters.
- **Smart Filtering & Search**: Global search across all fields and multi-select category slicers.
- **Data Export**: One-click download of the active filtered dataset as CSV.
- **One-Click Demo Datasets**: Included sample sales and metrics sheets for instant demonstration.

---

## 🛠️ Project Structure

```
powerBI_Sync/
├── .venv/                   # Python Virtual Environment
└── gsheet_dashboard/
    ├── app.py              # Main Streamlit dashboard
    ├── requirements.txt    # Python dependencies
    ├── run.bat             # 1-click Windows launcher
    └── README.md           # Documentation & instructions
```
