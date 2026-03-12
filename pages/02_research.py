import streamlit as st
import json
import sys
import os
from datetime import datetime

# Add root folder to sys_path to find utils correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.web_scraper import gather_web_context
from utils.triangulation import triangulate_research_vs_documents
from utils.research_agent import generate_research_report

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Module 2 — Research Agent", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #f8fafc; }
h1,h2,h3,h4 { color: #1B3A6B; }
.stButton > button { background:#1B3A6B!important;color:white!important;border-radius:7px!important;font-weight:600!important; }
.stButton > button:hover { background:#2563EB!important; }
</style>
""", unsafe_allow_html=True)

# ── STEP 1: Session persistence ───────────────────────────────────────────────
def load_payload(name: str, filepath: str, required_step: int):
    if name not in st.session_state:
        try:
            with open(filepath) as f:
                st.session_state[name] = json.load(f)
            st.info(f"Session restored from {filepath}")
        except FileNotFoundError:
            st.warning(f"⚠ {name} not found. Please complete Step {required_step} first.")
            if st.button(f"← Go to Step {required_step}"):
                st.switch_page(f"pages/0{required_step}_{'ingestor' if required_step==1 else 'research'}.py")
            st.stop()

load_payload("extraction_payload", "./data/extraction_payload.json", 1)

# ── Step progress bar ─────────────────────────────────────────────────────────
steps_done = sum([
    "extraction_payload" in st.session_state,
    "research_payload"   in st.session_state,
    "recommendation_payload" in st.session_state,
])
st.title("🔍 Module 2 — Research Agent")
st.progress(steps_done / 4, text=f"Pipeline: {steps_done}/4 modules complete")
st.divider()

extraction = st.session_state["extraction_payload"]
entity = extraction.get("entity_context", {})
company_name = entity.get("company_name", "Unknown Company")
sector = entity.get("sector", "Unknown Sector")
cin = entity.get("cin", "")

# STEP 2 — PRIMARY INSIGHTS PORTAL
st.subheader("Primary Due Diligence Inputs")
with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        factory_capacity_pct = st.slider("Factory / Office Operating Capacity (%)", 0, 100, 80)
        management_quality = st.selectbox("Management Quality Assessment", ["Excellent", "Good", "Average", "Below Average", "Concerning"])
        site_visit_notes = st.text_area("Site Visit Observations (free text)", placeholder="e.g. Factory running at 40% capacity. New machinery installed. Stock levels high.")
        management_interview_notes = st.text_area("Management Interview Notes", placeholder="e.g. Promoter evasive about related-party transactions.")
    with col2:
        relationship_manager_rating = st.select_slider("RM's Overall Gut Rating", options=["Very Negative", "Negative", "Neutral", "Positive", "Very Positive"])
        existing_bank_conduct = st.selectbox("Existing Account Conduct (if applicable)", ["N/A", "Satisfactory", "Minor Irregularities", "Frequent Overdues", "NPA History"])
        
        # India-specific primary fields
        cibil_commercial_verified = st.selectbox("CIBIL Commercial Report Verified?", ["Not Yet", "Yes — Clean", "Yes — Minor Issues", "Yes — Significant Issues", "Not Available / NBFC not rated"])
        ecourt_search_done = st.checkbox("e-Courts litigation search completed?")
        ecourt_cases_found = st.number_input("Number of active court cases found (e-Courts)", min_value=0, value=0) if ecourt_search_done else 0
        rbi_circular_compliance = st.selectbox("RBI Circular Compliance Status", ["Not Applicable", "Fully Compliant", "Pending Items", "Non-Compliant"])

if st.button("Confirm Inputs & Run Web Intelligence", type="primary"):
    # Clear previous results if button is clicked again
    st.session_state.pop('web_context', None)
    st.session_state.pop('triangulation_flags', None)
    st.session_state.pop('research_report', None)

    # STEP 1 — WEB INTELLIGENCE GATHERING
    with st.status("Gathering Intelligence...", expanded=True) as status:
        st.write("Scanning news databases...")
        st.write("Checking NCLT and legal records...")
        st.write("Analyzing sector outlook...")
        st.write("Investigating promoter background...")
        st.write("Checking MCA / ROC filings...")
        st.write("Scanning GST compliance records...")
        
        web_context = gather_web_context(company_name, sector, cin)
        st.session_state['web_context'] = web_context
        
        # STEP 3 — RESEARCH vs DOCUMENT TRIANGULATION
        st.write("Triangulating web signals vs internal documents...")
        fraud_flags = extraction.get("fraud_flags", [])
        triangulation_flags = triangulate_research_vs_documents(web_context, extraction, fraud_flags, entity)
        st.session_state['triangulation_flags'] = triangulation_flags
        
        # STEP 4 — UNIFIED RESEARCH AGENT (LLM)
        st.write("Synthesizing unified risk profile...")
        primary_insights = {
            "factory_capacity_pct": factory_capacity_pct,
            "management_quality": management_quality,
            "site_visit_notes": site_visit_notes,
            "management_interview_notes": management_interview_notes,
            "rm_rating": relationship_manager_rating,
            "account_conduct": existing_bank_conduct,
            "cibil_commercial_verified": cibil_commercial_verified,
            "ecourt_cases_found": ecourt_cases_found,
            "rbi_compliance": rbi_circular_compliance
        }
        st.session_state["primary_insights"] = primary_insights
        
        report = generate_research_report(
            company_name, sector, cin, web_context, primary_insights, extraction, fraud_flags, triangulation_flags
        )
        st.session_state['research_report'] = report
        
        status.update(label="Research Complete!", state="complete", expanded=False)

# STEP 5 — DISPLAY RESEARCH RESULTS
if 'research_report' in st.session_state:
    report = st.session_state['research_report']
    triangulation_flags = st.session_state.get('triangulation_flags', [])
    
    st.markdown("---")
    
    # Row 0 — Triangulation Alerts
    if triangulation_flags:
        st.error("⚡ TRIANGULATION ALERTS — Contradictions Detected")
        st.caption("These flags highlight contradictions between web intelligence and your uploaded documents. They require analyst resolution before proceeding.")
        for flag in triangulation_flags:
            st.warning(f"**[{flag['severity']}] {flag['flag']}**\n\n{flag['detail']}")
    
    # Row 1 — Risk Score Cards
    st.subheader("Risk Dimensions (Scores out of 10)")
    cols = st.columns(7)
    
    scores = [
        ("News", report.news_risk_score),
        ("Legal", report.legal_risk_score),
        ("Sector", report.sector_risk_score),
        ("Operational", report.operational_risk_score),
        ("Promoter", report.promoter_risk_score),
        ("MCA", report.mca_risk_score),
        ("GST Compliance", report.gst_compliance_score)
    ]
    
    for col, (label, score) in zip(cols, scores):
        color = "green" if score < 4 else "orange" if score <= 6 else "red"
        col.metric(label, f"{score}/10")
    
    # Row 2 — Early Warning Signals
    st.subheader("Early Warning Signals")
    if not report.early_warning_signals:
        st.write("None detected.")
    for sig in report.early_warning_signals:
        sev_color = "red" if sig.severity in ["HIGH", "CRITICAL"] else "orange" if sig.severity == "MEDIUM" else "green"
        st.markdown(f"**:{sev_color}[[{sig.severity}]]** {sig.signal} ({sig.source}) - {sig.five_c_mapping}")
        st.caption(sig.detail)
    
    # Row 3 — Expandable summaries
    with st.expander("News Intelligence"):
        st.write(report.news_summary)
    with st.expander("Legal Risk Analysis"):
        st.write(report.legal_summary)
    with st.expander("Sector Outlook"):
        st.write(report.sector_summary)
    with st.expander("Promoter Background"):
        st.write(report.promoter_summary)
    with st.expander("MCA / ROC Compliance"):
        st.write(report.mca_summary)
    with st.expander("GST Compliance Analysis"):
        st.write(report.gst_compliance_summary)
    
    # Row 4 — India-Specific Flags
    st.subheader("India-Specific Findings")
    for fl in report.india_specific_flags:
        st.info(f"📍 {fl}")
    
    # STEP 6 — OUTPUT CONTRACT (CRITICAL)
    if st.button("Confirm Research & Proceed", type="primary"):
        st.session_state["research_payload"] = {
            "research_output": report.dict(),
            "triangulation_flags": triangulation_flags,
            "primary_insights": st.session_state["primary_insights"],
            "web_context_used": st.session_state["web_context"],
            "research_timestamp": datetime.now().isoformat()
        }
        
        with open("./data/research_payload.json", "w") as f:
            json.dump(st.session_state["research_payload"], f, indent=4)
            
        st.success("Research profile confirmed and saved. Proceeding to risk summary...")
        st.balloons()
        
        st.divider()
        n1, n2 = st.columns(2)
        with n1:
            if st.button("← Back to Module 1"):
                st.switch_page("pages/01_ingestor.py")
        with n2:
            if st.button("Proceed to Step 3 →"):
                st.switch_page("pages/03_recommendation.py")
