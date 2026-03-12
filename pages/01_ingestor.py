import streamlit as st
import pandas as pd
import json
import os
import base64
from datetime import datetime, date
from pydantic import BaseModel, create_model
from typing import Literal, Optional, List, Dict
import plotly.graph_objects as go
import tempfile

from utils.gemini_client import call_gemini_with_retry
from utils.docling_parser import parse_document
from utils.schema_editor import render_schema_editor
from utils.fraud_engine import detect_revenue_anomalies
from utils.ui_icons import svg_header, get_svg, icon_label

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Module 1 — Ingestor", layout="wide")

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

# Data Models
class DocumentClassification(BaseModel):
    filename: str
    detected_type: Literal[
        "ALM", "ShareholdingPattern", "BorrowingProfile", "AnnualReport", 
        "PortfolioPerformance", "BankStatement", "GSTReturn", "Unknown"
    ]
    confidence: float
    reasoning: str

# Session Init
if "step" not in st.session_state:
    st.session_state["step"] = 1
if "entity_context" not in st.session_state:
    st.session_state["entity_context"] = {}
if "classification_results" not in st.session_state:
    st.session_state["classification_results"] = {}  # dict of filename -> classification 
if "accepted_files" not in st.session_state:
    st.session_state["accepted_files"] = []
if "schema_config" not in st.session_state:
    st.session_state["schema_config"] = None
if "extraction_results" not in st.session_state:
    st.session_state["extraction_results"] = {}
if "final_extraction" not in st.session_state:
    st.session_state["final_extraction"] = {}

# ── STEP 1: Session persistence ───────────────────────────────────────────────
def load_payload(name: str, filepath: str):
    if name not in st.session_state:
        try:
            with open(filepath) as f:
                st.session_state[name] = json.load(f)
            st.info(f"Session restored from {filepath}")
        except FileNotFoundError:
            pass

load_payload("extraction_payload", "./data/extraction_payload.json")

# ── Step progress bar ─────────────────────────────────────────────────────────
steps_done = sum([
    "extraction_payload" in st.session_state,
    "research_payload"   in st.session_state,
    "recommendation_payload" in st.session_state,
])
svg_header("FOLDER", "Module 1 — Ingestor & Data Extractor", level=1)
st.progress(steps_done / 4, text=f"Pipeline: {steps_done}/4 modules complete")
st.divider()


def render_step_1():
    st.header("Step 1: Entity Onboarding")
    
    with st.form("onboarding_form"):
        st.subheader("Entity Details")
        c1, c2 = st.columns(2)
        company_name = c1.text_input("Company Name")
        cin = c2.text_input("CIN (21 chars)")
        pan = c1.text_input("PAN (10 chars)")
        sector = c2.selectbox("Sector", ["Manufacturing", "NBFC", "Real Estate", "Infrastructure", "Steel", "Pharma", "Other"])
        sub_sector = c1.text_input("Sub-sector")
        turnover = c2.number_input("Annual Turnover (₹ Cr)", min_value=0.0)
        years_op = c1.number_input("Years in Operation", min_value=0)
        
        cibil = c2.number_input("CIBIL Commercial Score (1-10)", min_value=1.0, max_value=10.0, value=7.0, help="CIBIL Commercial rank 1 = highest risk, 10 = lowest risk")
        mca_date = c1.date_input("MCA Last Filing Date")
        gst_mismatch = c2.selectbox("GSTR-2A vs 3B Mismatch Flag", ["Not Checked", "No Mismatch", "Minor (<5%)", "Moderate (5–15%)", "Severe (>15%)"])

        st.subheader("Loan Details")
        c3, c4 = st.columns(2)
        loan_type = c3.selectbox("Loan Type", ["Term Loan", "Working Capital", "CC Limit", "LC/BG Facility"])
        loan_amount = c4.number_input("Loan Amount Requested (₹ Cr)", min_value=0.0)
        tenure = c3.number_input("Tenure (months)", min_value=0)
        purpose = c4.text_area("Purpose of Loan")
        existing_rel = c3.radio("Existing Relationship with Bank", ["Yes", "No"])
        collateral_type = c3.selectbox("Collateral Type", ["Real Estate", "Plant & Machinery", "FD", "Stocks", "None"])
        collateral_value = c4.number_input("Collateral Value (₹ Cr)", min_value=0.0)
        
        submitted = st.form_submit_button("Save & Proceed")
        if submitted:
            st.session_state["entity_context"] = {
                "company_name": company_name,
                "cin": cin,
                "pan": pan,
                "sector": sector,
                "sub_sector": sub_sector,
                "turnover": turnover,
                "years_op": years_op,
                "cibil_commercial_score": cibil,
                "mca_last_filing_date": mca_date,
                "gstr_2a_3b_mismatch_flag": gst_mismatch,
                "loan_type": loan_type,
                "loan_amount": loan_amount,
                "tenure": tenure,
                "purpose": purpose,
                "existing_relationship": existing_rel,
                "collateral_type": collateral_type,
                "collateral_value": collateral_value,
            }
            st.session_state["step"] = 2
            st.rerun()
            
    with st.expander("View Saved Context"):
        st.json(st.session_state["entity_context"])

