import json
from typing import List, Literal, Optional
from pydantic import BaseModel
from utils.gemini_client import call_gemini_with_retry

class RiskSignal(BaseModel):
    signal: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    source: Literal["NEWS", "LEGAL", "SECTOR", "PROMOTER", "PRIMARY", "FINANCIAL", "MCA", "GST", "TRIANGULATION"]
    detail: str
    five_c_mapping: Literal["Character", "Capacity", "Capital", "Collateral", "Conditions"]

class ResearchOutput(BaseModel):
    news_risk_score: float
    legal_risk_score: float
    sector_risk_score: float
    operational_risk_score: float
    promoter_risk_score: float
    mca_risk_score: float
    gst_compliance_score: float

    news_summary: str
    legal_summary: str
    sector_summary: str
    promoter_summary: str
    operational_summary: str
    mca_summary: str
    gst_compliance_summary: str

    early_warning_signals: List[RiskSignal]
    triangulation_flags: List[dict]

    india_specific_flags: List[str]

    composite_external_risk_score: float
    research_confidence: float

def generate_research_report(
    company_name: str,
    sector: str,
    cin: str,
    web_context: dict,
    primary_insights: dict,
    extraction: dict,
    fraud_flags: list,
    triangulation_flags: list
) -> ResearchOutput:
    
    financials = extraction.get("financials", {})
    entity_context = extraction.get("entity_context", {})
    
    schema_json = json.dumps(ResearchOutput.model_json_schema())

    system_prompt = f"""
    You are a Senior Credit Intelligence Analyst at a leading Indian bank. Analyze the provided web intelligence,
    primary field notes, and financial fraud flags for {company_name} in the {sector} sector.

    Evaluate across 7 dimensions:
    1. NEWS RISK: Negative press, management changes, fraud allegations, regulatory actions
    2. LEGAL RISK: NCLT filings, court cases, recovery suits, director disqualifications, e-Courts records
    3. SECTOR RISK: Industry headwinds, RBI/SEBI regulations, demand slowdown, commodity risks
    4. PROMOTER RISK: Background issues, pledge ratios, related-party concerns, MCA flags
    5. OPERATIONAL RISK: Factory capacity, management quality, RM observations, account conduct
    6. MCA COMPLIANCE RISK: ROC filing gaps, director disqualification, annual return defaults
    7. GST COMPLIANCE RISK: GSTR-2A vs 3B discrepancy, fake ITC, GST notices, filing regularity

    INDIA-SPECIFIC MANDATORY CHECKS — you MUST address each:
    - GSTR-2A vs 3B: Is there a discrepancy? What does it signal?
    - CIBIL Commercial: What does the score indicate?
    - MCA Filing: Is the company current on ROC filings?
    - e-Courts: Are there active litigation records?
    - RBI Circular Compliance: Any regulatory action pending?

    TRIANGULATION: The input includes triangulation_flags showing contradictions between web data and documents. 
    Incorporate these as CRITICAL early warning signals.

    Be specific. Cite the source snippet when flagging risk.
    Return valid JSON matching the exact Pydantic schema provided below:
    
    {schema_json}

    Ensure all float scores are between 0 and 10, and research_confidence is between 0 and 1.
    """

    user_content = f"""
    COMPANY: {company_name}
    SECTOR: {sector}
    CIN: {cin}

    WEB INTELLIGENCE:
    News: {web_context.get('news_context', '')}
    Legal: {web_context.get('legal_context', '')}
    Sector: {web_context.get('sector_context', '')}
    Promoter: {web_context.get('promoter_context', '')}
    MCA/ROC: {web_context.get('mca_context', '')}
    GST Compliance: {web_context.get('gst_context', '')}

    PRIMARY FIELD NOTES:
    Factory Capacity: {primary_insights.get('factory_capacity_pct', 80)}%
    Management Quality: {primary_insights.get('management_quality', 'Average')}
    Site Visit: {primary_insights.get('site_visit_notes', '')}
    Interview Notes: {primary_insights.get('management_interview_notes', '')}
    RM Rating: {primary_insights.get('rm_rating', 'Neutral')}
    Account Conduct: {primary_insights.get('account_conduct', 'N/A')}
    CIBIL Commercial Verified: {primary_insights.get('cibil_commercial_verified', 'Not Yet')}
    e-Courts Cases Found: {primary_insights.get('ecourt_cases_found', 0)}
    RBI Circular Compliance: {primary_insights.get('rbi_compliance', 'Not Applicable')}

    INDIA-SPECIFIC DATA FROM DOCUMENTS:
    GSTR-2A vs 3B Variance: {extraction.get('gst_variance_pct', 0)}%
    CIBIL Commercial Score: {entity_context.get('cibil_commercial_score', 'N/A')}
    MCA Last Filing: {entity_context.get('mca_last_filing_date', 'N/A')}

    EXISTING FRAUD FLAGS FROM DOCUMENT ANALYSIS:
    {json.dumps(fraud_flags, indent=2)}

    TRIANGULATION FLAGS (contradictions between web & docs):
    {json.dumps(triangulation_flags, indent=2)}
    """
    
    try:
        response_text = call_gemini_with_retry(
            contents=[
                {"role": "user", "parts": [system_prompt]},
                {"role": "user", "parts": [user_content]}
            ],
            response_mime_type="application/json"
        )
        
        report_data = json.loads(response_text)
        report_data["triangulation_flags"] = triangulation_flags
        return ResearchOutput(**report_data)
    except Exception as e:
        print(f"Error calling Gemini or parsing response: {e}")
        # Bubble up the error instead of returning mock data
        raise e
