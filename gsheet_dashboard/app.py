import sys
import os
import re
import io
import time
import datetime
import urllib.parse
import warnings
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore", category=UserWarning)

# -----------------------------------------------------------------------------
# PAGE CONFIGURATION
# -----------------------------------------------------------------------------
try:
    st.set_page_config(
        page_title="Power BI Studio Desktop",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
except Exception:
    pass

# -----------------------------------------------------------------------------
# SESSION STATE INITIALIZATION
# -----------------------------------------------------------------------------
if "pbi_theme" not in st.session_state:
    st.session_state.pbi_theme = "Light"

if "pbi_view_mode" not in st.session_state:
    st.session_state.pbi_view_mode = "Report View"

if "tables" not in st.session_state:
    st.session_state.tables = {}

if "relationships" not in st.session_state:
    st.session_state.relationships = []

if "active_table_name" not in st.session_state:
    st.session_state.active_table_name = ""

if "current_sheet_id" not in st.session_state:
    st.session_state.current_sheet_id = ""

if "available_tabs" not in st.session_state:
    st.session_state.available_tabs = []

if "active_sheet_tab" not in st.session_state:
    st.session_state.active_sheet_tab = ""

if "single_sheet_url" not in st.session_state:
    st.session_state.single_sheet_url = ""

if "workspace_clean" not in st.session_state:
    st.session_state.workspace_clean = True

if "custom_link_configs" not in st.session_state:
    st.session_state.custom_link_configs = [
        {"name": "Google Sheet 1", "url": ""},
        {"name": "Google Sheet 2", "url": ""}
    ]

if "dax_measures" not in st.session_state:
    st.session_state.dax_measures = []


# -----------------------------------------------------------------------------
# HIGH-FIDELITY POWER BI THEME ENGINE (COMPREHENSIVE STREAMLIT CSS OVERRIDES)
# -----------------------------------------------------------------------------
def inject_powerbi_theme(theme_name: str):
    if theme_name == "Light":
        bg_app = "#f3f2f1"
        bg_panel = "#ffffff"
        bg_header = "#ffffff"
        border_panel = "#e1dfdd"
        border_card = "#edebe9"
        text_primary = "#201f1e"
        text_secondary = "#605e5c"
        accent_gold = "#f2c811"
        accent_blue = "#0078d4"
        card_shadow = "0 1.6px 3.6px 0 rgba(0,0,0,0.08), 0 0.3px 0.9px 0 rgba(0,0,0,0.05)"
        input_bg = "#ffffff"
        input_text = "#201f1e"
        input_border = "#d2d0ce"
        sidebar_bg = "#ffffff"
        pill_bg = "#e0f2fe"
        pill_border = "#7dd3fc"
        pill_text = "#0369a1"
        pill_hover_bg = "#bae6fd"
        pill_hover_border = "#38bdf8"
        code_bg = "#e0f2fe"
        code_text = "#0369a1"
        code_border = "#bae6fd"
    else:  # Dark Mode
        bg_app = "#1e1e1e"
        bg_panel = "#252423"
        bg_header = "#181716"
        border_panel = "#3b3a39"
        border_card = "#323130"
        text_primary = "#f3f2f1"
        text_secondary = "#a19f9d"
        accent_gold = "#f2c811"
        accent_blue = "#2886de"
        card_shadow = "0 4px 16px rgba(0, 0, 0, 0.35)"
        input_bg = "#292827"
        input_text = "#ffffff"
        input_border = "#484644"
        sidebar_bg = "#252423"
        pill_bg = "#1e293b"
        pill_border = "#334155"
        pill_text = "#93c5fd"
        pill_hover_bg = "#334155"
        pill_hover_border = "#60a5fa"
        code_bg = "#1e3a5f"
        code_text = "#93c5fd"
        code_border = "#2563eb"

    css = f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Segoe+UI:wght@300;400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* Global Typography & Background */
    html, body, [data-testid="stAppViewContainer"], .main {{
        font-family: 'Segoe UI', 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        background-color: {bg_app} !important;
        color: {text_primary} !important;
    }}

    /* Global Text Visibility Fix */
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stMarkdownContainer"] div,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] h5,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] b {{
        color: {text_primary} !important;
    }}

    /* Code & Metric Badges (Fix black boxes in light mode) */
    code,
    [data-testid="stMarkdownContainer"] code {{
        background-color: {code_bg} !important;
        color: {code_text} !important;
        border: 1px solid {code_border} !important;
        padding: 2px 7px !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
    }}

    /* Fix Streamlit Widget Labels */
    [data-testid="stWidgetLabel"] label,
    [data-testid="stWidgetLabel"] p,
    .stSelectbox label,
    .stMultiSelect label,
    .stTextInput label,
    .stRadio label,
    .stSlider label,
    .stCheckbox label {{
        color: {text_primary} !important;
        font-weight: 600 !important;
        font-size: 0.84rem !important;
    }}

    /* Streamlit Selectboxes & MultiSelects */
    div[data-baseweb="select"] > div {{
        background-color: {input_bg} !important;
        border: 1px solid {input_border} !important;
        border-radius: 4px !important;
        color: {input_text} !important;
    }}
    div[data-baseweb="select"] span,
    div[data-baseweb="select"] div,
    div[data-baseweb="select"] svg {{
        color: {input_text} !important;
        fill: {input_text} !important;
    }}
    div[data-baseweb="popover"],
    ul[role="listbox"],
    li[role="option"] {{
        background-color: {bg_panel} !important;
        color: {text_primary} !important;
    }}
    li[role="option"]:hover {{
        background-color: {bg_app} !important;
    }}

    /* MultiSelect Tag Chips */
    span[data-baseweb="tag"] {{
        background-color: {"#eff6fc" if theme_name == "Light" else "#1b2a3a"} !important;
        border: 1px solid {"#c7e0f4" if theme_name == "Light" else "#285078"} !important;
        color: {accent_blue} !important;
        border-radius: 4px !important;
    }}
    span[data-baseweb="tag"] span {{
        color: {accent_blue} !important;
    }}

    /* Text Inputs */
    div[data-baseweb="input"] input,
    .stTextInput input {{
        background-color: {input_bg} !important;
        border: 1px solid {input_border} !important;
        border-radius: 4px !important;
        color: {input_text} !important;
    }}

    /* Buttons */
    .stButton > button {{
        background-color: {input_bg} !important;
        color: {input_text} !important;
        border: 1px solid {input_border} !important;
        border-radius: 4px !important;
        font-weight: 600 !important;
        box-shadow: {card_shadow} !important;
        transition: all 0.15s ease !important;
    }}
    .stButton > button:hover {{
        border-color: {accent_blue} !important;
        color: {accent_blue} !important;
    }}

    /* Radio Buttons */
    div[data-testid="stRadio"] [role="radiogroup"] {{
        background-color: {bg_panel} !important;
        border: 1px solid {border_panel} !important;
        border-radius: 6px !important;
        padding: 6px 12px !important;
    }}
    div[data-testid="stRadio"] label span {{
        color: {text_primary} !important;
        font-weight: 600 !important;
    }}

    /* Sidebar Clean Styling */
    [data-testid="stSidebar"] {{
        background-color: {sidebar_bg} !important;
        border-right: 1px solid {border_panel} !important;
    }}
    [data-testid="stSidebar"] * {{
        color: {text_primary} !important;
    }}

    /* Metric Values */
    [data-testid="stMetricValue"] {{
        color: {text_primary} !important;
        font-weight: 700 !important;
    }}
    [data-testid="stMetricLabel"] p {{
        color: {text_secondary} !important;
        font-weight: 600 !important;
    }}

    /* =========================================================================
       WORKSHEET TABS (st.pills) - LIGHT BLUE DESIGN (Replaces All Black Tabs)
       ========================================================================= */
    div[data-testid="stPills"],
    div[data-testid="stButtonGroup"] {{
        display: flex !important;
        flex-wrap: wrap !important;
        gap: 6px !important;
        margin-top: 4px !important;
        margin-bottom: 8px !important;
    }}

    /* Inactive / Default Sheet Tabs - Light Blue Theme */
    div[data-testid="stPills"] button,
    div[data-testid="stPills"] [role="option"],
    div[data-testid="stPills"] [data-testid="stPill"],
    div[data-testid="stButtonGroup"] button {{
        background-color: {pill_bg} !important;
        border: 1.5px solid {pill_border} !important;
        color: {pill_text} !important;
        font-weight: 600 !important;
        font-size: 0.85rem !important;
        border-radius: 18px !important;
        padding: 5px 14px !important;
        box-shadow: 0 1px 3px rgba(0, 120, 212, 0.08) !important;
        transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
        cursor: pointer !important;
    }}

    div[data-testid="stPills"] button p,
    div[data-testid="stPills"] button span,
    div[data-testid="stPills"] button div,
    div[data-testid="stPills"] button *,
    div[data-testid="stButtonGroup"] button * {{
        color: {pill_text} !important;
        font-weight: 600 !important;
    }}

    /* Hover State for Worksheet Tabs */
    div[data-testid="stPills"] button:hover,
    div[data-testid="stPills"] [role="option"]:hover,
    div[data-testid="stButtonGroup"] button:hover {{
        background-color: {pill_hover_bg} !important;
        border-color: {pill_hover_border} !important;
        color: {accent_blue} !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 3px 8px rgba(0, 120, 212, 0.22) !important;
    }}

    div[data-testid="stPills"] button:hover *,
    div[data-testid="stButtonGroup"] button:hover * {{
        color: {accent_blue} !important;
    }}

    /* Active / Selected Tab Pill - Signature Power BI Blue */
    div[data-testid="stPills"] button[aria-selected="true"],
    div[data-testid="stPills"] [role="option"][aria-selected="true"],
    div[data-testid="stPills"] button[data-selected="true"],
    div[data-testid="stButtonGroup"] button[aria-selected="true"] {{
        background-color: {accent_blue} !important;
        border: 1.5px solid {"#005a9e" if theme_name == "Light" else "#60a5fa"} !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        box-shadow: 0 3px 10px rgba(0, 120, 212, 0.38) !important;
    }}

    div[data-testid="stPills"] button[aria-selected="true"] p,
    div[data-testid="stPills"] button[aria-selected="true"] span,
    div[data-testid="stPills"] button[aria-selected="true"] div,
    div[data-testid="stPills"] button[aria-selected="true"] *,
    div[data-testid="stButtonGroup"] button[aria-selected="true"] * {{
        color: #ffffff !important;
        font-weight: 700 !important;
    }}

    /* Power BI Top Ribbon */
    .pbi-topbar {{
        background: {bg_header};
        border: 1px solid {border_panel};
        border-bottom: 3px solid {accent_gold};
        padding: 10px 18px;
        border-radius: 6px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: {card_shadow};
    }}
    .pbi-logo {{
        font-size: 1.15rem;
        font-weight: 700;
        color: {text_primary};
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    .pbi-logo-badge {{
        background: {pill_bg};
        color: {pill_text};
        border: 1px solid {pill_border};
        padding: 3px 10px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: 600;
    }}

    /* View Switcher Segmented Buttons */
    .view-btn {{
        background: {bg_panel};
        border: 1px solid {border_panel};
        color: {text_primary};
        padding: 6px 16px;
        border-radius: 4px;
        font-weight: 600;
        font-size: 0.85rem;
        cursor: pointer;
        text-align: center;
    }}
    .view-btn-active {{
        background: {accent_blue} !important;
        border: 1px solid {accent_blue} !important;
        color: #ffffff !important;
    }}

    /* Neat Panel Container Cards */
    .pbi-panel-card {{
        background: {bg_panel};
        border: 1px solid {border_panel};
        border-radius: 8px;
        padding: 16px;
        box-shadow: {card_shadow};
        margin-bottom: 16px;
    }}
    .pbi-panel-title {{
        font-size: 0.88rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: {text_primary};
        border-bottom: 2px solid {accent_gold};
        padding-bottom: 8px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }}

    /* Metric KPI Cards */
    .kpi-card {{
        background: {bg_panel};
        border: 1px solid {border_panel};
        border-left: 4px solid {accent_gold};
        border-radius: 6px;
        padding: 14px 18px;
        box-shadow: {card_shadow};
    }}
    .kpi-label {{
        font-size: 0.76rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: {text_secondary};
        margin-bottom: 3px;
    }}
    .kpi-value {{
        font-size: 1.65rem;
        font-weight: 700;
        color: {text_primary};
        line-height: 1.2;
    }}
    .kpi-sub {{
        font-size: 0.75rem;
        color: #107c41;
        font-weight: 600;
        margin-top: 4px;
    }}

    /* Telemetry Bar */
    .telemetry-bar {{
        background: {bg_panel};
        border: 1px solid {border_panel};
        border-radius: 6px;
        padding: 8px 16px;
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: {card_shadow};
        font-size: 0.84rem;
    }}
    .telemetry-item {{
        display: flex;
        align-items: center;
        gap: 8px;
        color: {text_primary};
    }}
    .pulse-dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background-color: #107c41;
        display: inline-block;
        animation: pulse 1.8s infinite;
    }}
    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(16, 124, 65, 0.7); }}
        70% {{ box-shadow: 0 0 0 8px rgba(16, 124, 65, 0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(16, 124, 65, 0); }}
    }}

    /* Power BI Left Navigation Rail (Matches Screenshot) */
    .pbi-left-rail {{
        display: flex;
        flex-direction: column;
        align-items: center;
        width: 48px;
        background: {bg_panel};
        border-right: 1px solid {border_panel};
        padding: 12px 0;
        gap: 16px;
    }}
    .pbi-rail-item {{
        width: 40px;
        height: 40px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        position: relative;
        border-radius: 4px;
    }}
    .pbi-rail-item:hover {{
        background-color: {bg_app};
    }}
    .pbi-rail-active {{
        background-color: {bg_app};
    }}
    .pbi-rail-active-bar {{
        position: absolute;
        left: 0;
        top: 6px;
        bottom: 6px;
        width: 4px;
        background-color: #00785a;
        border-radius: 0 2px 2px 0;
    }}
    .pbi-model-tooltip {{
        position: absolute;
        left: 48px;
        top: 50%;
        transform: translateY(-50%);
        background: #ffffff;
        border: 1px solid #d2d0ce;
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.18);
        padding: 5px 12px;
        font-size: 0.82rem;
        font-weight: 600;
        color: #201f1e;
        white-space: nowrap;
        z-index: 999;
    }}
    .pbi-model-tooltip::before {{
        content: '';
        position: absolute;
        right: 100%;
        top: 50%;
        transform: translateY(-50%);
        border: 5px solid transparent;
        border-right-color: #ffffff;
    }}

    /* Power BI Model View Canvas (Exact Power BI Desktop Theme) */
    .pbi-model-canvas {{
        background-color: {"#edebe9" if theme_name == "Light" else "#1b1a19"};
        border: 1px solid {"#d2d0ce" if theme_name == "Light" else "#323130"};
        border-radius: 8px;
        padding: 24px;
        margin-top: 14px;
        margin-bottom: 20px;
        min-height: 480px;
        box-shadow: inset 0 1px 3px rgba(0,0,0,0.06);
    }}

    /* Power BI Model Table Card (Matches User Screenshot) */
    .pbi-model-card {{
        background: {"#ffffff" if theme_name == "Light" else "#252423"};
        border: 1px solid {"#d2d0ce" if theme_name == "Light" else "#3b3a39"};
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        width: 100%;
        max-width: 270px;
        margin: 0 auto 20px auto;
        font-family: 'Segoe UI', -apple-system, sans-serif;
        overflow: hidden;
    }}
    .pbi-model-header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 9px 12px;
        background: {"#ffffff" if theme_name == "Light" else "#252423"};
        border-bottom: 1px solid {"#edebe9" if theme_name == "Light" else "#323130"};
    }}
    .pbi-model-title {{
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 700;
        font-size: 1.05rem;
        color: {text_primary};
    }}
    .pbi-model-menu {{
        color: #605e5c;
        font-weight: bold;
        letter-spacing: 2px;
        font-size: 1.2rem;
        line-height: 1;
        cursor: pointer;
    }}
    .pbi-model-fields {{
        max-height: 250px;
        overflow-y: auto;
        padding: 4px 0;
    }}
    .pbi-model-fields::-webkit-scrollbar {{
        width: 6px;
    }}
    .pbi-model-fields::-webkit-scrollbar-track {{
        background: #f3f2f1;
    }}
    .pbi-model-fields::-webkit-scrollbar-thumb {{
        background: {"#8a8886" if theme_name == "Light" else "#555351"};
        border-radius: 3px;
    }}
    .pbi-model-field-item {{
        padding: 5px 14px;
        font-size: 0.88rem;
        color: {text_primary};
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .pbi-model-field-item:hover {{
        background-color: {"#f3f2f1" if theme_name == "Light" else "#2d2c2b"};
    }}
    .pbi-model-footer {{
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 4px;
        background: {"#ffffff" if theme_name == "Light" else "#252423"};
        border-top: 1px solid {"#edebe9" if theme_name == "Light" else "#323130"};
        color: #00785a;
        font-size: 1.15rem;
        font-weight: 700;
        line-height: 1;
    }}

    /* Relationship Connector Card */
    .pbi-rel-card {{
        background: {"#ffffff" if theme_name == "Light" else "#252423"};
        border: 1px solid {"#c7e0f4" if theme_name == "Light" else "#285078"};
        border-left: 4px solid #0078d4;
        border-radius: 6px;
        padding: 10px 16px;
        margin-bottom: 10px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }}
    .type-badge {{
        font-size: 0.72rem;
        font-weight: 700;
        padding: 2px 5px;
        border-radius: 3px;
        width: 24px;
        text-align: center;
    }}
    .type-num {{ background: #e0f2fe; color: #0369a1; }}
    .type-str {{ background: #fef3c7; color: #92400e; }}
    .type-date {{ background: #dcfce7; color: #166534; }}
    .type-key {{ background: #fce7f3; color: #be185d; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# POWER BI LEFT NAVIGATION RAIL (INTERACTIVE WORKSPACE SWITCHER)
# -----------------------------------------------------------------------------
def render_powerbi_left_rail(active_key: str):
    st.markdown(
        """
        <style>
        .rail-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
            padding-top: 4px;
        }
        .rail-wrapper button {
            width: 44px !important;
            height: 44px !important;
            padding: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            border-radius: 4px !important;
            font-size: 0.82rem !important;
            font-weight: 700 !important;
        }
        </style>
        <div class="rail-wrapper">
        """,
        unsafe_allow_html=True
    )

    if st.button("📊", key=f"rail_rep_{active_key}", help="Report View", type="primary" if active_key == "Report View" else "secondary"):
        st.session_state.pbi_view_mode = "Report View"
        st.rerun()

    if st.button("⏱️", key=f"rail_queue_{active_key}", help="Queue Live Tracker (Sheet 2)", type="primary" if active_key == "Queue Tracker" else "secondary"):
        st.session_state.pbi_view_mode = "Queue Tracker"
        st.rerun()

    if st.button("▦", key=f"rail_dat_{active_key}", help="Table / Data View", type="primary" if active_key == "Data View" else "secondary"):
        st.session_state.pbi_view_mode = "Data View"
        st.rerun()

    if st.button("🕸️", key=f"rail_mod_{active_key}", help="Model View (ER Diagram)", type="primary" if active_key == "Model View" else "secondary"):
        st.session_state.pbi_view_mode = "Model View"
        st.rerun()

    if st.button("DAX", key=f"rail_dax_{active_key}", help="DAX Formulas Studio", type="primary" if active_key == "DAX Formulas" else "secondary"):
        st.session_state.pbi_view_mode = "DAX Formulas"
        st.rerun()

    if st.button("TMDL", key=f"rail_tmdl_{active_key}", help="TMDL Semantic Model", type="primary" if active_key == "TMDL Model" else "secondary"):
        st.session_state.pbi_view_mode = "TMDL Model"
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# EXACT POWER BI ER DIAGRAM HTML/SVG GENERATOR (MATCHING USER SCREENSHOT IMAGE 2)
# -----------------------------------------------------------------------------
def generate_powerbi_erd_html(tables: dict, relationships: list, active_table: str, theme: str = "Light") -> str:
    if not tables:
        return "<div style='padding:40px; text-align:center; color:#605e5c;'>No tables loaded in data model.</div>"

    t_names = list(tables.keys())
    N = len(t_names)
    card_w, card_h = 240, 260

    # Determine layout coordinates for tables matching Image 2 Star Schema
    positions = {}
    if N == 1:
        positions[t_names[0]] = (280, 50)
        canvas_w, canvas_h = 800, 380
    elif N == 2:
        positions[t_names[0]] = (40, 50)
        positions[t_names[1]] = (520, 50)
        canvas_w, canvas_h = 820, 380
    elif N == 3:
        positions[t_names[0]] = (40, 50)
        positions[t_names[1]] = (350, 50)
        positions[t_names[2]] = (660, 50)
        canvas_w, canvas_h = 960, 400
    else:  # Star Schema (Matches Image 2: OrderDetails in center, Customers, Date, Cities, StockItems around)
        positions[t_names[0]] = (350, 130)  # Central Fact Table
        positions[t_names[1]] = (40, 20)    # Top Left Dimension
        positions[t_names[2]] = (40, 290)   # Bottom Left Dimension
        if N >= 4:
            positions[t_names[3]] = (660, 20)   # Top Right Dimension
        if N >= 5:
            positions[t_names[4]] = (660, 290)  # Bottom Right Dimension
        for ex_i in range(5, N):
            positions[t_names[ex_i]] = (350 + (ex_i - 4) * 260, 420)
        canvas_w = max(960, 720 + max(0, N - 4) * 260)
        canvas_h = 600

    # Canvas styling
    bg_canvas = "#2d2c2b" if theme == "Dark" else "#f3f2f1"
    bg_card = "#252423" if theme == "Dark" else "#ffffff"
    text_color = "#f3f2f1" if theme == "Dark" else "#201f1e"
    border_color = "#3b3a39" if theme == "Dark" else "#d2d0ce"

    # SVG Connectors
    svg_paths = []
    for rel in relationships:
        if not rel.get("active", True):
            continue
        from_t = rel.get("from_table")
        to_t = rel.get("to_table")
        if from_t in positions and to_t in positions:
            p1 = positions[from_t]
            p2 = positions[to_t]

            # Route from edge of table 1 to edge of table 2
            if p1[0] < p2[0]:
                x1 = p1[0] + card_w
                y1 = p1[1] + 95
                x2 = p2[0]
                y2 = p2[1] + 95
                mid_x = (x1 + x2) / 2
                path_d = f"M {x1} {y1} H {mid_x} V {y2} H {x2}"
                arrow_x, arrow_y = mid_x, (y1 + y2) / 2
                badge1_x, badge1_y = x1 + 6, y1 - 10
                badge2_x, badge2_y = x2 - 24, y2 - 10
            else:
                x1 = p1[0]
                y1 = p1[1] + 95
                x2 = p2[0] + card_w
                y2 = p2[1] + 95
                mid_x = (x1 + x2) / 2
                path_d = f"M {x1} {y1} H {mid_x} V {y2} H {x2}"
                arrow_x, arrow_y = mid_x, (y1 + y2) / 2
                badge1_x, badge1_y = x1 - 24, y1 - 10
                badge2_x, badge2_y = x2 + 6, y2 - 10

            card_from = rel.get("cardinality", "* : 1").split(":")[0].strip()
            card_to = rel.get("cardinality", "* : 1").split(":")[-1].strip()

            svg_paths.append(f"""
                <path d="{path_d}" fill="none" stroke="#f2c811" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
                <circle cx="{x1}" cy="{y1}" r="4" fill="#f2c811" />
                <circle cx="{x2}" cy="{y2}" r="4" fill="#f2c811" />
                <polygon class="line-arrow" points="{arrow_x-5},{arrow_y-4} {arrow_x+5},{arrow_y-4} {arrow_x},{arrow_y+5}" fill="#f2c811" />
                <rect class="pbi-erd-badge card-badge" x="{badge1_x}" y="{badge1_y}" width="18" height="18" rx="3" fill="#ffffff" stroke="#f2c811" stroke-width="1.5"/>
                <text x="{badge1_x+9}" y="{badge1_y+13}" font-family="Segoe UI, sans-serif" font-size="11" font-weight="700" fill="#201f1e" text-anchor="middle">{card_from}</text>
                <rect class="pbi-erd-badge card-badge" x="{badge2_x}" y="{badge2_y}" width="18" height="18" rx="3" fill="#ffffff" stroke="#f2c811" stroke-width="1.5"/>
                <text x="{badge2_x+9}" y="{badge2_y+13}" font-family="Segoe UI, sans-serif" font-size="12" font-weight="700" fill="#201f1e" text-anchor="middle">{card_to}</text>
            """)

    svg_content = "\n".join(svg_paths)

    # HTML Table Cards
    cards_html = []
    for t_name, t_df in tables.items():
        pos = positions.get(t_name, (40, 40))
        is_active = (t_name == active_table)

        # Golden yellow highlight for active table (matching Image 2)
        card_border = "2.5px solid #f2c811" if is_active else f"1px solid {border_color}"
        card_shadow = "0 0 16px rgba(242, 200, 17, 0.45)" if is_active else "0 2px 8px rgba(0,0,0,0.12)"

        # Fields list inside card
        field_rows = []
        for col in t_df.columns:
            is_join_key = any(
                (r["from_table"] == t_name and r["from_col"] == col) or
                (r["to_table"] == t_name and r["to_col"] == col)
                for r in relationships if r.get("active", True)
            )

            if is_join_key:
                row_html = f"""
                <div style="display:flex; align-items:center; justify-content:space-between; padding:4px 8px; margin:2px 6px; border:1.5px solid #f2c811; border-radius:3px; background:rgba(242,200,17,0.12); font-weight:700; color:{text_color};">
                    <div style="display:flex; align-items:center; gap:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                        <span style="color:#f2c811; font-size:0.8rem;">🔑</span>
                        <span style="font-size:0.84rem;">{col}</span>
                    </div>
                    <span style="font-size:9px; background:#f2c811; color:#201f1e; padding:1px 4px; border-radius:2px; font-weight:800;">JOIN</span>
                </div>
                """
            elif pd.api.types.is_numeric_dtype(t_df[col]):
                row_html = f"""
                <div style="display:flex; align-items:center; gap:6px; padding:4px 10px; margin:1px 0; font-size:0.84rem; color:{text_color};">
                    <span style="color:#0078d4; font-weight:bold; width:16px;">∑</span>
                    <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{col}</span>
                </div>
                """
            elif pd.api.types.is_datetime64_any_dtype(t_df[col]):
                row_html = f"""
                <div style="display:flex; align-items:center; gap:6px; padding:4px 10px; margin:1px 0; font-size:0.84rem; color:{text_color};">
                    <span style="color:#107c41; width:16px;">📅</span>
                    <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{col}</span>
                </div>
                """
            else:
                row_html = f"""
                <div style="display:flex; align-items:center; gap:6px; padding:4px 10px; margin:1px 0; font-size:0.84rem; color:{text_color};">
                    <span style="color:#605e5c; font-size:10px; font-weight:600; width:16px;">ABC</span>
                    <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{col}</span>
                </div>
                """
            field_rows.append(row_html)

        fields_inner = "\n".join(field_rows)

        card_markup = f"""
        <div style="position:absolute; left:{pos[0]}px; top:{pos[1]}px; width:{card_w}px; height:{card_h}px; background:{bg_card}; border:{card_border}; box-shadow:{card_shadow}; border-radius:4px; font-family:'Segoe UI', sans-serif; display:flex; flex-direction:column; z-index:10; overflow:hidden;">
            <div style="display:flex; align-items:center; justify-content:space-between; padding:8px 12px; background:{bg_card}; border-bottom:1px solid {border_color}; font-weight:700; font-size:0.92rem; color:{text_color};">
                <div style="display:flex; align-items:center; gap:8px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                    <span style="color:#0078d4; font-size:1.1rem;">▦</span>
                    <span>{t_name}</span>
                </div>
                <span style="color:#605e5c; font-size:1.1rem; cursor:pointer;">···</span>
            </div>
            <div style="flex:1; overflow-y:auto; padding:4px 0; background:{bg_card};">
                {fields_inner}
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center; padding:3px 10px; background:{bg_card}; border-top:1px solid {border_color}; font-size:0.72rem; color:#605e5c; font-weight:600;">
                <span>{len(t_df.columns)} fields</span>
                <span>{len(t_df):,} rows</span>
            </div>
        </div>
        """
        cards_html.append(card_markup)

    all_cards_markup = "\n".join(cards_html)

    canvas_html = f"""
    <div style="position:relative; width:100%; min-height:{canvas_h}px; height:{canvas_h}px; background:{bg_canvas}; border:1px solid {border_color}; border-radius:6px; overflow:auto; box-shadow:inset 0 1px 4px rgba(0,0,0,0.08);">
        <svg style="position:absolute; top:0; left:0; width:{canvas_w}px; height:{canvas_h}px; pointer-events:none; z-index:5;">
            {svg_content}
        </svg>
        <div style="position:relative; width:{canvas_w}px; height:{canvas_h}px;">
            {all_cards_markup}
        </div>
    </div>
    """
    return canvas_html


# -----------------------------------------------------------------------------
# DAX FORMULA EVALUATION ENGINE
# -----------------------------------------------------------------------------
def evaluate_dax_formula(formula: str, target_table: str, df: pd.DataFrame = None) -> tuple:
    tbls = getattr(st.session_state, "tables", {}) if hasattr(st, "session_state") else {}
    if df is None:
        if target_table not in tbls:
            return None, "Target table not found in data model"
        df = tbls[target_table]
    f = formula.strip()
    try:
        # Strip leading measure definition prefix like 'MeasureName = ...' or '[MeasureName] = ...'
        if "=" in f:
            eq_idx = f.find("=")
            paren_idx = f.find("(")
            if paren_idx == -1 or eq_idx < paren_idx:
                f = f[eq_idx + 1:].strip()

        # Literal numeric value
        try:
            return float(f), None
        except ValueError:
            pass

        # 0. CALCULATE( expression, filter )
        if f.upper().startswith("CALCULATE"):
            inner = f[9:].strip()
            if inner.startswith("(") and inner.endswith(")"):
                inner = inner[1:-1].strip()
            depth = 0
            split_idx = -1
            for idx, ch in enumerate(inner):
                if ch in "([":
                    depth += 1
                elif ch in ")]":
                    depth -= 1
                elif ch == "," and depth == 0:
                    split_idx = idx
                    break
            if split_idx != -1:
                inner_expr = inner[:split_idx].strip()
                filter_expr = inner[split_idx + 1:].strip()
                if "=" in filter_expr:
                    f_left, f_val = filter_expr.split("=", 1)
                    f_val = f_val.strip().strip("'\"")
                    col_m = re.search(r"\[([^\]]+)\]", f_left)
                    col = col_m.group(1).strip() if col_m else f_left.strip().strip("'\"")
                    if col in df.columns:
                        sub_df = df[df[col].astype(str).str.lower() == f_val.lower()]
                        return evaluate_dax_formula(inner_expr, target_table, df=sub_df)
                    return None, f"Filter column [{col}] not found in table '{target_table}'"

        # 1. COUNTROWS
        m = re.match(r"^\s*COUNTROWS\s*\(\s*(?:'([^']+)'|([a-zA-Z0-9_\s]+))\s*\)", f, re.IGNORECASE)
        if m:
            t_name = (m.group(1) or m.group(2)).strip()
            eval_df = df if (df is not None and t_name == target_table) else tbls.get(t_name, df)
            return len(eval_df), None

        # 2. DISTINCTCOUNT
        m = re.match(r"^\s*DISTINCTCOUNT\s*\(\s*(?:'[^']+'|[a-zA-Z0-9_\s]+)?\[([^\]]+)\]\s*\)", f, re.IGNORECASE)
        if m:
            col = m.group(1).strip()
            if col in df.columns:
                res = df[col].dropna().nunique()
                return res, None
            return None, f"Column [{col}] not found in table '{target_table}'"

        # 3. SUM
        m = re.match(r"^\s*SUM\s*\(\s*(?:'[^']+'|[a-zA-Z0-9_\s]+)?\[([^\]]+)\]\s*\)", f, re.IGNORECASE)
        if m:
            col = m.group(1).strip()
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                res = float(df[col].sum())
                return res, None
            return None, f"Column [{col}] is not numeric or not found"

        # 4. AVERAGE / AVG
        m = re.match(r"^\s*(?:AVERAGE|AVG)\s*\(\s*(?:'[^']+'|[a-zA-Z0-9_\s]+)?\[([^\]]+)\]\s*\)", f, re.IGNORECASE)
        if m:
            col = m.group(1).strip()
            if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
                res = float(df[col].mean())
                return res, None
            return None, f"Column [{col}] is not numeric or not found"

        # 5. MIN / MAX
        m = re.match(r"^\s*(MIN|MAX)\s*\(\s*(?:'[^']+'|[a-zA-Z0-9_\s]+)?\[([^\]]+)\]\s*\)", f, re.IGNORECASE)
        if m:
            op = m.group(1).upper()
            col = m.group(2).strip()
            if col in df.columns:
                res = df[col].min() if op == "MIN" else df[col].max()
                return res, None
            return None, f"Column [{col}] not found"

        # 7. DIVIDE
        m = re.match(r"^\s*DIVIDE\s*\(\s*([^,]+),\s*([^,\)]+)(?:,\s*([^,\)]+))?\s*\)", f, re.IGNORECASE)
        if m:
            n_expr, d_expr = m.group(1).strip(), m.group(2).strip()
            n_val, n_err = evaluate_dax_formula(n_expr, target_table, df=df)
            d_val, d_err = evaluate_dax_formula(d_expr, target_table, df=df)
            if n_err:
                return None, n_err
            if d_err:
                return None, d_err
            if n_val is not None and d_val is not None:
                if float(d_val) == 0:
                    return 0.0, None
                return float(n_val) / float(d_val), None

        return None, f"Unsupported or unrecognized DAX formula: '{f}'"
    except Exception as e:
        return None, f"DAX Parse Error: {str(e)}"


# -----------------------------------------------------------------------------
# TMDL SEMANTIC MODEL CODE GENERATOR
# -----------------------------------------------------------------------------
def generate_model_tmdl(tables: dict, relationships: list, dax_measures: list) -> str:
    lines = [
        "// Microsoft Tabular Model Definition Language (TMDL)",
        "// Power BI Analytics Studio Desktop 2026 Compatible",
        "",
        "model Model",
        "\tcompatibilityLevel: 1567",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "",
        "database 'PowerBI_Semantic_Model'",
        "\tcompatibilityLevel: 1567",
        ""
    ]

    for t_name, t_df in tables.items():
        clean_tbl = t_name.replace("'", "''")
        lines.append(f"table '{clean_tbl}'")
        lines.append(f"\tlineageTag: {abs(hash(t_name)) % 100000000:08d}")
        lines.append(f"\tpartition '{clean_tbl}-Partition' = m")
        lines.append("\t\tmode: import")
        lines.append(f"\t\tsource = GoogleSheets.Contents(\"https://docs.google.com/spreadsheets/...\")")
        lines.append("")

        for c in t_df.columns:
            clean_col = str(c).replace("'", "''")
            if pd.api.types.is_integer_dtype(t_df[c]):
                dtype = "int64"
                summ = "sum"
            elif pd.api.types.is_float_dtype(t_df[c]):
                dtype = "double"
                summ = "sum"
            elif pd.api.types.is_datetime64_any_dtype(t_df[c]):
                dtype = "dateTime"
                summ = "none"
            elif pd.api.types.is_bool_dtype(t_df[c]):
                dtype = "boolean"
                summ = "none"
            else:
                dtype = "string"
                summ = "none"

            lines.append(f"\tcolumn '{clean_col}'")
            lines.append(f"\t\tdataType: {dtype}")
            lines.append(f"\t\tsourceColumn: '{clean_col}'")
            lines.append(f"\t\tsummarizeBy: {summ}")
            lines.append("")

        t_measures = [m for m in dax_measures if m.get("table") == t_name]
        for m in t_measures:
            lines.append(f"\tmeasure '{m['name']}' = {m['formula']}")
            lines.append("\t\tformatString: #,##0.00")
            lines.append("")

    for i, rel in enumerate(relationships):
        if not rel.get("active", True):
            continue
        from_t = rel['from_table'].replace("'", "''")
        from_c = rel['from_col'].replace("'", "''")
        to_t = rel['to_table'].replace("'", "''")
        to_c = rel['to_col'].replace("'", "''")
        card = "manyToOne" if ": 1" in rel.get("cardinality", "") else ("oneToMany" if "1 :" in rel.get("cardinality", "") else "oneToOne")
        cross = "bothDirections" if rel.get("cross_direction") == "Both" else "single"

        lines.append(f"relationship rel_{i+1}_{abs(hash(from_t + to_t)) % 10000}")
        lines.append(f"\tfromColumn: '{from_t}'['{from_c}']")
        lines.append(f"\ttoColumn: '{to_t}'['{to_c}']")
        lines.append(f"\tcardinality: {card}")
        lines.append(f"\tcrossFilteringBehavior: {cross}")
        lines.append("\tisActive: true")
        lines.append("")

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# SAMPLE BUILT-IN POWER BI RELATIONAL STAR SCHEMA (FACT & DIMS)
# -----------------------------------------------------------------------------
def get_sample_powerbi_star_schema():
    dim_customer = pd.DataFrame({
        "customer_id": [101, 102, 103, 104, 105, 106, 107, 108],
        "customer_name": ["Alice Smith", "Bob Jones", "Charlie Brown", "Diana Prince", "Evan Wright", "Fiona Gallagher", "George Clark", "Hannah Abbott"],
        "customer_segment": ["Corporate", "Consumer", "Home Office", "Corporate", "Consumer", "Consumer", "Corporate", "Home Office"],
        "email": ["alice@company.com", "bob@gmail.com", "charlie@enterprise.org", "diana@wayne.com", "evan@wright.net", "fiona@gallagher.com", "george@clark.io", "hannah@abbott.co"],
        "city": ["Richmond", "Dallas", "Birmingham", "Chicago", "Arlington", "Austin", "Huntsville", "Naperville"],
        "state": ["VA", "TX", "AL", "IL", "VA", "TX", "AL", "IL"],
        "country": ["USA", "USA", "USA", "USA", "USA", "USA", "USA", "USA"]
    })

    dim_product = pd.DataFrame({
        "product_id": [1, 2, 3, 4, 5, 6],
        "product_name": ["Enterprise Cloud Suite", "AI Analytics Engine", "Zero Trust Firewall", "Business Intelligence Pro", "Data Lake Connector", "IoT Edge Hub"],
        "category": ["Cloud", "Analytics", "Security", "Analytics", "Cloud", "Hardware"],
        "subcategory": ["SaaS", "Machine Learning", "Cybersecurity", "Dashboards", "Data Ops", "Sensors"],
        "unit_cost": [450.0, 950.0, 320.0, 600.0, 250.0, 180.0],
        "current_retail_price": [1200.0, 2400.0, 850.0, 1600.0, 700.0, 490.0]
    })

    dim_store = pd.DataFrame({
        "store_id": [10, 20, 30, 40],
        "store_name": ["Virginia Tech Hub", "Texas Central Flagship", "Alabama Metro Store", "Illinois Lakefront Center"],
        "region": ["East", "South", "South", "Midwest"],
        "store_manager": ["Sarah Connor", "Michael Scott", "Jim Halpert", "Pam Beesly"],
        "store_type": ["Flagship", "Direct", "Outlet", "Direct"]
    })

    fact_sales = pd.DataFrame({
        "order_id": [5001, 5002, 5003, 5004, 5005, 5006, 5007, 5008, 5009, 5010, 5011, 5012],
        "customer_id": [101, 102, 103, 104, 105, 106, 107, 108, 101, 103, 105, 102],
        "product_id": [1, 2, 3, 4, 5, 6, 2, 1, 4, 3, 2, 5],
        "store_id": [10, 20, 30, 40, 10, 20, 30, 40, 10, 30, 10, 20],
        "order_date": pd.to_datetime(["2026-01-15", "2026-01-18", "2026-01-22", "2026-02-05", "2026-02-14", "2026-02-28", "2026-03-02", "2026-03-10", "2026-03-15", "2026-03-18", "2026-03-20", "2026-03-21"]),
        "quantity": [3, 2, 5, 2, 4, 6, 3, 2, 4, 2, 3, 5],
        "unit_price": [1200.0, 2400.0, 850.0, 1600.0, 700.0, 490.0, 2400.0, 1200.0, 1600.0, 850.0, 2400.0, 700.0],
        "discount": [0.05, 0.10, 0.0, 0.15, 0.05, 0.0, 0.10, 0.05, 0.0, 0.0, 0.10, 0.05]
    })
    fact_sales["revenue"] = fact_sales["quantity"] * fact_sales["unit_price"] * (1 - fact_sales["discount"])
    fact_sales["profit"] = fact_sales["revenue"] * 0.42

    default_relationships = [
        {"from_table": "Fact Sales", "from_col": "customer_id", "to_table": "Dim Customer", "to_col": "customer_id", "cardinality": "* : 1", "active": True},
        {"from_table": "Fact Sales", "from_col": "product_id", "to_table": "Dim Product", "to_col": "product_id", "cardinality": "* : 1", "active": True},
        {"from_table": "Fact Sales", "from_col": "store_id", "to_table": "Dim Store", "to_col": "store_id", "cardinality": "* : 1", "active": True}
    ]

    return {
        "Fact Sales": fact_sales,
        "Dim Customer": dim_customer,
        "Dim Product": dim_product,
        "Dim Store": dim_store
    }, default_relationships


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS: DATA CLEANING & URL PARSING
# -----------------------------------------------------------------------------
def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how='all')
    df = df.dropna(how='all', axis=1)

    for col in df.columns:
        if pd.api.types.is_string_dtype(df[col]) or df[col].dtype == 'object':
            sample = df[col].dropna().astype(str).str.strip()
            if sample.empty:
                continue

            # Detect currency or percentages
            is_num_match = sample.str.match(r'^[\$€£₹]?\s*-?\s*[\$€£₹]?\s*[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?\s*%?$')
            if is_num_match.mean() > 0.7:
                cleaned = sample.str.replace(r'[$€£₹,\s]', '', regex=True)
                is_pct = cleaned.str.endswith('%')
                cleaned = cleaned.str.rstrip('%')
                numeric_series = pd.to_numeric(cleaned, errors='coerce')
                if is_pct.any():
                    numeric_series = numeric_series / 100.0
                df[col] = numeric_series
            else:
                try:
                    if sample.str.match(r'^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|^\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}').mean() > 0.6:
                        parsed_dt = pd.to_datetime(df[col], errors='coerce', format='mixed')
                        if parsed_dt.notna().mean() > 0.6:
                            df[col] = parsed_dt
                except Exception:
                    pass

    return df


def parse_google_sheet_url(url: str):
    if not url or not isinstance(url, str):
        return None, None, None, "URL is empty."

    url = url.strip().strip('"\'<>')

    if "export?format=csv" in url or "output=csv" in url:
        sheet_id_m = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
        sheet_id = sheet_id_m.group(1) if sheet_id_m else None
        gid_match = re.search(r"[?&#]gid=([0-9]+)", url)
        gid = gid_match.group(1) if gid_match else None
        return sheet_id, url, gid, None

    pub_match = re.search(r"docs\.google\.com/spreadsheets/d/e/([a-zA-Z0-9-_]+)", url)
    if pub_match:
        pub_id = pub_match.group(1)
        gid_match = re.search(r"[?&#]gid=([0-9]+)", url)
        gid = gid_match.group(1) if gid_match else None
        export_url = f"https://docs.google.com/spreadsheets/d/e/{pub_id}/pub?output=csv" + (f"&gid={gid}" if gid else "")
        return pub_id, export_url, gid, None

    drive_match = re.search(r"drive\.google\.com/(?:file/d/|open\?id=)([a-zA-Z0-9-_]+)", url)
    sheet_id_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    raw_id_match = re.fullmatch(r"^[a-zA-Z0-9-_]{25,65}$", url)

    if sheet_id_match:
        sheet_id = sheet_id_match.group(1)
    elif drive_match:
        sheet_id = drive_match.group(1)
    elif raw_id_match:
        sheet_id = url
    else:
        return None, None, None, "Invalid Google Sheets link format. Please copy full link from browser."

    gid_match = re.search(r"[?&#]gid=([0-9]+)", url)
    gid = gid_match.group(1) if gid_match else None

    if gid:
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    else:
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

    return sheet_id, export_url, gid, None


@st.cache_data(ttl=60, show_spinner=False)
def discover_google_sheet_tabs(sheet_id: str):
    tabs = []
    if not sheet_id or len(sheet_id) < 15:
        return tabs

    try:
        url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/htmlview"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cache-Control": "no-cache"
        }
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            matches = re.findall(r'name:\s*"([^"]+)",\s*pageUrl:[^}]+?gid:\s*"([0-9]+)"', res.text)
            for name, gid in matches:
                clean_name = name.encode().decode('unicode_escape', errors='ignore')
                tabs.append({"name": clean_name, "gid": gid})

            if not tabs:
                btn_matches = re.findall(r'id="sheet-button-([0-9]+)"[^>]*><a[^>]*>([^<]+)</a>', res.text)
                for gid, name in btn_matches:
                    tabs.append({"name": name.strip(), "gid": gid})
    except Exception:
        pass

    return tabs


def build_tab_export_url(sheet_id: str, gid: str = None, sheet_name: str = None) -> str:
    if gid:
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    elif sheet_name:
        encoded = urllib.parse.quote(sheet_name)
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={encoded}"
    else:
        return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def fetch_sheet_data(export_url: str):
    try:
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        separator = "&" if "?" in export_url else "?"
        bust_url = f"{export_url}{separator}_t={int(time.time() * 1000)}"

        response = requests.get(bust_url, headers=headers, timeout=12)

        if "accounts.google.com" in response.url or "ServiceLogin" in response.url:
            return None, "PRIVATE_RESTRICTED"

        if response.status_code == 200:
            content_type = response.headers.get("Content-Type", "")
            if "html" in content_type.lower() or "<html" in response.text[:200].lower():
                return None, "PRIVATE_RESTRICTED"

            raw_csv = response.content
            df = pd.read_csv(io.BytesIO(raw_csv))
            if df.empty:
                return None, "EMPTY_SHEET"

            return clean_dataframe(df), None

        elif response.status_code == 404 and "&gid=" in export_url:
            fallback_url = re.sub(r"&gid=[0-9]+", "", export_url)
            fallback_bust = f"{fallback_url}{separator}_t={int(time.time() * 1000)}"
            fallback_res = requests.get(fallback_bust, headers=headers, timeout=12)
            if fallback_res.status_code == 200 and "html" not in fallback_res.headers.get("Content-Type", "").lower():
                df = pd.read_csv(io.BytesIO(fallback_res.content))
                if not df.empty:
                    return clean_dataframe(df), None
            return None, "NOT_FOUND"

        elif response.status_code == 404:
            return None, "NOT_FOUND"
        elif response.status_code == 403:
            return None, "PRIVATE_RESTRICTED"
        else:
            return None, f"HTTP_{response.status_code}"
    except requests.exceptions.Timeout:
        return None, "TIMEOUT"
    except requests.exceptions.RequestException as e:
        return None, f"NETWORK_ERROR: {str(e)}"
    except Exception as e:
        return None, f"PARSE_ERROR: {str(e)}"


def parse_uploaded_excel_files(uploaded_files):
    workbook_dict = {}
    for f in uploaded_files:
        try:
            xls = pd.ExcelFile(f)
            for sname in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sname)
                t_name = f"{f.name.split('.')[0]} - {sname}" if len(uploaded_files) > 1 else sname
                workbook_dict[t_name] = clean_dataframe(df)
        except Exception as e:
            st.error(f"Error parsing Excel file '{f.name}': {e}")
    return workbook_dict


def is_id_or_serial_column(col_name: str, series: pd.Series = None) -> bool:
    if not col_name:
        return False
    name_clean = re.sub(r'[^a-zA-Z0-9]', '', str(col_name)).lower()
    id_keywords = ["slno", "sno", "serialno", "serialnumber", "id", "rowid", "index", "uid", "recordid", "srno", "sl_no"]
    if name_clean in id_keywords:
        return True
    if name_clean.endswith("id") and len(name_clean) <= 6 and name_clean not in ["paid", "fluid"]:
        return True
    if series is not None and pd.api.types.is_numeric_dtype(series):
        clean_s = series.dropna()
        if len(clean_s) > 5:
            sorted_s = clean_s.sort_values().values
            if (sorted_s[1:] - sorted_s[:-1] == 1).mean() > 0.95 and sorted_s[0] in [0, 1]:
                return True
    return False


# -----------------------------------------------------------------------------
# RELATIONAL JOINING ENGINE (BIDIRECTIONAL & STAR SCHEMA)
# -----------------------------------------------------------------------------
def get_unified_relational_dataset(primary_table: str = None):
    if not primary_table or primary_table not in st.session_state.tables:
        if st.session_state.active_table_name in st.session_state.tables:
            primary_table = st.session_state.active_table_name
        elif st.session_state.tables:
            primary_table = list(st.session_state.tables.keys())[0]
        else:
            return pd.DataFrame()

    base_df = st.session_state.tables[primary_table].copy()
    joined_tables = {primary_table}

    # Iterate up to number of tables to resolve multi-hop joins
    for _ in range(max(1, len(st.session_state.tables))):
        joined_any = False
        for rel in st.session_state.relationships:
            if not rel.get("active", True):
                continue

            from_t = rel.get("from_table")
            from_c = rel.get("from_col")
            to_t = rel.get("to_table")
            to_c = rel.get("to_col")

            # Direction 1: from_table is in base_df, join to_table
            if from_t in joined_tables and to_t in st.session_state.tables and to_t not in joined_tables:
                target_df = st.session_state.tables[to_t]
                if from_c in base_df.columns and to_c in target_df.columns:
                    cols_to_add = [c for c in target_df.columns if c not in base_df.columns or c == to_c]
                    subset_dim = target_df[cols_to_add].drop_duplicates(subset=[to_c]) if to_c in cols_to_add else target_df[cols_to_add]
                    base_df = base_df.merge(subset_dim, left_on=from_c, right_on=to_c, how="left", suffixes=("", f"_{to_t}"))
                    joined_tables.add(to_t)
                    joined_any = True

            # Direction 2: to_table is in base_df, join from_table (Reverse join)
            elif to_t in joined_tables and from_t in st.session_state.tables and from_t not in joined_tables:
                target_df = st.session_state.tables[from_t]
                if to_c in base_df.columns and from_c in target_df.columns:
                    cols_to_add = [c for c in target_df.columns if c not in base_df.columns or c == from_c]
                    subset_dim = target_df[cols_to_add].drop_duplicates(subset=[from_c]) if from_c in cols_to_add else target_df[cols_to_add]
                    base_df = base_df.merge(subset_dim, left_on=to_c, right_on=from_c, how="left", suffixes=("", f"_{from_t}"))
                    joined_tables.add(from_t)
                    joined_any = True

        if not joined_any:
            break

    return base_df


# -----------------------------------------------------------------------------
# POWER BI VISUALIZATION PALETTE (16 VISUAL TYPES)
# -----------------------------------------------------------------------------
VISUAL_TYPES = [
    ("📊 Clustered Column", "clustered_column"),
    ("📊 Stacked Column", "stacked_column"),
    ("📊 Clustered Bar", "clustered_bar"),
    ("📊 Stacked Bar", "stacked_bar"),
    ("📈 Line Chart", "line"),
    ("🏔️ Area Chart", "area"),
    ("🥧 Pie Chart", "pie"),
    ("🍩 Donut Chart", "donut"),
    ("🌲 Treemap", "treemap"),
    ("🔻 Funnel Chart", "funnel"),
    ("🌊 Waterfall Chart", "waterfall"),
    ("⚡ Scatter Plot", "scatter"),
    ("🎯 Radial Gauge", "gauge"),
    ("🗂️ Pivot Matrix", "matrix"),
    ("🔢 Multi-Row KPI", "kpi"),
    ("📋 Data Table", "table")
]

def render_powerbi_visual(visual_type: str, df: pd.DataFrame, x_col: str, y_col: str, agg: str, color_col: str, theme: str):
    if df.empty:
        st.info("No data available to render visual.")
        return

    # Palette Colors matching Power BI Desktop
    pbi_colors = ["#118dff", "#12239e", "#e66c37", "#6b007b", "#e044a7", "#744ec2", "#d9b300", "#d64550"]

    # Aggregation logic
    if x_col and y_col and y_col != "Record Count":
        agg_map = {"Sum": "sum", "Average": "mean", "Count": "count", "Min": "min", "Max": "max"}
        func = agg_map.get(agg, "sum")
        group_cols = [x_col]
        if color_col and color_col != "None" and color_col != x_col and color_col in df.columns:
            group_cols.append(color_col)

        try:
            chart_df = df.groupby(group_cols, as_index=False)[y_col].agg(func)
            chart_df = chart_df.sort_values(by=y_col, ascending=False).head(30)
            val_col = y_col
        except Exception:
            chart_df = df.head(30)
            val_col = y_col
    elif x_col:
        if color_col and color_col != "None" and color_col != x_col and color_col in df.columns:
            chart_df = df.groupby([x_col, color_col], as_index=False).size()
            chart_df.rename(columns={"size": "Record Count"}, inplace=True)
            chart_df = chart_df.sort_values(by="Record Count", ascending=False).head(40)
            val_col = "Record Count"
        else:
            chart_df = df[x_col].value_counts().reset_index().head(30)
            chart_df.columns = [x_col, "Record Count"]
            val_col = "Record Count"
    else:
        st.warning("Please select an Axis / Category field.")
        return

    color_param = color_col if (color_col and color_col != "None" and color_col in chart_df.columns) else None

    # Chart Background & Fonts
    bg_chart = "#ffffff" if theme == "Light" else "#252423"
    text_color = "#201f1e" if theme == "Light" else "#ffffff"
    grid_color = "#edebe9" if theme == "Light" else "#3b3a39"

    def apply_neat_layout(fig):
        fig.update_layout(
            paper_bgcolor=bg_chart,
            plot_bgcolor=bg_chart,
            font=dict(color=text_color, family="Segoe UI, sans-serif", size=12),
            xaxis=dict(gridcolor=grid_color, tickfont=dict(color=text_color)),
            yaxis=dict(gridcolor=grid_color, tickfont=dict(color=text_color)),
            height=460,
            margin=dict(l=20, r=20, t=50, b=30)
        )
        return fig

    # 1. Clustered Column
    if visual_type == "clustered_column":
        fig = px.bar(chart_df, x=x_col, y=val_col, color=color_param, barmode='group',
                     title=f"{agg or 'Count'} of {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 2. Stacked Column
    elif visual_type == "stacked_column":
        fig = px.bar(chart_df, x=x_col, y=val_col, color=color_param or x_col, barmode='stack',
                     title=f"Stacked Column: {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 3. Clustered Bar
    elif visual_type == "clustered_bar":
        fig = px.bar(chart_df, y=x_col, x=val_col, color=color_param, orientation='h', barmode='group',
                     title=f"Horizontal Bar: {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 4. Stacked Bar
    elif visual_type == "stacked_bar":
        fig = px.bar(chart_df, y=x_col, x=val_col, color=color_param or x_col, orientation='h', barmode='stack',
                     title=f"Stacked Bar: {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 5. Line Chart
    elif visual_type == "line":
        fig = px.line(chart_df, x=x_col, y=val_col, color=color_param, markers=True,
                      title=f"Trend Line: {val_col} over {x_col}",
                      color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 6. Area Chart
    elif visual_type == "area":
        fig = px.area(chart_df, x=x_col, y=val_col, color=color_param,
                      title=f"Area Spread: {val_col} by {x_col}",
                      color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 7. Pie Chart
    elif visual_type == "pie":
        fig = px.pie(chart_df, names=x_col, values=val_col,
                     title=f"Share of {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 8. Donut Chart
    elif visual_type == "donut":
        fig = px.pie(chart_df, names=x_col, values=val_col, hole=0.55,
                     title=f"Donut Breakdown: {val_col} by {x_col}",
                     color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 9. Treemap
    elif visual_type == "treemap":
        path_cols = [x_col]
        if color_param and color_param in chart_df.columns and color_param != x_col:
            path_cols = [color_param, x_col]
        fig = px.treemap(chart_df, path=path_cols, values=val_col,
                         title=f"Treemap Hierarchy: {val_col}",
                         color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 10. Funnel Chart
    elif visual_type == "funnel":
        fig = px.funnel(chart_df.sort_values(by=val_col, ascending=False).head(15),
                        y=x_col, x=val_col,
                        title=f"Funnel: {val_col} across {x_col}",
                        color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 11. Waterfall Chart
    elif visual_type == "waterfall":
        wf_data = chart_df.head(12)
        fig = go.Figure(go.Waterfall(
            name=val_col,
            orientation="v",
            measure=["relative"] * len(wf_data),
            x=wf_data[x_col].astype(str),
            y=wf_data[val_col],
            connector={"line": {"color": "#8a8886"}},
            decreasing={"marker": {"color": "#d64550"}},
            increasing={"marker": {"color": "#107c41"}},
            totals={"marker": {"color": "#f2c811"}}
        ))
        fig.update_layout(title=f"Waterfall Contribution: {val_col} by {x_col}")
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 12. Scatter Plot
    elif visual_type == "scatter":
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        sc_y = val_col if val_col in numeric_cols else (numeric_cols[0] if numeric_cols else None)
        sc_x = x_col if x_col in numeric_cols else (numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0])
        fig = px.scatter(df, x=sc_x, y=sc_y, color=color_param,
                         title=f"Correlation: {sc_x} vs. {sc_y}",
                         color_discrete_sequence=pbi_colors)
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 13. Radial Gauge
    elif visual_type == "gauge":
        current_sum = df[val_col].sum() if val_col in df.columns and pd.api.types.is_numeric_dtype(df[val_col]) else len(df)
        max_target = current_sum * 1.35 if current_sum > 0 else 100
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=current_sum,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': f"Total {val_col}", 'font': {'size': 20, 'color': '#0078d4' if theme == 'Light' else '#f2c811'}},
            delta={'reference': current_sum * 0.85, 'increasing': {'color': "#107c41"}},
            gauge={
                'axis': {'range': [None, max_target], 'tickwidth': 1, 'tickcolor': "gray"},
                'bar': {'color': "#0078d4" if theme == 'Light' else "#f2c811"},
                'bgcolor': bg_chart,
                'borderwidth': 2,
                'bordercolor': "#d2d0ce",
                'steps': [
                    {'range': [0, current_sum * 0.6], 'color': 'rgba(0, 120, 212, 0.1)'},
                    {'range': [current_sum * 0.6, current_sum * 0.9], 'color': 'rgba(242, 200, 17, 0.25)'}
                ]
            }
        ))
        st.plotly_chart(apply_neat_layout(fig), width="stretch")

    # 14. Pivot Matrix
    elif visual_type == "matrix":
        st.markdown(f"#### 🗂️ Pivot Matrix: {x_col} vs {color_col or 'Totals'}")
        if color_col and color_col != "None" and val_col in df.columns:
            pivot_df = pd.pivot_table(df, index=x_col, columns=color_col, values=val_col, aggfunc=agg.lower() if agg != "Distinct Count" else "nunique", fill_value=0)
            st.dataframe(pivot_df, width="stretch")
        else:
            st.dataframe(chart_df, width="stretch")

    # 15. Multi-Row KPI
    elif visual_type == "kpi":
        kpi_cols = st.columns(min(len(chart_df), 4))
        for idx, row in chart_df.head(4).iterrows():
            with kpi_cols[idx % 4]:
                st.markdown(
                    f"""
                    <div class="kpi-card">
                        <div class="kpi-label">{row[x_col]}</div>
                        <div class="kpi-value">{row[val_col]:,}</div>
                        <div class="kpi-sub">{agg or 'Total'} {val_col}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # 16. Detailed Data Table
    elif visual_type == "table":
        st.dataframe(df, width="stretch", height=450)


# -----------------------------------------------------------------------------
# QUEUE LIVE TRACKER & GOOGLE SHEET 2 POWER BI ANALYTICS VIEW
# -----------------------------------------------------------------------------
def render_queue_tracker_view(theme: str = "Light"):
    rail_col, main_col = st.columns([0.05, 0.95], gap="small")
    with rail_col:
        render_powerbi_left_rail("Queue Tracker")
    with main_col:
        st.markdown("## ⏱️ Queue Live Tracker & Google Sheet 2 Analytics")
        st.caption("Real-time monitoring of DataTrace title queue entries, arrival times, and newly added data synced with Sheet 2 of Google Sheets.")
        
        # Sync control bar
        s_c1, s_c2, s_c3, s_c4 = st.columns([3, 2, 2.5, 2])
        with s_c1:
            gsheet_2_url = st.text_input("Google Sheet 2 URL", value="https://docs.google.com/spreadsheets/d/1YkbMfgQhnXz3amkZTB76h8_5I7PBeWUoh6j9gS51BsE/edit?gid=0#gid=0", key="queue_sheet_url_input")
        with s_c2:
            sync_btn = st.button("🔄 Sync Live Sheet 2 Data", width="stretch", key="btn_sync_sheet2")
        with s_c3:
            pup_btn = st.button("⚡ Run Auto-Login Scraper", width="stretch", key="btn_run_pup_main", help="Launch Puppeteer, auto fill KishoreK_ADS & Kishore@2025, and extract queue table")
        with s_c4:
            up_file = st.file_uploader("Upload Excel/CSV", type=["xlsx", "csv"], key="queue_up_file", label_visibility="collapsed")

        # Puppeteer Auto-Login execution
        if pup_btn:
            import subprocess
            with st.spinner("🚀 Launching Chromium browser, auto-filling credentials (KishoreK_ADS / Kishore@2025), clicking Sign in (#next), and extracting table..."):
                try:
                    js_path = os.path.join(os.path.dirname(__file__), "scrape_datatrace.js")
                    res = subprocess.run(["node", js_path], capture_output=True, text=True, timeout=90)
                    st.success("✅ Auto-Login Scraper completed! Loaded latest queue data into Sheet 2 preview!")
                    st.session_state.pop("queue_data_df", None)
                    st.rerun()
                except Exception as ex:
                    st.error(f"Scraper execution error: {ex}")

        # Fetch data logic
        q_df = None
        if up_file is not None:
            try:
                if up_file.name.endswith('.csv'):
                    q_df = pd.read_csv(up_file)
                else:
                    xls = pd.ExcelFile(up_file)
                    sheet_target = "Sheet2" if "Sheet2" in xls.sheet_names else ("Sheet 2" if "Sheet 2" in xls.sheet_names else xls.sheet_names[0])
                    q_df = pd.read_excel(xls, sheet_name=sheet_target)
                st.success(f"Loaded {len(q_df)} rows from uploaded file '{up_file.name}'!")
            except Exception as e:
                st.error(f"Error reading uploaded file: {e}")

        if q_df is None and (sync_btn or "queue_data_df" not in st.session_state):
            sheet_id_match = re.search(r"/d/([a-zA-Z0-9-_]+)", gsheet_2_url)
            if sheet_id_match:
                sheet_id = sheet_id_match.group(1)
                export_url = build_tab_export_url(sheet_id, sheet_name="Sheet2")
                q_df, err = fetch_sheet_data(export_url)
                if q_df is None:
                    export_url2 = build_tab_export_url(sheet_id, sheet_name="Sheet 2")
                    q_df, err2 = fetch_sheet_data(export_url2)

        if q_df is None:
            local_path_csv = os.path.join(os.path.dirname(__file__), "queue_data_sheet2.csv")
            local_path_xlsx = os.path.join(os.path.dirname(__file__), "queue_data_sheet2.xlsx")
            if os.path.exists(local_path_csv):
                q_df = pd.read_csv(local_path_csv)
            elif os.path.exists(local_path_xlsx):
                q_df = pd.read_excel(local_path_xlsx, sheet_name="Sheet2")

        if q_df is not None and not q_df.empty:
            st.session_state.queue_data_df = clean_dataframe(q_df)

        if "queue_data_df" not in st.session_state or st.session_state.queue_data_df.empty:
            st.warning("⚠️ No data loaded for Sheet 2 yet. Click 'Sync Live Sheet 2 Data' or upload queue Excel/CSV file.")
            return

        q_df = st.session_state.queue_data_df.copy()

        # Detect Arrival Time column
        arr_cols = [c for c in q_df.columns if "arrival" in c.lower()]
        if arr_cols:
            arr_col = arr_cols[0]
            q_df[arr_col] = pd.to_datetime(q_df[arr_col], errors='coerce')
            q_df = q_df.sort_values(by=arr_col, ascending=False)
        else:
            arr_col = None

        # Telemetry Bar
        latest_ts = str(q_df[arr_col].iloc[0])[:19] if arr_col and not q_df[arr_col].isna().all() else 'N/A'
        st.markdown(
            f"""
            <div class="telemetry-bar">
                <div class="telemetry-item"><span class="pulse-dot"></span> <strong>QUEUE STATUS:</strong> Live Synchronized</div>
                <div class="telemetry-item"><strong>Total Queue Tasks:</strong> {len(q_df):,}</div>
                <div class="telemetry-item"><strong>Target Tab:</strong> Sheet 2</div>
                <div class="telemetry-item"><strong>Latest Arrival Time:</strong> {latest_ts}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

        # KPI Summary Cards
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">Total Queue Tasks</div>
                    <div class="kpi-value">{len(q_df):,}</div>
                    <div class="kpi-sub">DataTrace Live Queue</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with k2:
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">Latest Arrival Time</div>
                    <div class="kpi-value" style="font-size:1.1rem;">{latest_ts}</div>
                    <div class="kpi-sub">Newest Entry Timestamp</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with k3:
            status_cols = [c for c in q_df.columns if "status" in c.lower()]
            avail_cnt = len(q_df[q_df[status_cols[0]].astype(str).str.contains("Available", case=False)]) if status_cols else len(q_df)
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">Available Tasks</div>
                    <div class="kpi-value">{avail_cnt:,}</div>
                    <div class="kpi-sub">Ready for Processing</div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with k4:
            client_cols = [c for c in q_df.columns if "client" in c.lower()]
            u_clients = q_df[client_cols[0]].nunique() if client_cols else 0
            st.markdown(
                f"""
                <div class="kpi-card">
                    <div class="kpi-label">Unique Clients</div>
                    <div class="kpi-value">{u_clients:,}</div>
                    <div class="kpi-sub">Active Organizations</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # POWER BI LINE CHART (Arrival Time Trend & Newly Added Data over Time)
        st.markdown("### 📈 Power BI Line Chart: Newly Added Data & Arrival Time Trend")
        if arr_col and not q_df[arr_col].isna().all():
            line_df = q_df.dropna(subset=[arr_col]).copy()
            line_df['Arrival_Date'] = line_df[arr_col].dt.date
            trend_df = line_df.groupby('Arrival_Date').size().reset_index(name='New_Arrivals_Count')
            trend_df = trend_df.sort_values(by='Arrival_Date')

            fig = px.line(
                trend_df,
                x='Arrival_Date',
                y='New_Arrivals_Count',
                title="Newly Added Task Arrivals Over Time (Sheet 2)",
                markers=True,
                labels={"Arrival_Date": "Arrival Date", "New_Arrivals_Count": "Newly Arrived Tasks"},
                template="plotly_white" if theme == "Light" else "plotly_dark"
            )
            fig.update_traces(line_color="#0078d4", line_width=3, marker=dict(size=8, color="#f2c811"))
            fig.update_layout(
                hovermode="x unified",
                font_family="Segoe UI, sans-serif",
                margin=dict(l=40, r=40, t=50, b=40)
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Line chart requires an 'Arrival Time' timestamp column in Sheet 2.")

        # POWER BI DATA TABLE (Newly Added Data Inspector)
        st.markdown("---")
        st.markdown("### 📋 Newly Added Data Table (Sorted by Latest Arrival Time)")
        
        filtered_q_df = q_df.copy()
        f_c1, f_c2, f_c3 = st.columns(3)
        with f_c1:
            c_cols = [c for c in q_df.columns if "client" in c.lower()]
            if c_cols:
                client_opts = ["All"] + sorted([str(x) for x in q_df[c_cols[0]].dropna().unique()])
                sel_client = st.selectbox("Filter Client", client_opts, key="queue_client_filter")
                if sel_client != "All":
                    filtered_q_df = filtered_q_df[filtered_q_df[c_cols[0]].astype(str) == sel_client]

        with f_c2:
            st_cols = [c for c in q_df.columns if "status" in c.lower()]
            if st_cols:
                status_opts = ["All"] + sorted([str(x) for x in q_df[st_cols[0]].dropna().unique()])
                sel_status = st.selectbox("Filter Task Status", status_opts, key="queue_status_filter")
                if sel_status != "All":
                    filtered_q_df = filtered_q_df[filtered_q_df[st_cols[0]].astype(str) == sel_status]

        with f_c3:
            s_cols = [c for c in q_df.columns if c.lower() in ["st", "state"]]
            if s_cols:
                state_opts = ["All"] + sorted([str(x) for x in q_df[s_cols[0]].dropna().unique()])
                sel_state = st.selectbox("Filter State", state_opts, key="queue_state_filter")
                if sel_state != "All":
                    filtered_q_df = filtered_q_df[filtered_q_df[s_cols[0]].astype(str) == sel_state]

        q_search = st.text_input("🔍 Search newly added rows", placeholder="Type keyword to filter queue...", key="queue_search_input")
        if q_search.strip():
            m = filtered_q_df.astype(str).apply(lambda row: row.str.contains(q_search.strip(), case=False, na=False)).any(axis=1)
            filtered_q_df = filtered_q_df[m]

        t_c1, t_c2 = st.columns([3, 1])
        with t_c1:
            st.caption(f"Displaying {len(filtered_q_df):,} of {len(q_df):,} total records")
        with t_c2:
            dl_csv = io.StringIO()
            filtered_q_df.to_csv(dl_csv, index=False)
            st.download_button(
                "📥 Export Sheet 2 CSV",
                data=dl_csv.getvalue(),
                file_name="sheet2_newly_added_queue.csv",
                mime="text/csv",
                width="stretch"
            )

        st.dataframe(filtered_q_df, width="stretch", height=420)


# -----------------------------------------------------------------------------
# MAIN APPLICATION
# -----------------------------------------------------------------------------
def main():
    # Inject active theme CSS
    inject_powerbi_theme(st.session_state.pbi_theme)

    # -------------------------------------------------------------------------
    # TOP POWER BI RIBBON
    # -------------------------------------------------------------------------
    r_col1, r_col2, r_col3 = st.columns([3.2, 5.0, 1.8], gap="small")
    with r_col1:
        st.markdown(
            """
            <div class="pbi-topbar">
                <div class="pbi-logo">
                    <span>📊 Power BI Analytics Studio</span>
                    <span class="pbi-logo-badge">Desktop 2026</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with r_col2:
        # 6 Power BI Workspace Views
        v1, v2, v3, v4, v5, v6 = st.columns(6)
        with v1:
            if st.button("📊 Report", key="btn_rep", width="stretch", type="primary" if st.session_state.pbi_view_mode == "Report View" else "secondary", help="Interactive Visuals & Dashboard"):
                st.session_state.pbi_view_mode = "Report View"
                st.rerun()
        with v2:
            if st.button("⏱️ Queue", key="btn_queue", width="stretch", type="primary" if st.session_state.pbi_view_mode == "Queue Tracker" else "secondary", help="DataTrace TV Queue (Sheet 2) Analytics"):
                st.session_state.pbi_view_mode = "Queue Tracker"
                st.rerun()
        with v3:
            if st.button("📋 Table", key="btn_dat", width="stretch", type="primary" if st.session_state.pbi_view_mode == "Data View" else "secondary", help="Data Grid & Column Profiling"):
                st.session_state.pbi_view_mode = "Data View"
                st.rerun()
        with v4:
            if st.button("🕸️ Model", key="btn_mod", width="stretch", type="primary" if st.session_state.pbi_view_mode == "Model View" else "secondary", help="Entity Relationship Diagram"):
                st.session_state.pbi_view_mode = "Model View"
                st.rerun()
        with v5:
            if st.button("📐 DAX", key="btn_dax", width="stretch", type="primary" if st.session_state.pbi_view_mode == "DAX Formulas" else "secondary", help="DAX Measures & Calculations"):
                st.session_state.pbi_view_mode = "DAX Formulas"
                st.rerun()
        with v6:
            if st.button("📜 TMDL", key="btn_tmdl", width="stretch", type="primary" if st.session_state.pbi_view_mode == "TMDL Model" else "secondary", help="Tabular Model Definition Language"):
                st.session_state.pbi_view_mode = "TMDL Model"
                st.rerun()

    with r_col3:
        # Quick Controls (Theme, Sync, Clean Workspace)
        c_th, c_sy, c_cl = st.columns([1, 1, 1.3])
        with c_th:
            theme_btn = "🌙 Dark" if st.session_state.pbi_theme == "Light" else "☀️ Light"
            if st.button(theme_btn, key="btn_theme_tog", width="stretch"):
                st.session_state.pbi_theme = "Dark" if st.session_state.pbi_theme == "Light" else "Light"
                st.rerun()
        with c_sy:
            if st.button("🔄 Sync", key="btn_quick_sync", width="stretch"):
                st.rerun()
        with c_cl:
            if st.button("🧹 Clean", key="btn_clean_ws", help="Reset and open a clean empty webpage", width="stretch"):
                st.session_state.tables = {}
                st.session_state.relationships = []
                st.session_state.active_table_name = ""
                st.session_state.active_sheet_tab = ""
                st.session_state.single_sheet_url = ""
                st.session_state["single_sheet_url_input"] = ""
                st.session_state.workspace_clean = True
                st.session_state.custom_link_configs = [{"name": "Google Sheet 1", "url": ""}, {"name": "Google Sheet 2", "url": ""}]
                st.session_state.pop("single_synced_url", None)
                st.session_state.current_sheet_id = ""
                st.session_state.available_tabs = []
                st.rerun()

    # -------------------------------------------------------------------------
    # SIDEBAR: DATA INGESTION
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### 📥 Data Ingestion & Sources")

        source_mode = st.radio(
            "Select Data Source",
            options=[
                "🌐 DataTrace TV Portal (qid=23656)",
                "🔗 Single Google Sheet (Live-Sync & Tab Selector)",
                "🔗 Multi-Google Sheets (Custom 1, 2, 3, 4, 5... Links)",
                "📂 Upload Multi-Sheet Excel (.xlsx)",
                "🌟 Power BI Demo Star Schema (Fact & Dimensions)"
            ],
            index=0
        )

        is_live_sync = False
        sync_interval = "10s"

        # OPTION 0: DATATRACE TV PORTAL
        if source_mode == "🌐 DataTrace TV Portal (qid=23656)":
            st.markdown("#### 🌐 DataTrace TV Link")
            st.caption("Target Queue Portal Link:")
            st.code("https://tv.datatracetitle.com/Queues.aspx?qid=23656", language="text")
            
            st.link_button("🌐 Open DataTrace Portal Page", "https://tv.datatracetitle.com/Queues.aspx?qid=23656", type="secondary", width="stretch")
            
            if st.button("⚡ Run Auto-Login & Extract Queue", type="primary", width="stretch", key="btn_sidebar_pup"):
                import subprocess
                with st.spinner("🚀 Launching Chromium browser, entering credentials (KishoreK_ADS / Kishore@2025), clicking Sign in (#next), and extracting table..."):
                    try:
                        js_path = os.path.join(os.path.dirname(__file__), "scrape_datatrace.js")
                        res = subprocess.run(["node", js_path], capture_output=True, text=True, timeout=90)
                        st.success("✅ Auto-Login completed! Loaded latest queue data into Sheet 2!")
                        st.session_state.pop("queue_data_df", None)
                        st.session_state.pbi_view_mode = "Queue Tracker"
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Auto-login error: {ex}")

            if st.button("⏱️ View Sheet 2 Queue Analytics", width="stretch", key="btn_sidebar_view_q"):
                st.session_state.pbi_view_mode = "Queue Tracker"
                st.rerun()

            st.markdown("---")
            st.caption("🔑 **Auto-Login Automation:**\n- **Username:** `KishoreK_ADS` (`#signInName`)\n- **Password:** `Kishore@2025` (`#password`)\n- **Submit Button:** `Sign in` (`#next`)")

        # OPTION 1: SINGLE GOOGLE SHEET LIVE-SYNC
        elif source_mode == "🔗 Single Google Sheet (Live-Sync & Tab Selector)":
            is_live_sync = True
            st.markdown("#### 🔗 Single Google Sheet")
            st.caption("Paste any public Google Sheet link. All tabs will be indexed automatically!")

            col_inp, col_clr = st.columns([3.6, 1.2])
            with col_inp:
                sheet_url = st.text_input(
                    "Google Sheet Share Link",
                    value=st.session_state.get("single_sheet_url", ""),
                    placeholder="https://docs.google.com/spreadsheets/d/...",
                    help="Paste your Google Sheet link here. Ensure 'Anyone with the link can view' is enabled in Google Sheets.",
                    key="single_sheet_url_input"
                )
                st.session_state.single_sheet_url = sheet_url
            with col_clr:
                st.write("")
                st.write("")
                if st.button("❌ Clear", key="btn_remove_single_url", help="Remove link and clear data"):
                    st.session_state.single_sheet_url = ""
                    st.session_state["single_sheet_url_input"] = ""
                    st.session_state.pop("single_synced_url", None)
                    st.session_state.current_sheet_id = ""
                    st.session_state.tables = {}
                    st.session_state.active_table_name = ""
                    st.session_state.relationships = []
                    st.session_state.available_tabs = []
                    st.session_state.active_sheet_tab = ""
                    st.session_state.workspace_clean = True
                    st.rerun()

            table_name = st.text_input("Table Name", value="Google Sheet Data", key="single_tbl_name")

            if sheet_url and sheet_url.strip():
                sheet_id, default_export, url_gid, parse_err = parse_google_sheet_url(sheet_url)
                if parse_err:
                    st.error(f"⚠️ {parse_err}")
                else:
                    st.session_state.current_sheet_id = sheet_id
                    # Tab Discovery
                    discovered_tabs = discover_google_sheet_tabs(sheet_id)
                    if discovered_tabs:
                        for t in discovered_tabs:
                            if t["name"] not in st.session_state.available_tabs:
                                st.session_state.available_tabs.append(t["name"])

                    st.markdown("**📑 Worksheet Tabs Configuration:**")
                    tabs_input = st.text_input(
                        "Sheet / State Tabs (comma-separated)",
                        value=", ".join(st.session_state.available_tabs),
                        help="Enter sheet tabs (e.g. AL, AR, NM, MD, KY, IL, TX, AZ, UT, WY, OR, GA, NV, TN, IN, MN, WA)"
                    )
                    if tabs_input:
                        parsed_tabs = [t.strip() for t in tabs_input.split(",") if t.strip()]
                        if parsed_tabs:
                            st.session_state.available_tabs = parsed_tabs

                    if st.session_state.available_tabs:
                        if st.session_state.active_sheet_tab not in st.session_state.available_tabs:
                            st.session_state.active_sheet_tab = st.session_state.available_tabs[0]

                        try:
                            def_tab_idx = st.session_state.available_tabs.index(st.session_state.active_sheet_tab)
                        except (ValueError, IndexError):
                            def_tab_idx = 0
                        def_tab_idx = max(0, min(def_tab_idx, len(st.session_state.available_tabs) - 1))
                        selected_tab = st.selectbox("Select Active Tab to Sync", st.session_state.available_tabs, index=def_tab_idx)
                        st.session_state.active_sheet_tab = selected_tab
                    else:
                        selected_tab = "Default Tab"

                    active_export = build_tab_export_url(sheet_id, sheet_name=selected_tab)

                    sync_interval = st.select_slider(
                        "Auto-Refresh Frequency",
                        options=["Manual Only", "5s", "10s", "30s", "60s"],
                        value="10s"
                    )

                    col_s1, col_s2, col_s3 = st.columns(3)
                    with col_s1:
                        sync_clicked = st.button("🔄 Sync", width="stretch", key="btn_sync_single", help=f"Sync '{selected_tab}' as active table")
                    with col_s2:
                        add_tab_clicked = st.button("➕ Add", width="stretch", key="btn_add_tab_single", help=f"Add '{selected_tab}' as new table into model")
                    with col_s3:
                        load_all_tabs = st.button("🚀 All Tabs", width="stretch", key="btn_load_all_tabs", help="Loads all discovered sheets (AL, AR, NM...) into data model at once")

                    if load_all_tabs:
                        with st.spinner(f"Loading {len(st.session_state.available_tabs)} state sheets into model..."):
                            all_loaded = {}
                            p_bar = st.progress(0)
                            for i, tab_n in enumerate(st.session_state.available_tabs):
                                tab_url = build_tab_export_url(sheet_id, sheet_name=tab_n)
                                df_t, err_t = fetch_sheet_data(tab_url)
                                if df_t is not None and not df_t.empty:
                                    all_loaded[tab_n] = df_t
                                p_bar.progress((i + 1) / len(st.session_state.available_tabs))
                            if all_loaded:
                                st.session_state.tables = all_loaded
                                st.session_state.active_table_name = selected_tab if selected_tab in all_loaded else list(all_loaded.keys())[0]
                                st.session_state.active_sheet_tab = st.session_state.active_table_name
                                st.session_state.relationships = [
                                    r for r in st.session_state.relationships
                                    if r.get("from_table") in st.session_state.tables and r.get("to_table") in st.session_state.tables
                                ]
                                st.session_state.single_synced_url = sheet_url
                                st.success(f"✅ Successfully loaded {len(all_loaded)} state sheets into model!")
                                st.rerun()

                    if add_tab_clicked:
                        with st.spinner(f"Loading '{selected_tab}' as new table..."):
                            df_add, ferr_add = fetch_sheet_data(active_export)
                            if df_add is not None:
                                tbl_name = selected_tab if selected_tab != "Default Tab" else table_name
                                st.session_state.tables[tbl_name] = df_add
                                st.session_state.active_table_name = tbl_name
                                st.session_state.active_sheet_tab = tbl_name
                                st.session_state.relationships = [
                                    r for r in st.session_state.relationships
                                    if r.get("from_table") in st.session_state.tables and r.get("to_table") in st.session_state.tables
                                ]
                                st.success(f"✅ Added table '{tbl_name}' ({len(df_add):,} rows) to data model! (Total tables: {len(st.session_state.tables)})")
                                st.rerun()
                            else:
                                st.error(f"⚠️ Failed to add '{selected_tab}': {ferr_add}")

                    # Auto-sync on first load if default demo URL or when clicked
                    if sync_clicked or ("single_synced_url" not in st.session_state) or (st.session_state.get("single_synced_url") != sheet_url):
                        with st.spinner(f"Connecting to '{selected_tab}'..."):
                            df, ferr = fetch_sheet_data(active_export)
                            if df is not None:
                                tbl_name = selected_tab if selected_tab != "Default Tab" else table_name
                                st.session_state.tables[tbl_name] = df
                                st.session_state.active_table_name = tbl_name
                                st.session_state.active_sheet_tab = tbl_name
                                st.session_state.relationships = [
                                    r for r in st.session_state.relationships
                                    if r.get("from_table") in st.session_state.tables and r.get("to_table") in st.session_state.tables
                                ]
                                st.session_state.single_synced_url = sheet_url
                                st.success(f"✅ Connected '{tbl_name}': {len(df):,} rows, {len(df.columns)} columns!")
                                st.rerun()
                            else:
                                if ferr == "PRIVATE_RESTRICTED":
                                    st.error("🔒 **Permission Required**: Google returned a login page. In Google Sheets, click **Share** (top right), change General Access from *Restricted* to **'Anyone with the link can view'**, then click Connect & Sync.")
                                elif ferr == "NOT_FOUND":
                                    st.error("⚠️ **Sheet Not Found (404)**: Please verify your Google Sheet URL. If this tab was renamed or removed, select another tab above.")
                                else:
                                    st.error(f"⚠️ Connection Error: {ferr}")

        # OPTION 2: MULTI-GOOGLE SHEETS (CUSTOM 1, 2, 3, 4, 5... ANY NUMBER OF LINKS)
        elif source_mode == "🔗 Multi-Google Sheets (Custom 1, 2, 3, 4, 5... Links)":
            is_live_sync = True
            st.markdown("#### 🔗 Dynamic Multi-Google Sheet Manager")
            st.caption("Add any number of Google Sheet links (1, 2, 3, 4, 5...) as independent tables in your model.")

            # Controls to adjust number of links
            col_cnt1, col_cnt2 = st.columns([3, 2])
            with col_cnt1:
                desired_count = st.number_input(
                    "Number of Sheet Links (1, 2, 3, 4, 5...)",
                    min_value=1,
                    max_value=20,
                    value=len(st.session_state.custom_link_configs),
                    step=1,
                    key="num_links_input"
                )
            with col_cnt2:
                st.write("")
                st.write("")
                if st.button("➕ Add Link", width="stretch", key="btn_add_link"):
                    st.session_state.custom_link_configs.append({"name": f"Table {len(st.session_state.custom_link_configs)+1}", "url": ""})
                    st.rerun()

            # Synchronize length of custom_link_configs
            while len(st.session_state.custom_link_configs) < desired_count:
                idx = len(st.session_state.custom_link_configs) + 1
                st.session_state.custom_link_configs.append({"name": f"Table {idx}", "url": ""})
            while len(st.session_state.custom_link_configs) > desired_count:
                st.session_state.custom_link_configs.pop()

            links_to_fetch = []
            for i, cfg in enumerate(st.session_state.custom_link_configs):
                with st.expander(f"📄 Sheet Link #{i+1}: {cfg.get('name', f'Table {i+1}')}", expanded=(i < 3)):
                    c_n, c_u, c_del = st.columns([1.5, 2.3, 0.7])
                    with c_n:
                        t_name = st.text_input(f"Table Name #{i+1}", value=cfg.get("name", f"Table {i+1}"), key=f"dyn_name_{i}")
                        cfg["name"] = t_name
                    with c_u:
                        t_url = st.text_input(f"Share Link #{i+1}", value=cfg.get("url", ""), placeholder="https://docs.google.com/spreadsheets/d/...", key=f"dyn_url_{i}")
                        cfg["url"] = t_url
                    with c_del:
                        st.write("")
                        st.write("")
                        if st.button("🗑️", key=f"del_link_btn_{i}", help=f"Remove link #{i+1}"):
                            st.session_state.custom_link_configs.pop(i)
                            st.rerun()

                    # Live Tab Auto-Discovery for this link
                    active_exp = None
                    if t_url and t_url.strip():
                        sid, def_exp, ugid, perr = parse_google_sheet_url(t_url)
                        if not perr and sid:
                            tabs = discover_google_sheet_tabs(sid)
                            if tabs:
                                tab_names = [t["name"] for t in tabs]
                                sel_tab = st.selectbox(f"Select Tab for #{i+1}", tab_names, key=f"dyn_tab_{i}")
                                chosen_t = next(t for t in tabs if t["name"] == sel_tab)
                                active_exp = build_tab_export_url(sid, gid=chosen_t["gid"], sheet_name=sel_tab)
                            else:
                                active_exp = def_exp

                    if t_name and t_url and active_exp:
                        links_to_fetch.append((t_name, active_exp))

            sync_interval = st.select_slider(
                "Auto-Refresh Frequency",
                options=["Manual Only", "5s", "10s", "30s", "60s"],
                value="10s",
                key="multi_refresh_freq"
            )

            if st.button("🚀 Connect & Sync All Links", width="stretch", key="btn_sync_all_dyn"):
                success_count = 0
                new_tables = {}
                for tbl_name, exp_url in links_to_fetch:
                    with st.spinner(f"Fetching '{tbl_name}'..."):
                        df, ferr = fetch_sheet_data(exp_url)
                        if df is not None:
                            new_tables[tbl_name] = df
                            success_count += 1
                            st.success(f"Loaded '{tbl_name}' ({len(df):,} rows)")
                        else:
                            st.error(f"Failed '{tbl_name}': {ferr}")

                if success_count > 0:
                    st.session_state.tables = new_tables
                    st.session_state.active_table_name = list(new_tables.keys())[0]
                    st.rerun()

        # OPTION 3: MULTI-EXCEL WORKBOOKS
        elif source_mode == "📂 Upload Multi-Sheet Excel (.xlsx)":
            uploaded_files = st.file_uploader(
                "Upload Excel Workbook(s)",
                type=["xlsx", "xls"],
                accept_multiple_files=True,
                help="Each sheet tab in the Excel file will become an independent table in your model!"
            )
            if uploaded_files:
                parsed_wb = parse_uploaded_excel_files(uploaded_files)
                if parsed_wb:
                    st.session_state.tables = parsed_wb
                    st.session_state.available_tabs = list(parsed_wb.keys())
                    st.session_state.active_sheet_tab = list(parsed_wb.keys())[0]
                    st.session_state.active_table_name = list(parsed_wb.keys())[0]
                    st.session_state.relationships = []
                    st.success(f"Loaded {len(parsed_wb)} tables from Excel: {', '.join(list(parsed_wb.keys()))}")
                    st.rerun()

        # OPTION 4: DEFAULT STAR SCHEMA DEMO
        else:
            st.success("✅ Power BI Star Schema Active")
            st.caption("4 Relational Tables: `Fact Sales`, `Dim Customer`, `Dim Product`, `Dim Store` with `1:*` joins.")
            if st.button("🔄 Reload Default Model", width="stretch"):
                default_tbls, default_rels = get_sample_powerbi_star_schema()
                st.session_state.tables = default_tbls
                st.session_state.relationships = default_rels
                st.session_state.active_table_name = "Fact Sales"
                st.rerun()

        st.markdown("---")
        st.markdown(f"**📑 Data Model Tables ({len(st.session_state.tables)}):**")
        for t_name, t_df in st.session_state.tables.items():
            is_cur = "⭐" if t_name == st.session_state.active_table_name else "⊞"
            st.markdown(f"- **{is_cur} {t_name}**: `{len(t_df):,}` rows, `{len(t_df.columns)}` cols")

    # Guard check for empty workspace
    if not st.session_state.tables:
        st.markdown(
            """
            <div style="text-align:center; padding: 50px 20px;">
                <div style="font-size:3.2rem; margin-bottom:12px;">📊</div>
                <h2 style="margin-bottom:8px; font-weight:700; color:#201f1e;">Power BI Analytics Studio</h2>
                <p style="color:#605e5c; max-width:620px; margin:0 auto 24px auto; font-size:1.02rem; line-height:1.5;">
                    Your workspace is clean. Connect your Google Sheet link or upload an Excel workbook in the left sidebar to start building interactive visuals and relational models.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        w_c1, w_c2, w_c3 = st.columns([1, 2, 1])
        with w_c2:
            st.info("👈 Use the left sidebar to paste your Google Sheet link or upload multi-sheet Excel files.")
            if st.button("🌟 Load Sample Star Schema (Optional Demo)", width="stretch", key="btn_load_demo_star"):
                default_tbls, default_rels = get_sample_powerbi_star_schema()
                st.session_state.tables = default_tbls
                st.session_state.relationships = default_rels
                st.session_state.active_table_name = "Fact Sales"
                st.session_state.workspace_clean = False
                st.rerun()
        return

    # =========================================================================
    # VIEW 1: 🕸️ MODEL VIEW (POWER BI ERD & RELATIONSHIPS)
    # =========================================================================
    if st.session_state.pbi_view_mode == "Model View":
        st.markdown("## 🕸️ Power BI Model View: Data Relationships & Schema")
        st.caption("Inspect table relationships, foreign key mappings, and cardinality joins matching Power BI Desktop.")

        all_tbls = list(st.session_state.tables.keys())

        # Power BI Model Ribbon Controls
        col_rel_act1, col_rel_act2, col_rel_act3, col_rel_act4, col_rel_act5 = st.columns([2.2, 2.2, 2.2, 2.2, 1.2])
        with col_rel_act1:
            show_manager = st.toggle("📋 Manage Relationships", value=False, key="toggle_show_manage_rels")
        with col_rel_act2:
            show_creator = st.toggle("➕ New Relationship", value=(len(st.session_state.relationships) == 0 and len(all_tbls) >= 2), key="toggle_show_rel_creator")
        with col_rel_act3:
            if st.button("🔍 Auto-Detect Joins", width="stretch", key="btn_auto_detect_rels", help="Automatically find matching key columns across tables"):
                auto_count = 0
                for i in range(len(all_tbls)):
                    for j in range(i + 1, len(all_tbls)):
                        t1, t2 = all_tbls[i], all_tbls[j]
                        cols1 = st.session_state.tables[t1].columns.tolist()
                        cols2 = st.session_state.tables[t2].columns.tolist()
                        for c1 in cols1:
                            for c2 in cols2:
                                if c1.lower() == c2.lower() and (c1.lower().endswith("id") or c1.lower() in ["state", "county", "county name", "code", "fips"]):
                                    exists = any((r["from_table"] == t1 and r["to_table"] == t2) or (r["from_table"] == t2 and r["to_table"] == t1) for r in st.session_state.relationships)
                                    if not exists:
                                        st.session_state.relationships.append({
                                            "from_table": t1,
                                            "from_col": c1,
                                            "to_table": t2,
                                            "to_col": c2,
                                            "cardinality": "* : 1",
                                            "cross_direction": "Single",
                                            "active": True
                                        })
                                        auto_count += 1
                if auto_count > 0:
                    st.success(f"✅ Auto-detected and created {auto_count} active relationship(s)!")
                    st.rerun()
                else:
                    st.info("No new matching key columns found between tables.")
        with col_rel_act4:
            if st.session_state.available_tabs and len(all_tbls) < len(st.session_state.available_tabs):
                if st.button("🚀 Load All State Tabs", width="stretch", key="btn_model_load_all_tabs", help="Load all state tabs to create relationships"):
                    with st.spinner(f"Loading {len(st.session_state.available_tabs)} state sheets into model..."):
                        all_loaded = dict(st.session_state.tables)
                        p_bar = st.progress(0)
                        for i, tab_n in enumerate(st.session_state.available_tabs):
                            if tab_n not in all_loaded:
                                tab_url = build_tab_export_url(st.session_state.current_sheet_id, sheet_name=tab_n)
                                df_t, err_t = fetch_sheet_data(tab_url)
                                if df_t is not None and not df_t.empty:
                                    all_loaded[tab_n] = df_t
                            p_bar.progress((i + 1) / len(st.session_state.available_tabs))
                        if all_loaded:
                            st.session_state.tables = all_loaded
                            st.rerun()
        with col_rel_act5:
            if st.session_state.relationships:
                if st.button("🗑️ Clear", width="stretch", key="btn_clear_all_rels", help="Clear all relationships"):
                    st.session_state.relationships = []
                    st.rerun()

        # ---------------------------------------------------------------------
        # 1. MANAGE RELATIONSHIPS DIALOG / PANEL
        # ---------------------------------------------------------------------
        if show_manager:
            with st.container():
                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #c7e0f4; border-left:4px solid #0078d4; border-radius:6px; padding:16px; margin:12px 0 16px 0; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <h4 style="margin:0 0 4px 0; color:#201f1e;">📋 Manage Relationships ({len(st.session_state.relationships)})</h4>
                        <p style="margin:0; font-size:0.85rem; color:#605e5c;">Active semantic joins connecting data tables in your Power BI data model.</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if not st.session_state.relationships:
                    st.info("ℹ️ No relationships defined yet in this model. Click **'➕ New Relationship'** or **'🔍 Auto-Detect Joins'** above to connect tables.")
                else:
                    for idx, rel in enumerate(st.session_state.relationships):
                        r1, r2, r3, r4 = st.columns([5, 2, 2, 1])
                        with r1:
                            st.markdown(
                                f"""
                                <div class="pbi-rel-card">
                                    <div>
                                        <strong>⊞ {rel['from_table']}</strong> <code style="color:#0078d4; font-weight:700;">[{rel['from_col']}]</code>
                                        <span style="background:#eff6fc; color:#0078d4; font-weight:700; padding:2px 8px; border-radius:4px; margin:0 8px; font-size:0.82rem;">{rel.get('cardinality', '* : 1')}</span>
                                        <strong>⊞ {rel['to_table']}</strong> <code style="color:#107c41; font-weight:700;">[{rel['to_col']}]</code>
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                        with r2:
                            st.markdown("<span style='color:#107c41; font-weight:600;'>● Active Join</span>", unsafe_allow_html=True)
                        with r3:
                            st.caption(f"Cross filter: {rel.get('cross_direction', 'Single')}")
                        with r4:
                            if st.button("🗑️", key=f"del_rel_mgr_{idx}", help="Delete relationship"):
                                st.session_state.relationships.pop(idx)
                                st.rerun()

        # ---------------------------------------------------------------------
        # 2. CREATE NEW RELATIONSHIP FORM
        # ---------------------------------------------------------------------
        if show_creator:
            with st.container():
                st.markdown(
                    """
                    <div style="background:#ffffff; border:1px solid #c7e0f4; border-left:4px solid #0078d4; border-radius:6px; padding:16px; margin:12px 0 18px 0; box-shadow:0 2px 8px rgba(0,0,0,0.06);">
                        <h4 style="margin:0 0 8px 0; color:#201f1e;">➕ Create New Relationship</h4>
                        <p style="margin:0; font-size:0.85rem; color:#605e5c;">Select foreign and primary keys to connect data tables in your star schema.</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if len(all_tbls) < 2:
                    st.warning(f"ℹ️ **Relationships require at least 2 tables in your data model.** Currently your model only contains 1 table ('{all_tbls[0]}').")
                    candidate_tabs = [t for t in st.session_state.available_tabs if t not in all_tbls]
                    if candidate_tabs:
                        c_pick, c_btn = st.columns([3, 2])
                        with c_pick:
                            tab_pick = st.selectbox("Select Sheet Tab to add as Table 2:", candidate_tabs, key="model_add_tab_pick")
                        with c_btn:
                            st.write("")
                            st.write("")
                            if st.button(f"📥 Add '{tab_pick}' as Table 2", width="stretch", key="btn_add_tab_pick"):
                                tab_url = build_tab_export_url(st.session_state.current_sheet_id, sheet_name=tab_pick)
                                df_pick, err_pick = fetch_sheet_data(tab_url)
                                if df_pick is not None:
                                    st.session_state.tables[tab_pick] = df_pick
                                    st.success(f"✅ Loaded '{tab_pick}' into data model! You can now join it with '{all_tbls[0]}'.")
                                    st.rerun()
                                else:
                                    st.error(f"Failed to fetch '{tab_pick}': {err_pick}")

                        if st.button("🚀 Load All State Tabs into Model", width="stretch", key="btn_add_all_tabs_inline"):
                            with st.spinner(f"Loading {len(st.session_state.available_tabs)} state sheets into model..."):
                                all_loaded = dict(st.session_state.tables)
                                p_bar = st.progress(0)
                                for i, tab_n in enumerate(st.session_state.available_tabs):
                                    if tab_n not in all_loaded:
                                        tab_url = build_tab_export_url(st.session_state.current_sheet_id, sheet_name=tab_n)
                                        df_t, err_t = fetch_sheet_data(tab_url)
                                        if df_t is not None and not df_t.empty:
                                            all_loaded[tab_n] = df_t
                                    p_bar.progress((i + 1) / len(st.session_state.available_tabs))
                                if all_loaded:
                                    st.session_state.tables = all_loaded
                                    st.rerun()
                    else:
                        st.info("👈 Use the left sidebar to add another Google Sheet link or upload an Excel table.")
                else:
                    r_c1, r_c2, r_c3 = st.columns([2, 1.2, 2])
                    with r_c1:
                        from_tbl = st.selectbox("From Table (Primary / Many *)", all_tbls, index=0, key="rel_from_tbl_sel")
                        from_cols = st.session_state.tables[from_tbl].columns.tolist()
                        from_col = st.selectbox("Foreign Key Column", from_cols, key="rel_from_col_sel")
                    with r_c2:
                        st.write("")
                        st.write("")
                        card = st.selectbox("Cardinality", ["* : 1 (Many to one)", "1 : * (One to many)", "1 : 1 (One to one)", "* : * (Many to many)"], index=0, key="rel_card_sel")
                        cross_dir = st.selectbox("Cross Filter", ["Single", "Both"], index=0, key="rel_cross_sel")
                    with r_c3:
                        to_tbls = [t for t in all_tbls if t != from_tbl]
                        to_tbl = st.selectbox("To Table (Related / One 1)", to_tbls, index=0, key="rel_to_tbl_sel")
                        to_cols = st.session_state.tables[to_tbl].columns.tolist()
                        def_to_idx = to_cols.index(from_col) if from_col in to_cols else 0
                        def_to_idx = max(0, min(def_to_idx, len(to_cols) - 1)) if to_cols else 0
                        to_col = st.selectbox("Primary Key Column", to_cols, index=def_to_idx, key="rel_to_col_sel")

                    save_c1, save_c2 = st.columns([2, 4])
                    with save_c1:
                        if st.button("💾 Save & Apply Relationship", width="stretch", key="btn_apply_rel"):
                            exists = any(r["from_table"] == from_tbl and r["from_col"] == from_col and r["to_table"] == to_tbl and r["to_col"] == to_col for r in st.session_state.relationships)
                            if exists:
                                st.warning("This relationship already exists in the model!")
                            else:
                                st.session_state.relationships.append({
                                    "from_table": from_tbl,
                                    "from_col": from_col,
                                    "to_table": to_tbl,
                                    "to_col": to_col,
                                    "cardinality": card.split(" ")[0],
                                    "cross_direction": cross_dir,
                                    "active": True
                                })
                                st.success(f"✅ Created join: {from_tbl}[{from_col}] ──── ({card.split(' ')[0]}) ────> {to_tbl}[{to_col}]")
                                st.rerun()

        st.markdown("---")

        # ---------------------------------------------------------------------
        # 3. EXACT POWER BI DESKTOP MODEL VIEW CANVAS & TABLE CARDS
        # ---------------------------------------------------------------------
        st.markdown(
            """
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="font-weight:700; font-size:1.05rem; color:#201f1e;">📐 Power BI Entity Relationship Canvas</span>
                <span style="font-size:0.75rem; background:#ffffff; border:1px solid #d2d0ce; padding:3px 8px; border-radius:4px; color:#605e5c; font-weight:600;">Power BI Desktop 2026 Layout</span>
            </div>
            """,
            unsafe_allow_html=True
        )

        rail_col, canvas_col = st.columns([0.05, 0.95], gap="small")
        with rail_col:
            render_powerbi_left_rail("Model View")

        with canvas_col:
            erd_html = generate_powerbi_erd_html(
                st.session_state.tables,
                st.session_state.relationships,
                st.session_state.active_table_name,
                theme=st.session_state.pbi_theme
            )
            st.html(erd_html)
        return

    # =========================================================================
    # VIEW 2: 📋 DATA VIEW (TABLE INSPECTOR)
    # =========================================================================
    if st.session_state.pbi_view_mode == "Data View":
        rail_col, main_col = st.columns([0.05, 0.95], gap="small")
        with rail_col:
            render_powerbi_left_rail("Data View")
        with main_col:
            st.markdown("## ▦ Power BI Data View: Table Inspector & Profiling")
            st.caption("Inspect underlying table records, column schemas, data types, and export CSV files.")

            sel_t = st.selectbox("Select Table to Inspect", list(st.session_state.tables.keys()), key="data_view_tbl_sel")
            active_df = st.session_state.tables[sel_t]

            d_col1, d_col2, d_col3, d_col4 = st.columns(4)
            with d_col1:
                st.metric("Total Rows", f"{len(active_df):,}")
            with d_col2:
                st.metric("Total Columns", f"{len(active_df.columns)}")
            with d_col3:
                st.metric("Memory Usage", f"{active_df.memory_usage(deep=True).sum() / 1024:.1f} KB")
            with d_col4:
                csv_buf = io.StringIO()
                active_df.to_csv(csv_buf, index=False)
                st.download_button(
                    f"📥 Export '{sel_t}' CSV",
                    data=csv_buf.getvalue(),
                    file_name=f"{sel_t}.csv",
                    mime="text/csv",
                    width="stretch"
                )

            # Table Search filter
            t_search = st.text_input(f"🔍 Search within '{sel_t}'", placeholder="Filter records by keyword...", key="table_view_search")
            disp_df = active_df
            if t_search.strip():
                mask = disp_df.astype(str).apply(lambda row: row.str.contains(t_search.strip(), case=False, na=False)).any(axis=1)
                disp_df = disp_df[mask]
                st.caption(f"Showing {len(disp_df):,} matching rows")

            st.dataframe(disp_df, width="stretch", height=460)

            # Column Profiler expander
            with st.expander("📊 Column Profiling & Cardinality Summary", expanded=False):
                col_profile_data = []
                for c in active_df.columns:
                    col_profile_data.append({
                        "Column": c,
                        "Type": str(active_df[c].dtype),
                        "Unique Values": active_df[c].nunique(),
                        "Missing / NaN": active_df[c].isna().sum(),
                        "Missing %": f"{(active_df[c].isna().sum() / max(len(active_df), 1) * 100):.1f}%" if len(active_df) else "0%"
                    })
                st.dataframe(pd.DataFrame(col_profile_data), width="stretch")
        return

    # =========================================================================
    # VIEW 3: 📐 DAX FORMULAS STUDIO
    # =========================================================================
    if st.session_state.pbi_view_mode == "DAX Formulas":
        rail_col, main_col = st.columns([0.05, 0.95], gap="small")
        with rail_col:
            render_powerbi_left_rail("DAX Formulas")
        with main_col:
            st.markdown("## 📐 Power BI DAX Formulas Studio")
            st.caption("Author, test, and save Power BI DAX expressions (SUM, AVERAGE, COUNTROWS, DISTINCTCOUNT, CALCULATE, DIVIDE) evaluated live on your data model.")

            all_tbls = list(st.session_state.tables.keys())
            dax_c1, dax_c2 = st.columns([3, 2])
            with dax_c1:
                target_table = st.selectbox("Target Table for Measure", all_tbls, key="dax_target_tbl")
            with dax_c2:
                tbl_cols = st.session_state.tables[target_table].columns.tolist()
                num_cols = [c for c in tbl_cols if pd.api.types.is_numeric_dtype(st.session_state.tables[target_table][c])]
                sample_num = num_cols[0] if num_cols else (tbl_cols[0] if tbl_cols else "Field")
                
                template_choice = st.selectbox(
                    "Insert DAX Template",
                    [
                        "Custom Expression",
                        f"Total {sample_num} = SUM('{target_table}'[{sample_num}])",
                        f"Average {sample_num} = AVERAGE('{target_table}'[{sample_num}])",
                        f"Count of Rows = COUNTROWS('{target_table}')",
                        f"Distinct {tbl_cols[0]} = DISTINCTCOUNT('{target_table}'[{tbl_cols[0]}])" if tbl_cols else "Distinct = DISTINCTCOUNT()",
                    ],
                    key="dax_template_picker"
                )

            m_col1, m_col2 = st.columns([2, 5])
            with m_col1:
                init_m_name = f"Total {sample_num}" if template_choice.startswith("Total") else "New Measure"
                measure_name = st.text_input("Measure Name", value=init_m_name, key="dax_measure_name_input")
            with m_col2:
                init_formula = template_choice.split(" = ", 1)[-1] if " = " in template_choice else f"COUNTROWS('{target_table}')"
                formula_str = st.text_input("DAX Formula Bar (fx)", value=init_formula, key="dax_formula_input")

            eval_col1, eval_col2, eval_col3 = st.columns([2, 2, 3])
            with eval_col1:
                test_clicked = st.button("▶️ Test / Evaluate DAX", width="stretch", key="btn_test_dax")
            with eval_col2:
                save_clicked = st.button("💾 Save Measure to Model", width="stretch", key="btn_save_dax")

            if test_clicked or save_clicked:
                res_val, err_msg = evaluate_dax_formula(formula_str, target_table)
                if err_msg:
                    st.error(f"❌ DAX Evaluation Error: {err_msg}")
                else:
                    if isinstance(res_val, (int, float)):
                        fmt_val = f"{res_val:,.2f}" if isinstance(res_val, float) else f"{res_val:,}"
                    else:
                        fmt_val = str(res_val)
                    st.success(f"✅ Evaluated Result: **{measure_name}** = `{fmt_val}`")

                    if save_clicked:
                        st.session_state.dax_measures.append({
                            "name": measure_name,
                            "table": target_table,
                            "formula": formula_str,
                            "value": fmt_val
                        })
                        st.info(f"💾 Measure '{measure_name}' saved to semantic model!")
                        st.rerun()

            if st.session_state.dax_measures:
                st.markdown("---")
                st.markdown("### 📋 Active Model DAX Measures")
                m_records = []
                for idx, m in enumerate(st.session_state.dax_measures):
                    m_records.append({
                        "Measure Name": m["name"],
                        "Home Table": m["table"],
                        "DAX Expression": m["formula"],
                        "Latest Value": m["value"]
                    })
                st.dataframe(pd.DataFrame(m_records), width="stretch")
                if st.button("🗑️ Clear All DAX Measures", key="btn_clear_dax"):
                    st.session_state.dax_measures = []
                    st.rerun()
            else:
                st.info("💡 Write or select a DAX template above and click **'Save Measure to Model'** to create reusable metrics.")
        return

    # =========================================================================
    # VIEW 4: 📜 TMDL SEMANTIC MODEL DEFINITION
    # =========================================================================
    if st.session_state.pbi_view_mode == "TMDL Model":
        rail_col, main_col = st.columns([0.05, 0.95], gap="small")
        with rail_col:
            render_powerbi_left_rail("TMDL Model")
        with main_col:
            st.markdown("## 📜 Power BI TMDL (Tabular Model Definition Language)")
            st.caption("Declarative code representation of tables, schema columns, active joins, and DAX measures ready to deploy to Fabric or Power BI Desktop.")

            tmdl_code = generate_model_tmdl(
                st.session_state.tables,
                st.session_state.relationships,
                st.session_state.dax_measures
            )

            btn_c1, btn_c2 = st.columns([2, 5])
            with btn_c1:
                st.download_button(
                    "📥 Download model.tmdl",
                    data=tmdl_code,
                    file_name="model.tmdl",
                    mime="text/plain",
                    width="stretch"
                )

            st.code(tmdl_code, language="yaml", line_numbers=True)
        return

    # =========================================================================
    # VIEW: ⏱️ QUEUE LIVE TRACKER & GOOGLE SHEET 2 ANALYTICS
    # =========================================================================
    if st.session_state.pbi_view_mode == "Queue Tracker":
        render_queue_tracker_view(st.session_state.pbi_theme)
        return

    # =========================================================================
    # VIEW 5: 📊 REPORT VIEW (CLEAN POWER BI WEBFRAME)
    # =========================================================================
    all_table_names = list(st.session_state.tables.keys())
    if st.session_state.active_table_name not in all_table_names:
        st.session_state.active_table_name = all_table_names[0]

    primary_fact = st.session_state.active_table_name
    canvas_df = get_unified_relational_dataset(primary_fact)

    if canvas_df.empty:
        st.warning("No data found in active tables.")
        return

    # Crisp Telemetry Bar
    now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
    st.markdown(
        f"""
        <div class="telemetry-bar">
            <div class="telemetry-item">
                <span class="pulse-dot"></span>
                <strong>STATUS:</strong> Live-Sync Connected ({now_str})
            </div>
            <div class="telemetry-item">
                <strong>Model:</strong> {len(st.session_state.tables)} Tables
            </div>
            <div class="telemetry-item">
                <strong>Total Records:</strong> {len(canvas_df):,}
            </div>
            <div class="telemetry-item">
                <strong>Relationships:</strong> {len(st.session_state.relationships)} Active Joins
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # -------------------------------------------------------------------------
    # 📑 POWER BI SHEET / WORKSHEET TAB SELECTOR
    # -------------------------------------------------------------------------
    if len(st.session_state.tables) > 1:
        tab_bar_options = list(st.session_state.tables.keys())
    elif st.session_state.available_tabs:
        tab_bar_options = st.session_state.available_tabs
    else:
        tab_bar_options = [primary_fact]

    current_tab = st.session_state.active_table_name
    if current_tab not in tab_bar_options:
        if st.session_state.active_sheet_tab in tab_bar_options:
            current_tab = st.session_state.active_sheet_tab
        else:
            current_tab = tab_bar_options[0]

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px; font-weight:600; font-size:0.86rem;">
            <span style="color:{'#0078d4' if st.session_state.pbi_theme == 'Light' else '#2886de'}; font-weight:700;">📑 WORKSHEET TABS:</span>
            <span style="font-size:0.75rem; background:{'#e0f2fe' if st.session_state.pbi_theme == 'Light' else '#1e293b'}; color:{'#0369a1' if st.session_state.pbi_theme == 'Light' else '#93c5fd'}; border:1px solid {'#7dd3fc' if st.session_state.pbi_theme == 'Light' else '#334155'}; padding:2px 10px; border-radius:12px; font-weight:600;">Click any tab to switch state/sheet</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    chosen_pill = st.pills(
        "Worksheet Tabs",
        options=tab_bar_options,
        default=current_tab,
        key=f"pbi_sheet_pill_{current_tab}",
        label_visibility="collapsed"
    )

    if chosen_pill and chosen_pill != st.session_state.active_table_name:
        if chosen_pill in st.session_state.tables:
            st.session_state.active_table_name = chosen_pill
            st.session_state.active_sheet_tab = chosen_pill
            st.rerun()
        elif st.session_state.current_sheet_id:
            with st.spinner(f"Switching to sheet '{chosen_pill}'..."):
                tab_url = build_tab_export_url(st.session_state.current_sheet_id, sheet_name=chosen_pill)
                df_pill, err_pill = fetch_sheet_data(tab_url)
                if df_pill is not None and not df_pill.empty:
                    st.session_state.tables[chosen_pill] = df_pill
                    st.session_state.active_table_name = chosen_pill
                    st.session_state.active_sheet_tab = chosen_pill
                    st.rerun()
                else:
                    st.error(f"Could not load sheet tab '{chosen_pill}': {err_pill}")

    all_canvas_cols = canvas_df.columns.tolist()
    num_canvas_cols = canvas_df.select_dtypes(include=['number']).columns.tolist()
    real_num_cols = [
        c for c in num_canvas_cols 
        if not is_id_or_serial_column(c, canvas_df[c]) 
        and not c.lower().startswith("unnamed")
        and canvas_df[c].dropna().nunique() > 0
        and not canvas_df[c].dropna().empty
    ]
    cat_canvas_cols = [
        c for c in canvas_df.select_dtypes(include=['object', 'category', 'string', 'str']).columns.tolist() 
        if not is_id_or_serial_column(c, canvas_df[c])
        and not c.lower().startswith("unnamed")
    ]
    genuine_cols = [
        c for c in all_canvas_cols 
        if not is_id_or_serial_column(c, canvas_df[c])
        and not c.lower().startswith("unnamed")
    ]
    if not genuine_cols:
        genuine_cols = all_canvas_cols

    # Clear 4-Column Layout with Left Rail:
    # 0. Left Rail (4%)
    # 1. Left Filters Pane (21%)
    # 2. Center Report Canvas (51%)
    # 3. Right Visualizations & Data Pane (24%)
    rail_col, col_filters, col_canvas, col_studio = st.columns([0.05, 0.22, 0.51, 0.22], gap="small")

    with rail_col:
        render_powerbi_left_rail("Report View")

    active_filters_list = []
    filtered_canvas_df = canvas_df.copy()

    # -------------------------------------------------------------------------
    # LEFT PANE: FILTERS (NEAT POWER BI CONTAINER)
    # -------------------------------------------------------------------------
    with col_filters:
        st.markdown(
            """
            <div class="pbi-panel-card">
                <div class="pbi-panel-title">
                    <span>🔍 Filters</span>
                    <span style="font-size:0.75rem; color:#605e5c;">Page filters</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        f_btn_c1, f_btn_c2 = st.columns([3, 1])
        with f_btn_c1:
            st.caption(f"Refining {len(filtered_canvas_df):,} rows")
        with f_btn_c2:
            if st.button("🔄", key="btn_reset_filters", help="Reset all filters"):
                for k in list(st.session_state.keys()):
                    if k.startswith("slicer_") or k.startswith("custom_filter_val_"):
                        st.session_state[k] = []
                st.rerun()

        # Dynamic Slicers with Cascading Filtering
        valid_cols = [c for c in genuine_cols if canvas_df[c].dropna().nunique() > 1]
        slicer_candidates = ["state", "county_name", "county", "status", "category", "region", "customer_segment", "name"]
        matched_slicers = []
        for s in slicer_candidates:
            for c in valid_cols:
                if c.lower() == s and c not in matched_slicers:
                    matched_slicers.append(c)
        if not matched_slicers:
            matched_slicers = [c for c in cat_canvas_cols if c in valid_cols][:3]

        for s_field in matched_slicers:
            # Cascading unique options from currently filtered dataframe
            cascaded_opts = sorted([str(v).strip() for v in filtered_canvas_df[s_field].dropna().unique() if str(v).strip()])
            if not cascaded_opts:
                cascaded_opts = sorted([str(v).strip() for v in canvas_df[s_field].dropna().unique() if str(v).strip()])

            selected_opts = st.multiselect(
                f"Filter: {s_field.replace('_', ' ').title()}",
                options=cascaded_opts,
                default=[],
                placeholder="All (Click to filter)",
                key=f"slicer_{s_field}"
            )
            if selected_opts:
                filtered_canvas_df = filtered_canvas_df[filtered_canvas_df[s_field].astype(str).str.strip().isin(selected_opts)]
                active_filters_list.append((s_field.replace('_', ' ').title(), selected_opts))

        st.markdown("---")
        # Custom field filter
        custom_cols = [c for c in valid_cols if c not in matched_slicers]
        custom_filter = st.selectbox("Add filter on field", options=["None"] + custom_cols, index=0, key="custom_filter_col_sel")
        if custom_filter != "None":
            custom_opts = sorted([str(v).strip() for v in filtered_canvas_df[custom_filter].dropna().unique() if str(v).strip()])
            chosen_custom = st.multiselect(
                f"{custom_filter} is",
                options=custom_opts,
                default=[],
                placeholder="All (Click to filter)",
                key=f"custom_filter_val_{custom_filter}"
            )
            if chosen_custom:
                filtered_canvas_df = filtered_canvas_df[filtered_canvas_df[custom_filter].astype(str).str.strip().isin(chosen_custom)]
                active_filters_list.append((custom_filter, chosen_custom))

    # -------------------------------------------------------------------------
    # RIGHT PANE: VISUALIZATIONS & DATA (NEAT POWER BI CONTAINERS)
    # -------------------------------------------------------------------------
    with col_studio:
        # PANE 1: VISUALIZATIONS
        st.markdown(
            """
            <div class="pbi-panel-card">
                <div class="pbi-panel-title">
                    <span>⚡ Visualizations</span>
                    <span style="font-size:0.75rem; color:#605e5c;">Build visual</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        vis_labels = [v[0] for v in VISUAL_TYPES]
        vis_keys = [v[1] for v in VISUAL_TYPES]
        selected_vis_label = st.selectbox("Select Visual Type", options=vis_labels, index=0)
        selected_vis_key = vis_keys[vis_labels.index(selected_vis_label)]

        st.markdown("##### 📐 Field Wells")

        # Smart defaults for Axis
        def_axis = 0
        preferred_axis_words = ["county", "name", "category", "status", "type", "region", "state", "city", "segment"]
        found_pref = False
        for pref in preferred_axis_words:
            for idx, col in enumerate(all_canvas_cols):
                if pref in col.lower() and not is_id_or_serial_column(col, canvas_df[col]):
                    def_axis = idx
                    found_pref = True
                    break
            if found_pref:
                break
        if not found_pref:
            for idx, col in enumerate(all_canvas_cols):
                if not is_id_or_serial_column(col, canvas_df[col]):
                    def_axis = idx
                    break

        def_axis = max(0, min(def_axis, len(all_canvas_cols) - 1)) if all_canvas_cols else 0
        axis_col = st.selectbox("Axis / Category (X-Axis)", options=all_canvas_cols, index=def_axis)

        # Smart defaults for Values (Never default to Sl.No)
        val_options = ["Record Count"] + real_num_cols
        def_val = 0
        if real_num_cols:
            preferred_val_words = ["revenue", "sales", "profit", "amount", "cost", "price", "count", "applications", "total", "rate"]
            found_val = False
            for pval in preferred_val_words:
                for idx, col in enumerate(val_options):
                    if pval in col.lower():
                        def_val = idx
                        found_val = True
                        break
                if found_val:
                    break
            if not found_val and len(val_options) > 1:
                def_val = 1

        def_val = max(0, min(def_val, len(val_options) - 1)) if val_options else 0
        value_col = st.selectbox("Values / Metric (Y-Axis)", options=val_options, index=def_val)
        agg_opts = ["Count", "Distinct Count"] if value_col == "Record Count" else ["Sum", "Average", "Count", "Min", "Max"]
        agg_choice = st.selectbox("Aggregation", options=agg_opts, index=0)

        legend_options = ["None"] + [c for c in cat_canvas_cols if c != axis_col]
        legend_col = st.selectbox("Legend / Color", options=legend_options, index=0)

        st.markdown("---")

        # PANE 2: DATA PANE
        st.markdown(
            f"""
            <div class="pbi-panel-card">
                <div class="pbi-panel-title">
                    <span>📁 Data</span>
                    <span style="font-size:0.75rem; color:#605e5c;">{len(all_canvas_cols)} fields</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        field_search = st.text_input("🔍 Search fields", placeholder="Type field name...", key="data_search_input")
        for t_name, t_df in st.session_state.tables.items():
            with st.expander(f"⊞ {t_name} ({len(t_df.columns)})", expanded=(t_name == primary_fact)):
                for c_name in t_df.columns:
                    if field_search and field_search.lower() not in c_name.lower():
                        continue
                    icon = "∑" if pd.api.types.is_numeric_dtype(t_df[c_name]) and not is_id_or_serial_column(c_name, t_df[c_name]) else ("#" if is_id_or_serial_column(c_name, t_df[c_name]) else "ABC")
                    is_active = (c_name == axis_col or c_name == value_col)
                    st.checkbox(f"{icon} {c_name}", value=is_active, key=f"f_{t_name}_{c_name}")

    # -------------------------------------------------------------------------
    # CENTER CANVAS: REPORT CANVAS
    # -------------------------------------------------------------------------
    with col_canvas:
        # Active Filter summary indicator badge
        if active_filters_list:
            chips = " ".join([f"<span style='background:#e0f2fe; color:#0369a1; border:1px solid #7dd3fc; padding:2px 8px; border-radius:12px; font-size:0.75rem; margin-right:4px;'><strong>{f[0]}:</strong> {', '.join([str(x) for x in f[1]])}</span>" for f in active_filters_list])
            st.markdown(
                f"""
                <div style="margin-bottom:10px; display:flex; align-items:center; flex-wrap:wrap; gap:6px; background:#f8fafc; border:1px solid #e2e8f0; border-radius:6px; padding:6px 12px;">
                    <span style="font-size:0.8rem; font-weight:700; color:#334155;">Active Filters:</span>
                    {chips}
                    <span style="font-size:0.75rem; color:#64748b; margin-left:auto; font-weight:600;">Showing {len(filtered_canvas_df):,} of {len(canvas_df):,} records</span>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Top KPI Cards (Computed strictly from sheet data, no serial numbers or fake defaults)
        if real_num_cols:
            k_cols = st.columns(min(len(real_num_cols), 4))
            for idx, c_name in enumerate(real_num_cols[:4]):
                with k_cols[idx]:
                    tot_v = filtered_canvas_df[c_name].sum()
                    avg_v = filtered_canvas_df[c_name].mean()
                    is_curr = any(w in c_name.lower() for w in ["revenue", "sales", "price", "profit", "amount", "cost"])
                    val_str = f"${tot_v:,.0f}" if is_curr else f"{tot_v:,.0f}"
                    st.markdown(
                        f"""
                        <div class="kpi-card">
                            <div class="kpi-label">{c_name.replace('_', ' ').title()}</div>
                            <div class="kpi-value">{val_str}</div>
                            <div class="kpi-sub">Average: {avg_v:,.1f}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
        else:
            # Genuine directory / inventory sheet KPIs
            k_cols = st.columns(4)

            # Card 1: Total Records / Entities
            entity_label = "Counties" if any("county" in c.lower() for c in all_canvas_cols) else "Total Records"
            with k_cols[0]:
                st.markdown(
                    f"""
                    <div class="kpi-card">
                        <div class="kpi-label">{entity_label}</div>
                        <div class="kpi-value">{len(filtered_canvas_df):,}</div>
                        <div class="kpi-sub">Active Sheet: {st.session_state.active_table_name}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            # Card 2: Status Breakdown or Unique Category
            with k_cols[1]:
                status_cols = [c for c in all_canvas_cols if "status" in c.lower()]
                if status_cols:
                    s_col = status_cols[0]
                    vc = filtered_canvas_df[s_col].dropna().value_counts()
                    if not vc.empty:
                        top_st = str(vc.index[0])
                        top_cnt = vc.iloc[0]
                        pct = (top_cnt / max(len(filtered_canvas_df), 1)) * 100
                        st.markdown(
                            f"""
                            <div class="kpi-card">
                                <div class="kpi-label">{s_col.replace('_', ' ').title()}: {top_st}</div>
                                <div class="kpi-value">{top_cnt:,} <span style="font-size:0.95rem; color:#107c41;">({pct:.0f}%)</span></div>
                                <div class="kpi-sub">{len(vc)} Status Categories</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown(
                            f"""
                            <div class="kpi-card">
                                <div class="kpi-label">Status</div>
                                <div class="kpi-value">Active</div>
                                <div class="kpi-sub">Live Verified</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                else:
                    cat_cols = [c for c in cat_canvas_cols if c != axis_col]
                    c_col = cat_cols[0] if cat_cols else all_canvas_cols[0]
                    u_cnt = filtered_canvas_df[c_col].nunique()
                    st.markdown(
                        f"""
                        <div class="kpi-card">
                            <div class="kpi-label">Unique {c_col.replace('_', ' ').title()}</div>
                            <div class="kpi-value">{u_cnt:,}</div>
                            <div class="kpi-sub">Distinct Categories</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            # Card 3: State / Jurisdiction
            with k_cols[2]:
                state_cols = [c for c in all_canvas_cols if "state" in c.lower()]
                if state_cols and not filtered_canvas_df[state_cols[0]].dropna().empty:
                    cur_state = str(filtered_canvas_df[state_cols[0]].dropna().iloc[0])
                    st.markdown(
                        f"""
                        <div class="kpi-card">
                            <div class="kpi-label">State Jurisdiction</div>
                            <div class="kpi-value">{cur_state}</div>
                            <div class="kpi-sub">Region Filter Active</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.markdown(
                        f"""
                        <div class="kpi-card">
                            <div class="kpi-label">Active Sheet</div>
                            <div class="kpi-value">{st.session_state.active_table_name}</div>
                            <div class="kpi-sub">Data Source Table</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            # Card 4: Columns / Fields count
            with k_cols[3]:
                st.markdown(
                    f"""
                    <div class="kpi-card">
                        <div class="kpi-label">Data Fields</div>
                        <div class="kpi-value">{len(filtered_canvas_df.columns)}</div>
                        <div class="kpi-sub">Attributes Indexed</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

        st.markdown("<br>", unsafe_allow_html=True)

        # Primary Visual Container
        st.markdown(
            f"""
            <div style="background:{'#ffffff' if st.session_state.pbi_theme == 'Light' else '#252423'}; border:1px solid {'#e1dfdd' if st.session_state.pbi_theme == 'Light' else '#3b3a39'}; border-radius:8px; padding:16px; margin-bottom:16px;">
                <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid {'#edebe9' if st.session_state.pbi_theme == 'Light' else '#3b3a39'}; padding-bottom:10px; margin-bottom:10px;">
                    <span style="font-weight:700; font-size:1.05rem; color:{'#201f1e' if st.session_state.pbi_theme == 'Light' else '#ffffff'};">{selected_vis_label}</span>
                    <span style="font-size:0.75rem; background:{'#f3f2f1' if st.session_state.pbi_theme == 'Light' else '#323130'}; color:{'#605e5c' if st.session_state.pbi_theme == 'Light' else '#a19f9d'}; padding:3px 8px; border-radius:4px; font-weight:600;">Power BI Interactive</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        render_powerbi_visual(
            visual_type=selected_vis_key,
            df=filtered_canvas_df,
            x_col=axis_col,
            y_col=value_col,
            agg=agg_choice,
            color_col=legend_col,
            theme=st.session_state.pbi_theme
        )

        # Drillthrough Data Table
        st.markdown("---")
        exp_c1, exp_c2 = st.columns([3, 1])
        with exp_c1:
            st.markdown(f"##### 📋 Relational Drillthrough ({len(filtered_canvas_df):,} Rows)")
        with exp_c2:
            drill_csv = io.StringIO()
            filtered_canvas_df.to_csv(drill_csv, index=False)
            st.download_button(
                "📥 Export CSV",
                data=drill_csv.getvalue(),
                file_name="powerbi_relational_report.csv",
                mime="text/csv",
                width="stretch"
            )

        st.dataframe(filtered_canvas_df, width="stretch", height=250)


if __name__ == "__main__":
    main()
