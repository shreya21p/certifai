"""
Tests for certifai/modules/ingestor.py

Run from the certifai/ directory:
    pytest tests/test_ingestor.py -v
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

# Allow imports from the certifai package root
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.ingestor import (
    CompanyReport,
    FinancialMetrics,
    detect_revenue_anomalies,
    parse_structured_file,
    run_ingestor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CSV = (
    Path(__file__).resolve().parent.parent
    / "shared_data"
    / "uploads"
    / "financials_sample.csv"
)


# ---------------------------------------------------------------------------
# Test 1: Structured CSV Parsing
# ---------------------------------------------------------------------------

def test_structured_parse_csv():
    """parse_structured_file should correctly read all 6 metrics from the sample CSV."""
    result = parse_structured_file(SAMPLE_CSV)

    metrics = result["metrics"]
    assert metrics["revenue"] == 50_000_000,       "Revenue mismatch"
    assert metrics["debt"] == 15_000_000,           "Debt mismatch"
    assert metrics["cash_flow"] == 8_000_000,       "Cash flow mismatch"
    assert metrics["gst_sales"] == 45_000_000,      "GST sales mismatch"
    assert metrics["bank_inflows"] == 30_000_000,   "Bank inflows mismatch"
    assert metrics["promoter_pledge_percent"] == pytest.approx(22.5), "Pledge mismatch"


# ---------------------------------------------------------------------------
# Test 2: Fraud Flag — Revenue Inflation TRIGGERED
# ---------------------------------------------------------------------------

def test_fraud_flag_triggered():
    """
    Rule: bank_inflows < 0.5 * revenue → "Revenue Inflation Risk" must appear.
    Here revenue = 100, bank_inflows = 40 (< 50).
    """
    metrics = FinancialMetrics(
        revenue=100_000_000,
        debt=20_000_000,
        cash_flow=5_000_000,
        gst_sales=80_000_000,
        bank_inflows=40_000_000,   # < 50% of revenue → FRAUD FLAG
        promoter_pledge_percent=10.0,
    )
    flags = detect_revenue_anomalies(metrics)
    assert "Revenue Inflation Risk" in flags, (
        f"Expected 'Revenue Inflation Risk' in flags, got: {flags}"
    )


# ---------------------------------------------------------------------------
# Test 3: Fraud Flag — Revenue Inflation NOT triggered (healthy metrics)
# ---------------------------------------------------------------------------

def test_fraud_flag_clean():
    """
    Rule: bank_inflows >= 0.5 * revenue → no fraud flag should be raised.
    Here revenue = 100, bank_inflows = 60 (> 50).
    """
    metrics = FinancialMetrics(
        revenue=100_000_000,
        debt=20_000_000,
        cash_flow=12_000_000,
        gst_sales=90_000_000,
        bank_inflows=60_000_000,   # ≥ 50% of revenue → CLEAN
        promoter_pledge_percent=15.0,
    )
    flags = detect_revenue_anomalies(metrics)
    assert "Revenue Inflation Risk" not in flags, (
        f"Expected no Revenue Inflation Risk flag, got: {flags}"
    )


# ---------------------------------------------------------------------------
# Test 4: Full run_ingestor pipeline — output JSON matches Pydantic schema
# ---------------------------------------------------------------------------

def test_output_json_schema(tmp_path):
    """
    run_ingestor should write a valid JSON file whose structure matches CompanyReport.
    Uses the sample CSV in shared_data/uploads/ (no Gemini API key needed).
    """
    upload_folder = SAMPLE_CSV.parent
    output_json = tmp_path / "financial_summary.json"

    report = run_ingestor(str(upload_folder), str(output_json))

    # Return type should be CompanyReport
    assert isinstance(report, CompanyReport)

    # JSON file must exist and be parseable
    assert output_json.exists(), "Output JSON was not written"
    data = json.loads(output_json.read_text())

    # Top-level keys
    assert "company_name" in data
    assert "metrics" in data
    assert "fraud_flags" in data

    # Metrics keys
    expected_keys = {"revenue", "debt", "cash_flow", "gst_sales", "bank_inflows", "promoter_pledge_percent"}
    assert expected_keys == set(data["metrics"].keys()), (
        f"Metrics keys mismatch: {set(data['metrics'].keys())}"
    )

    # Types
    assert isinstance(data["company_name"], str)
    assert isinstance(data["fraud_flags"], list)

    # Sample CSV has healthy metrics — Revenue Inflation Risk should NOT appear
    assert "Revenue Inflation Risk" not in data["fraud_flags"], (
        "Unexpected Revenue Inflation Risk flag on healthy sample data"
    )


# ---------------------------------------------------------------------------
# Test 5: Fraud — High Promoter Pledge Rule
# ---------------------------------------------------------------------------

def test_high_promoter_pledge_flag():
    """Promoter pledge > 50% should raise 'High Promoter Pledge Risk'."""
    metrics = FinancialMetrics(
        revenue=100_000_000,
        debt=20_000_000,
        cash_flow=12_000_000,
        gst_sales=90_000_000,
        bank_inflows=60_000_000,
        promoter_pledge_percent=65.0,  # > 50% → risk
    )
    flags = detect_revenue_anomalies(metrics)
    assert "High Promoter Pledge Risk" in flags, (
        f"Expected 'High Promoter Pledge Risk', got: {flags}"
    )


# ---------------------------------------------------------------------------
# Test 6: Fraud — GST-Revenue Mismatch Rule
# ---------------------------------------------------------------------------

def test_gst_revenue_mismatch_flag():
    """gst_sales < 70% of revenue should raise 'GST-Revenue Mismatch'."""
    metrics = FinancialMetrics(
        revenue=100_000_000,
        debt=20_000_000,
        cash_flow=12_000_000,
        gst_sales=50_000_000,   # < 70% of revenue → mismatch
        bank_inflows=80_000_000,
        promoter_pledge_percent=10.0,
    )
    flags = detect_revenue_anomalies(metrics)
    assert "GST-Revenue Mismatch" in flags, (
        f"Expected 'GST-Revenue Mismatch', got: {flags}"
    )
