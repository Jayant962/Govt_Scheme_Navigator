"""
app.py

Government Scheme Recommendation Platform
Clean, light UI | Curated scheme database | At-most-5 results with Show More
"""

import json
import logging
import os
import sys
from html import escape
from datetime import datetime
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import streamlit as st
from dotenv import load_dotenv
load_dotenv()  # load GOOGLE_API_KEY from .env before any module initialization

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="GovtSchemeAI – Find Your Benefits",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)

from database.db_manager import DBManager
from modules.eligibility_engine import EligibilityEngine
from modules.ranking_engine import RankingEngine
from modules.vector_store import VectorStore
from modules.explanation_chain import ExplanationChain

logging.basicConfig(level=logging.WARNING)

# ── Constants ─────────────────────────────────────────────────────────────────
INDIAN_STATES = [
    "All India", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar",
    "Chhattisgarh", "Goa", "Gujarat", "Haryana", "Himachal Pradesh",
    "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi (NCT)", "Jammu & Kashmir", "Ladakh", "Puducherry",
]
CATEGORIES       = ["General", "OBC", "SC", "ST", "EWS", "Minority"]
OCCUPATIONS      = ["Student", "Farmer", "Street Vendor", "Business Owner",
                    "Self-Employed", "Private Employee", "Government Employee",
                    "Labourer", "Unemployed", "Homemaker", "Other"]
EDUCATION_LEVELS = ["Illiterate", "5th Pass", "8th Pass", "10th Pass",
                    "12th Pass", "Diploma", "Graduate", "Post Graduate", "PhD"]

SHOW_STEP = 3   # how many extra schemes to load on "Show More"

# ── Application theme ─────────────────────────────────────────────────────────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif !important;
}

/* Page background */
.stApp, .main {
    background-color: #f0f4f8 !important;
}

/* Sidebar shell */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 60%, #0f172a 100%) !important;
    border-right: 1px solid #334155 !important;
    box-shadow: 4px 0 24px rgba(0,0,0,0.18) !important;
}
section[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #f8fafc !important;
    letter-spacing: -0.02em;
}

/* Sidebar inputs */
section[data-testid="stSidebar"] input,
section[data-testid="stSidebar"] textarea {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    color: #f1f5f9 !important;
    border-radius: 8px !important;
    font-size: 0.875rem !important;
}
section[data-testid="stSidebar"] input:focus,
section[data-testid="stSidebar"] textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 2px rgba(99,102,241,0.2) !important;
    outline: none !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    color: #f1f5f9 !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] span {
    color: #f1f5f9 !important;
}
section[data-testid="stSidebar"] label {
    color: #94a3b8 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}
section[data-testid="stSidebar"] [data-testid="stCheckbox"] label {
    color: #cbd5e1 !important;
    font-size: 0.875rem !important;
    text-transform: none !important;
    letter-spacing: normal !important;
    font-weight: 400 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: #334155 !important;
    margin: 10px 0 !important;
}

/* Section label in sidebar */
.sidebar-section-label {
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #818cf8 !important;
    padding: 16px 0 6px;
    border-bottom: 1px solid #334155;
    margin-bottom: 8px;
}
.sidebar-brand {
    padding: 6px 0 12px;
}
.sidebar-brand-title {
    color: #f8fafc !important;
    font-size: 1.25rem;
    font-weight: 800;
    letter-spacing: -0.02em;
}
.sidebar-brand-sub {
    color: #94a3b8 !important;
    font-size: 0.78rem;
    line-height: 1.4;
    margin-top: 2px;
}

/* Page header */
.page-header {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: none;
    border-radius: 14px;
    padding: 28px 32px;
    margin-bottom: 24px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.12);
}
.page-header h1 {
    color: #f8fafc !important;
}
.page-header p {
    color: #94a3b8 !important;
}

