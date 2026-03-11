"""
credit_engine.py  —  CertifAI Recommendation Engine (The Quant Layer)
=====================================================================
Implements deterministic financial mathematics to evaluate Probability of
Default (PD) and structure a loan offer, with no heavy ML dependencies.

Entry point
-----------
    run_credit_engine(financial_json_path, intelligence_json_path, output_json_path)

Expected input schemas
----------------------
financial_summary.json  (produced by the Ingestor):
{
    "revenue":              <float>,   # total revenue / turnover
    "ebit":                 <float>,   # earnings before interest & taxes
    "ebitda":               <float>,   # EBITDA
    "total_assets":         <float>,
    "total_liabilities":    <float>,
    "current_assets":       <float>,
    "current_liabilities":  <float>,
    "retained_earnings":    <float>,
    "market_cap":           <float>,   # use book equity if unlisted
    "operating_cash_flow":  <float>,
    "loan_amount_requested":<float>,
    "collateral_value":     <float>
}

external_intelligence.json  (produced by the Research Agent):
{
    "sector_risk_flag":     <bool>,    # true = elevated sector risk
    "adverse_news_score":   <float>,   # 0.0 (clean) – 1.0 (very risky)
    "management_risk_flag": <bool>
}

Output  →  risk_decision.json:
{
    "decision":         "APPROVE" | "MANUAL_REVIEW" | "REJECT",
    "PD":               <float>,   # Probability of Default  0–1
    "LGD":              <float>,   # Loss Given Default       0–1
    "expected_loss":    <float>,   # PD × LGD × loan_amount  (currency units)
    "max_loan_amount":  <float>,
    "interest_rate":    <float>    # annualised rate as decimal, e.g. 0.12 = 12 %
}
"""

