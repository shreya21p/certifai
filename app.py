"""
CertifAI — Shared State Orchestrator
=====================================
Entry point that wires all agent modules together via shared JSON state.

Usage examples:
    # Run only the Research Agent
    python app.py --mode research --company "Adani Ports" --sector "Infrastructure"

    # Run all agents in sequence (full pipeline)
    python app.py --mode all --company "Reliance Retail" --sector "Retail"
"""

import argparse
import json
import os

# Shared output paths (single source of truth for all agents)
SHARED = {
    "financial_summary":      "shared_data/financial_summary.json",
    "external_intelligence":  "shared_data/external_intelligence.json",
    "risk_decision":          "shared_data/risk_decision.json",
    "final_cam_report":       "shared_data/final_cam_report.pdf",
}


def run_research(company: str, sector: str) -> None:
    """Run the Research Agent (OSINT) module."""
    from modules.research_agent import run_research_agent

    result = run_research_agent(
        company_name=company,
        sector=sector,
        output_json_path=SHARED["external_intelligence"],
    )
    print("\n=== Research Agent Output ===")
    print(json.dumps(result.model_dump(), indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="CertifAI — Digital Credit OSINT Platform"
    )
    parser.add_argument(
        "--mode",
        choices=["research", "all"],
        default="research",
        help="Which agent module(s) to run",
    )
    parser.add_argument("--company", required=True, help="Company name")
    parser.add_argument("--sector",  required=True, help="Business sector")
    args = parser.parse_args()

    if args.mode in ("research", "all"):
        run_research(args.company, args.sector)

    # Future agents will be plugged in here:
    # if args.mode == "all":
    #     run_credit_engine(...)
    #     run_cam_generator(...)


if __name__ == "__main__":
    main()
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