/* Unified Scheme Card Design */
.scheme-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 22px 26px;
    margin-bottom: 18px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.04), 0 2px 4px -1px rgba(0, 0, 0, 0.02);
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.scheme-card:hover {
    border-color: #cbd5e1;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -4px rgba(0, 0, 0, 0.02);
}

/* Eligibility Accents on Left Border */
.scheme-card-green {
    border-left: 4px solid #10b981;
}
.scheme-card-blue {
    border-left: 4px solid #4f46e5;
}
.scheme-card-orange {
    border-left: 4px solid #f59e0b;
}

/* Card Header elements */
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 10px;
}
.scheme-title {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.4;
}
.rank-badge {
    color: #4f46e5;
    font-weight: 800;
    margin-right: 4px;
}

/* Score display */
.score-container {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    min-width: 80px;
}
.score-num {
    font-size: 1.4rem;
    font-weight: 700;
    line-height: 1;
}
.score-caption {
    color: #64748b;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.05em;
    margin-bottom: 4px;
    text-transform: uppercase;
}
.score-total {
    font-size: 0.75rem;
    color: #94a3b8;
    font-weight: 500;
}
.score-bar-bg {
    background: #f1f5f9;
    border-radius: 4px;
    height: 6px;
    width: 76px;
    margin-top: 6px;
    overflow: hidden;
}
.score-bar-fill {
    height: 100%;
    border-radius: 4px;
}

/* Meta Chips */
.meta-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 14px;
}
.chip {
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 6px;
    border: 1px solid #e2e8f0;
}
.chip-state {
    background: #eff6ff;
    color: #1e40af;
    border-color: #dbeafe;
}
.chip-category {
    background: #faf5ff;
    color: #5b21b6;
    border-color: #e9d5ff;
}
.chip-income {
    background: #ecfdf5;
    color: #065f46;
    border-color: #a7f3d0;
}

/* Detail text sections */
.info-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94a3b8;
    margin-bottom: 4px;
    margin-top: 10px;
}
.info-text {
    font-size: 0.88rem;
    color: #334155;
    line-height: 1.55;
}

/* Status evaluation tags */
.status-chips-container {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 4px;
}
.chip-status {
    font-size: 0.72rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid transparent;
}
.chip-match {
    background: #f0fdf4;
    color: #15803d;
    border-color: #bbf7d0;
}
.chip-mismatch {
    background: #fef2f2;
    color: #b91c1c;
    border-color: #fecaca;
}

/* Application buttons */
.link-apply {
    display: inline-block;
    background: #4f46e5;
    color: #ffffff !important;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 8px 18px;
    border-radius: 6px;
    text-decoration: none !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    transition: background 0.15s ease;
}
.link-apply:hover {
    background: #4338ca;
}
.link-source {
    display: inline-block;
    background: #ffffff;
    color: #4f46e5 !important;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 8px 18px;
    border-radius: 6px;
    text-decoration: none !important;
    border: 1px solid #e2e8f0;
    transition: background 0.15s ease, border-color 0.15s ease;
}
.link-source:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
}

/* Welcome state card */
.welcome-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 40px 36px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}
.welcome-card h2 {
    color: #0f172a;
    font-size: 1.4rem;
    font-weight: 700;
    margin-bottom: 8px;
}
.welcome-card p {
    color: #64748b;
    font-size: 0.95rem;
    margin-bottom: 24px;
}
.step-row {
    display: flex;
    gap: 16px;
    margin-top: 24px;
}
@media (max-width: 768px) {
    .step-row { flex-direction: column; }
}
.step-box {
    flex: 1;
    background: #f8fafc;
    border: 1px solid #f1f5f9;
    border-radius: 8px;
    padding: 20px 18px;
    text-align: left;
}
.step-num {
    font-size: 0.68rem;
    font-weight: 700;
    color: #4f46e5;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
.step-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #0f172a;
    margin: 6px 0 4px;
}
.step-desc {
    font-size: 0.8rem;
    color: #64748b;
    line-height: 1.45;
}

