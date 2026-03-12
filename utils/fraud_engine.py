from typing import List

def check_mca_filing_gap(entity: dict) -> dict | None:
    mca_date = entity.get("mca_last_filing_date")
    if not mca_date:
        return None
        
    from datetime import date
    try:
        # Check if it's already a date object or string
        if isinstance(mca_date, date):
            gap_days = (date.today() - mca_date).days
        else:
            # Assuming YYYY-MM-DD
            from datetime import datetime
            mca_date_obj = datetime.strptime(str(mca_date), "%Y-%m-%d").date()
            gap_days = (date.today() - mca_date_obj).days
            
        if gap_days > 365:
            return {
                "flag": "MCA_FILING_GAP_CRITICAL",
                "severity": "HIGH",
                "detail": f"Last MCA filing was {gap_days} days ago. Companies Act mandates annual filing. Possible compliance breach.",
                "five_c": "Character"
            }
        elif gap_days > 180:
            return {
                "flag": "MCA_FILING_DELAYED",
                "severity": "MEDIUM",
                "detail": f"MCA filing is {gap_days} days old — approaching annual deadline.",
                "five_c": "Character"
            }
    except Exception as e:
        return None
        
    return None

def detect_revenue_anomalies(extraction_dict: dict, entity: dict) -> List[dict]:
    flags = []

    declared = extraction_dict.get("revenue_cr") or 0
    gst_sales = extraction_dict.get("gst_declared_sales_cr") or 0
    
    avg_bank_inflow = extraction_dict.get("avg_monthly_bank_inflow_cr")
    bank_inflow = (avg_bank_inflow * 12) if avg_bank_inflow else 0
    
    cashflow = extraction_dict.get("operating_cashflow_cr") or 0
    pledge = extraction_dict.get("promoter_pledge_pct") or 0

    # Flag 1: Revenue Inflation Risk
    if bank_inflow > 0 and bank_inflow < (0.5 * declared):
        flags.append({
            "flag": "HIGH_REVENUE_INFLATION_RISK",
            "severity": "CRITICAL",
            "detail": f"Bank inflows ₹{bank_inflow:.1f}Cr are less than 50% of declared revenue ₹{declared:.1f}Cr",
            "five_c": "Character"
        })

    # Flag 2: Circular Trading Risk
    if gst_sales > 0 and gst_sales > (1.3 * declared):
        flags.append({
            "flag": "CIRCULAR_TRADING_RISK",
            "severity": "HIGH",
            "detail": f"GST sales ₹{gst_sales:.1f}Cr exceed declared P&L revenue by >30%",
            "five_c": "Character"
        })

    # Flag 3: Earnings Quality Risk
    if declared > 0 and cashflow < (0.1 * declared):
        flags.append({
            "flag": "EARNINGS_QUALITY_RISK",
            "severity": "HIGH",
            "detail": "Operating cashflow <10% of revenue. Possible revenue inflation or working capital stress.",
            "five_c": "Capacity"
        })

    # Flag 4: Promoter Pledge Risk
    if pledge > 50:
        flags.append({
            "flag": "PROMOTER_PLEDGE_RISK",
            "severity": "MEDIUM",
            "detail": f"Promoter pledge at {pledge}% — above 50% threshold",
            "five_c": "Character"
        })

    # Flag 5: GSTR-2A vs 3B Mismatch
    gst_variance = extraction_dict.get("gst_2a_vs_3b_variance_pct") or 0
    onboarding_flag = entity.get("gstr_2a_3b_mismatch_flag", "Not Checked")
    if gst_variance > 15 or onboarding_flag == "Severe (>15%)":
        flags.append({
            "flag": "GSTR_2A_3B_SEVERE_MISMATCH",
            "severity": "CRITICAL",
            "detail": f"GSTR-2A input credit vs 3B output tax variance is {gst_variance:.1f}%. Possible ITC fraud or suppression of sales.",
            "five_c": "Character"
        })
    elif gst_variance > 5 or onboarding_flag == "Moderate (5–15%)":
        flags.append({
            "flag": "GSTR_2A_3B_MODERATE_MISMATCH",
            "severity": "HIGH",
            "detail": f"GSTR-2A vs 3B variance at {gst_variance:.1f}%. Seek reconciliation statement from borrower.",
            "five_c": "Character"
        })

    # Flag 6: CIBIL Commercial Score Risk
    cibil = entity.get("cibil_commercial_score")
    if cibil is not None:
        if cibil <= 3:
            flags.append({
                "flag": "CIBIL_COMMERCIAL_HIGH_RISK",
                "severity": "CRITICAL",
                "detail": f"CIBIL Commercial Score is {cibil}/10 (rank 1–3 = high default probability). Cross-reference with bureau report.",
                "five_c": "Character"
            })
        elif cibil <= 5:
            flags.append({
                "flag": "CIBIL_COMMERCIAL_MODERATE_RISK",
                "severity": "MEDIUM",
                "detail": f"CIBIL Commercial Score is {cibil}/10. Review payment track record.",
                "five_c": "Character"
            })

    # Flag 7: MCA Filing Gap
    mca_flag = check_mca_filing_gap(entity)
    if mca_flag:
        flags.append(mca_flag)

    # Flag 8: Portfolio NPA Stress
    npa = extraction_dict.get("npa_pct") or 0
    par90 = extraction_dict.get("par_90_pct") or 0
    
    if npa > 10 or par90 > 8:
        flags.append({
            "flag": "PORTFOLIO_NPA_STRESS",
            "severity": "HIGH",
            "detail": f"Gross NPA at {npa:.1f}%, PAR-90 at {par90:.1f}%. Asset quality under severe stress.",
            "five_c": "Capacity"
        })

    return flags