FILENAME_KEYWORDS = {
    "ALM":                  ["alm", "asset_liab", "assetliab", "liquidity"],
    "ShareholdingPattern":  ["shareholding", "shareholder", "ownership", "promoter"],
    "BorrowingProfile":     ["borrow", "debt", "loan_profile", "credit_profile"],
    "AnnualReport":         ["annual", "p&l", "pnl", "financials", "balance_sheet"],
    "PortfolioPerformance": ["portfolio", "npa", "dpd", "par", "collection", "vintage"],
    "BankStatement":        ["bank", "statement", "txn", "transaction"],
    "GSTReturn":            ["gst", "gstr", "tax_return"],
}

def classify_by_filename(filename: str) -> dict:
    """Fast offline classifier: keyword-match the filename. No API call needed."""
    name_lower = filename.lower()
    for doc_type, keywords in FILENAME_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return {
                "filename": filename,
                "detected_type": doc_type,
                "confidence": 0.75,
                "reasoning": f"Classified from filename keywords (offline fallback). API unavailable or rate-limited."
            }
    return {
        "filename": filename,
        "detected_type": "Unknown",
        "confidence": 0.3,
        "reasoning": "No keyword match in filename. Please override manually."
    }

def classify_document(filename, file_bytes):
    ext = os.path.splitext(filename)[1].lower()
    contents = []
    
    prompt = f"""
You are a financial document classifier. Classify the following document content.

Document filename: {filename}

Respond with ONLY a valid JSON object. No explanation, no markdown, no code fences.
Exactly this format:
{{"detected_type": "ALM", "confidence": 0.95, "reasoning": "Contains maturity buckets and liquidity gap"}}

detected_type must be one of: ALM, ShareholdingPattern, BorrowingProfile, AnnualReport, PortfolioPerformance, BankStatement, GSTReturn, Unknown
confidence must be a float between 0 and 1
"""

    try:
        if ext in ['.xlsx', '.csv']:
            preview_text = file_bytes[:500].decode("utf-8", errors="ignore")
            contents = [prompt + "\n\nPreview: " + preview_text]
        elif ext == '.pdf':
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
                tf.write(file_bytes)
                tf_path = tf.name
            try:
                markdown_text = parse_document(tf_path)
                preview_text = markdown_text[:2000]
            finally:
                os.remove(tf_path)
            contents = [prompt + "\n\nPreview: " + preview_text]
        elif ext in ['.jpg', '.jpeg', '.png']:
            img_data = {
                "mime_type": f"image/{ext[1:]}",
                "data": file_bytes
            }
            contents = [prompt, img_data]
        else:
            return classify_by_filename(filename)
            
        res_text = call_gemini_with_retry(contents, response_mime_type="application/json")
        res_json = json.loads(res_text)
        return res_json
    except Exception as e:
        err_str = str(e)
        is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
        is_key_err = "400" in err_str or "403" in err_str or "expired" in err_str.lower() or "leaked" in err_str.lower()
        if is_quota or is_key_err:
            st.warning(f"API unavailable for **{filename}** — using filename-based classification instead.", icon=":material/warning:")
            return classify_by_filename(filename)
        st.error(f"Classification error for {filename}: {e}")
        return {"filename": filename, "detected_type": "Unknown", "confidence": 0.0, "reasoning": str(e)}

