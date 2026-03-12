from typing import List

def triangulate_research_vs_documents(web_context: dict, extraction: dict, fraud_flags: list, entity: dict) -> List[dict]:
    """
    Cross-reference web intelligence findings against extracted document data.
    Surface contradictions as high-priority triangulation flags.
    """
    triangulation_flags = []
    financials = extraction.get("financials", {})

    # Triangulation 1: Legal web signal vs clean documents
    legal_keywords = ["nclt", "insolvency", "court", "default", "recovery", "lawsuit", "fraud", "ed raid", "sebi notice", "rbi action"]
    legal_text = web_context.get("legal_context", "").lower()
    legal_hits = [kw for kw in legal_keywords if kw in legal_text]
    doc_legal_flags = [f for f in fraud_flags if "legal" in f.get("flag", "").lower()]
    
    if legal_hits and not doc_legal_flags:
        triangulation_flags.append({
            "flag": "LEGAL_SIGNAL_DOCUMENT_MISMATCH",
            "severity": "HIGH",
            "detail": f"Web sources mention legal keywords: {legal_hits} — but no legal flags found in uploaded documents. Request court clearance certificate from borrower.",
            "source": "TRIANGULATION",
            "five_c": "Character"
        })

    # Triangulation 2: Revenue web signal vs declared revenue
    revenue_cr = financials.get("revenue_cr", 0) or 0
    turnover_cr = entity.get("annual_turnover_cr", 0) or 0
    if float(revenue_cr) > 0 and float(turnover_cr) > 0:
        variance_pct = abs(float(revenue_cr) - float(turnover_cr)) / float(turnover_cr) * 100
        if variance_pct > 25:
            triangulation_flags.append({
                "flag": "DECLARED_VS_DOCUMENT_REVENUE_GAP",
                "severity": "HIGH",
                "detail": f"Onboarding turnover ₹{turnover_cr}Cr differs from document-extracted revenue ₹{revenue_cr}Cr by {variance_pct:.1f}%. Seek clarification.",
                "source": "TRIANGULATION",
                "five_c": "Capacity"
            })

    # Triangulation 3: GST web compliance vs GST document data
    gst_news = web_context.get("gst_context", "").lower()
    gst_keywords = ["gst notice", "fake itc", "gst evasion", "gstr mismatch", "fake invoice"]
    gst_web_hits = [kw for kw in gst_keywords if kw in gst_news]
    gst_variance = financials.get("gst_2a_vs_3b_variance_pct", 0) or 0
    
    if gst_web_hits and float(gst_variance) < 5:
        triangulation_flags.append({
            "flag": "GST_WEB_SIGNAL_VS_DOCUMENT_MISMATCH",
            "severity": "CRITICAL",
            "detail": f"Web sources flag GST issues ({gst_web_hits}) but GSTR-2A vs 3B variance shows only {float(gst_variance):.1f}% in documents. Independent GST verification required.",
            "source": "TRIANGULATION",
            "five_c": "Character"
        })

    # Triangulation 4: Promoter pledge web signal vs document
    pledge_news = web_context.get("promoter_context", "").lower()
    pledge_pct = financials.get("promoter_pledge_pct", 0) or 0
    if "pledge" in pledge_news and float(pledge_pct) < 30:
        triangulation_flags.append({
            "flag": "PROMOTER_PLEDGE_WEB_VS_DOCUMENT_GAP",
            "severity": "MEDIUM",
            "detail": f"News mentions promoter pledge activity but document shows only {pledge_pct}%. Verify latest pledge data from NSDL/CDSL.",
            "source": "TRIANGULATION",
            "five_c": "Character"
        })

    # Triangulation 5: MCA web signals vs onboarding data
    mca_text = web_context.get("mca_context", "").lower()
    mca_keywords = ["director disqualified", "struck off", "mca notice", "roc show cause", "annual return default"]
    mca_hits = [kw for kw in mca_keywords if kw in mca_text]
    if mca_hits:
        triangulation_flags.append({
            "flag": "MCA_COMPLIANCE_WEB_SIGNAL",
            "severity": "HIGH",
            "detail": f"MCA/ROC web search flagged: {mca_hits}. Verify on MCA21 portal before proceeding.",
            "source": "TRIANGULATION",
            "five_c": "Character"
        })

    return triangulation_flags
