"""
app.py — CertifAI Platform Entry Point
=======================================
Orchestrates the full underwriting pipeline.
Currently wires the Data Ingestor module.
"""

import sys
from pathlib import Path

# Add project root to path so sub-modules resolve correctly
sys.path.insert(0, str(Path(__file__).parent))

from modules.ingestor import run_ingestor


def main():
    """Run the Data Ingestor on the default shared_data/uploads/ folder."""
    upload_folder = Path(__file__).parent / "shared_data" / "uploads"
    output_json = Path(__file__).parent / "shared_data" / "financial_summary.json"

    print(f"[CertifAI] Running Data Ingestor on: {upload_folder}")
    report = run_ingestor(str(upload_folder), str(output_json))

    print(f"\n[CertifAI] Company      : {report.company_name}")
    print(f"[CertifAI] Revenue      : ₹{report.metrics.revenue:,}")
    print(f"[CertifAI] Debt         : ₹{report.metrics.debt:,}")
    print(f"[CertifAI] Cash Flow    : ₹{report.metrics.cash_flow:,}")
    print(f"[CertifAI] GST Sales    : ₹{report.metrics.gst_sales:,}")
    print(f"[CertifAI] Bank Inflows : ₹{report.metrics.bank_inflows:,}")
    print(f"[CertifAI] Pledge %     : {report.metrics.promoter_pledge_percent}%")
    print(f"[CertifAI] Fraud Flags  : {report.fraud_flags or 'None'}")
    print(f"\n[CertifAI] Full report  → {output_json}")


if __name__ == "__main__":
    main()