def render_step_2():
    st.header("Step 2: Document Upload & Classification")
    
    uploaded_files = st.file_uploader("Upload financial documents", accept_multiple_files=True, type=['pdf', 'xlsx', 'csv', 'jpg', 'jpeg', 'png'])
    
    if st.button("Run Auto-Classification") and uploaded_files:
        progress = st.progress(0)
        status = st.empty()
        total = len(uploaded_files)
        
        for i, f in enumerate(uploaded_files):
            if f.name not in st.session_state["classification_results"]:
                status.info(f"Classifying {i+1}/{total}: **{f.name}**...")
                res = classify_document(f.name, f.getvalue())
                if res:
                    st.session_state["classification_results"][f.name] = res
                    st.session_state[f"file_data_{f.name}"] = f.getvalue()
                # Throttle: 5s between calls to stay within free-tier RPM limits
                if i < total - 1:
                    import time
                    time.sleep(5)
            progress.progress((i + 1) / total)
        
        status.success("Classification complete!", icon=":material/check_circle:")
    
    if st.session_state["classification_results"]:
        st.subheader("Classification Results")
        
        # Human in the loop editing
        df_list = []
        for name, res in st.session_state["classification_results"].items():
            df_list.append({
                "Filename": name,
                "AI-Detected Type": res.get("detected_type", "Unknown"),
                "Confidence": res.get("confidence", 0.0),
                "Reasoning": res.get("reasoning", ""),
                "Accept": True
            })
        
        if df_list:
            df = pd.DataFrame(df_list)
            types = ["ALM", "ShareholdingPattern", "BorrowingProfile", "AnnualReport", "PortfolioPerformance", "BankStatement", "GSTReturn", "Unknown"]
            edited_df = st.data_editor(
                df,
                column_config={
                    "AI-Detected Type": st.column_config.SelectboxColumn("Type", options=types, required=True),
                    "Accept": st.column_config.CheckboxColumn("Accept/Reject")
                },
                disabled=["Filename", "Confidence", "Reasoning"],
                hide_index=True
            )
            
            if st.button("Confirm Classification & Proceed"):
                accepted = edited_df[edited_df["Accept"] == True]
                st.session_state["accepted_files"] = []
                for _, row in accepted.iterrows():
                    st.session_state["accepted_files"].append({
                        "filename": row["Filename"],
                        "type": row["AI-Detected Type"]
                    })
                st.session_state["step"] = 3
                st.rerun()

def render_step_3():
    st.header("Step 3: Dynamic Schema Editor")
    schema_df = render_schema_editor()
    
    if st.button("Confirm Schema & Proceed"):
        enabled_rows = schema_df[schema_df["Enabled"] == True]
        st.session_state["schema_config"] = enabled_rows.to_dict('records')
        st.session_state["step"] = 4
        st.rerun()
        
    if st.button("Back to Classification"):
        st.session_state["step"] = 2
        st.rerun()