/* Results header styling */
.results-header {
    font-size: 0.9rem;
    color: #64748b;
    margin-bottom: 18px;
    padding-bottom: 12px;
    border-bottom: 1px solid #f1f5f9;
}
.results-header strong {
    color: #0f172a;
}

/* Custom styled Streamlit widgets */
.stButton > button {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.88rem !important;
    padding: 8px 16px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    transition: background 0.15s ease !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%) !important;
}
.stButton > button[kind="secondary"] {
    background-color: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
}
.stButton > button[kind="secondary"]:hover {
    background-color: #f8fafc !important;
    border-color: #cbd5e1 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    border-radius: 10px !important;
    box-shadow: 0 4px 14px rgba(99,102,241,0.4) !important;
    padding: 12px 20px !important;
    width: 100%;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    box-shadow: 0 6px 20px rgba(99,102,241,0.5) !important;
    transform: translateY(-1px) !important;
}

/* Hide streamlit branding and menus */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Explain trigger pill — sits inline after the text, looks minimal */
.explain-pill > div > button {
    background: transparent !important;
    border: 1.5px solid #a5b4fc !important;
    color: #6366f1 !important;
    box-shadow: none !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    padding: 1px 10px !important;
    border-radius: 999px !important;
    min-height: unset !important;
    line-height: 1.6 !important;
    transition: background 0.15s, border-color 0.15s !important;
}
.explain-pill > div > button:hover {
    background: #eef2ff !important;
    border-color: #6366f1 !important;
}
/* Explain trigger — looks like an indigo text link */
.explain-link button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: #6366f1 !important;
    font-size: 0.875rem !important;
    font-weight: 600 !important;
    padding: 0 !important;
    text-decoration: underline !important;
    text-decoration-color: #a5b4fc !important;
    text-underline-offset: 3px !important;
    min-height: unset !important;
    cursor: pointer !important;
    transition: color 0.15s !important;
}
.explain-link button:hover {
    color: #4f46e5 !important;
    background: transparent !important;
    text-decoration-color: #4f46e5 !important;
}
</style>
"""

# ── Cached resources ──────────────────────────────────────────────────────────

@st.cache_resource
def get_db() -> DBManager:
    return DBManager()

@st.cache_resource
def get_eligibility_engine() -> EligibilityEngine:
    return EligibilityEngine()

@st.cache_resource
def get_ranking_engine() -> RankingEngine:
    return RankingEngine()

@st.cache_resource
def get_vector_store() -> VectorStore:
    vs = VectorStore()
    if not vs.load():
        try:
            schemes = get_db().get_all_schemes()
            if schemes:
                vs.build(schemes)
        except Exception as exc:
            logging.warning("Could not build vector store: %s", exc)
    return vs

@st.cache_resource
def get_explanation_chain() -> ExplanationChain:
    return ExplanationChain()

@st.cache_data(ttl=300)
def load_all_schemes() -> List[Dict]:
    return get_db().get_all_schemes()


def _valid_http_url(value: Any) -> str:
    """Return a safe absolute HTTP(S) URL, or an empty string."""
    url = str(value or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url





# ── Scheme card renderer ──────────────────────────────────────────────────────

def render_scheme_card(result: Dict[str, Any], rank: int):
    score = max(0, min(100, int(result.get("eligibility_score", 0) or 0)))
    name = escape(str(result.get("scheme_name", "")))
    score_label = escape(str(result.get("score_label", "Eligibility")))

    if score >= 80:
        card_border_cls = "scheme-card-green"
        bar_color = "#10b981"  # Emerald
    elif score >= 60:
        card_border_cls = "scheme-card-blue"
        bar_color = "#4f46e5"  # Indigo
    else:
        card_border_cls = "scheme-card-orange"
        bar_color = "#f59e0b"  # Amber

    # ── Meta pills ────────────────────────────────────────────────────────────
    state_raw   = result.get("state", ["All"])
    cat_raw     = result.get("category", ["All"])
    income_lim  = result.get("income_limit")
    occ_raw     = result.get("occupation", ["All"])

    state_str = ", ".join(map(str, state_raw[:2])) if isinstance(state_raw, list) else str(state_raw)
    cat_str = ", ".join(map(str, cat_raw[:2])) if isinstance(cat_raw, list) else str(cat_raw)
    occ_str = ", ".join(map(str, occ_raw[:2])) if isinstance(occ_raw, list) else str(occ_raw)
    state_str = escape(state_str)
    cat_str = escape(cat_str)
    occ_str = escape(occ_str)
    income_str = f"Income ≤ Rs {income_lim:,.0f}" if income_lim else "No Income Cap"

    # Build chips — skip generic 'All' values
    def _is_generic(val) -> bool:
        if val is None:
            return True
        items = val if isinstance(val, list) else [val]
        return all(str(v).strip().lower() in ("all", "all india", "") for v in items)

    chips_html = ""
    if not _is_generic(state_raw):
        chips_html += f'<span class="chip chip-state">🗺️ {state_str}</span>'
    else:
        chips_html += '<span class="chip chip-state">🇮🇳 All India</span>'
    if not _is_generic(cat_raw):
        chips_html += f'<span class="chip chip-category">🏷️ {cat_str}</span>'
    if not _is_generic(occ_raw):
        chips_html += f'<span class="chip chip-category">👤 For: {occ_str}</span>'
    chips_html += f'<span class="chip chip-income">{income_str}</span>'

    # ── Benefits ──────────────────────────────────────────────────────────────
    benefits = escape(str(result.get("benefits") or result.get("description") or ""))
    benefits_html = ""
    if benefits:
        benefits_html = f'''
        <div style="margin-top: 14px;">
            <div class="info-label">What You Get (Benefits)</div>
            <div class="info-text">{benefits}</div>
        </div>
        '''

    # ── Why you qualify (chips) ───────────────────────────────────────────────
    matches   = result.get("match_reasons",    [])
    mismatches = result.get("mismatch_reasons", [])
    eligibility_html = ""
    if matches or mismatches:
        match_chips = "".join(
            f'<span class="chip-status chip-match">'
            f'{escape(str(r).replace("✅ ", "").replace("⚠️ ", ""))}</span>'
            for r in matches[:4]
        )
        mismatch_chips = "".join(
            f'<span class="chip-status chip-mismatch">'
            f'{escape(str(r).replace("❌ ", ""))}</span>'
            for r in mismatches[:2]
        )
        eligibility_html = f'''
        <div style="margin-top: 12px;">
            <div class="info-label">Eligibility Match Analysis</div>
            <div class="status-chips-container">
                {match_chips}
                {mismatch_chips}
            </div>
        </div>
        '''

    # ── Links ─────────────────────────────────────────────────────────────────
    app_link = _valid_http_url(result.get("application_link"))
    src_link = _valid_http_url(result.get("source_url"))

    # ── Full Card HTML ────────────────────────────────────────────────────────
    card_html = dedent(
        f"""
        <div class="scheme-card {card_border_cls}">
            <div class="card-header">
                <div class="scheme-title">
                    <span class="rank-badge">#{rank}</span> {name}
                </div>
                <div class="score-container">
                    <div class="score-caption">{score_label}</div>
                    <div class="score-num" style="color: {bar_color};">{score}<span class="score-total">/100</span></div>
                    <div class="score-bar-bg">
                        <div class="score-bar-fill" style="width: {score}%; background: {bar_color};"></div>
                    </div>
                </div>
            </div>
            <div class="meta-chips">
                {chips_html}
            </div>
            {benefits_html}
            {eligibility_html}
        </div>
        """
    ).strip()
    # Streamlit's Markdown parser treats any indented HTML line after a blank
    # line as code. Compact the complete card so closing tags never appear as
    # visible `</div>` blocks.
    card_html = "".join(line.strip() for line in card_html.splitlines())

    st.markdown(card_html, unsafe_allow_html=True)

    # Native Streamlit links are more reliable than anchors embedded in HTML.
    if app_link or src_link:
        link_columns = st.columns([1, 1, 3])
        if app_link:
            link_columns[0].link_button(
                "Apply Online ↗",
                app_link,
                use_container_width=True,
            )
        if src_link and src_link.rstrip("/") != app_link.rstrip("/"):
            link_columns[1].link_button(
                "Official Portal ↗",
                src_link,
                use_container_width=True,
            )


# ── Semantic Search tab ───────────────────────────────────────────────────────

def render_search_tab():
    st.markdown(
        '<p style="color:#64748b;font-size:0.9rem;margin-bottom:12px;">'
        "Search schemes using natural language — powered by FAISS vector similarity.</p>",
        unsafe_allow_html=True,
    )
    query = st.text_input("Search query", placeholder="e.g. pension for widows below poverty line",
                          key="sem_query", label_visibility="collapsed")
    if st.button("Search", key="sem_btn"):
        if not query.strip():
            st.warning("Please enter a search query.")
            return
        vs = get_vector_store()
        with st.spinner("Searching…"):
            results = vs.search(query, top_k=5)
        if results:
            st.success(f"Found {len(results)} scheme(s).")
            for i, r in enumerate(results, 1):
                render_scheme_card(
                    {
                        **r,
                        "eligibility_score": int(r.get("similarity_score", 0) * 100),
                        "score_label": "Semantic match",
                        "match_reasons": [
                            f"✅ Semantic similarity: {r.get('similarity_score', 0):.2f}"
                        ],
                        "mismatch_reasons": [],
                    },
                    i,
                )
        else:
            st.info("No results found. Try a different keyword.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.markdown(CSS, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand">'
            '<div class="sidebar-brand-title">🇮🇳 GovtSchemeAI</div>'
            '<div class="sidebar-brand-sub">Personalized government benefit finder</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        st.markdown('<div class="sidebar-section-label">Personal Details</div>',
                    unsafe_allow_html=True)
        user_name = st.text_input("Full Name", value="Rajesh Kumar")
        age       = st.number_input("Age", min_value=1, max_value=100, value=35)
        gender    = st.selectbox("Gender", ["Male", "Female", "Other"])
        state     = st.selectbox("State / UT", INDIAN_STATES,
                                 index=INDIAN_STATES.index("Punjab"))
        district  = st.text_input("District", value="Ludhiana")

        st.markdown('<div class="sidebar-section-label">Financial Details</div>',
                    unsafe_allow_html=True)
        annual_income = st.number_input("Annual Income (Rs)", min_value=0,
                                         max_value=10_000_000, value=150_000, step=10_000)
        category      = st.selectbox("Social Category", CATEGORIES)
        occupation    = st.selectbox("Occupation", OCCUPATIONS)
        education     = st.selectbox("Education Level", EDUCATION_LEVELS)
        residence     = st.selectbox("Residence Type", ["Rural", "Urban", "Both"])

        st.markdown('<div class="sidebar-section-label">Special Conditions</div>',
                    unsafe_allow_html=True)
        is_disabled     = st.checkbox("Person with Disability")
        is_minority     = st.checkbox("Minority Community")
        is_widow        = st.checkbox("Widow / Widower")
        is_ex_serviceman = st.checkbox("Ex-Serviceman")

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        find_btn = st.button("Find My Schemes", type="primary", use_container_width=True)

    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        '<div class="page-header">'
        '<div style="display: flex; align-items: center; gap: 12px; margin-bottom: 6px;">'
        '<span style="font-size: 1.8rem;">🏛️</span>'
        '<h1 style="margin: 0; font-size: 1.8rem; font-weight: 800;">GovtSchemeAI Portal</h1>'
        '</div>'
        '<p style="margin: 0; font-size: 0.95rem;">'
        'Empowering citizens to discover and access personalized government benefits. Real-time eligibility evaluation across 200+ schemes.'
        '</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Auto-init DB if empty
    db = get_db()
    if db.count_schemes() == 0:
        with st.spinner("Setting up scheme database for the first time…"):
            try:
                from update_schemes import run_pipeline
                run_pipeline(use_live_scraping=False)
                st.cache_data.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Initialization failed: {exc}")
                return

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_recs, tab_search = st.tabs(["Recommendations", "Semantic Search"])

    with tab_recs:
        if find_btn:
            # Reset pagination on new search
            st.session_state["shown_count"] = 5

        if find_btn or "last_results" in st.session_state:

            if find_btn:
                user_profile = {
                    "user_name":       user_name,
                    "age":             int(age),
                    "gender":          gender,
                    "state":           state if state != "All India" else "",
                    "district":        district,
                    "annual_income":   int(annual_income),
                    "category":        category,
                    "occupation":      occupation,
                    "education":       education.lower(),
                    "residence_type":  residence,
                    "is_disabled":     is_disabled,
                    "is_minority":     is_minority,
                    "is_widow":        is_widow,
                    "is_ex_serviceman": is_ex_serviceman,
                }

                all_schemes = load_all_schemes()
                if not all_schemes:
                    st.error("No schemes in database. Please try again in a moment.")
                    return

                engine  = get_eligibility_engine()
                ranker  = get_ranking_engine()

                with st.spinner("Checking eligibility…"):
                    elig_results = engine.check_all(user_profile, all_schemes)

                # Rank ALL results (no cap yet — pagination handles display)
                all_ranked = ranker.rank(elig_results, top_n=None, eligible_only=False)

                # Store in session state
                st.session_state["last_results"]   = all_ranked
                st.session_state["last_profile"]   = user_profile
                st.session_state["total_schemes"]  = len(all_schemes)

                # Save history silently
                try:
                    db.save_recommendation_history(user_name, user_profile, all_ranked[:5])
                except Exception:
                    pass

            # Pull from session state (persists across Show More clicks)
            all_ranked    = st.session_state.get("last_results",  [])
            user_profile  = st.session_state.get("last_profile",  {})
            total_schemes = st.session_state.get("total_schemes", 0)
            shown_count   = st.session_state.get("shown_count",   5)

            if not all_ranked:
                st.info("No schemes matched your profile. Try adjusting your details.")
            else:
                to_display = all_ranked[:shown_count]
                remaining  = len(all_ranked) - shown_count

                name_str = user_profile.get("user_name", "You")
                st.markdown(
                    f'<div class="results-header">Showing <strong>{len(to_display)}</strong> '
                    f'of <strong>{len(all_ranked)}</strong> matched schemes for '
                    f'<strong>{name_str}</strong> '
                    f'<span style="color:#94a3b8;">· checked against {total_schemes} curated govt schemes</span></div>',
                    unsafe_allow_html=True,
                )

                for i, result in enumerate(to_display, 1):
                    render_scheme_card(result, i)

                    # ── AI Explanation inline trigger ─────────────────────
                    scheme_key = f"explain_{i}_{result.get('scheme_id', i)}"
                    cache_key  = f"explain_cache_{scheme_key}"
                    expand_key = f"explain_open_{scheme_key}"
                    is_open    = st.session_state.get(expand_key, False)

                    # Single tight row: text on left, pill toggle immediately after
                    _ek = expand_key  # capture for closure
                    def _toggle_explain(_key=_ek):
                        st.session_state[_key] = not st.session_state.get(_key, False)

                    # Single text-link trigger (no separate arrow button)
                    col_link, col_gap = st.columns([3.5, 8.5])
                    with col_link:
                        st.markdown('<div class="explain-link">', unsafe_allow_html=True)
                        st.button(
                            "✨ Why am I eligible for this scheme?",
                            key=f"toggle_{scheme_key}",
                            on_click=_toggle_explain,
                        )
                        st.markdown('</div>', unsafe_allow_html=True)

                    # Explanation panel
                    if is_open:
                        if cache_key not in st.session_state:
                            with st.spinner("Generating personalised explanation…"):
                                chain = get_explanation_chain()
                                explanation = chain.explain(user_profile, result)
                            st.session_state[cache_key] = explanation

                        import re as _re
                        def _fmt(text: str) -> str:
                            lines = text.strip().splitlines()
                            out = []
                            for ln in lines:
                                ln = ln.strip()
                                if not ln:
                                    continue
                                m = _re.match(r'^(\d+)\.\s+([A-Z][A-Z ]+)[:：](.*)$', ln)
                                if m:
                                    out.append(
                                        f'<p style="margin:10px 0 2px;font-size:0.78rem;'
                                        f'font-weight:700;color:#6366f1;text-transform:uppercase;'
                                        f'letter-spacing:0.07em;">{m.group(2).strip()}</p>'
                                        f'<p style="margin:0 0 4px;font-size:0.92rem;color:#1e293b;">'
                                        f'{m.group(3).strip()}</p>'
                                    )
                                else:
                                    out.append(
                                        f'<p style="margin:4px 0;font-size:0.92rem;'
                                        f'color:#334155;">{ln}</p>'
                                    )
                            return "\n".join(out)

                        st.markdown(
                            f'<div style="background:linear-gradient(135deg,#eef2ff 0%,#f5f3ff 100%);'
                            f'border-left:4px solid #6366f1;border-radius:0 12px 12px 0;'
                            f'padding:14px 20px;margin:0 0 18px 0;">'
                            f'{_fmt(st.session_state[cache_key])}'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Show More / No More
                if remaining > 0:
                    more_count = min(SHOW_STEP, remaining)
                    _sc = shown_count  # capture for closure
                    _mc = more_count
                    def _do_show_more(_s=_sc, _m=_mc):
                        st.session_state["shown_count"] = _s + _m
                    st.button(
                        f"Show {more_count} More Schemes",
                        key="show_more_btn",
                        on_click=_do_show_more,
                    )
                elif len(all_ranked) <= shown_count and len(all_ranked) > 0:
                    st.markdown(
                        '<p style="color:#94a3b8;font-size:0.82rem;text-align:center;'
                        'margin-top:8px;">No more schemes available for your profile.</p>',
                        unsafe_allow_html=True,
                    )

        else:
            # Welcome state
            st.markdown(
                '<div class="welcome-card">'
                '<div style="font-size:2rem;margin-bottom:10px;">🏛️</div>'
                '<h2>Find Government Schemes You Deserve</h2>'
                '<p>Fill in your profile on the left sidebar and click '
                '<strong>Find My Schemes</strong> to get personalised recommendations.</p>'
                '<div class="step-row">'
                '<div class="step-box">'
                '<div class="step-num">Step 1</div>'
                '<div class="step-title">Fill Your Profile</div>'
                '<div class="step-desc">Enter your age, income, state, category, and occupation.</div>'
                '</div>'
                '<div class="step-box">'
                '<div class="step-num">Step 2</div>'
                '<div class="step-title">Click Find</div>'
                '<div class="step-desc">We check eligibility across all available government schemes.</div>'
                '</div>'
                '<div class="step-box">'
                '<div class="step-num">Step 3</div>'
                '<div class="step-title">View & Apply</div>'
                '<div class="step-desc">See matched schemes with benefits and direct apply links.</div>'
                '</div>'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    with tab_search:
        render_search_tab()


if __name__ == "__main__":
    main()
