import streamlit as st
import pandas as pd

DEFAULT_SCHEMA = [
    # Annual Report / P&L fields
    {"Enabled": True, "Field Key": "revenue_cr", "Display Label": "Revenue", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "ebitda_cr", "Display Label": "EBITDA", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "pat_cr", "Display Label": "PAT", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "total_debt_cr", "Display Label": "Total Debt", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "total_assets_cr", "Display Label": "Total Assets", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "net_worth_cr", "Display Label": "Net Worth", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    {"Enabled": True, "Field Key": "operating_cashflow_cr", "Display Label": "Operating Cashflow", "Category": "Financial", "Unit": "₹ Cr", "Required": True},
    
    # ALM fields
    {"Enabled": True, "Field Key": "liquidity_gap_cr", "Display Label": "Liquidity Gap", "Category": "ALM", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "total_outflows_cr", "Display Label": "Total Outflows", "Category": "ALM", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "short_term_liabilities_cr", "Display Label": "Short Term Liabilities", "Category": "ALM", "Unit": "₹ Cr", "Required": False},
    
    # Borrowing Profile fields
    {"Enabled": True, "Field Key": "secured_debt_cr", "Display Label": "Secured Debt", "Category": "Borrowing", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "unsecured_debt_cr", "Display Label": "Unsecured Debt", "Category": "Borrowing", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "debt_to_equity_ratio", "Display Label": "Debt to Equity Ratio", "Category": "Borrowing", "Unit": "ratio", "Required": True},
    {"Enabled": True, "Field Key": "average_interest_rate", "Display Label": "Average Interest Rate", "Category": "Borrowing", "Unit": "%", "Required": False},
    
    # Shareholding Pattern fields
    {"Enabled": True, "Field Key": "promoter_holding_pct", "Display Label": "Promoter Holding", "Category": "Shareholding", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "promoter_pledge_pct", "Display Label": "Promoter Pledge", "Category": "Shareholding", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "institutional_holding_pct", "Display Label": "Institutional Holding", "Category": "Shareholding", "Unit": "%", "Required": False},
    
    # Portfolio Performance fields
    {"Enabled": True, "Field Key": "npa_pct", "Display Label": "NPA %", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "portfolio_yield_pct", "Display Label": "Portfolio Yield", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "par_30_pct", "Display Label": "PAR >30 Days", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "par_90_pct", "Display Label": "PAR >90 Days", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "collection_efficiency_pct", "Display Label": "Collection Efficiency", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "gross_npa_cr", "Display Label": "Gross NPA", "Category": "Portfolio", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "net_npa_cr", "Display Label": "Net NPA", "Category": "Portfolio", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "provision_coverage_ratio_pct", "Display Label": "Provision Coverage Ratio", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "vintage_30dpd_pct", "Display Label": "30 DPD Vintage", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "vintage_90dpd_pct", "Display Label": "90 DPD Vintage", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "credit_cost_pct", "Display Label": "Credit Cost", "Category": "Portfolio", "Unit": "%", "Required": False},
    {"Enabled": True, "Field Key": "disbursement_cr", "Display Label": "Disbursement", "Category": "Portfolio", "Unit": "₹ Cr", "Required": False},
    
    # Bank Statement fields
    {"Enabled": True, "Field Key": "avg_monthly_bank_inflow_cr", "Display Label": "Avg Monthly Inflow", "Category": "BankStatement", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "avg_monthly_bank_outflow_cr", "Display Label": "Avg Monthly Outflow", "Category": "BankStatement", "Unit": "₹ Cr", "Required": False},
    
    # GST fields
    {"Enabled": True, "Field Key": "gst_declared_sales_cr", "Display Label": "GST Declared Sales", "Category": "GST", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "gst_2a_input_credit_cr", "Display Label": "GSTR-2A Input Credit", "Category": "GST", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "gst_3b_output_tax_cr", "Display Label": "GSTR-3B Output Tax", "Category": "GST", "Unit": "₹ Cr", "Required": False},
    {"Enabled": True, "Field Key": "gst_filing_regularity", "Display Label": "GST Filing Regularity", "Category": "GST", "Unit": "str", "Required": False},
]

def render_schema_editor():
    st.subheader("Configure Extraction Schema")
    st.markdown("Toggle, rename, or add fields before extraction runs. Changes apply to this session only.")
    
    if "current_schema" not in st.session_state:
        st.session_state["current_schema"] = pd.DataFrame(DEFAULT_SCHEMA)
    
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("➕ Add Custom Field"):
            new_row = pd.DataFrame([{
                "Enabled": True, 
                "Field Key": "new_custom_field", 
                "Display Label": "New Field", 
                "Category": "Financial", 
                "Unit": "text", 
                "Required": False
            }])
            st.session_state["current_schema"] = pd.concat([st.session_state["current_schema"], new_row], ignore_index=True)
            st.rerun()
            
    with col2:
        if st.button("🔄 Reset to Defaults"):
            st.session_state["current_schema"] = pd.DataFrame(DEFAULT_SCHEMA)
            st.rerun()

    edited_df = st.data_editor(
        st.session_state["current_schema"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=["Financial", "ALM", "Borrowing", "Shareholding", "Portfolio", "BankStatement", "GST"],
                required=True
            )
        }
    )
    
    # Store the latest edits back to session state so they aren't lost on rerun
    st.session_state["current_schema"] = edited_df

    return edited_df
