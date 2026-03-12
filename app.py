"""
app.py — Intelli-Credit Main Application Shell
Entry point for the entire 4-module corporate credit underwriting pipeline.
"""

import json
import os
from datetime import datetime

import streamlit as st
from utils.ui_icons import svg_header, get_svg, icon_label

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Intelli-Credit",
    page_icon=":material/account_balance:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
}
.stApp { background: #F8FAFC; }

/* Hide default Streamlit menu */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header { visibility: hidden; }

/* Buttons */
.stButton > button {
    background: #1B3A6B !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.4rem !important;
    transition: all 0.2s ease !important;
}
.stButton > button:hover {
    background: #2563EB !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(37,99,235,0.3) !important;
}

/* Cards */
.ic-card {
    background: white;
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    border: 1px solid #e2e8f0;
    margin-bottom: 1rem;
}

/* Step badges */
.step-done  { color: #059669; font-weight: 700; }
.step-active{ color: #2563EB; font-weight: 700; }
.step-todo  { color: #94a3b8; }

/* Hero */
.hero-title {
    font-size: 3.5rem;
    font-weight: 800;
    color: #1B3A6B;
    line-height: 1.1;
}
.hero-tag {
    font-size: 1.2rem;
    color: #475569;
    margin-top: 0.5rem;
}
.hero-badge {
    display: inline-block;
    background: #dbeafe;
    color: #1d4ed8;
    border-radius: 20px;
    padding: 0.25rem 0.8rem;
    font-size: 0.78rem;
    font-weight: 600;
    margin: 0.25rem 0.2rem;
}
.scenario-approve {
    border-left: 4px solid #059669;
    background: #f0fdf4;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}
.scenario-review {
    border-left: 4px solid #d97706;
    background: #fffbeb;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}
.scenario-reject {
    border-left: 4px solid #dc2626;
    background: #fef2f2;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.5rem 0;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DEMO SCENARIOS DATA
# ─────────────────────────────────────────────────────────────────────────────
DEMO_SCENARIOS = {

    "ABC Manufacturing — APPROVE (Clean Profile)": {
        "extraction_payload": {
            "entity_context": {
                "company_name": "ABC Manufacturing Pvt Ltd",
                "cin": "U74999MH2010PTC204567",
                "pan": "AABCM1234F",
                "sector": "Manufacturing",
                "sub_sector": "Auto Components",
                "annual_turnover_cr": 520,
                "loan_amount": 20,
                "loan_amount_cr": 20,
                "loan_type": "Term Loan",
                "collateral_type": "Real Estate",
                "collateral_value": 35,
                "collateral_value_cr": 35,
                "cibil_commercial_score": 8,
                "gstr_2a_3b_mismatch_flag": "No Mismatch",
                "mca_last_filing_date": "2024-09-15",
                "years_op": 14,
                "existing_relationship": "Yes",
                "tenure": 60,
                "purpose": "Capacity expansion — new manufacturing unit",
            },
            "financials": {
                "revenue_cr": 520,
                "ebitda_cr": 80,
                "pat_cr": 41,
                "total_debt_cr": 290,
                "net_worth_cr": 180,
                "operating_cashflow_cr": 62,
                "total_assets_cr": 580,
                "promoter_holding_pct": 67.4,
                "promoter_pledge_pct": 28,
                "gst_declared_sales_cr": 498,
                "gst_2a_vs_3b_variance_pct": 2.1,
                "avg_monthly_bank_inflow_cr": 44.5,
                "npa_pct": None,
                "par_90_pct": None,
                "collection_efficiency_pct": None,
                "cibil_commercial_score": 8,
            },
            "fraud_flags": [],
            "document_sources": ["AnnualReport_FY24.pdf", "BankStatement_Q3.xlsx"],
            "extraction_timestamp": datetime.now().isoformat(),
            "schema_config": [],
            "data_lineage": {},
            "gst_variance_pct": 2.1,
        },
        "research_payload": {
            "research_output": {
                "composite_external_risk_score": 4.2,
                "legal_risk_score": 2.0,
                "operational_risk_score": 3.0,
                "mca_risk_score": 1.5,
                "gst_compliance_score": 2.0,
                "sector_risk_score": 3.5,
                "sector_summary": "Indian auto-component manufacturing is seeing strong demand "
                                  "driven by EV transition and PLI schemes. Mid-sized players "
                                  "with domestic exposure well-positioned.",
                "early_warning_signals": [],
                "news_summary": "No adverse news found for ABC Manufacturing Pvt Ltd. "
                                "Company featured in ET for production expansion in Q2 FY25.",
            },
            "primary_insights": {
                "factory_capacity_pct": 82,
                "management_quality": "Good",
                "cibil_commercial_verified": "Yes — Clean",
                "ecourt_cases_found": 0,
                "rbi_compliance": "Fully Compliant",
                "mca_last_filing_date": "2024-09-15",
            },
            "triangulation_flags": [],
            "research_timestamp": datetime.now().isoformat(),
        },
        "recommendation_payload": {
            "decision": "APPROVE",
            "recommended_loan_cr": 18,
            "recommended_rate_pct": 11.2,
            "pd": 0.18,
            "lgd": 0.42,
            "z_score": 2.74,
            "confidence": 0.82,
            "decision_rationale": [
                "Strong revenue growth trajectory with EBITDA margin at 15.4% — above sector median.",
                "Adequate debt service coverage; operating cashflow of ₹62Cr comfortably covers ₹34.8Cr annual obligation.",
                "Clean CIBIL Commercial Score of 8/10 and zero fraud flags indicate high character integrity.",
            ],
            "swot": {
                "strengths": ["Established 14-year operating history", "Clean compliance record"],
                "weaknesses": ["Moderate promoter pledge at 28%", "Single-sector concentration"],
                "opportunities": ["PLI scheme benefits", "Export market expansion"],
                "threats": ["Input cost volatility", "EV disruption risk"],
            },
            "five_cs": {
                "character":  {"score": 8, "comment": "Clean bureau, no litigation, strong governance"},
                "capacity":   {"score": 7, "comment": "DSCR 1.78x; adequate debt serviceability"},
                "capital":    {"score": 7, "comment": "Net worth ₹180Cr; leverage moderate"},
                "collateral": {"score": 8, "comment": "Real Estate LTV 60% effective coverage"},
                "conditions": {"score": 7, "comment": "Sector tailwinds; PLI beneficiary"},
            },
            "conditions": [
                "Quarterly financial reporting to be submitted within 45 days of period end.",
                "Promoter pledge not to exceed 40% during loan tenure.",
                "Revenue covenant: minimum ₹450Cr annual turnover.",
            ],
            "rejection_reason": None,
            "india_specific_concerns": [],
            "fraud_score": 0,
            "fraud_flags": [],
            "triangulation_flags": [],
            "early_warning_signals": [],
            "recommendation_timestamp": datetime.now().isoformat(),
        },
    },

    "XYZ Traders — MANUAL REVIEW (GST Mismatch + Moderate Risk)": {
        "extraction_payload": {
            "entity_context": {
                "company_name": "XYZ Traders Pvt Ltd",
                "cin": "U51909DL2015PTC289012",
                "pan": "AABCX5678G",
                "sector": "Other",
                "sub_sector": "Trading",
                "annual_turnover_cr": 180,
                "loan_amount": 25,
                "loan_amount_cr": 25,
                "loan_type": "Working Capital",
                "collateral_type": "Stocks",
                "collateral_value": 18,
                "collateral_value_cr": 18,
                "cibil_commercial_score": 5,
                "gstr_2a_3b_mismatch_flag": "Moderate (5–15%)",
                "mca_last_filing_date": "2024-04-10",
                "years_op": 9,
                "existing_relationship": "No",
                "tenure": 36,
                "purpose": "Working capital for bulk trading operations",
            },
            "financials": {
                "revenue_cr": 180,
                "ebitda_cr": 22,
                "pat_cr": 9,
                "total_debt_cr": 140,
                "net_worth_cr": 55,
                "operating_cashflow_cr": 15,
                "total_assets_cr": 210,
                "promoter_holding_pct": 72.0,
                "promoter_pledge_pct": 48,
                "gst_declared_sales_cr": 205,
                "gst_2a_vs_3b_variance_pct": 11.8,
                "avg_monthly_bank_inflow_cr": 12.0,
                "cibil_commercial_score": 5,
            },
            "fraud_flags": [
                {"flag": "GSTR_2A_3B_MODERATE_MISMATCH", "severity": "HIGH",
                 "detail": "GSTR-2A vs 3B variance at 11.8%. Seek reconciliation statement.",
                 "five_c": "Character"},
                {"flag": "EARNINGS_QUALITY_RISK", "severity": "HIGH",
                 "detail": "Operating cashflow 8.3% of revenue. Possible working capital stress.",
                 "five_c": "Capacity"},
            ],
            "document_sources": ["BankStatement_FY24.pdf", "GSTReturn_Q4.xlsx"],
            "extraction_timestamp": datetime.now().isoformat(),
            "schema_config": [],
            "data_lineage": {},
            "gst_variance_pct": 11.8,
        },
        "research_payload": {
            "research_output": {
                "composite_external_risk_score": 6.1,
                "legal_risk_score": 4.5,
                "operational_risk_score": 5.5,
                "mca_risk_score": 3.0,
                "gst_compliance_score": 6.5,
                "sector_risk_score": 5.5,
                "sector_summary": "Indian trading sector faces margin pressure in FY25 due "
                                  "to import cost volatility and GST enforcement tightening.",
                "early_warning_signals": [
                    {"signal": "HIGH_GST_VARIANCE", "severity": "HIGH",
                     "source": "GST", "five_c_mapping": "Character"},
                ],
                "news_summary": "Minor trade disputes reported in 2024. No major fraud cases.",
            },
            "primary_insights": {
                "factory_capacity_pct": 65,
                "management_quality": "Average",
                "cibil_commercial_verified": "Yes — Minor Issues",
                "ecourt_cases_found": 2,
                "rbi_compliance": "Pending Items",
                "mca_last_filing_date": "2024-04-10",
            },
            "triangulation_flags": [
                {"flag": "DECLARED_VS_DOCUMENT_REVENUE_GAP", "severity": "HIGH",
                 "detail": "Onboarding turnover ₹180Cr vs GST-declared ₹205Cr — 14% gap.",
                 "recommended_action": "Obtain GST reconciliation and board resolution."},
            ],
            "research_timestamp": datetime.now().isoformat(),
        },
        "recommendation_payload": {
            "decision": "MANUAL_REVIEW",
            "recommended_loan_cr": 15,
            "recommended_rate_pct": 14.5,
            "pd": 0.38,
            "lgd": 0.68,
            "z_score": 1.95,
            "confidence": 0.61,
            "decision_rationale": [
                "GST 2A/3B variance of 11.8% requires reconciliation before approval.",
                "Promoter pledge at 48% is elevated; collateral quality (Stocks) carries 50% haircut.",
                "Moderate CIBIL score 5/10 and 2 active e-Court cases require senior review.",
            ],
            "swot": {
                "strengths": ["Established trading relationships", "Revenue scale of ₹180Cr"],
                "weaknesses": ["High GST variance", "Weak operating cashflow at 8.3%"],
                "opportunities": ["Working capital optimisation", "GST compliance improvement"],
                "threats": ["Regulatory action on GST discrepancy", "Debt-heavy balance sheet"],
            },
            "five_cs": {
                "character":  {"score": 5, "comment": "GST variance and e-Court cases require resolution"},
                "capacity":   {"score": 5, "comment": "DSCR borderline at 0.89x; cashflow weak"},
                "capital":    {"score": 5, "comment": "D/E ratio 2.5x is elevated for trading"},
                "collateral": {"score": 4, "comment": "Stocks with 50% haircut; limited coverage"},
                "conditions": {"score": 5, "comment": "Trading sector headwinds in FY25"},
            },
            "conditions": [
                "GST reconciliation statement (2A vs 3B) mandatory pre-disbursement.",
                "Promoter pledge cap at 50%; personal guarantee required.",
                "Monthly bank statement submission for first 12 months.",
            ],
            "rejection_reason": None,
            "india_specific_concerns": [
                "GSTR-2A vs 3B variance of 11.8% is close to threshold for serious scrutiny.",
                "CIBIL Commercial Score 5/10 indicates payment delays on existing obligations.",
                "2 active e-Court cases require legal clearance before disbursement.",
            ],
            "fraud_score": 30,
            "fraud_flags": [
                {"flag": "GSTR_2A_3B_MODERATE_MISMATCH", "severity": "HIGH",
                 "detail": "GSTR-2A vs 3B variance at 11.8%.", "five_c": "Character"},
                {"flag": "EARNINGS_QUALITY_RISK", "severity": "HIGH",
                 "detail": "Operating cashflow 8.3% of revenue.", "five_c": "Capacity"},
            ],
            "triangulation_flags": [
                {"flag": "DECLARED_VS_DOCUMENT_REVENUE_GAP", "severity": "HIGH",
                 "detail": "Onboarding ₹180Cr vs GST ₹205Cr — 14% gap."},
            ],
            "early_warning_signals": [
                {"signal": "HIGH_GST_VARIANCE", "severity": "HIGH", "source": "GST"},
            ],
            "recommendation_timestamp": datetime.now().isoformat(),
        },
    },

    "PQR Real Estate — REJECT (Litigation + Low Cashflow)": {
        "extraction_payload": {
            "entity_context": {
                "company_name": "PQR Real Estate Dev Ltd",
                "cin": "U70100MH2008PLC183456",
                "pan": "AABCP9012H",
                "sector": "Real Estate",
                "sub_sector": "Residential Development",
                "annual_turnover_cr": 95,
                "loan_amount": 40,
                "loan_amount_cr": 40,
                "loan_type": "Term Loan",
                "collateral_type": "Real Estate",
                "collateral_value": 28,
                "collateral_value_cr": 28,
                "cibil_commercial_score": 2,
                "gstr_2a_3b_mismatch_flag": "Severe (>15%)",
                "mca_last_filing_date": "2023-06-30",
                "years_op": 16,
                "existing_relationship": "No",
                "tenure": 84,
                "purpose": "Project completion funding for stalled residential project",
            },
            "financials": {
                "revenue_cr": 95,
                "ebitda_cr": 8,
                "pat_cr": 1.2,
                "total_debt_cr": 310,
                "net_worth_cr": 42,
                "operating_cashflow_cr": 3.5,
                "total_assets_cr": 380,
                "promoter_holding_pct": 58.0,
                "promoter_pledge_pct": 72,
                "gst_declared_sales_cr": 132,
                "gst_2a_vs_3b_variance_pct": 28.5,
                "avg_monthly_bank_inflow_cr": 4.2,
                "cibil_commercial_score": 2,
            },
            "fraud_flags": [
                {"flag": "HIGH_REVENUE_INFLATION_RISK", "severity": "CRITICAL",
                 "detail": "Bank inflows ₹50.4Cr vs declared revenue ₹95Cr — possible inflation.",
                 "five_c": "Character"},
                {"flag": "GSTR_2A_3B_SEVERE_MISMATCH", "severity": "CRITICAL",
                 "detail": "GST 2A/3B variance 28.5% — possible ITC fraud or sales suppression.",
                 "five_c": "Character"},
                {"flag": "PROMOTER_PLEDGE_RISK", "severity": "MEDIUM",
                 "detail": "Promoter pledge at 72% — significant margin call risk.",
                 "five_c": "Character"},
                {"flag": "CIBIL_COMMERCIAL_HIGH_RISK", "severity": "CRITICAL",
                 "detail": "CIBIL Commercial Score 2/10 — high default probability.",
                 "five_c": "Character"},
            ],
            "document_sources": ["AnnualReport_FY24.pdf", "GSTReturn_FY24.pdf"],
            "extraction_timestamp": datetime.now().isoformat(),
            "schema_config": [],
            "data_lineage": {},
            "gst_variance_pct": 28.5,
        },
        "research_payload": {
            "research_output": {
                "composite_external_risk_score": 8.4,
                "legal_risk_score": 8.0,
                "operational_risk_score": 7.5,
                "mca_risk_score": 6.5,
                "gst_compliance_score": 9.0,
                "sector_risk_score": 7.0,
                "sector_summary": "Indian real estate sector in FY25 faces liquidity stress "
                                  "for mid-tier developers with stalled projects. NCLT "
                                  "filings have surged 32% YoY. Regulatory tightening by "
                                  "RERA has increased compliance burden.",
                "early_warning_signals": [
                    {"signal": "NCLT_PROCEEDINGS", "severity": "CRITICAL",
                     "source": "LEGAL", "five_c_mapping": "Character"},
                    {"signal": "STALLED_PROJECT_RISK", "severity": "HIGH",
                     "source": "NEWS", "five_c_mapping": "Capacity"},
                ],
                "news_summary": "Multiple NCLT filings and stalled projects reported in 2024-25. "
                                "GST department investigation reported in ET Prime, March 2025.",
            },
            "primary_insights": {
                "factory_capacity_pct": 25,
                "management_quality": "Concerning",
                "cibil_commercial_verified": "Yes — Significant Issues",
                "ecourt_cases_found": 8,
                "rbi_compliance": "Non-Compliant",
                "mca_last_filing_date": "2023-06-30",
            },
            "triangulation_flags": [
                {"flag": "LEGAL_SIGNAL_DOCUMENT_MISMATCH", "severity": "HIGH",
                 "detail": "NCLT proceedings found during web research but no legal documents uploaded.",
                 "recommended_action": "Obtain court orders and legal opinion letter."},
                {"flag": "GST_WEB_SIGNAL_VS_DOCUMENT_MISMATCH", "severity": "CRITICAL",
                 "detail": "GST fraud case in news but company claims clean filing in onboarding form.",
                 "recommended_action": "Escalate to compliance team. Do not disburse."},
            ],
            "research_timestamp": datetime.now().isoformat(),
        },
        "recommendation_payload": {
            "decision": "REJECT",
            "recommended_loan_cr": 0,
            "recommended_rate_pct": 0,
            "pd": 0.72,
            "lgd": 0.85,
            "z_score": 1.12,
            "confidence": 0.31,
            "decision_rationale": [
                "Three CRITICAL fraud flags including revenue inflation, GST ITC fraud risk, and CIBIL 2/10.",
                "Operating cashflow ₹3.5Cr vs debt obligation ₹37.2Cr annual — DSCR of 0.09x is critically insufficient.",
                "8 active e-Court cases and NCLT proceedings indicate severe legal risk and promoter integrity concerns.",
            ],
            "swot": {
                "strengths": ["Asset base of ₹380Cr provides theoretical collateral", "16-year vintage"],
                "weaknesses": ["Extreme leverage D/E 7.4x", "Near-zero cashflow generation"],
                "opportunities": ["Project completion could release trapped value"],
                "threats": ["NCLT proceedings", "GST investigation", "Promoter pledge calls"],
            },
            "five_cs": {
                "character":  {"score": 1, "comment": "CIBIL 2/10, GST fraud signals, NCLT filings"},
                "capacity":   {"score": 1, "comment": "DSCR 0.09x — cannot service existing debt"},
                "capital":    {"score": 2, "comment": "Negative free cashflow; D/E 7.4x unsustainable"},
                "collateral": {"score": 3, "comment": "RE collateral at 30% haircut; stalled project risk"},
                "conditions": {"score": 2, "comment": "Real estate sector stress; RERA compliance issues"},
            },
            "conditions": [],
            "rejection_reason": (
                "Multiple CRITICAL fraud flags, CIBIL score 2/10, GST 2A/3B variance 28.5%, "
                "8 active e-Court cases, NCLT proceedings, and operating cashflow <4% of revenue "
                "indicate extreme default risk. Credit facility cannot be extended."
            ),
            "india_specific_concerns": [
                "CIBIL Commercial Score 2/10 places this entity in the highest-risk decile.",
                "GST 2A/3B variance of 28.5% indicates possible Input Tax Credit fraud — GST dept investigation reported.",
                "MCA filing gap > 630 days indicates possible shell company activity.",
                "8 e-Court cases including NCLT proceedings require legal opinion before any credit decision.",
                "Promoter pledge at 72% creates systemic margin call risk.",
            ],
            "fraud_score": 100,
            "fraud_flags": [
                {"flag": "HIGH_REVENUE_INFLATION_RISK", "severity": "CRITICAL",
                 "detail": "Bank inflows ₹50.4Cr vs declared ₹95Cr.", "five_c": "Character"},
                {"flag": "GSTR_2A_3B_SEVERE_MISMATCH", "severity": "CRITICAL",
                 "detail": "GST variance 28.5%.", "five_c": "Character"},
                {"flag": "CIBIL_COMMERCIAL_HIGH_RISK", "severity": "CRITICAL",
                 "detail": "CIBIL 2/10.", "five_c": "Character"},
                {"flag": "PROMOTER_PLEDGE_RISK", "severity": "MEDIUM",
                 "detail": "Pledge at 72%.", "five_c": "Character"},
            ],
            "triangulation_flags": [
                {"flag": "GST_WEB_SIGNAL_VS_DOCUMENT_MISMATCH", "severity": "CRITICAL",
                 "detail": "GST fraud news vs clean filing claim."},
                {"flag": "LEGAL_SIGNAL_DOCUMENT_MISMATCH", "severity": "HIGH",
                 "detail": "NCLT proceedings not disclosed."},
            ],
            "early_warning_signals": [
                {"signal": "NCLT_PROCEEDINGS", "severity": "CRITICAL", "source": "LEGAL"},
                {"signal": "STALLED_PROJECT_RISK", "severity": "HIGH", "source": "NEWS"},
            ],
            "recommendation_timestamp": datetime.now().isoformat(),
        },
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)


def _load_payload_silent(name: str, filepath: str) -> bool:
    """Silently loads a payload from file into session state if not present."""
    if name not in st.session_state:
        try:
            with open(filepath) as f:
                st.session_state[name] = json.load(f)
            return True
        except FileNotFoundError:
            return False
    return True


# Auto-restore payloads silently
for _pname, _fpath in [
    ("extraction_payload",      "./data/extraction_payload.json"),
    ("research_payload",        "./data/research_payload.json"),
    ("recommendation_payload",  "./data/recommendation_payload.json"),
]:
    _load_payload_silent(_pname, _fpath)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='text-align:center;padding:1rem 0 0.5rem'>
        <div style='display:flex;justify-content:center;margin-bottom:0.5rem'>{get_svg("BANK", size=48, color="#1B3A6B")}</div>
        <span style='font-size:1.3rem;font-weight:800;color:#1B3A6B'>Intelli-Credit</span><br>
        <span style='font-size:0.72rem;color:#64748b'>AI-Powered Credit Underwriting</span>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

    st.markdown("**Pipeline Navigation**")
    st.page_link("pages/01_ingestor.py",       label="Step 1 — Entity & Docs", icon=":material/snippet_folder:")
    st.page_link("pages/02_research.py",       label="Step 2 — Research", icon=":material/search:")
    st.page_link("pages/03_recommendation.py", label="Step 3 — Risk Engine", icon=":material/fact_check:")
    st.page_link("pages/04_cam.py",            label="Step 4 — CAM Report", icon=":material/description:")
    
    st.divider()

    # ── Key metrics if available ──────────────────────────────────────────────
    rec = st.session_state.get("recommendation_payload", {})
    if rec:
        decision = rec.get("decision", "—")
        dec_color = {"APPROVE": "#059669", "MANUAL_REVIEW": "#d97706", "REJECT": "#dc2626"}.get(decision, "#64748b")
        st.markdown(
            f"**Decision:** <span style='color:{dec_color};font-weight:700'>{decision}</span>  \n"
            f"**PD:** {rec.get('pd', 0)*100:.1f}%  \n"
            f"**Rate:** {rec.get('recommended_rate_pct', 0):.1f}%  \n"
            f"**Max Loan:** ₹{rec.get('recommended_loan_cr', 0):.0f} Cr",
            unsafe_allow_html=True,
        )
        st.divider()

    # ── Company name ──────────────────────────────────────────────────────────
    ext = st.session_state.get("extraction_payload", {})
    company = (ext.get("entity_context") or {}).get("company_name", "")
    if company:
        st.markdown(f"{icon_label('BANK', company)}", unsafe_allow_html=True)
        st.divider()

    # ── CAM Version Display ───────────────────────────────────────────────────
    try:
        with open("./data/cam_audit_log.json") as _f:
            _log = json.load(_f)
        if _log:
            last = _log[-1]
            st.markdown(
                f"📄 **CAM Version:** {last['version']}  \n"
                f"🕐 {last['timestamp'][:16].replace('T', ' ')}"
            )
            if st.button("View Version History", icon=":material/history"):
                st.session_state["show_version_history"] = True
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

    st.divider()
    # ── Databricks note ───────────────────────────────────────────────────────
    st.info(
        "💡 **Databricks:** Running in local demo mode. "
        "Payloads saved to `./data/*.json`.  \n"
        "See `utils/databricks_connector.py` for production integration."
    )


# ─────────────────────────────────────────────────────────────────────────────
# LANDING PAGE
# ─────────────────────────────────────────────────────────────────────────────
svg_header("BANK", "Intelli-Credit", level=1, size=48)
st.markdown("<div class='hero-tag'>AI-Powered Corporate Credit Underwriting.<br>From Raw PDF to CAM in Minutes.</div>", unsafe_allow_html=True)
st.markdown(f"""
<div style='margin:1rem 0'>
    <span class='hero-badge'>{icon_label("FLASH", "Gemini 2.0 Flash", size=14)}</span>
    <span class='hero-badge'>{icon_label("REPORT", "Docling PDF Parsing", size=14)}</span>
    <span class='hero-badge'>{icon_label("TRIANGULATION", "Fraud Triangulation", size=14)}</span>
    <span class='hero-badge'>{icon_label("CHART", "Altman Z-Score", size=14)}</span>
    <span class='hero-badge'>{icon_label("EDIT", "CAM PDF Export", size=14)}</span>
</div>
""", unsafe_allow_html=True)

st.markdown("")
col_cta, col_demo = st.columns([1, 2])
with col_cta:
    st.markdown("""
    <div class='ic-card'>
        <h3 style='color:#1B3A6B;margin-top:0'>Start New Application</h3>
        <p style='color:#475569;font-size:0.9rem'>
            Upload financial documents and run the full 4-module underwriting pipeline.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Begin Application → Module 1", use_container_width=True):
        st.switch_page("pages/01_ingestor.py")

with col_demo:
    st.markdown("""
    <div class='ic-card'>
        <h3 style='color:#1B3A6B;margin-top:0'>Load Demo Scenario</h3>
        <p style='color:#475569;font-size:0.9rem'>
            Instantly load a pre-built borrower profile to explore the full pipeline output.
        </p>
    </div>
    """, unsafe_allow_html=True)

    selected_scenario = st.selectbox(
        "Select Demo Scenario",
        options=list(DEMO_SCENARIOS.keys()),
        label_visibility="collapsed",
    )

    if st.button("Load Demo Data", icon=":material/flash_on:", use_container_width=True):
        scenario = DEMO_SCENARIOS[selected_scenario]
        st.session_state["extraction_payload"]     = scenario["extraction_payload"]
        st.session_state["research_payload"]       = scenario["research_payload"]
        st.session_state["recommendation_payload"] = scenario["recommendation_payload"]

        # Persist to disk so all pages can auto-restore
        for key, fname in [
            ("extraction_payload", "extraction_payload.json"),
            ("research_payload", "research_payload.json"),
            ("recommendation_payload", "recommendation_payload.json"),
        ]:
            with open(f"./data/{fname}", "w") as wf:
                json.dump(scenario[key], wf, indent=2, default=str)

        st.success(f"Demo loaded: **{selected_scenario.split(' — ')[0]}**", icon=":material/check_circle:")
        st.rerun()

# ── Scenario preview cards ────────────────────────────────────────────────────
st.markdown("### Available Demo Scenarios")
sc1, sc2, sc3 = st.columns(3)

with sc1:
    st.markdown("""
    <div class='scenario-approve'>
        <b>ABC Manufacturing Pvt Ltd</b><br>
        <span style='font-size:0.8rem;color:#065f46'>
        Sector: Manufacturing | ₹20Cr Term Loan<br>
        Z-Score: 2.74 | PD: 18% | CIBIL: 8/10<br>
        <b>Decision: APPROVE @ 11.2%</b>
        </span>
    </div>
    """, unsafe_allow_html=True)

with sc2:
    st.markdown("""
    <div class='scenario-review'>
        <b>XYZ Traders Pvt Ltd</b><br>
        <span style='font-size:0.8rem;color:#92400e'>
        Sector: Trading | ₹25Cr Working Capital<br>
        Z-Score: 1.95 | PD: 38% | CIBIL: 5/10<br>
        <b>Decision: MANUAL REVIEW @ 14.5%</b>
        </span>
    </div>
    """, unsafe_allow_html=True)

with sc3:
    st.markdown(f"""
    <div class='scenario-reject'>
        <b>PQR Real Estate Dev Ltd</b><br>
        <span style='font-size:0.8rem;color:#7f1d1d'>
        Sector: Real Estate | ₹40Cr Term Loan<br>
        Z-Score: 1.12 | PD: 72% | CIBIL: 2/10<br>
        <b>Decision: REJECT</b>
        </span>
    </div>
    """, unsafe_allow_html=True)

# ── Pipeline overview ─────────────────────────────────────────────────────────
st.divider()
st.markdown("### Pipeline Architecture")
p1, p2, p3, p4 = st.columns(4)
for col, icon_name, title, desc in [
    (p1, "FOLDER", "Module 1\nIngestor",     "Entity onboarding, document upload, AI classification, extraction & fraud detection"),
    (p2, "SEARCH", "Module 2\nResearch",     "OSINT research, web scraping, sector analysis & triangulation vs documents"),
    (p3, "CHART",  "Module 3\nRisk Engine",  "Altman Z-Score, PD, LGD, max loan sizing, interest rate & fraud dashboard"),
    (p4, "REPORT", "Module 4\nCAM Report",   "Multi-agent AI CAM generation, HITL review, PDF/Word export & versioning"),
]:
    col.markdown(
        f"<div class='ic-card' style='text-align:center'>"
        f"<div style='display:flex;justify-content:center;margin-bottom:0.5rem'>{get_svg(icon_name, size=40, color='#1B3A6B')}</div>"
        f"<div style='font-weight:700;color:#1B3A6B;white-space:pre-line;font-size:0.9rem'>{title}</div>"
        f"<div style='font-size:0.78rem;color:#64748b;margin-top:4px'>{desc}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
