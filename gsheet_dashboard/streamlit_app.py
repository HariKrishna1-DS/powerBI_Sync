"""Streamlit DataTrace Dashboard: Analytics for Online/Ground, Client, and Product breakdown."""
import io
import json
from pathlib import Path
from preview_store import PreviewStore

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
PREVIEWS_DIR = BASE_DIR / 'previews'

# Page Configuration
st.set_page_config(
    page_title="DataTrace Streamlit Dashboard",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Theme State Management
if "theme" not in st.session_state:
    st.session_state.theme = "light"

def toggle_theme():
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"

IS_DARK = st.session_state.theme == "dark"

# Dynamic CSS Theme Variables
BG_COLOR = "#0f172a" if IS_DARK else "#f8fafc"
CARD_BG = "#1e293b" if IS_DARK else "#ffffff"
TEXT_COLOR = "#f8fafc" if IS_DARK else "#0f172a"
MUTED_TEXT = "#94a3b8" if IS_DARK else "#64748b"
BORDER_COLOR = "#334155" if IS_DARK else "#e2e8f0"
ACCENT_TEAL = "#147d72"
ACCENT_AMBER = "#d97706"
ACCENT_BLUE = "#2563eb"
ACCENT_PURPLE = "#7c3aed"

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], .main {{
        background-color: {BG_COLOR} !important;
        color: {TEXT_COLOR} !important;
        font-family: 'DM Sans', sans-serif !important;
    }}
    
    [data-testid="stHeader"], footer, #MainMenu {{
        display: none !important;
    }}
    
    .block-container {{
        padding: 1.5rem 2rem 3rem !important;
        max-width: 1400px !important;
    }}
    
    .metric-card {{
        background: {CARD_BG};
        border: 1px solid {BORDER_COLOR};
        border-radius: 10px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        transition: transform 0.15s ease;
    }}
    .metric-card:hover {{
        transform: translateY(-2px);
    }}
    .metric-label {{
        font-size: 0.78rem;
        color: {MUTED_TEXT};
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    .metric-value {{
        font-size: 1.85rem;
        font-weight: 700;
        color: {TEXT_COLOR};
        margin-top: 0.25rem;
        letter-spacing: -0.03em;
    }}
    .metric-sub {{
        font-size: 0.75rem;
        color: {MUTED_TEXT};
        margin-top: 0.3rem;
    }}
    
    .chart-card {{
        background: {CARD_BG};
        border: 1px solid {BORDER_COLOR};
        border-radius: 10px;
        padding: 1.25rem 1.4rem 0.8rem;
        margin-bottom: 1.2rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .chart-title {{
        font-size: 0.95rem;
        font-weight: 700;
        color: {TEXT_COLOR};
        margin-bottom: 0.2rem;
    }}
    .chart-desc {{
        font-size: 0.76rem;
        color: {MUTED_TEXT};
        margin-bottom: 0.8rem;
    }}
    
    .badge {{
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.72rem;
        font-weight: 600;
    }}
    .badge-online {{ background: rgba(20, 125, 114, 0.15); color: #0d5c54; }}
    .badge-ground {{ background: rgba(217, 119, 6, 0.15); color: #9a5406; }}
    
    button[data-baseweb="tab"] {{
        background: transparent !important;
        color: {MUTED_TEXT} !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        padding: 0.6rem 1.2rem !important;
        border-radius: 8px !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {TEXT_COLOR} !important;
        background: {CARD_BG} !important;
        border: 1px solid {BORDER_COLOR} !important;
    }}
    [data-baseweb="tab-highlight"], [data-baseweb="tab-border"] {{
        display: none !important;
    }}
    [data-baseweb="tab-list"] {{
        gap: 6px !important;
        background: rgba(0,0,0,0.03) !important;
        border: 1px solid {BORDER_COLOR} !important;
        border-radius: 10px !important;
        padding: 4px;
        margin-bottom: 1.5rem;
    }}
</style>
""", unsafe_allow_html=True)


# Data Loading Functions
@st.cache_data(ttl=60)
def load_available_sources():
    return {'Google Sheets production trackers': ('sheets', None)}


def load_preview_data(source_type, source_val):
    from datatrace_sync import target_worksheet
    from tracker_sync import read_trackers
    try:
        book, _ = target_worksheet()
        df = pd.DataFrame([row for rows in read_trackers(book).values() for row in rows]).fillna('')
    except Exception as exc:
        st.error(f'Google Sheet unavailable: {exc}')
        st.stop()
    
    if not df.empty:
        df.columns = [str(c).strip() for c in df.columns]
        # Standardize column names if needed
        col_map = {
            'Online/Ground': 'Online/ Ground',
            'Online/ Gorund': 'Online/ Ground',
            'Order number': 'Order Number',
            'ClientCode': 'Client',
            'Status': 'Task Status'
        }
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
    return df


# Header Component
col_title, col_theme = st.columns([8, 2])
with col_title:
    st.markdown("""
    <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 0.5rem;">
        <div style="background: #147d72; color: white; border-radius: 8px; width: 40px; height: 40px; display: grid; place-items: center; font-weight: 700; font-size: 1.2rem;">⚡</div>
        <div>
            <h1 style="margin:0; font-size: 1.7rem; font-weight: 700;">DataTrace Analytics Dashboard</h1>
            <p style="margin:0; font-size: 0.82rem; color: #64748b;">Interactive breakdown for <b>Online/Ground</b>, <b>Client</b>, and <b>Product</b> columns</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_theme:
    st.button("☀️ Light Mode" if IS_DARK else "🌙 Dark Mode", on_click=toggle_theme, use_container_width=True)

st.markdown("<hr style='margin: 1rem 0 1.5rem; border: none; border-top: 1px solid #e2e8f0;'>", unsafe_allow_html=True)

# Data Source Selection & Sidebar Filters
sources = load_available_sources()
if not sources:
    st.error("No DataTrace queue data found. Please run an extraction or place `queue_data_sheet2.csv` in `gsheet_dashboard`.")
    st.stop()

with st.sidebar:
    st.markdown("### ⚙️ Data Controls")
    selected_source_name = st.selectbox("Data source", list(sources.keys()))
    st.markdown("---")
    st.markdown("### 🔍 Filters")

source_type, source_val = sources[selected_source_name]
df_raw = load_preview_data(source_type, source_val)

if df_raw.empty:
    st.warning("Selected preview contains no data rows.")
    st.stop()

# Validate Required Columns
required_cols = ['Online/ Ground', 'Client', 'Product']
missing_cols = [c for c in required_cols if c not in df_raw.columns]
if missing_cols:
    st.error(f"Missing required columns in dataset: {', '.join(missing_cols)}")
    st.stop()

# Sidebar Multi-select Filters
with st.sidebar:
    # Online/Ground filter
    og_options = sorted(df_raw['Online/ Ground'].dropna().astype(str).unique())
    selected_og = st.multiselect("Online / Ground", og_options, default=og_options)
    
    # Client filter
    client_options = sorted(df_raw['Client'].dropna().astype(str).unique())
    selected_clients = st.multiselect("Client", client_options, default=client_options)
    
    # Product filter
    product_options = sorted(df_raw['Product'].dropna().astype(str).unique())
    selected_products = st.multiselect("Product", product_options, default=product_options)
    
    search_query = st.text_input("Global Search", placeholder="Search Order, Borrower, State...")
    
    if st.button("Reset Filters", use_container_width=True):
        st.rerun()

# Apply Filters
df = df_raw.copy()
df['Online/ Ground'] = df['Online/ Ground'].astype(str).str.strip()
df['Client'] = df['Client'].astype(str).str.strip()
df['Product'] = df['Product'].astype(str).str.strip()

if selected_og:
    df = df[df['Online/ Ground'].isin(selected_og)]
if selected_clients:
    df = df[df['Client'].isin(selected_clients)]
if selected_products:
    df = df[df['Product'].isin(selected_products)]
if search_query:
    query_lower = search_query.lower()
    mask = df.apply(lambda row: row.astype(str).str.lower().str.contains(query_lower).any(), axis=1)
    df = df[mask]

# Summary KPI Cards Row
k1, k2, k3, k4, k5 = st.columns(5)

total_orders = len(df)
online_count = len(df[df['Online/ Ground'].str.lower() == 'online'])
ground_count = len(df[df['Online/ Ground'].str.lower() == 'ground'])
unique_clients = df['Client'].nunique()
full_title_count = len(df[df['Product'].str.lower() == 'full title'])

with k1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Total Queue Orders</div>
        <div class="metric-value">{total_orders:,}</div>
        <div class="metric-sub">Active tasks in snapshot</div>
    </div>
    """, unsafe_allow_html=True)

with k2:
    online_pct = (online_count / total_orders * 100) if total_orders else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Online Queue</div>
        <div class="metric-value" style="color: #147d72;">{online_count:,}</div>
        <div class="metric-sub"><b>{online_pct:.1f}%</b> of total queue</div>
    </div>
    """, unsafe_allow_html=True)

with k3:
    ground_pct = (ground_count / total_orders * 100) if total_orders else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Ground Queue</div>
        <div class="metric-value" style="color: #d97706;">{ground_count:,}</div>
        <div class="metric-sub"><b>{ground_pct:.1f}%</b> of total queue</div>
    </div>
    """, unsafe_allow_html=True)

with k4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Active Clients</div>
        <div class="metric-value" style="color: #2563eb;">{unique_clients}</div>
        <div class="metric-sub">Top client: <b>{df['Client'].mode()[0] if not df.empty else 'N/A'}</b></div>
    </div>
    """, unsafe_allow_html=True)

with k5:
    full_title_pct = (full_title_count / total_orders * 100) if total_orders else 0
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Full Title Products</div>
        <div class="metric-value" style="color: #7c3aed;">{full_title_count:,}</div>
        <div class="metric-sub"><b>{full_title_pct:.1f}%</b> Full Title share</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Main Navigation Tabs
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Column Analytics Overview",
    "🏢 Client Breakdown & Products",
    "📈 Arrival Date Trends",
    "📋 Raw Data & Export"
])

# Shared Plotly Layout Template
PLOT_CONFIG = {"displayModeBar": False}
plotly_template = "plotly_dark" if IS_DARK else "plotly_white"

with tab1:
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.markdown("""
        <div class="chart-card">
            <div class="chart-title">Online vs Ground Share</div>
            <div class="chart-subtitle">Proportion of queue tasks extracted by delivery method</div>
        """, unsafe_allow_html=True)
        
        og_summary = df['Online/ Ground'].value_counts().reset_index()
        og_summary.columns = ['Online/ Ground', 'Orders']
        fig_og = px.pie(
            og_summary,
            names='Online/ Ground',
            values='Orders',
            hole=0.55,
            color='Online/ Ground',
            color_discrete_map={'Online': '#147d72', 'Ground': '#d97706'},
            template=plotly_template
        )
        fig_og.update_traces(textinfo='percent+label', marker=dict(line=dict(color=CARD_BG, width=2)))
        fig_og.update_layout(showlegend=True, margin=dict(l=10, r=10, t=10, b=10), height=320)
        st.plotly_chart(fig_og, use_container_width=True, config=PLOT_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_b:
        st.markdown("""
        <div class="chart-card">
            <div class="chart-title">Product Distribution</div>
            <div class="chart-subtitle">Order volume grouped by DataTrace product type</div>
        """, unsafe_allow_html=True)
        
        prod_summary = df['Product'].value_counts().reset_index()
        prod_summary.columns = ['Product', 'Orders']
        fig_prod = px.bar(
            prod_summary,
            x='Orders',
            y='Product',
            orientation='h',
            text='Orders',
            color='Orders',
            color_continuous_scale=['#94a3b8', '#147d72'],
            template=plotly_template
        )
        fig_prod.update_traces(texttemplate='%{text}', textposition='outside')
        fig_prod.update_layout(
            yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
            margin=dict(l=10, r=30, t=10, b=10),
            height=320
        )
        st.plotly_chart(fig_prod, use_container_width=True, config=PLOT_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Client Breakdown Chart
    st.markdown("""
    <div class="chart-card">
        <div class="chart-title">Top Clients by Queue Volume</div>
        <div class="chart-subtitle">Breakdown of orders per client code</div>
    """, unsafe_allow_html=True)
    
    client_summary = df['Client'].value_counts().head(12).reset_index()
    client_summary.columns = ['Client', 'Orders']
    fig_client = px.bar(
        client_summary,
        x='Client',
        y='Orders',
        text='Orders',
        color='Orders',
        color_continuous_scale=['#2563eb', '#147d72'],
        template=plotly_template
    )
    fig_client.update_traces(texttemplate='%{text}', textposition='outside')
    fig_client.update_layout(coloraxis_showscale=False, margin=dict(l=10, r=10, t=20, b=10), height=340)
    st.plotly_chart(fig_client, use_container_width=True, config=PLOT_CONFIG)
    st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    st.markdown("""
    <div class="chart-card">
        <div class="chart-title">Client vs Online/Ground Cross-Analysis</div>
        <div class="chart-subtitle">Distribution of Online and Ground orders across top clients</div>
    """, unsafe_allow_html=True)
    
    client_og = df.groupby(['Client', 'Online/ Ground']).size().reset_index(name='Orders')
    top_10_clients = df['Client'].value_counts().head(10).index
    client_og_filtered = client_og[client_og['Client'].isin(top_10_clients)]
    
    fig_cross = px.bar(
        client_og_filtered,
        x='Client',
        y='Orders',
        color='Online/ Ground',
        barmode='group',
        color_discrete_map={'Online': '#147d72', 'Ground': '#d97706'},
        template=plotly_template
    )
    fig_cross.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=350)
    st.plotly_chart(fig_cross, use_container_width=True, config=PLOT_CONFIG)
    st.markdown("</div>", unsafe_allow_html=True)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        st.markdown("""
        <div class="chart-card">
            <div class="chart-title">Product Split: Full Title vs Remaining</div>
            <div class="chart-subtitle">Standardized Product classification share</div>
        """, unsafe_allow_html=True)
        
        full_t = len(df[df['Product'].str.lower() == 'full title'])
        rem_t = len(df[df['Product'].str.lower() != 'full title'])
        split_df = pd.DataFrame([
            {'Category': 'Full Title', 'Count': full_t},
            {'Category': 'Remaining Products', 'Count': rem_t}
        ])
        fig_split = px.pie(
            split_df,
            names='Category',
            values='Count',
            hole=0.5,
            color='Category',
            color_discrete_map={'Full Title': '#7c3aed', 'Remaining Products': '#2563eb'},
            template=plotly_template
        )
        fig_split.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=300)
        st.plotly_chart(fig_split, use_container_width=True, config=PLOT_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_c2:
        st.markdown("""
        <div class="chart-card">
            <div class="chart-title">Online / Ground per Product</div>
            <div class="chart-subtitle">How product categories map to delivery channels</div>
        """, unsafe_allow_html=True)
        
        prod_og = df.groupby(['Product', 'Online/ Ground']).size().reset_index(name='Orders')
        fig_pog = px.bar(
            prod_og,
            x='Orders',
            y='Product',
            color='Online/ Ground',
            orientation='h',
            color_discrete_map={'Online': '#147d72', 'Ground': '#d97706'},
            template=plotly_template
        )
        fig_pog.update_layout(yaxis=dict(autorange="reversed"), margin=dict(l=10, r=10, t=10, b=10), height=300)
        st.plotly_chart(fig_pog, use_container_width=True, config=PLOT_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)

with tab3:
    date_col = next((c for c in ['Arrival Date', 'Arrival Time', 'Date', 'In-Time', 'Received Date'] if c in df.columns), None)
    if date_col:
        st.markdown(f"""
        <div class="chart-card">
            <div class="chart-title">Order Arrival Trend ({date_col})</div>
            <div class="chart-subtitle">Daily order arrival volume over time</div>
        """, unsafe_allow_html=True)
        
        df_date = df.copy()
        df_date['Parsed_Date'] = pd.to_datetime(df_date[date_col], errors='coerce').dt.date
        trend_data = df_date.dropna(subset=['Parsed_Date']).groupby('Parsed_Date').size().reset_index(name='Orders')
        trend_data.sort_values('Parsed_Date', inplace=True)
        
        fig_trend = px.area(
            trend_data,
            x='Parsed_Date',
            y='Orders',
            markers=True,
            color_discrete_sequence=['#147d72'],
            template=plotly_template
        )
        fig_trend.update_layout(
            xaxis_title="Arrival Date",
            yaxis_title="Order Volume",
            margin=dict(l=10, r=10, t=20, b=10),
            height=360
        )
        st.plotly_chart(fig_trend, use_container_width=True, config=PLOT_CONFIG)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("No Arrival Date / Time column found in the current dataset.")

with tab4:
    st.markdown(f"### Filtered Queue Data ({len(df):,} rows)")
    
    # Display Columns Selector
    display_cols = st.multiselect(
        "Columns to display",
        list(df.columns),
        default=[c for c in ['Order Number', 'Borrower', 'Online/ Ground', 'Client', 'Product', 'Task Status', 'St', 'County', 'Arrival Time'] if c in df.columns]
    )
    
    st.dataframe(df[display_cols] if display_cols else df, use_container_width=True, height=450)
    
    # Export Options
    col_e1, col_e2 = st.columns([2, 8])
    with col_e1:
        csv_buffer = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Download Filtered CSV",
            data=csv_buffer,
            file_name=f"datatrace_filtered_{selected_source_name.split()[0]}.csv",
            mime="text/csv",
            use_container_width=True
        )