FIELD_ALIASES = {
    "revenue_cr":                ["Revenue from Operations", "Total Revenue", "Net Sales",
                                   "Revenue from operations", "Turnover", "Sales"],
    "ebitda_cr":                 ["EBITDA", "Operating Profit", "Earnings before interest"],
    "pat_cr":                    ["PAT", "Profit After Tax", "Net Profit", "Total Comprehensive Income"],
    "total_debt_cr":             ["Total Debt", "Total Borrowings", "Total Outstanding"],
    "total_assets_cr":           ["Total Assets", "TOTAL ASSETS", "Total Application"],
    "net_worth_cr":              ["Net Worth", "Total Equity", "Shareholders Equity",
                                   "TOTAL EQUITY", "Equity + Reserves"],
    "operating_cashflow_cr":     ["Net Cash from Operations", "Cash from Operating Activities",
                                   "NET CASH FROM OPERATIONS"],
    "promoter_holding_pct":      ["Promoter Holding", "Promoter %", "% Holding promoter",
                                   "Sub-total Promoters %"],
    "promoter_pledge_pct":       ["Pledge %", "Pledged %", "% Pledged", "Pledge as % of Total Equity"],
    "npa_pct":                   ["Gross NPA %", "NPA %", "GNPA %", "Gross NPA"],
    "net_npa_pct":               ["Net NPA %", "NNPA %", "Net NPA"],
    "par_30_pct":                ["PAR > 30", "PAR 30", "Portfolio at Risk 30 days",
                                   "PAR > 30 Days %"],
    "par_90_pct":                ["PAR > 90", "PAR 90", "Portfolio at Risk 90 days",
                                   "PAR > 90 Days %"],
    "collection_efficiency_pct": ["Collection Efficiency", "Collection %", "CE %"],
    "provision_coverage_ratio_pct": ["Provision Coverage", "PCR", "Provision Coverage Ratio %"],
    "credit_cost_pct":           ["Credit Cost", "Credit Cost %"],
    "vintage_30dpd_pct":         ["Vintage 30 DPD", "30-DPD", "30DPD vintage"],
    "vintage_90dpd_pct":         ["Vintage 90 DPD", "90-DPD", "90DPD vintage"],
    "avg_monthly_bank_inflow_cr": ["Average Monthly Inflow", "Monthly Bank Inflow",
                                    "Monthly inflow", "Bank Inflow (monthly)"],
    "avg_monthly_bank_outflow_cr": ["Average Monthly Outflow", "Monthly Bank Outflow"],
    "gst_declared_sales_cr":     ["GST Sales", "GSTR Sales", "Declared Sales (GST)",
                                   "GST-implied sales"],
    "gst_2a_input_credit_cr":    ["GSTR-2A", "2A Input Credit", "Input Tax Credit"],
    "gst_3b_output_tax_cr":      ["GSTR-3B", "3B Output Tax", "Output Tax"],
    "gst_2a_vs_3b_variance_pct": ["GSTR variance", "2A vs 3B", "GST mismatch %"],
    "liquidity_gap_cr":          ["Liquidity Gap", "Gap (A-B)", "Net Gap"],
    "secured_debt_cr":           ["Secured Debt", "Secured Term Loans", "Secured Borrowings"],
    "unsecured_debt_cr":         ["Unsecured Debt", "Unsecured Borrowings", "Director Loan"],
    "debt_to_equity_ratio":      ["D/E Ratio", "Debt to Equity", "Leverage Ratio"],
}

def get_aliases(field_key: str) -> str:
    aliases = FIELD_ALIASES.get(field_key, [field_key])
    return " / ".join(aliases)

DOC_TYPE_FIELDS = {
    "AnnualReport":        ["revenue_cr","ebitda_cr","pat_cr","total_debt_cr",
                            "total_assets_cr","net_worth_cr","operating_cashflow_cr",
                            "debt_to_equity_ratio"],
    "ALM":                 ["liquidity_gap_cr","total_outflows_cr","short_term_liabilities_cr"],
    "ShareholdingPattern": ["promoter_holding_pct","promoter_pledge_pct","institutional_holding_pct"],
    "BorrowingProfile":    ["secured_debt_cr","unsecured_debt_cr","average_interest_rate",
                            "avg_monthly_bank_inflow_cr","avg_monthly_bank_outflow_cr"],
    "PortfolioPerformance":["npa_pct","net_npa_pct","par_30_pct","par_90_pct",
                            "collection_efficiency_pct","provision_coverage_ratio_pct",
                            "credit_cost_pct","vintage_30dpd_pct","vintage_90dpd_pct",
                            "disbursement_cr","gross_npa_cr"],
    "GSTReturn":           ["gst_declared_sales_cr","gst_2a_input_credit_cr",
                            "gst_3b_output_tax_cr","gst_2a_vs_3b_variance_pct",
                            "gst_filing_regularity"],
    "BankStatement":       ["avg_monthly_bank_inflow_cr","avg_monthly_bank_outflow_cr"],
}

