"""
credit_engine.py — Deterministic quantitative credit risk engine for Intelli-Credit Module 3.
All calculations are pure Python with no LLM dependencies.
"""

from __future__ import annotations
import math
import yaml
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# Load credit policy once at import time
# ─────────────────────────────────────────────────────────────────────────────
_POLICY_PATH = Path(__file__).resolve().parent.parent / "credit_policy.yaml"
try:
    with open(_POLICY_PATH) as _f:
        _POLICY = yaml.safe_load(_f)
except FileNotFoundError:
    _POLICY = {}

_LTV_THRESHOLDS: dict = _POLICY.get("LTV_THRESHOLDS", {
    "Real Estate": 70,
    "Plant & Machinery": 50,
    "FD": 90,
    "Stocks": 40,
})


def _safe_div(num: float, den: float, fallback: float = 0.0) -> float:
    """Division with zero / None guard."""
    if not den or den == 0 or not num:
        return fallback
    return float(num) / float(den)


class CreditEngine:
    """
    Pure-math credit risk engine.
    All methods accept raw dicts extracted from session payloads.
    """

    # ── Collateral haircuts ──────────────────────────────────────────────────
    COLLATERAL_HAIRCUTS: dict[str, float] = {
        "Real Estate":       0.30,
        "Plant & Machinery": 0.45,
        "FD":                0.05,
        "Stocks":            0.50,
        "None":              1.00,
    }

    # ── Sector volatility (used in interest-rate premium) ───────────────────
    SECTOR_VOLATILITY: dict[str, float] = {
        "Steel":          0.18,
        "Real Estate":    0.22,
        "NBFC":           0.20,
        "Manufacturing":  0.15,
        "Infrastructure": 0.17,
        "Pharma":         0.12,
        "Other":          0.16,
    }

    # ────────────────────────────────────────────────────────────────────────
    # 1. ALTMAN Z-SCORE
    # ────────────────────────────────────────────────────────────────────────
    def calculate_altman_z_score(self, f: dict) -> tuple[float, str]:
        """
        Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5
        Returns (z_score, band) where band is 'Safe', 'Grey', or 'Distress'.
        """
        total_assets = float(f.get("total_assets_cr") or 0)
        revenue      = float(f.get("revenue_cr")      or 0)
        ebitda       = float(f.get("ebitda_cr")        or 0)
        pat          = float(f.get("pat_cr")           or 0)
        net_worth    = float(f.get("net_worth_cr")     or 0)
        total_debt   = float(f.get("total_debt_cr")    or 0)

        # Working capital proxy: net_worth - long-term debt (simplified)
        working_capital = net_worth - (total_debt * 0.5)

        x1 = _safe_div(working_capital, total_assets)   # WC / TA
        x2 = _safe_div(pat, total_assets)                # Retained Earnings ≈ PAT
        x3 = _safe_div(ebitda, total_assets)             # EBIT ≈ EBITDA / TA
        x4 = _safe_div(net_worth, max(total_debt, 0.01)) # Equity / Debt
        x5 = _safe_div(revenue, total_assets)            # Revenue / TA

        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5

        if z > 2.99:
            band = "Safe"
        elif z >= 1.81:
            band = "Grey"
        else:
            band = "Distress"

        return round(z, 3), band

    # ────────────────────────────────────────────────────────────────────────
    # 2. PROBABILITY OF DEFAULT
    # ────────────────────────────────────────────────────────────────────────
    def calculate_pd(
        self,
        f: dict,
        external_risk: float,
        z_score: float,
        research_payload: dict | None = None,
        entity: dict | None = None,
    ) -> float:
        """Rule-based PD in [0.0, 0.95]."""
        research_payload = research_payload or {}
        entity = entity or {}

        # ── Base PD from Z-score band ────────────────────────────────────
        if z_score > 2.99:
            pd = 0.05
        elif z_score >= 1.81:
            pd = 0.20
        else:
            pd = 0.45

        # ── D/E adjustment ───────────────────────────────────────────────
        net_worth  = float(f.get("net_worth_cr")  or 1)
        total_debt = float(f.get("total_debt_cr") or 0)
        de = _safe_div(total_debt, max(net_worth, 0.01))
        if de > 5:
            pd += 0.15
        elif de > 3:
            pd += 0.10

        # ── External risk (0-10 → +0 to +0.20) ──────────────────────────
        pd += (_safe_div(float(external_risk or 0), 10)) * 0.20

        # ── DSCR adjustment ──────────────────────────────────────────────
        ocf = float(f.get("operating_cashflow_cr") or 0)
        dscr = _safe_div(ocf, max(total_debt * 0.12, 0.01))
        if dscr < 1.0:
            pd += 0.15
        elif dscr < 1.25:
            pd += 0.08

        # ── India-specific signals ───────────────────────────────────────
        cibil = f.get("cibil_commercial_score")
        if cibil is not None:
            try:
                cibil = float(cibil)
                if cibil <= 3:
                    pd += 0.15
                elif cibil <= 5:
                    pd += 0.08
            except (ValueError, TypeError):
                pass

        gst_var = float(f.get("gst_2a_vs_3b_variance_pct") or 0)
        if gst_var > 15:
            pd += 0.10
        elif gst_var > 5:
            pd += 0.05

        # ── e-Courts cases ───────────────────────────────────────────────
        primary = research_payload.get("primary_insights", {}) or {}
        ecourt = int(primary.get("ecourt_cases_found") or 0)
        if ecourt > 5:
            pd += 0.10
        elif ecourt > 0:
            pd += 0.05

        # ── Triangulation flags ──────────────────────────────────────────
        tri_flags = research_payload.get("triangulation_flags", []) or []
        critical_tri = sum(
            1 for t in tri_flags if (t or {}).get("severity") == "CRITICAL"
        )
        pd += critical_tri * 0.08

        # ── POSITIVE INDICATOR BONUSES (reduce PD) ───────────────────────

        # CIBIL bonus — strong score is a direct predictor of repayment
        cibil = f.get("cibil_commercial_score") or entity.get("cibil_commercial_score") if hasattr(f, 'get') else None
        if cibil:
            try:
                cibil_val = float(cibil)
                if cibil_val >= 8:   pd -= 0.10   # excellent credit history
                elif cibil_val >= 7: pd -= 0.06   # good credit history
                elif cibil_val >= 6: pd -= 0.03   # above average
            except (ValueError, TypeError):
                pass

        # Zero / low GST variance bonus — clean compliance
        gst_var = float(f.get("gst_2a_vs_3b_variance_pct") or 0)
        if gst_var == 0 or gst_var < 2:
            pd -= 0.05    # clean GST record is strong character signal

        # Strong DSCR bonus
        cf = float(f.get("operating_cashflow_cr") or 0)
        td = float(f.get("total_debt_cr") or 1)
        dscr = _safe_div(cf, max(td * 0.12, 0.01))
        if dscr > 2.0:   pd -= 0.06
        elif dscr > 1.5: pd -= 0.03

        # Revenue growth signal (if 3-year data available)
        rev_growth = float(f.get("revenue_cagr_3yr_pct") or 0)
        if rev_growth > 15: pd -= 0.04
        elif rev_growth > 8: pd -= 0.02

        # Floor — PD cannot go below 3% for any live company
        pd = max(0.03, round(pd, 4))

        return round(min(pd, 0.95), 4)

    # ────────────────────────────────────────────────────────────────────────
    # 2.5 Z-BAND NARRATIVE
    # ────────────────────────────────────────────────────────────────────────
    def z_band(self, z: float) -> tuple[str, str]:
        """Returns (band_label, narrative_description)"""
        if z > 2.99:
            return "Safe Zone", f"Z-Score {z:.2f} — above 2.99 safe threshold. Low financial distress risk."
        elif z > 2.60:
            return "Upper Grey Zone", f"Z-Score {z:.2f} — approaching safe zone. One strong financial year would push to safe territory."
        elif z > 2.20:
            return "Mid Grey Zone", f"Z-Score {z:.2f} — moderate distress risk. Monitor leverage and cashflow closely."
        elif z > 1.81:
            return "Lower Grey Zone", f"Z-Score {z:.2f} — near grey/distress boundary. Revenue growth trajectory is the key watchpoint."
        else:
            return "Distress Zone", f"Z-Score {z:.2f} — below 1.81 distress threshold. High default probability indicated."

    # ────────────────────────────────────────────────────────────────────────
    # 3. LOSS GIVEN DEFAULT
    # ────────────────────────────────────────────────────────────────────────
    def calculate_lgd(
        self,
        collateral_type: str,
        collateral_value: float,
        loan_amount: float,
    ) -> float:
        """Returns LGD in [0.05, 0.90]."""
        collateral_value = float(collateral_value or 0)
        loan_amount      = float(loan_amount or 1)

        haircut = self.COLLATERAL_HAIRCUTS.get(collateral_type, 1.0)
        effective_collateral = collateral_value * (1 - haircut)
        coverage_ratio = _safe_div(effective_collateral, loan_amount)
        lgd = max(0.05, 1 - coverage_ratio)
        return round(min(lgd, 0.90), 4)

    # ────────────────────────────────────────────────────────────────────────
    # 4. MAXIMUM LOAN SIZING
    # ────────────────────────────────────────────────────────────────────────
    def calculate_max_loan(self, f: dict, entity: dict) -> dict:
        """
        Returns dict with DSCR-based, EBITDA-multiple, LTV limits, and final max.
        Reads sector_ltv from credit_policy.yaml.
        """
        ocf             = float(f.get("operating_cashflow_cr") or 0)
        ebitda          = float(f.get("ebitda_cr")             or 0)
        collateral_type = entity.get("collateral_type", "None")
        collateral_val  = float(entity.get("collateral_value") or
                                entity.get("collateral_value_cr") or 0)

        # Method 1: DSCR-based (min DSCR 1.25, 12% annual rate)
        dscr_limit = _safe_div(ocf, 1.25) / 0.12 if ocf > 0 else 0

        # Method 2: EBITDA × 3.5
        ebitda_limit = ebitda * 3.5

        # Method 3: LTV from policy
        haircut = self.COLLATERAL_HAIRCUTS.get(collateral_type, 1.0)
        ltv_pct = _LTV_THRESHOLDS.get(collateral_type, 50)
        ltv_limit = collateral_val * (1 - haircut) * (ltv_pct / 100)

        candidates = [x for x in [dscr_limit, ebitda_limit, ltv_limit] if x > 0]
        max_loan = min(candidates) if candidates else 0

        return {
            "dscr_limit":    round(dscr_limit,    2),
            "ebitda_limit":  round(ebitda_limit,  2),
            "ltv_limit":     round(ltv_limit,      2),
            "max_loan":      round(max_loan,        2),
        }

    # ────────────────────────────────────────────────────────────────────────
    # 5. INTEREST RATE
    # ────────────────────────────────────────────────────────────────────────
    def calculate_interest_rate(
        self,
        pd: float,
        lgd: float,
        sector: str,
    ) -> float:
        """Returns annual interest rate %, capped [8.5, 22.0]."""
        base_rate     = 9.5                                # MCLR proxy
        risk_premium  = pd * 8.0
        el_premium    = pd * lgd * 1.5
        sector_vol    = self.SECTOR_VOLATILITY.get(sector, 0.16) * 10
        rate = base_rate + risk_premium + el_premium + sector_vol
        return round(min(max(rate, 8.5), 22.0), 2)

    # ────────────────────────────────────────────────────────────────────────
    # 6. EDGE CASE EVALUATION
    # ────────────────────────────────────────────────────────────────────────
    def evaluate_edge_cases(
        self,
        f: dict,
        flags: list,
        research_payload: dict | None = None,
    ) -> dict:
        """
        Returns confidence score (0-1) and decision modifier.
        Decision modifier: None | 'MANUAL_REVIEW' | 'REJECT'
        """
        research_payload = research_payload or {}
        confidence = 0.85

        flags = flags or []

        # ── Fraud flag deductions ────────────────────────────────────────
        for flag in flags:
            sev = (flag or {}).get("severity", "")
            if sev == "CRITICAL":
                confidence -= 0.30
            elif sev == "HIGH":
                confidence -= 0.15

        # ── Missing-data deductions ──────────────────────────────────────
        if not f.get("ebitda_cr"):
            confidence -= 0.10
        if not f.get("operating_cashflow_cr"):
            confidence -= 0.10

        # ── Revenue–cashflow mismatch ────────────────────────────────────
        revenue = float(f.get("revenue_cr") or 0)
        ocf     = float(f.get("operating_cashflow_cr") or 0)
        if revenue > 0 and ocf < 0.1 * revenue:
            confidence -= 0.20

        # ── Factory capacity ─────────────────────────────────────────────
        primary = research_payload.get("primary_insights", {}) or {}
        cap_pct = primary.get("factory_capacity_pct")
        if cap_pct is not None:
            try:
                if float(cap_pct) < 50:
                    confidence -= 0.10
            except (ValueError, TypeError):
                pass

        # ── Triangulation flag deductions (NEW) ──────────────────────────
        tri_flags = research_payload.get("triangulation_flags", []) or []
        for tf in tri_flags:
            sev = (tf or {}).get("severity", "")
            if sev == "CRITICAL":
                confidence -= 0.20

        # ── GST 2A/3B variance ───────────────────────────────────────────
        gst_var = float(f.get("gst_2a_vs_3b_variance_pct") or 0)
        if gst_var > 15:
            confidence -= 0.15

        # ── CIBIL Commercial Score ───────────────────────────────────────
        cibil = f.get("cibil_commercial_score")
        if cibil is not None:
            try:
                if float(cibil) <= 3:
                    confidence -= 0.15
            except (ValueError, TypeError):
                pass

        # ── e-Courts cases ───────────────────────────────────────────────
        ecourt = int(primary.get("ecourt_cases_found") or 0)
        if ecourt > 5:
            confidence -= 0.10

        # ── MCA filing gap ───────────────────────────────────────────────
        from datetime import date, datetime
        mca_date_raw = (research_payload.get("primary_insights") or {}).get("mca_last_filing_date")
        if not mca_date_raw:
            # Try extraction payload (passed via flags context indirectly; skip silently)
            pass
        if mca_date_raw:
            try:
                if isinstance(mca_date_raw, str):
                    mca_dt = datetime.strptime(mca_date_raw, "%Y-%m-%d").date()
                else:
                    mca_dt = mca_date_raw
                gap = (date.today() - mca_dt).days
                if gap > 365:
                    confidence -= 0.10
            except Exception:
                pass

        # ── Floor at zero ────────────────────────────────────────────────
        confidence = round(max(confidence, 0.0), 4)

        # ── Derive decision modifier ─────────────────────────────────────
        if confidence < 0.30:
            modifier = "REJECT"
        elif confidence < 0.50:
            modifier = "MANUAL_REVIEW"
        else:
            modifier = None

        return {"confidence": confidence, "decision_modifier": modifier}

    # ────────────────────────────────────────────────────────────────────────
    # 7. ORCHESTRATOR
    # ────────────────────────────────────────────────────────────────────────
    def run_credit_evaluation(
        self,
        extraction_payload: dict,
        research_payload: dict,
    ) -> dict:
        """
        Full pipeline. Returns a comprehensive evaluation dict ready for display.
        """
        f      = extraction_payload.get("financials", {}) or {}
        entity = extraction_payload.get("entity_context", {}) or {}
        flags  = extraction_payload.get("fraud_flags", []) or []

        research_output = research_payload.get("research_output", {}) or {}
        ext_risk = float(research_output.get("composite_external_risk_score") or 5)

        # ── Core calculations ────────────────────────────────────────────
        z_score, _ = self.calculate_altman_z_score(f)
        z_band_label, z_band_narrative = self.z_band(z_score)

        pd = self.calculate_pd(
            f=f,
            external_risk=ext_risk,
            z_score=z_score,
            research_payload=research_payload,
            entity=entity,
        )

        collateral_type  = entity.get("collateral_type", "None")
        collateral_value = float(entity.get("collateral_value") or
                                 entity.get("collateral_value_cr") or 0)
        loan_amount      = float(entity.get("loan_amount") or
                                 entity.get("loan_amount_cr") or 1)

        lgd = self.calculate_lgd(collateral_type, collateral_value, loan_amount)

        max_loan_info = self.calculate_max_loan(f, entity)
        max_loan = max_loan_info["max_loan"]

        sector = entity.get("sector", "Other")
        rate   = self.calculate_interest_rate(pd, lgd, sector)

        edge = self.evaluate_edge_cases(
            f=f,
            flags=flags,
            research_payload=research_payload,
        )
        confidence = edge["confidence"]
        modifier   = edge["decision_modifier"]

        # ── Final decision ───────────────────────────────────────────────
        if modifier == "REJECT":
            decision = "REJECT"
        elif modifier == "MANUAL_REVIEW":
            decision = "MANUAL_REVIEW"
        elif pd > 0.65:
            decision = "REJECT"
        elif pd > 0.45:
            decision = "MANUAL_REVIEW"
        else:
            decision = "APPROVE"

        return {
            "z_score":           z_score,
            "z_band":            z_band_label,
            "z_band_narrative":  z_band_narrative,
            "pd":                pd,
            "lgd":               lgd,
            "max_loan":          max_loan,
            "max_loan_breakdown": max_loan_info,
            "rate":              rate,
            "confidence":        confidence,
            "decision":          decision,
            "external_risk":     ext_risk,
            "flags":             flags,
            "sector":            sector,
            "loan_amount":       loan_amount,
            "collateral_type":   collateral_type,
            "collateral_value":  collateral_value,
        }
