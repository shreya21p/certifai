"""
Research Agent — OSINT Engine for CertifAI Digital Credit
==========================================================
Gathers qualitative signals (news, litigation, sector headwinds)
and uses an LLM to produce structured Early Warning Signals (EWS).

Entry point:
    run_research_agent(company_name, sector, output_json_path)
"""

import json
import os
import re
import time
from typing import Optional

from google import genai
from google.genai import types as genai_types
try:
    from ddgs import DDGS          # new package name (ddgs >= 1.0)
except ImportError:
    from duckduckgo_search import DDGS  # fallback for older installs
from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------

RISK_LEVELS = {"Low", "Medium", "High"}


class RiskDimensions(BaseModel):
    news_risk: str
    legal_risk: str
    sector_risk: str
    operational_risk: str

    @field_validator("news_risk", "legal_risk", "sector_risk", "operational_risk")
    @classmethod
    def must_be_valid_level(cls, v: str) -> str:
        if v not in RISK_LEVELS:
            raise ValueError(f"Risk level must be one of {RISK_LEVELS}, got '{v}'")
        return v


class ResearchOutput(BaseModel):
    company_name: str
    sector: str
    risk_dimensions: RiskDimensions
    early_warning_signals: list[str]
    raw_snippets_used: int
    timestamp: str


# ---------------------------------------------------------------------------
# Step 1 — Web search (3 targeted OSINT queries)
# ---------------------------------------------------------------------------

def gather_web_context(company_name: str, sector: str, max_snippets: int = 10) -> list[str]:
    """
    Executes 3 OSINT searches and returns up to `max_snippets` combined text snippets.

    Queries:
      1. "[Company] news"
      2. "[Company] lawsuit OR default OR NCLT"
      3. "[Sector] industry outlook India"
    """
    queries = [
        f"{company_name} news",
        f"{company_name} lawsuit OR default OR NCLT",
        f"{sector} industry outlook India",
    ]

    all_snippets: list[str] = []

    with DDGS() as ddgs:
        for query in queries:
            try:
                results = ddgs.text(query, max_results=5)
                for r in results:
                    # Combine title + snippet for richer context
                    title = r.get("title", "")
                    body = r.get("body", "")
                    snippet = f"[{title}] {body}".strip()
                    if snippet:
                        all_snippets.append(snippet)
                # Small delay to be polite to the search service
                time.sleep(0.5)
            except Exception as e:
                print(f"[ResearchAgent] Search failed for query '{query}': {e}")

    # Cap to max_snippets
    return all_snippets[:max_snippets]


# ---------------------------------------------------------------------------
# Step 2 & 3 — LLM risk analysis
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a senior Risk Analyst at a credit rating agency specializing in Indian SME finance.
You will be given a list of news/web snippets about a company and its industry sector.
Your job is to evaluate risk across four dimensions and flag early warning signals.

You MUST respond with ONLY valid JSON — no markdown fences, no extra text.
"""

USER_PROMPT_TEMPLATE = """
Company: {company_name}
Sector: {sector}

Web Intelligence Snippets (most recent):
---
{snippets_block}
---

Evaluate the following four risk dimensions. Use ONLY these values: "Low", "Medium", "High".

Respond with this exact JSON structure:
{{
  "news_risk": "<Low|Medium|High>",
  "legal_risk": "<Low|Medium|High>",
  "sector_risk": "<Low|Medium|High>",
  "operational_risk": "<Low|Medium|High>",
  "early_warning_signals": [
    "<signal 1>",
    "<signal 2>",
    "<signal 3 (optional)>"
  ]
}}

Risk dimension definitions:
- news_risk: Negative press, reputational damage, leadership controversies.
- legal_risk: Lawsuits, NCLT proceedings, regulatory notices, defaults.
- sector_risk: Industry-wide headwinds specific to the sector in India.
- operational_risk: Supply chain issues, workforce problems, production disruptions.