def extract_file_data(file_info, schema_config):
    filename = file_info["filename"]
    doc_type = file_info["type"]
    file_bytes = st.session_state.get(f"file_data_{filename}")
    if not file_bytes:
        return {}
        
    # Filter schema_config to only include relevant fields for this document type
    allowed_keys = DOC_TYPE_FIELDS.get(doc_type)
    if allowed_keys:
        relevant_fields = [f for f in schema_config if f["Field Key"] in allowed_keys]
    else:
        relevant_fields = schema_config # fallback to all if Unknown or not mapped
        
    fields_list_str = "\n".join([
        f'- {field["Field Key"]}: also labeled as {get_aliases(field["Field Key"])} | unit: {field.get("Unit","number")} | return null if not found'
        for field in relevant_fields
    ])
    
    system_prompt = f"""You are a financial data extraction expert. Extract values from the document below.

DOCUMENT TYPE: {doc_type}

FIELDS TO EXTRACT (try ALL aliases for each field):
{fields_list_str}

RULES:
1. Return ONLY a JSON object, no markdown, no explanation
2. Every enabled field key must appear in the output
3. If a value is not found in this document, return null (not 0)
4. For percentage fields, return the number only (e.g. 15.68 not "15.68%")
5. For crore fields, ensure value is in crores (not lakhs or rupees)
6. Include a "data_lineage" key mapping field_key to the exact cell/row where you found it
7. List all null fields in "missing_fields". Include "extraction_confidence" float and "source_documents" list natively in the root.

Return format:
{{
    "extraction_confidence": 0.95,
    "missing_fields": ["ebitda_cr"],
    "source_documents": ["{filename}"],
    "revenue_cr": 85.50,
    "data_lineage": {{"revenue_cr": "P&L sheet, row 3"}}
}}"""

    if doc_type == "PortfolioPerformance":
        system_prompt += """\n\nThis is a Portfolio Performance / Cuts document. For this specific document:
    Focus on: DPD buckets (0-30, 30-60, 60-90, 90+), PAR ratios, collection efficiency by vintage, geographic/product-wise NPA split, gross and net NPA amounts, provision coverage ratio, credit cost, disbursement trends. Extract vintage analysis if table is present."""

    ext = os.path.splitext(filename)[1].lower()
    
    try:
        if ext in ['.xlsx', '.csv']:
            # Structured extraction using pandas summary to LLM
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(file_bytes)
                tf_path = tf.name
            try:
                if ext == '.csv':
                    df = pd.read_csv(tf_path)
                else:
                    df = pd.read_excel(tf_path)
                df_summary = df.head(100).to_string() # send preview
            finally:
                os.remove(tf_path)
            
            contents = [system_prompt, f"Data Summary for {filename}:\n" + df_summary]
            res_text = call_gemini_with_retry(contents, response_mime_type="application/json")
        else:
            # Unstructured
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tf:
                tf.write(file_bytes)
                tf_path = tf.name
            try:
                markdown_text = parse_document(tf_path)
            finally:
                os.remove(tf_path)
                
            contents = [system_prompt, f"Document Markdown ({filename}):\n\n" + markdown_text]
            res_text = call_gemini_with_retry(contents, response_mime_type="application/json")
            
        return json.loads(res_text)
    except Exception as e:
        print(f"Extraction failed for {filename}: {e}")
        return {}

def render_step_4():
    st.header("Step 4: Extraction Engine (Docling + Gemini)")
    
    if st.button("Run Extraction"):
        with st.spinner("Extracting data... This may take a minute."):
            all_results = {}
            for file_info in st.session_state["accepted_files"]:
                st.write(f"Extracting from {file_info['filename']}...")
                res = extract_file_data(file_info, st.session_state["schema_config"])
                st.session_state["extraction_results"][file_info["filename"]] = res

    if st.session_state["extraction_results"]:
        st.subheader("Human-in-the-loop Extraction Review")
        
        # Merge results into a master payload
        master_data = {}
        master_lineage = {}
        
        for fname, res in st.session_state["extraction_results"].items():
            if not res: continue
            for k, v in res.items():
                if k not in ["extraction_confidence", "missing_fields", "source_documents", "data_lineage"]:
                    if v is not None:
                        master_data[k] = v
            if "data_lineage" in res:
                for k, v in res["data_lineage"].items():
                    master_lineage[k] = v
                    
        # Dynamically build editor fields
        st.write("Review the extracted fields.")
        cols = st.columns(3)
        col_idx = 0
        
        edited_final = {}
        for row in st.session_state["schema_config"]:
            key = row["Field Key"]
            label = row["Display Label"]
            val = master_data.get(key)
            lineage = master_lineage.get(key, "Not extracted")
            
            with cols[col_idx % 3]:
                st.markdown(f"**{label}**")
                if row["Unit"] in ["str", "text"]:
                    edited_final[key] = st.text_input(f"Value ({key})", value=str(val) if val is not None else "", key=f"edit_{key}")
                else:
                    edited_final[key] = st.number_input(f"Value ({key})", value=float(val) if val is not None else 0.0, key=f"edit_{key}")
                st.caption(f"Source: {lineage}")
                
            col_idx += 1
            
        if st.button("Approve Extraction"):
            st.session_state["final_extraction"] = edited_final
            st.session_state["final_lineage"] = master_lineage
            st.session_state["step"] = 5
            st.rerun()

