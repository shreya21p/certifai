"""
pages/03_recommendation.py — Module 3: Recommendation Engine & Forensic Dashboard
Intelli-Credit | Lead Financial Python Developer + Frontend Engineer
"""

import json
import os
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from utils.credit_engine import CreditEngine
from utils.gemini_client import call_gemini_with_retry
from utils.ui_icons import svg_header, get_svg, icon_label

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Module 3 — Recommendation Engine", layout="wide")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stApp { background: #f0f2f6; }
    h1, h2, h3, h4 { color: #1B3A6B; }
    .stButton > button {
        background: #1B3A6B; color: white;
        border-radius: 6px; border: none;
        font-weight: 600; padding: 0.4rem 1.2rem;
    }
    .stButton > button:hover { background: #2a5298; }
    .metric-card {
        background: white; border-radius: 12px;
        padding: 1rem 1.5rem;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #1B3A6B;
    }
    .decision-approve {
        background: linear-gradient(135deg, #065f46, #059669);
        color: white; border-radius: 12px; padding: 1.5rem 2rem;
        text-align: center; font-size: 2rem; font-weight: 700;
        letter-spacing: 2px;
        box-shadow: 0 4px 20px rgba(5,150,105,0.4);
    }
    .decision-review {
        background: linear-gradient(135deg, #92400e, #d97706);
        color: white; border-radius: 12px; padding: 1.5rem 2rem;
        text-align: center; font-size: 2rem; font-weight: 700;
        letter-spacing: 2px;
        box-shadow: 0 4px 20px rgba(217,119,6,0.4);
    }
    .decision-reject {
        background: linear-gradient(135deg, #7f1d1d, #dc2626);
        color: white; border-radius: 12px; padding: 1.5rem 2rem;
        text-align: center; font-size: 2rem; font-weight: 700;
        letter-spacing: 2px;
        box-shadow: 0 4px 20px rgba(220,38,38,0.4);
    }
    .swot-box {
        border-radius: 10px; padding: 1rem; min-height: 120px;
    }
    .india-concern {
        background: #fff7ed; border-left: 4px solid #ea580c;
        border-radius: 6px; padding: 0.6rem 1rem; margin: 0.3rem 0;
        color: #9a3412; font-size: 0.9rem;
    }
    .tri-flag-critical {
        background: #fef2f2; border-left: 4px solid #dc2626;
        border-radius: 6px; padding: 0.75rem 1rem; margin: 0.4rem 0;
    }
    .tri-flag-high {
        background: #fffbeb; border-left: 4px solid #f59e0b;
        border-radius: 6px; padding: 0.75rem 1rem; margin: 0.4rem 0;
    }
    .tri-flag-medium {
        background: #eff6ff; border-left: 4px solid #3b82f6;
        border-radius: 6px; padding: 0.75rem 1rem; margin: 0.4rem 0;
    }
    </style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SESSION PERSISTENCE
# ─────────────────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)

# ── STEP 1: Session persistence ───────────────────────────────────────────────
def load_payload(name: str, filepath: str, required_step: int):
    if name not in st.session_state:
        try:
            with open(filepath) as f:
                st.session_state[name] = json.load(f)
            st.info(f"Session restored from {filepath}")
        except FileNotFoundError:
            st.warning(f"{name} not found. Please complete Step {required_step} first.", icon=":material/warning:")
            if st.button(f"← Go to Step {required_step}"):
                st.switch_page(f"pages/0{required_step}_{'ingestor' if required_step==1 else 'research' if required_step==2 else 'recommendation'}.py")
            st.stop()

load_payload("extraction_payload", "./data/extraction_payload.json", 1)
load_payload("research_payload",   "./data/research_payload.json", 2)

# ── Step progress bar ─────────────────────────────────────────────────────────
steps_done = sum([
    "extraction_payload" in st.session_state,
    "research_payload"   in st.session_state,
    "recommendation_payload" in st.session_state,
])

extraction_payload: dict = st.session_state["extraction_payload"]
research_payload:   dict = st.session_state["research_payload"]

entity    = extraction_payload.get("entity_context", {}) or {}
financials = extraction_payload.get("financials", {}) or {}
doc_flags  = extraction_payload.get("fraud_flags", []) or []

research_output  = research_payload.get("research_output", {}) or {}
primary_insights = research_payload.get("primary_insights", {}) or {}
tri_flags_raw    = research_payload.get("triangulation_flags", []) or []
ewi_list         = research_output.get("early_warning_signals", []) or []

company_name = entity.get("company_name", "Entity")
sector       = entity.get("sector", "Other")
loan_amount  = float(entity.get("loan_amount") or entity.get("loan_amount_cr") or 0)

svg_header("BANK", "Module 3 — Recommendation Engine", level=1)
st.progress(steps_done / 4, text=f"Pipeline: {steps_done}/4 modules complete")
st.caption(f"Evaluating **{company_name}** | Sector: {sector} | Loan: ₹{loan_amount:.1f} Cr")
st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# PAGE HEADER
# ─────────────────────────────────────────────────────────────────────────────
# DELETED OLD HEADER
st.divider()

tab1, tab2 = st.tabs(["Credit Risk Engine", "Forensic Dashboard"])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — CREDIT RISK ENGINE
# ═════════════════════════════════════════════════════════════════════════════
with tab1:

    # ── Run engine ──────────────────────────────────────────────────────────
    engine = CreditEngine()

    with st.spinner("Running quantitative credit evaluation..."):
        result = engine.run_credit_evaluation(extraction_payload, research_payload)

    z_score    = result["z_score"]
    z_band     = result["z_band"]
    z_band_narrative = result.get("z_band_narrative", "")
    pd         = result["pd"]
    lgd        = result["lgd"]
    max_loan   = result["max_loan"]
    rate       = result["rate"]
    confidence = result["confidence"]
    decision   = result["decision"]
    ext_risk   = result["external_risk"]
    max_loan_breakdown = result["max_loan_breakdown"]

    # ── Gemini explainability ────────────────────────────────────────────────
    cibil_score    = financials.get("cibil_commercial_score", "N/A")
    gst_variance   = financials.get("gst_2a_vs_3b_variance_pct", 0) or 0
    ecourt_cases   = primary_insights.get("ecourt_cases_found", 0) or 0
    mca_status     = primary_insights.get("mca_last_filing_date", "Not available")
    rbi_compliance = research_output.get("gst_compliance_score", "N/A")
    z_band_label   = f"{z_score} ({z_band})"
    pd_pct         = round(pd * 100, 1)
    lgd_pct        = round(lgd * 100, 1)
    conf_pct       = round(confidence * 100, 1)

    gemini_response = None
    gemini_cache_key = "gemini_credit_assessment"

    if gemini_cache_key not in st.session_state:
        prompt = f"""
You are a Chief Credit Officer at a leading Indian bank.
Based on the quantitative credit analysis below, provide a structured credit assessment.

Company: {company_name}
Sector: {sector}
Loan Requested: ₹{loan_amount}Cr

QUANTITATIVE RESULTS:
- Altman Z-Score: {z_score} — {z_band_narrative}
- Probability of Default: {pd_pct}%
- Loss Given Default: {lgd_pct}%
- Max Recommended Loan: ₹{max_loan}Cr
- Recommended Interest Rate: {rate}%
- Decision: {decision}
- Confidence: {conf_pct}%

INDIA-SPECIFIC RISK INDICATORS:
- CIBIL Commercial Score: {cibil_score}
- GSTR-2A vs 3B Variance: {gst_variance}%
- e-Courts Active Cases: {ecourt_cases}
- MCA Filing Status: {mca_status}
- RBI/GST Compliance Score: {rbi_compliance}
- Triangulation Flags: {len(tri_flags_raw)} contradictions between web and documents

CRITICAL SCORING RULES FOR FIVE Cs — follow these exactly:
- Score of 1-2: Reserved ONLY for companies that should be REJECTED. Do not use these for APPROVE decisions.
- Score of 3-4: Significant concerns but approvable with conditions.
- Score of 5-6: Average — concerns present but manageable.
- Score of 7-8: Good — minor concerns only.
- Score of 9-10: Excellent — no material concerns.

For THIS company the decision is {decision} with {conf_pct}% confidence.
If decision is APPROVE, no single C score should be below 3.
If decision is MANUAL_REVIEW, no single C score should be below 2.
If decision is REJECT, scores of 1-2 are appropriate.

Also follow these India-specific scoring adjustments:
- CIBIL Commercial Score 7-8 → Character +1
- CIBIL Commercial Score 9-10 → Character +2
- Zero GSTR variance → Character +1
- Active e-Courts > 5 → Capacity -2
- Active e-Courts 1-5 → Capacity -1
- DSCR > 2.0 → Capacity +1
- MCA gap > 365 days → Character -1

RISK FLAGS: {json.dumps(doc_flags[:5], default=str)}
EXTERNAL RISK SCORE: {ext_risk}/10
EARLY WARNING SIGNALS: {json.dumps(ewi_list[:5], default=str)}
TRIANGULATION FLAGS: {json.dumps(tri_flags_raw[:3], default=str)}

Return JSON with exactly these fields:
{{
  "decision_rationale": ["point 1", "point 2", "point 3"],
  "swot": {{
    "strengths": ["s1", "s2"],
    "weaknesses": ["w1", "w2"],
    "opportunities": ["o1", "o2"],
    "threats": ["t1", "t2"]
  }},
  "five_cs_assessment": {{
    "character":   {{"score": 0, "comment": ""}},
    "capacity":    {{"score": 0, "comment": ""}},
    "capital":     {{"score": 0, "comment": ""}},
    "collateral":  {{"score": 0, "comment": ""}},
    "conditions":  {{"score": 0, "comment": ""}}
  }},
  "conditions_if_approved": ["condition 1", "condition 2"],
  "rejection_reason": null,
  "india_specific_concerns": ["concern 1", "concern 2"]
}}
"""
        try:
            with st.spinner("Generating AI credit assessment..."):
                raw = call_gemini_with_retry([prompt], response_mime_type="application/json")
                gemini_response = json.loads(raw)
                st.session_state[gemini_cache_key] = gemini_response
        except Exception as e:
            st.warning(f"AI assessment unavailable: {e}")
            gemini_response = {}
    else:
        gemini_response = st.session_state[gemini_cache_key]

    decision_rationale     = (gemini_response or {}).get("decision_rationale", [])
    swot                   = (gemini_response or {}).get("swot", {})
    five_cs_raw            = (gemini_response or {}).get("five_cs_assessment", {})
    conditions             = (gemini_response or {}).get("conditions_if_approved", [])
    rejection_reason       = (gemini_response or {}).get("rejection_reason")
    india_concerns         = (gemini_response or {}).get("india_specific_concerns", [])

    def validate_five_cs(five_cs: dict, decision: str) -> dict:
        """Ensure Five Cs scores are internally consistent with the decision."""
        min_score = {"APPROVE": 3, "MANUAL_REVIEW": 2, "REJECT": 1}.get(decision, 2)
        for c in ["character", "capacity", "capital", "collateral", "conditions"]:
            if c in five_cs:
                score = five_cs[c].get("score", 5)
                if score < min_score:
                    five_cs[c]["score"] = min_score
                    five_cs[c]["comment"] += (
                        f" [Score floor applied: minimum {min_score} for {decision} decision]"
                    )
        return five_cs

    five_cs = validate_five_cs(five_cs_raw, decision)

    # ── BUILD & SAVE OUTPUT PAYLOAD ──────────────────────────────────────────
    # Compute fraud_score for the output contract
    fraud_score = 0
    for fl in doc_flags:
        sev = (fl or {}).get("severity", "")
        if sev == "CRITICAL": fraud_score += 30
        elif sev == "HIGH":   fraud_score += 15
        elif sev == "MEDIUM": fraud_score += 8
    for tf in tri_flags_raw:
        sev = (tf or {}).get("severity", "")
        if sev == "CRITICAL": fraud_score += 20
        elif sev == "HIGH":   fraud_score += 10
    fraud_score = min(100, fraud_score)

    recommendation_payload = {
        "decision":               decision,
        "recommended_loan_cr":    max_loan,
        "recommended_rate_pct":   rate,
        "pd":                     pd,
        "lgd":                    lgd,
        "z_score":                z_score,
        "confidence":             confidence,
        "decision_rationale":     decision_rationale,
        "swot":                   swot,
        "five_cs":                five_cs,
        "conditions":             conditions,
        "rejection_reason":       rejection_reason,
        "india_specific_concerns": india_concerns,
        "fraud_score":            fraud_score,
        "fraud_flags":            doc_flags,
        "triangulation_flags":    tri_flags_raw,
        "early_warning_signals":  ewi_list,
        "recommendation_timestamp": datetime.now().isoformat(),
    }
    st.session_state["recommendation_payload"] = recommendation_payload
    try:
        with open("data/recommendation_payload.json", "w") as fp:
            json.dump(recommendation_payload, fp, indent=4, default=str)
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 1 — DECISION BANNER
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### Credit Decision")
    if decision == "APPROVE":
        icon = "✅"
        css_cls = "decision-approve"
    elif decision == "MANUAL_REVIEW":
        icon = "⚠️"
        css_cls = "decision-review"
    else:
        icon = "🚫"
        css_cls = "decision-reject"

    st.markdown(
        f'<div class="{css_cls}">{decision.replace("_", " ")}</div>',
        unsafe_allow_html=True,
    )
    st.markdown("")

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 2 — KEY METRICS
    # ─────────────────────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    z_color  = "normal" if z_band == "Safe" else ("off" if z_band == "Grey" else "inverse")
    pd_delta = f"{'Low' if pd < 0.25 else 'High'} risk"
    m1.metric("Altman Z-Score",        f"{z_score}",         f"{z_band}")
    m2.metric("Prob. of Default",       f"{pd_pct}%",         pd_delta)
    m3.metric("Loss Given Default",     f"{lgd_pct}%")
    m4.metric("Confidence Score",       f"{conf_pct}%")
    m5.metric("External Risk Score",    f"{ext_risk:.1f}/10")

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 3 — LOAN STRUCTURING TABLE
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("EDIT", "Loan Structuring", level=3)
    col_l, col_r = st.columns([3, 2])
    with col_l:
        import pandas as pd
        struct_data = {
            "Method":              ["DSCR-Based", "EBITDA Multiple (3.5×)", "Collateral LTV"],
            "Limit (₹ Cr)":       [
                max_loan_breakdown["dscr_limit"],
                max_loan_breakdown["ebitda_limit"],
                max_loan_breakdown["ltv_limit"],
            ],
        }
        df_struct = pd.DataFrame(struct_data)
        st.dataframe(df_struct, use_container_width=True, hide_index=True)
    with col_r:
        st.markdown(
            f"""
            <div class="metric-card">
                <p style="margin:0;font-size:0.8rem;color:#6b7280">Loan Requested</p>
                <p style="margin:0;font-size:1.5rem;font-weight:700;color:#1B3A6B">₹{loan_amount:.1f} Cr</p>
                <p style="margin:0;font-size:0.8rem;color:#6b7280;margin-top:0.5rem">Max Approved</p>
                <p style="margin:0;font-size:1.5rem;font-weight:700;color:#059669">₹{max_loan:.1f} Cr</p>
                <p style="margin:0;font-size:0.8rem;color:#6b7280;margin-top:0.5rem">Interest Rate</p>
                <p style="margin:0;font-size:1.5rem;font-weight:700;color:#d97706">{rate}% p.a.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 4 — FIVE Cs HEATMAP
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("DASHBOARD", "Five Cs Assessment", level=3)
    if five_cs:
        cs_names  = ["character", "capacity", "capital", "collateral", "conditions"]
        cs_labels = ["Character", "Capacity", "Capital", "Collateral", "Conditions"]
        cs_scores = [float((five_cs.get(c) or {}).get("score") or 0) for c in cs_names]
        cs_comments = [(five_cs.get(c) or {}).get("comment", "") for c in cs_names]

        cols_5c = st.columns(5)
        for col, label, score, comment in zip(cols_5c, cs_labels, cs_scores, cs_comments):
            color = (
                "#059669" if score >= 7
                else "#d97706" if score >= 4
                else "#dc2626"
            )
            col.markdown(
                f"""
                <div style="background:white;border-radius:10px;padding:1rem;
                            text-align:center;box-shadow:0 2px 8px rgba(0,0,0,0.08);
                            border-top:4px solid {color};">
                    <div style="font-size:1.8rem;font-weight:700;color:{color}">{score:.0f}</div>
                    <div style="font-size:0.75rem;font-weight:600;color:#374151;margin-top:2px">{label}</div>
                    <div style="font-size:0.7rem;color:#6b7280;margin-top:4px">{comment[:60]}{'…' if len(comment)>60 else ''}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.info("Five Cs assessment not available (AI call may have failed).")

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 5 — SWOT 2×2 GRID
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("ENTITY", "SWOT Analysis", level=3)
    if swot:
        sw_col, op_col = st.columns(2)
        with sw_col:
            strengths = swot.get("strengths", [])
            st.markdown(
                "<div class='swot-box' style='background:#ecfdf5;border:1.5px solid #059669'>"
                "<b style='color:#065f46'>💪 Strengths</b><ul style='margin-top:6px;color:#065f46'>"
                + "".join(f"<li style='font-size:0.85rem'>{s}</li>" for s in strengths)
                + "</ul></div>",
                unsafe_allow_html=True,
            )
        with op_col:
            opportunities = swot.get("opportunities", [])
            st.markdown(
                "<div class='swot-box' style='background:#eff6ff;border:1.5px solid #3b82f6'>"
                "<b style='color:#1d4ed8'>🚀 Opportunities</b><ul style='margin-top:6px;color:#1d4ed8'>"
                + "".join(f"<li style='font-size:0.85rem'>{o}</li>" for o in opportunities)
                + "</ul></div>",
                unsafe_allow_html=True,
            )
        wk_col, th_col = st.columns(2)
        with wk_col:
            weaknesses = swot.get("weaknesses", [])
            st.markdown(
                "<div class='swot-box' style='background:#fffbeb;border:1.5px solid #f59e0b'>"
                "<b style='color:#92400e'>⚠️ Weaknesses</b><ul style='margin-top:6px;color:#92400e'>"
                + "".join(f"<li style='font-size:0.85rem'>{w}</li>" for w in weaknesses)
                + "</ul></div>",
                unsafe_allow_html=True,
            )
        with th_col:
            threats = swot.get("threats", [])
            st.markdown(
                "<div class='swot-box' style='background:#fef2f2;border:1.5px solid #dc2626'>"
                "<b style='color:#7f1d1d'>🔴 Threats</b><ul style='margin-top:6px;color:#7f1d1d'>"
                + "".join(f"<li style='font-size:0.85rem'>{t}</li>" for t in threats)
                + "</ul></div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("SWOT not available.")

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 6 — DECISION RATIONALE
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("REPORT", "Decision Rationale", level=3)
    if decision_rationale:
        for i, point in enumerate(decision_rationale, 1):
            st.markdown(
                f"<div style='background:white;border-radius:8px;padding:0.6rem 1rem;"
                f"margin:0.3rem 0;box-shadow:0 1px 4px rgba(0,0,0,0.06);font-size:0.9rem'>"
                f"<b style='color:#1B3A6B'>{i}.</b> {point}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.info("Rationale not available.")

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 7 — INDIA-SPECIFIC CONCERNS  (NEW)
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("TRIANGULATION", "India-Specific Concerns", level=3)
    if india_concerns:
        for concern in india_concerns:
            st.markdown(
                f"<div class='india-concern'>🔶 {concern}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("No India-specific concerns flagged by the AI assessment.", icon=":material/check_circle:")

    # ── Extra India indicators panel ─────────────────────────────────────────
    with st.expander("India Risk Indicator Details", expanded=False):
        i1, i2, i3 = st.columns(3)
        i1.metric("CIBIL Commercial Score", f"{cibil_score}/10" if cibil_score != "N/A" else "N/A")
        i2.metric("GST 2A/3B Variance",     f"{gst_variance:.1f}%")
        i3.metric("e-Court Active Cases",   str(ecourt_cases))
        i4, i5 = st.columns(2)
        i4.metric("MCA Filing Date",         str(mca_status))
        i5.metric("Triangulation Conflicts", str(len(tri_flags_raw)))

    # ─────────────────────────────────────────────────────────────────────────
    # ROW 8 — CONDITIONS / REJECTION REASON
    # ─────────────────────────────────────────────────────────────────────────
    if decision == "APPROVE" and conditions:
        svg_header("CHECK", "Conditions for Approval", level=3)
        for i, cond in enumerate(conditions, 1):
            st.markdown(f"**{i}.** {cond}")
    elif decision == "REJECT" and rejection_reason:
        svg_header("ERROR", "Rejection Reason", level=3)
        st.error(rejection_reason)
    elif decision == "MANUAL_REVIEW":
        svg_header("SEARCH", "Manual Review Required", level=3)
        st.warning(
            "This case requires senior credit officer review due to elevated risk indicators. "
            "Review all fraud flags and triangulation conflicts before proceeding."
        )
        if conditions:
            st.markdown("**Proposed conditions if approved after review:**")
            for i, cond in enumerate(conditions, 1):
                st.markdown(f"{i}. {cond}")

    # ── Early Warning Signals ─────────────────────────────────────────────────
    if ewi_list:
        with st.expander(f"Early Warning Signals ({len(ewi_list)} detected)", expanded=False):
            for ew in ewi_list:
                if isinstance(ew, dict):
                    st.warning(f"**{ew.get('signal', ew.get('flag', 'EWS'))}** — {ew.get('detail', str(ew))}")
                else:
                    st.warning(str(ew))


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — FORENSIC FRAUD DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown("## 🔬 Forensic Fraud Dashboard")

    all_flags = doc_flags + [
        {**tf, "_source": "Triangulation"} for tf in tri_flags_raw
    ]

    # Recompute fraud score (same as above)
    fraud_score = 0
    for fl in doc_flags:
        sev = (fl or {}).get("severity", "")
        if sev == "CRITICAL": fraud_score += 30
        elif sev == "HIGH":   fraud_score += 15
        elif sev == "MEDIUM": fraud_score += 8
    for tf in tri_flags_raw:
        sev = (tf or {}).get("severity", "")
        if sev == "CRITICAL": fraud_score += 20
        elif sev == "HIGH":   fraud_score += 10
    fraud_score = min(100, fraud_score)

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 1 — FRAUD RISK SCORE GAUGE
    # ─────────────────────────────────────────────────────────────────────────
    p1, p2 = st.columns([1, 2])
    with p1:
        gauge_color = "#059669" if fraud_score < 30 else "#d97706" if fraud_score < 60 else "#dc2626"
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=fraud_score,
            title={"text": "Fraud Risk Score", "font": {"size": 16, "color": "#1B3A6B"}},
            number={"font": {"size": 36}, "suffix": "/100"},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1, "tickcolor": "#6b7280"},
                "bar":  {"color": gauge_color, "thickness": 0.3},
                "bgcolor": "white",
                "borderwidth": 2,
                "bordercolor": "#e5e7eb",
                "steps": [
                    {"range": [0,  30], "color": "#ecfdf5"},
                    {"range": [30, 60], "color": "#fffbeb"},
                    {"range": [60, 100],"color": "#fef2f2"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.75,
                    "value": fraud_score,
                },
            },
        ))
        fig_gauge.update_layout(
            height=300,
            margin=dict(t=40, b=10, l=20, r=20),
            paper_bgcolor="white",
            font={"family": "Inter"},
        )
        st.plotly_chart(fig_gauge, use_container_width=True)

        # Flag summary stats
        crit_count = sum(1 for f in all_flags if (f or {}).get("severity") == "CRITICAL")
        high_count = sum(1 for f in all_flags if (f or {}).get("severity") == "HIGH")
        med_count  = sum(1 for f in all_flags if (f or {}).get("severity") == "MEDIUM")
        st.markdown(
            f"<div style='text-align:center'>"
            f"🔴 <b>{crit_count} CRITICAL</b> &nbsp; "
            f"🟡 <b>{high_count} HIGH</b> &nbsp; "
            f"🔵 <b>{med_count} MEDIUM</b></div>",
            unsafe_allow_html=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 2 — FINANCIAL TIMELINE CHART
    # ─────────────────────────────────────────────────────────────────────────
    with p2:
        rev  = float(financials.get("revenue_cr")            or 0)
        ebit = float(financials.get("ebitda_cr")             or 0)
        pat  = float(financials.get("pat_cr")                or 0)
        ocf  = float(financials.get("operating_cashflow_cr") or 0)

        fig_bar = go.Figure()
        categories = ["Revenue", "EBITDA", "PAT", "Oper. Cashflow"]
        values     = [rev, ebit, pat, ocf]
        colors     = ["#1B3A6B", "#3b82f6", "#059669", "#f59e0b"]

        for cat, val, clr in zip(categories, values, colors):
            fig_bar.add_trace(go.Bar(
                name=cat, x=[cat], y=[val],
                marker_color=clr,
                text=[f"₹{val:.1f}Cr"], textposition="outside",
            ))

        # Overlay critical fraud flag annotations
        for i, fl in enumerate(all_flags[:3]):
            if (fl or {}).get("severity") == "CRITICAL":
                fig_bar.add_annotation(
                    x=0, y=max(rev, 1) * 1.1,
                    text=f"🚨 {fl.get('flag','FLAG')}",
                    showarrow=False,
                    font=dict(color="#dc2626", size=10),
                    bgcolor="#fef2f2",
                    bordercolor="#dc2626",
                )
                break  # one annotation is enough

        fig_bar.update_layout(
            title="Financial Profile (₹ Cr)",
            yaxis_title="₹ Crore",
            barmode="group",
            height=300,
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20),
            paper_bgcolor="white",
            plot_bgcolor="white",
            font={"family": "Inter"},
        )
        fig_bar.update_xaxes(showgrid=False)
        fig_bar.update_yaxes(gridcolor="#f3f4f6")
        st.plotly_chart(fig_bar, use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 3 — FIVE Cs RADAR CHART
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 🕸️ Five Cs Radar")
    if five_cs:
        cs_order = ["character", "capacity", "capital", "collateral", "conditions"]
        radar_scores = [float((five_cs.get(c) or {}).get("score") or 0) for c in cs_order]
        radar_labels = ["Character", "Capacity", "Capital", "Collateral", "Conditions"]

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=radar_scores + [radar_scores[0]],
            theta=radar_labels + [radar_labels[0]],
            fill="toself",
            fillcolor="rgba(27,58,107,0.15)",
            line=dict(color="#1B3A6B", width=2),
            name="Five Cs",
        ))
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 10], tickfont=dict(size=9)),
                angularaxis=dict(tickfont=dict(size=11, color="#1B3A6B")),
            ),
            showlegend=False,
            height=350,
            margin=dict(t=20, b=20, l=40, r=40),
            paper_bgcolor="white",
            font={"family": "Inter"},
        )
        st.plotly_chart(fig_radar, use_container_width=True)
    else:
        st.info("Five Cs radar unavailable — AI assessment required.")

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 4 — ENTITY RELATIONSHIP GRAPH (Native Plotly)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### 🕸️ Entity Relationship Graph")
    try:
        import plotly.graph_objects as go
        
        # We will position nodes manually for a clean "Star" layout around the Company
        nodes_data = {}
        edges_data = []
        
        # 1. Company (Center)
        nodes_data["company"] = {"label": company_name, "x": 0, "y": 0, "color": "#1B3A6B", "size": 35}
        
        # 2. Promoters
        promoter_holding = financials.get("promoter_holding_pct")
        if promoter_holding is not None:
            nodes_data["promoter"] = {"label": f"Promoters<br>({promoter_holding}%)", "x": 0, "y": 1, "color": "#3b82f6", "size": 25}
            edges_data.append(("company", "promoter", "Holds"))
            
            # Pledged
            pledge_pct = financials.get("promoter_pledge_pct")
            if pledge_pct and float(pledge_pct or 0) > 0:
                nodes_data["pledge"] = {"label": f"Pledged<br>({pledge_pct}%)", "x": 0, "y": 2, "color": "#f59e0b", "size": 20}
                edges_data.append(("promoter", "pledge", "Pledged"))

        # 3. Collateral
        col_type = entity.get("collateral_type", "None")
        col_value = float(entity.get("collateral_value") or entity.get("collateral_value_cr") or 0)
        if col_type and col_type != "None":
            nodes_data["collateral"] = {"label": f"Collateral<br>{col_type}<br>₹{col_value:.0f}Cr", "x": 1, "y": 0, "color": "#059669", "size": 25}
            edges_data.append(("company", "collateral", "Offered as"))

        # 4. Bank
        nodes_data["bank"] = {"label": "Lending Bank", "x": -1, "y": 0, "color": "#6d28d9", "size": 30}
        edges_data.append(("bank", "company", "Loan Applied"))

        # 5. Debt
        total_debt = float(financials.get("total_debt_cr") or 0)
        if total_debt > 0:
            nodes_data["debt"] = {"label": f"Existing Debt<br>₹{total_debt:.0f}Cr", "x": 0, "y": -1, "color": "#64748b", "size": 25}
            edges_data.append(("company", "debt", "Owes"))

        # Build Plotly Figure
        edge_x = []
        edge_y = []
        for src, dst, label in edges_data:
            x0, y0 = nodes_data[src]["x"], nodes_data[src]["y"]
            x1, y1 = nodes_data[dst]["x"], nodes_data[dst]["y"]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=3, color='#9ca3af'),
            hoverinfo='none',
            mode='lines'
        )

        node_x = [nd["x"] for nd in nodes_data.values()]
        node_y = [nd["y"] for nd in nodes_data.values()]
        node_text = [nd["label"] for nd in nodes_data.values()]
        node_color = [nd["color"] for nd in nodes_data.values()]
        node_size = [nd["size"] for nd in nodes_data.values()]

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            text=node_text,
            textposition="top center" if not any(y>0 for y in node_y) else "bottom center",
            hoverinfo='text',
            marker=dict(
                showscale=False,
                color=node_color,
                size=node_size,
                line_width=2,
                line_color='white'
            )
        )

        fig_net = go.Figure(data=[edge_trace, node_trace])
        fig_net.update_layout(
            title='',
            showlegend=False,
            height=400,
            hovermode='closest',
            margin=dict(b=20,l=20,r=20,t=20),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            plot_bgcolor="white",
            paper_bgcolor="white"
        )
            
        st.plotly_chart(fig_net, use_container_width=True)

    except Exception as ex:
        st.error(f"Entity graph error: {ex}")

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 5 — TRIANGULATION FLAGS  (NEW)
    # ─────────────────────────────────────────────────────────────────────────
    st.markdown("### ⚡ Document vs Web Triangulation Conflicts")
    if tri_flags_raw:
        for tf in tri_flags_raw:
            tf = tf or {}
            sev  = tf.get("severity", "MEDIUM")
            flag = tf.get("flag", "TRIANGULATION_CONFLICT")
            det  = tf.get("detail", "")
            action = tf.get("recommended_action", "Seek clarification from borrower.")

            css_cls = (
                "tri-flag-critical" if sev == "CRITICAL"
                else "tri-flag-high"   if sev == "HIGH"
                else "tri-flag-medium"
            )
            icon = "🔴" if sev == "CRITICAL" else "🟡" if sev == "HIGH" else "🔵"
            st.markdown(
                f"""<div class='{css_cls}'>
                    <div style='font-weight:700;font-size:0.9rem'>{flag}
                        <span style='float:right;background:#e5e7eb;border-radius:4px;
                        padding:1px 6px;font-size:0.75rem;font-weight:600'>{sev}</span>
                    </div>
                    <div style='font-size:0.82rem;margin-top:4px;color:#374151'>{det}</div>
                    <div style='font-size:0.78rem;margin-top:6px;color:#6b7280'>
                        📌 <i>Analyst action: {action}</i></div>
                </div>""",
                unsafe_allow_html=True,
            )
    else:
        st.success("No document-vs-web triangulation conflicts detected.", icon=":material/check_circle:")

    # ─────────────────────────────────────────────────────────────────────────
    # PANEL 6 — FULL FRAUD FLAGS TABLE
    # ─────────────────────────────────────────────────────────────────────────
    svg_header("REPORT", "Complete Fraud Flags Register", level=3)
    if all_flags:
        import pandas as _pd2
        rows = []
        for fl in doc_flags:
            rows.append({
                "Flag":     (fl or {}).get("flag",     ""),
                "Severity": (fl or {}).get("severity", ""),
                "Detail":   (fl or {}).get("detail",   ""),
                "Five C":   (fl or {}).get("five_c",   ""),
                "Source":   (fl or {}).get("source",   "Document Analysis"),
                "Type":     "Document",
            })
        for tf in tri_flags_raw:
            rows.append({
                "Flag":     (tf or {}).get("flag",     ""),
                "Severity": (tf or {}).get("severity", ""),
                "Detail":   (tf or {}).get("detail",   ""),
                "Five C":   (tf or {}).get("five_c",   ""),
                "Source":   (tf or {}).get("source",   "Web Research"),
                "Type":     "Triangulation",
            })
        df_flags = _pd2.DataFrame(rows)

        def severity_style(val):
            c = {"CRITICAL": "background:#fef2f2;color:#dc2626;font-weight:700",
                 "HIGH":     "background:#fffbeb;color:#d97706;font-weight:600",
                 "MEDIUM":   "background:#eff6ff;color:#2563eb"}.get(val, "")
            return c

        st.dataframe(
            df_flags.style.map(severity_style, subset=["Severity"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No fraud flags registered.", icon=":material/check_circle:")

    # ── Footer ───────────────────────────────────────────────────────────────
    st.divider()
    
    n1, n2 = st.columns(2)
    with n1:
        if st.button("← Back to Module 2"):
            st.switch_page("pages/02_research.py")
    with n2:
        if st.button("Proceed to Step 4 →"):
            st.switch_page("pages/04_cam.py")

    st.caption(
        f"📁 Recommendation payload saved → `./data/recommendation_payload.json` | "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