import json
import math
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    """Load JSON from *path*, returning an empty dict on any error."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"[CreditEngine] Input file not found: {path}")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _safe_div(numerator: float, denominator: float, fallback: float = 0.0) -> float:
    """Division that never raises ZeroDivisionError."""
    if denominator == 0:
        return fallback
    return numerator / denominator


# ---------------------------------------------------------------------------
# 1. Altman Z-Score  →  Probability of Default (PD)
# ---------------------------------------------------------------------------

def calculate_altman_z_score(fin: dict) -> float:
    """
    Classic Altman Z-Score for private manufacturing firms (Z'-Score):

        Z' = 0.717·X1 + 0.847·X2 + 3.107·X3 + 0.420·X4 + 0.998·X5

    X1  = Working Capital / Total Assets
    X2  = Retained Earnings / Total Assets
    X3  = EBIT / Total Assets
    X4  = Book Value of Equity / Total Liabilities
    X5  = Revenue / Total Assets
    """
    total_assets      = fin.get("total_assets",         1.0)
    total_liabilities = fin.get("total_liabilities",    1.0)
    current_assets    = fin.get("current_assets",        0.0)
    current_liabilities = fin.get("current_liabilities", 0.0)
    retained_earnings = fin.get("retained_earnings",     0.0)
    ebit              = fin.get("ebit",                  0.0)
    revenue           = fin.get("revenue",               0.0)
    # Use market_cap as equity proxy; fall back to (assets - liabilities)
    equity            = fin.get("market_cap", max(total_assets - total_liabilities, 0.0))

    working_capital = current_assets - current_liabilities

    x1 = _safe_div(working_capital,   total_assets)
    x2 = _safe_div(retained_earnings, total_assets)
    x3 = _safe_div(ebit,              total_assets)
    x4 = _safe_div(equity,            total_liabilities)
    x5 = _safe_div(revenue,           total_assets)

    z_score = (0.717 * x1 +
               0.847 * x2 +
               3.107 * x3 +
               0.420 * x4 +
               0.998 * x5)

    return round(z_score, 4)


def z_score_to_pd(z: float) -> float:
    """
    Map Altman Z'-Score to a base Probability of Default.

    Zone          Z-Score      Base PD
    ─────────────────────────────────
    Distress      Z < 1.8      0.65
    Grey zone     1.8 – 3.0    linear interpolation  0.30 – 0.65
    Safe          Z > 3.0      0.10
    """
    if z < 1.8:
        return 0.65
    elif z > 3.0:
        return 0.10
    else:
        # Linearly interpolate: at 1.8 → 0.65, at 3.0 → 0.30
        slope = (0.30 - 0.65) / (3.0 - 1.8)
        pd = 0.65 + slope * (z - 1.8)
        return round(pd, 4)


def adjust_pd_with_intelligence(base_pd: float, intel: dict) -> float:
    """
    Apply qualitative adjustments from the Research Agent's intelligence JSON.

    Adjustments (additive to base PD, capped at 0.95):
      • Sector risk flag     → +0.05
      • Adverse news score   → scaled linearly up to +0.10
      • Management risk flag → +0.05
    """
    adjustment = 0.0

    if intel.get("sector_risk_flag", False):
        adjustment += 0.05

    adverse = float(intel.get("adverse_news_score", 0.0))
    adjustment += adverse * 0.10          # max +0.10 when score = 1.0

    if intel.get("management_risk_flag", False):
        adjustment += 0.05

    adjusted = base_pd + adjustment
    return round(min(adjusted, 0.95), 4)  # cap at 0.95


# ---------------------------------------------------------------------------
# 2. Loss Given Default (LGD)
# ---------------------------------------------------------------------------

def calculate_lgd(fin: dict) -> float:
    """
    LGD = 1 – min( (Collateral_Value × 0.7) / Loan_Amount,  1 )

    Represents the fraction of the loan exposure lost if the borrower defaults.
    """
    collateral_value  = fin.get("collateral_value",      0.0)
    loan_amount       = fin.get("loan_amount_requested", 1.0)

    recovery_rate = min(_safe_div(collateral_value * 0.70, loan_amount), 1.0)
    lgd = 1.0 - recovery_rate
    return round(lgd, 4)


# ---------------------------------------------------------------------------
# 3. Loan Structuring  →  Max Loan Amount
# ---------------------------------------------------------------------------

def calculate_max_loan(fin: dict) -> float:
    """
    Maximum loan is the *most restrictive* of three constraints:

      1. DSCR Method      : Operating_Cash_Flow / 1.2
      2. EBITDA Multiple  : Operating_Cash_Flow × 4
      3. Collateral Cap   : Collateral_Value    × 0.70

    Any negative or zero constraint is floored at 0 to stay economically
    meaningful.
    """
    ocf        = fin.get("operating_cash_flow", 0.0)
    ebitda     = fin.get("ebitda",              0.0)
    collateral = fin.get("collateral_value",    0.0)

    # Use EBITDA for the multiple if OCF is unavailable / non-positive
    cash_flow_proxy = ocf if ocf > 0 else ebitda

    dscr_limit         = max(_safe_div(cash_flow_proxy, 1.2), 0.0)
    ebitda_limit       = max(cash_flow_proxy * 4.0, 0.0)
    collateral_limit   = max(collateral * 0.70, 0.0)

    max_loan = min(dscr_limit, ebitda_limit, collateral_limit)
    return round(max_loan, 2)


# ---------------------------------------------------------------------------
# 4. Interest Rate Pricing
# ---------------------------------------------------------------------------

def calculate_interest_rate(pd: float) -> float:
    """
    Risk-based pricing model:

        Rate = Risk-Free Rate + (PD × Spread_Multiplier)

    Base rate  : 8.0 %  (reflective of current Indian repo + spread)
    Multiplier : scales PD (0→1) to add 0–15 % risk premium
    Result caps: floored at 8 %, capped at 24 %
    """
    base_rate   = 0.08
    risk_spread = pd * 0.15
    rate = base_rate + risk_spread
    rate = max(0.08, min(rate, 0.24))
    return round(rate, 4)


# ---------------------------------------------------------------------------
# 5. Decision Logic
# ---------------------------------------------------------------------------

def make_decision(pd: float) -> str:
    """
    Threshold-based credit decision:

      PD > 0.60          → REJECT
      0.30 ≤ PD ≤ 0.60  → MANUAL_REVIEW
      PD < 0.30          → APPROVE
    """
    if pd > 0.60:
        return "REJECT"
    elif pd >= 0.30:
        return "MANUAL_REVIEW"
    else:
        return "APPROVE"


# ---------------------------------------------------------------------------
# 6. Main entry point
# ---------------------------------------------------------------------------

def run_credit_engine(
    financial_json_path:    str,
    intelligence_json_path: str,
    output_json_path:       str,
) -> dict:
    """
    Orchestrates the full credit evaluation pipeline.

    Parameters
    ----------
    financial_json_path    : path to financial_summary.json
    intelligence_json_path : path to external_intelligence.json
    output_json_path       : path where risk_decision.json will be written

    Returns
    -------
    dict  – the same payload written to output_json_path
    """
    print(f"\n{'='*60}")
    print("  CertifAI Credit Engine  —  Evaluation Started")
    print(f"{'='*60}")

    # --- Load inputs -------------------------------------------------------
    fin   = _load_json(financial_json_path)
    intel = _load_json(intelligence_json_path)

    loan_amount = fin.get("loan_amount_requested", 0.0)

    # --- Step 1: Altman Z-Score & base PD ----------------------------------
    z_score  = calculate_altman_z_score(fin)
    base_pd  = z_score_to_pd(z_score)
    print(f"  Altman Z'-Score : {z_score}")
    print(f"  Base PD         : {base_pd:.2%}")

    # --- Step 2: Qualitative adjustment ------------------------------------
    pd = adjust_pd_with_intelligence(base_pd, intel)
    print(f"  Adjusted PD     : {pd:.2%}  (after intelligence overlay)")

    # --- Step 3: LGD -------------------------------------------------------
    lgd = calculate_lgd(fin)
    print(f"  LGD             : {lgd:.2%}")

    # --- Step 4: Expected Loss ---------------------------------------------
    expected_loss = round(pd * lgd * loan_amount, 2)
    print(f"  Expected Loss   : {expected_loss:,.2f}  (on requested {loan_amount:,.2f})")

    # --- Step 5: Max Loan Amount -------------------------------------------
    max_loan = calculate_max_loan(fin)
    print(f"  Max Loan Amount : {max_loan:,.2f}")

    # --- Step 6: Interest Rate ---------------------------------------------
    interest_rate = calculate_interest_rate(pd)
    print(f"  Interest Rate   : {interest_rate:.2%}")

    # --- Step 7: Decision --------------------------------------------------
    decision = make_decision(pd)
    print(f"\n  ► DECISION      : {decision}")
    print(f"{'='*60}\n")

    # --- Build output payload ----------------------------------------------
    result = {
        "decision":         decision,
        "PD":               pd,
        "LGD":              lgd,
        "expected_loss":    expected_loss,
        "max_loan_amount":  max_loan,
        "interest_rate":    interest_rate,
        # --- Audit trail fields ---
        "altman_z_score":   z_score,
        "base_pd_before_intel_adjustment": base_pd,
        "loan_amount_requested": loan_amount,
        "evaluated_at":     datetime.now(timezone.utc).isoformat(),
    }

    # --- Write output -------------------------------------------------------
    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)

    print(f"[CreditEngine] Output written → {output_json_path}")
    return result


# ---------------------------------------------------------------------------
# CLI convenience runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    financial_path    = os.path.join(BASE, "shared_data", "financial_summary.json")
    intelligence_path = os.path.join(BASE, "shared_data", "external_intelligence.json")
    output_path       = os.path.join(BASE, "shared_data", "risk_decision.json")

    # Allow CLI overrides: python credit_engine.py <fin> <intel> <out>
    if len(sys.argv) == 4:
        financial_path, intelligence_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]

    output = run_credit_engine(financial_path, intelligence_path, output_path)
    print(json.dumps(output, indent=2))