def render_step_5():
    st.header("Step 5: Fraud Triangulation Engine & Output")
    
    st.subheader("Fraud Engine Results")
    with st.spinner("Running deep triangulation..."):
        # Run GSTR reconciliation check
        final_ext = st.session_state["final_extraction"].copy()
        
        gst_2a = final_ext.get("gst_2a_input_credit_cr")
        gst_3b = final_ext.get("gst_3b_output_tax_cr")
        if gst_2a and gst_3b and gst_3b > 0:
            var = abs(gst_2a - gst_3b) / gst_3b * 100
            st.session_state["gst_variance_pct"] = var
            final_ext["gst_2a_vs_3b_variance_pct"] = var
            st.metric("GSTR-2A vs 3B Variance", f"{var:.2f}%")
        
        flags = detect_revenue_anomalies(final_ext, st.session_state["entity_context"])
        
        if not flags:
            st.success("No fraud flags detected.", icon=":material/check_circle:")
        else:
            for flag in flags:
                if flag["severity"] == "CRITICAL":
                    st.error(f"**{flag['flag']}** - {flag['detail']}", icon=":material/dangerous:")
                elif flag["severity"] == "HIGH":
                    st.warning(f"**{flag['flag']}** - {flag['detail']}", icon=":material/warning:")
                elif flag["severity"] == "MEDIUM":
                    st.info(f"**{flag['flag']}** - {flag['detail']}", icon=":material/info:")
                    
        # Portfolio Health gauges (if applicable)
        npa = final_ext.get("npa_pct")
        par30 = final_ext.get("par_30_pct")
        par90 = final_ext.get("par_90_pct")
        
        if any([npa, par30, par90]):
            st.subheader("Portfolio Health")
            
            c1, c2, c3 = st.columns(3)
            # Example gauge displays
            if par30 is not None:
                fig_par30 = go.Figure(go.Indicator(
                    mode="gauge+number", value=par30, title={'text': "PAR 30"},
                    gauge={'axis': {'range': [None, 30]}, 'bar': {'color': "#1B3A6B"}}
                ))
                c1.plotly_chart(fig_par30, use_container_width=True)
                
            if par90 is not None:
                fig_par90 = go.Figure(go.Indicator(
                    mode="gauge+number", value=par90, title={'text': "PAR 90"},
                    gauge={'axis': {'range': [None, 30]}, 'bar': {'color': "orange"}}
                ))
                c2.plotly_chart(fig_par90, use_container_width=True)
                
            if npa is not None:
                fig_npa = go.Figure(go.Indicator(
                    mode="gauge+number", value=npa, title={'text': "Gross NPA"},
                    gauge={'axis': {'range': [None, 20]}, 'bar': {'color': "red"}}
                ))
                c3.plotly_chart(fig_npa, use_container_width=True)
                
                
    st.subheader("Output Contract")
    if st.button("Confirm & Proceed to Research"):
        payload = {
            "entity_context": st.session_state.get("entity_context", {}),
            "financials": final_ext,
            "fraud_flags": flags,
            "document_sources": [f["filename"] for f in st.session_state.get("accepted_files", [])],
            "extraction_timestamp": datetime.now().isoformat(),
            "schema_config": st.session_state.get("schema_config", []),
            "data_lineage": st.session_state.get("final_lineage", {}),
            "gst_variance_pct": st.session_state.get("gst_variance_pct")
        }
        st.session_state["extraction_payload"] = payload
        
        with open("data/extraction_payload.json", "w") as f:
            json.dump(payload, f, indent=4, default=str)
            
        st.success("Extraction complete! Payload saved to ./data/extraction_payload.json")
        st.switch_page("pages/02_research.py")


def main():
    if st.session_state["step"] == 1:
        render_step_1()
    elif st.session_state["step"] == 2:
        render_step_2()
    elif st.session_state["step"] == 3:
        render_step_3()
    elif st.session_state["step"] == 4:
        render_step_4()
    elif st.session_state["step"] == 5:
        render_step_5()


if __name__ == "__main__":
    main()