Early warning signals should be concise, analyst-style alerts (e.g., "High litigation risk detected — NCLT proceedings identified").
Include 2–3 signals. Be specific, not generic.
"""


def analyse_with_llm(
    company_name: str,
    sector: str,
    snippets: list[str],
    api_key: Optional[str] = None,
) -> dict:
    """
    Sends the gathered snippets to Gemini and parses the structured JSON response.
    Falls back to a conservative default if the LLM call fails.
    """
    _api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not _api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set. Export it as an environment variable or pass it explicitly."
        )

    client = genai.Client(api_key=_api_key)

    snippets_block = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(snippets)
    ) if snippets else "No snippets retrieved — insufficient data."

    user_prompt = USER_PROMPT_TEMPLATE.format(
        company_name=company_name,
        sector=sector,
        snippets_block=snippets_block,
    )

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.2,
            ),
        )
        raw_text = response.text.strip()

        # Strip accidental markdown fences if present
        raw_text = re.sub(r"^```(?:json)?", "", raw_text, flags=re.MULTILINE).strip()
        raw_text = re.sub(r"```$", "", raw_text, flags=re.MULTILINE).strip()

        parsed = json.loads(raw_text)
        return parsed

    except json.JSONDecodeError as e:
        print(f"[ResearchAgent] LLM returned invalid JSON: {e}")
        return _conservative_fallback(company_name, sector)
    except Exception as e:
        print(f"[ResearchAgent] LLM call failed: {e}")
        return _conservative_fallback(company_name, sector)


def _conservative_fallback(company_name: str, sector: str) -> dict:
    """Returns a safe, conservative risk profile when the LLM is unavailable."""
    return {
        "news_risk": "Medium",
        "legal_risk": "Medium",
        "sector_risk": "Medium",
        "operational_risk": "Medium",
        "early_warning_signals": [
            "Insufficient data — manual review recommended",
            "LLM analysis unavailable; conservative risk applied",
        ],
    }


# ---------------------------------------------------------------------------
# Step 4 — Orchestrator: run_research_agent
# ---------------------------------------------------------------------------

def run_research_agent(
    company_name: str,
    sector: str,
    output_json_path: str,
    gemini_api_key: Optional[str] = None,
) -> ResearchOutput:
    """
    Main entry point for the Research Agent.

    Args:
        company_name:      Name of the company to analyse (e.g., "Reliance Industries").
        sector:            Business sector of the company (e.g., "Textiles").
        output_json_path:  Absolute or relative path where the JSON output will be saved.
        gemini_api_key:    Optional Gemini API key override (defaults to GEMINI_API_KEY env var).

    Returns:
        A validated ResearchOutput Pydantic object.
    """
    print(f"\n[ResearchAgent] ▶ Starting OSINT analysis for '{company_name}' ({sector})")

    # --- Step 1: Gather web context ---
    print("[ResearchAgent] 🔍 Gathering web intelligence…")
    snippets = gather_web_context(company_name, sector)
    print(f"[ResearchAgent] ✅ Retrieved {len(snippets)} snippets")

    # --- Step 2 & 3: LLM risk analysis ---
    print("[ResearchAgent] 🤖 Running LLM risk analysis…")
    llm_output = analyse_with_llm(company_name, sector, snippets, api_key=gemini_api_key)

    # --- Validate with Pydantic ---
    risk_dims = RiskDimensions(
        news_risk=llm_output.get("news_risk", "Medium"),
        legal_risk=llm_output.get("legal_risk", "Medium"),
        sector_risk=llm_output.get("sector_risk", "Medium"),
        operational_risk=llm_output.get("operational_risk", "Medium"),
    )

    ews_raw: list = llm_output.get("early_warning_signals", [])
    # Ensure we have 2–3 signals; trim gracefully
    early_warning_signals = [str(s) for s in ews_raw[:3]] if ews_raw else [
        "No specific early warning signals identified"
    ]

    from datetime import datetime, timezone
    output = ResearchOutput(
        company_name=company_name,
        sector=sector,
        risk_dimensions=risk_dims,
        early_warning_signals=early_warning_signals,
        raw_snippets_used=len(snippets),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # --- Step 4: Save JSON ---
    output_path = os.path.abspath(output_json_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"[ResearchAgent] 💾 Output saved → {output_path}")
    print(f"[ResearchAgent] ✅ Analysis complete\n")

    return output


# ---------------------------------------------------------------------------
# CLI convenience — python -m modules.research_agent
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CertifAI Research Agent — OSINT EWS Engine")
    parser.add_argument("--company", required=True, help="Company name (e.g., 'Adani Ports')")
    parser.add_argument("--sector", required=True, help="Sector (e.g., 'Infrastructure')")
    parser.add_argument(
        "--output",
        default="shared_data/external_intelligence.json",
        help="Output JSON path (default: shared_data/external_intelligence.json)",
    )
    parser.add_argument("--api-key", default=None, help="Gemini API key override")

    args = parser.parse_args()

    result = run_research_agent(
        company_name=args.company,
        sector=args.sector,
        output_json_path=args.output,
        gemini_api_key=args.api_key,
    )

    print(json.dumps(result.model_dump(), indent=2))
