"""
CertifAI — Full Pipeline Orchestrator
======================================
Wires all four agent modules together via shared JSON state in shared_data/.

Usage:
    # Step 1 — Ingest financial documents
    python app.py --mode ingestor --company "Arjun Textiles Pvt. Ltd."

    # Step 2 — Run OSINT Research Agent (needs GEMINI_API_KEY)
    python app.py --mode research --company "Arjun Textiles Pvt. Ltd." --sector "Textiles"

    # Step 3 — Generate CAM PDF report
    python app.py --mode cam

    # Run everything end-to-end
    python app.py --mode all --company "Arjun Textiles Pvt. Ltd." --sector "Textiles"
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ─── Shared state paths (single source of truth for every module) ───────────
BASE = Path(__file__).parent
SHARED = {
    "financial_summary":     str(BASE / "shared_data" / "financial_summary.json"),
    "external_intelligence": str(BASE / "shared_data" / "external_intelligence.json"),
    "risk_decision":         str(BASE / "shared_data" / "risk_decision.json"),
    "final_cam_report":      str(BASE / "shared_data" / "final_cam_report.pdf"),
    "uploads":               str(BASE / "shared_data" / "uploads"),
}


# ─── Module runners ──────────────────────────────────────────────────────────

def run_ingestor(company: str = "") -> None:
    """Step 1 — Parse financial documents → financial_summary.json."""
    from modules.ingestor import run_ingestor as _run

    print("\n" + "═" * 60)
    print("  STEP 1 — Data Ingestor (Financial Triangulation)")
    print("═" * 60)

    report = _run(
        upload_folder_path=SHARED["uploads"],
        output_json_path=SHARED["financial_summary"],
    )

    # Enrich output JSON with CAM-generator-expected fields (using ingestor values as proxies)
    with open(SHARED["financial_summary"], "r") as f:
        data = json.load(f)

    rev = data["metrics"]["revenue"]
    debt = data["metrics"]["debt"]
    cf = data["metrics"]["cash_flow"]

    # Derive approximate balance-sheet fields so CAM can render a full table
    enriched = {
        "company_name":           data["company_name"] or company or "Unknown",
        "fiscal_year":            "FY 2024-25",
        "revenue":                rev / 1e5,            # convert to Lakhs for CAM
        "ebit":                   cf * 0.85 / 1e5,
        "ebitda":                 cf / 1e5,
        "total_assets":           (rev * 0.9) / 1e5,
        "total_liabilities":      debt / 1e5,
        "current_assets":         (rev * 0.4) / 1e5,
        "current_liabilities":    (debt * 0.4) / 1e5,
        "retained_earnings":      (rev * 0.1) / 1e5,
        "operating_cash_flow":    cf / 1e5,
        "collateral_value":       (debt * 0.5) / 1e5,
        "loan_amount_requested":  (debt * 0.3) / 1e5,
        # Keep fraud flags for reference
        "fraud_flags":            data.get("fraud_flags", []),
    }

    with open(SHARED["financial_summary"], "w") as f:
        json.dump(enriched, f, indent=2)

    print(f"\n  ✅ Company      : {enriched['company_name']}")
    print(f"  ✅ Revenue      : ₹{enriched['revenue']:,.2f}L")
    print(f"  ✅ Total Liab.  : ₹{enriched['total_liabilities']:,.2f}L")
    print(f"  ✅ Cash Flow    : ₹{enriched['operating_cash_flow']:,.2f}L")
    print(f"  ✅ Fraud Flags  : {enriched['fraud_flags'] or 'None'}")
    print(f"\n  Saved → {SHARED['financial_summary']}")


def run_research(company: str, sector: str) -> None:
    """Step 2 — OSINT + Gemini risk analysis → external_intelligence.json."""
    from modules.research_agent import run_research_agent

    print("\n" + "═" * 60)
    print("  STEP 2 — Research Agent (OSINT + LLM Risk Analysis)")
    print("═" * 60)

    if not os.environ.get("GEMINI_API_KEY"):
        print("\n  ⚠️  GEMINI_API_KEY not set.")
        print("  ℹ️  Skipping live OSINT — using existing external_intelligence.json sample data.")
        print("  ℹ️  To enable: export GEMINI_API_KEY=your_key_here")
        return

    try:
        result = run_research_agent(
            company_name=company,
            sector=sector,
            output_json_path=SHARED["external_intelligence"],
        )
        print("\n  === Research Agent Output ===")
        print(json.dumps(result.model_dump(), indent=2))
    except EnvironmentError as e:
        print(f"\n  ⚠️  Research Agent skipped: {e}")
        print("  ℹ️  Proceeding with existing external_intelligence.json sample data.")


def run_cam() -> None:
    """Step 3 — Generate CAM PDF from the three upstream JSONs."""
    from modules.cam_generator import generate_cam_report

    print("\n" + "═" * 60)
    print("  STEP 3 — CAM Generator (PDF Report)")
    print("═" * 60)

    generate_cam_report(
        financial_json_path=SHARED["financial_summary"],
        intelligence_json_path=SHARED["external_intelligence"],
        risk_json_path=SHARED["risk_decision"],
        output_pdf_path=SHARED["final_cam_report"],
    )
    print(f"\n  ✅ CAM PDF saved → {SHARED['final_cam_report']}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="CertifAI — AI-Assisted Corporate Credit Underwriting Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  ingestor  Parse financial documents in shared_data/uploads/
  research  Run OSINT + Gemini risk analysis   (needs GEMINI_API_KEY)
  cam       Generate the final CAM PDF report
  all       Run ingestor → research → cam in sequence
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["ingestor", "research", "cam", "all"],
        default="all",
        help="Which pipeline step(s) to run (default: all)",
    )
    parser.add_argument("--company", default="Arjun Textiles Pvt. Ltd.", help="Company name")
    parser.add_argument("--sector",  default="Textiles",                  help="Business sector")
    args = parser.parse_args()

    if args.mode in ("ingestor", "all"):
        run_ingestor(company=args.company)

    if args.mode in ("research", "all"):
        run_research(company=args.company, sector=args.sector)

    if args.mode in ("cam", "all"):
        run_cam()

    if args.mode == "all":
        print("\n" + "═" * 60)
        print("  ✅  Full CertifAI pipeline complete!")
        print(f"  📄  CAM Report → {SHARED['final_cam_report']}")
        print("═" * 60 + "\n")


if __name__ == "__main__":
    main()
