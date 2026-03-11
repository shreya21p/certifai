"""
Data Ingestor — Financial Triangulation Module
================================================
Module: certifai/modules/ingestor.py

Entry point: run_ingestor(upload_folder_path, output_json_path)

Responsibilities:
  1. Scan upload_folder_path for financial documents (CSV, XLSX, PDF)
  2. Parse structured files with Pandas
  3. Parse unstructured PDFs with Gemini 1.5 Flash (multimodal)
  4. Extract the 6 core financial metrics
  5. Run triangulation fraud rules (Financial Triangulation Engine)
  6. Validate output with Pydantic and write JSON to output_json_path
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional

import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

# ---------------------------------------------------------------------------
# 1. Pydantic Output Schema
# ---------------------------------------------------------------------------

class FinancialMetrics(BaseModel):
    """Core financial metrics extracted from uploaded documents."""
    revenue: int = Field(0, description="Annual revenue / turnover (INR)")
    debt: int = Field(0, description="Total outstanding debt (INR)")
    cash_flow: int = Field(0, description="Operating cash flow (INR)")
    gst_sales: int = Field(0, description="GST-declared sales (INR)")
    bank_inflows: int = Field(0, description="Net bank inflows across all accounts (INR)")
    promoter_pledge_percent: float = Field(0.0, description="% of promoter shares pledged")


class CompanyReport(BaseModel):
    """Top-level output validated by Pydantic before writing to disk."""
    company_name: str
    metrics: FinancialMetrics
    fraud_flags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def ensure_company_name(self) -> "CompanyReport":
        if not self.company_name or self.company_name.strip() == "":
            self.company_name = "Unknown Company"
        return self


# ---------------------------------------------------------------------------
# 2. Keyword Maps — flexible column / key matching
# ---------------------------------------------------------------------------

METRIC_KEYWORDS: dict[str, list[str]] = {
    # NOTE: Keywords are sorted longest-first inside each list so the most
    # specific phrase wins when a column name contains multiple terms.
    "revenue": [
        "income from operations",
        "total revenue",
        "gross revenue",
        "net revenue",
        "net sales",        # 'net sales' is more specific than 'sales'
        "turnover",
        "revenue",
        # 'sales' intentionally removed — too short, collides with 'gst_sales'
    ],
    "debt": [
        "total borrowings",
        "total liabilities",
        "long term debt",
        "borrowings",
        "net debt",
        "total debt",
        "debt",
    ],
    "cash_flow": [
        "cash flow from operations",
        "net cash from operations",
        "operating cash flow",
        "operating_cash_flow",   # exact CSV column name
        "operating activities",
        "cash flow operations",
    ],
    "gst_sales": [
        "gst declared sales",
        "total taxable value",
        "gst turnover",
        "taxable turnover",
        "gst revenue",
        "gst sales",
        "gst_sales",            # exact CSV column name
        "gst",
    ],
    "bank_inflows": [
        "bank inflows",
        "bank_inflows",         # exact CSV column name
        "total inflows",
        "total credits",
        "credit turnover",
        "total credit",
        "net inflows",
        "bank credit",
    ],
    "promoter_pledge_percent": [
        "promoter pledge percent",
        "promoter_pledge_percent",  # exact CSV column name
        "promoter pledged",
        "promoter pledge",
        "pledged shares",
        "pledge percent",
        "% pledged",
        "pledge %",
    ],
}


def _match_metric(column_name: str) -> Optional[str]:
    """
    Return the internal metric key that best matches a column name.

    Strategy:
    - Strip and lowercase the column name.
    - Try EXACT match against known column names first (fastest path).
    - Then do keyword scan, checking longest keywords first to prefer
      specificity (e.g. 'gst_sales' beats 'sales' for a column named 'gst_sales').
    - Substring match: keyword IN col  (col contains keyword)
      — not col IN keyword, to avoid 'revenue' matching 'gst_revenue'.
    """
    col = column_name.lower().strip().replace(" ", "_")

    # Pass 1: exact match against all keywords
    for metric, keywords in METRIC_KEYWORDS.items():
        for kw in keywords:
            if col == kw.replace(" ", "_"):
                return metric

    # Pass 2: substring — keyword found within column name,
    # iterate keywords longest-first to prefer specific matches.
    for metric, keywords in METRIC_KEYWORDS.items():
        sorted_kws = sorted(keywords, key=len, reverse=True)
        for kw in sorted_kws:
            kw_norm = kw.replace(" ", "_")
            if kw_norm in col:
                return metric

    return None


def _safe_int(value) -> int:
    """Coerce a value to int, stripping currency symbols/commas."""
    if pd.isna(value):
        return 0
    s = str(value).replace(",", "").replace("₹", "").replace("$", "").strip()
    # Remove trailing label like "Cr", "L", "M"
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return 0


def _safe_float(value) -> float:
    """Coerce a value to float, stripping non-numeric characters."""
    if pd.isna(value):
        return 0.0
    s = str(value).replace(",", "").replace("%", "").strip()
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# 3. Structured File Parser (CSV / XLSX)
# ---------------------------------------------------------------------------

def parse_structured_file(file_path: str | Path) -> dict:
    """
    Parse a CSV or XLSX file and extract the 6 target financial metrics.

    Accepts two layouts:
      A) Column-per-metric  — each column header maps to a metric, values in rows.
      B) Row-per-metric     — first column is metric name, second column is value.
    """
    file_path = Path(file_path)
    logger.info("Parsing structured file: %s", file_path.name)

    if file_path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(file_path, dtype=str)
    else:
        df = pd.read_csv(file_path, dtype=str)

    results: dict[str, float] = {}
    company_name: str = ""

    # ---- Detect company name -----------------------------------------------
    for col in df.columns:
        if "company" in col.lower() or "name" in col.lower():
            company_name = str(df[col].iloc[0]).strip()
            break

    # ---- Try Layout A: column headers map to metrics -----------------------
    col_map: dict[str, str] = {}
    for col in df.columns:
        metric = _match_metric(col)
        if metric:
            col_map[col] = metric

    if col_map:
        # Use _safe_float for the percentage field; int for all monetary fields
        for col, metric in col_map.items():
            if metric == "promoter_pledge_percent":
                results[metric] = _safe_float(df[col].iloc[0])
            else:
                results[metric] = _safe_int(df[col].iloc[0])
        return {"company_name": company_name, "metrics": results}

    # ---- Fallback Layout B: key-value rows ---------------------------------
    if df.shape[1] >= 2:
        key_col, val_col = df.columns[0], df.columns[1]
        for _, row in df.iterrows():
            metric = _match_metric(str(row[key_col]))
            if metric:
                if metric == "promoter_pledge_percent":
                    results[metric] = _safe_float(row[val_col])
                else:
                    results[metric] = _safe_int(row[val_col])

    return {"company_name": company_name, "metrics": results}


# ---------------------------------------------------------------------------
# 4. PDF Parser — Gemini 1.5 Flash Multimodal
# ---------------------------------------------------------------------------

def parse_pdf_with_gemini(pdf_path: str | Path) -> dict:
    """
    Send the PDF to Gemini 1.5 Flash and ask it to extract financial metrics.

    Returns a dict with keys: company_name, metrics (same structure as above).
    Falls back to empty metrics if the API key is absent or the call fails.
    """
    pdf_path = Path(pdf_path)
    logger.info("Parsing PDF with Gemini: %s", pdf_path.name)

    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(
            "GOOGLE_API_KEY not set — skipping PDF parse for '%s'. "
            "Set the key in a .env file to enable PDF extraction.",
            pdf_path.name,
        )
        return {"company_name": "", "metrics": {}}

    try:
        import google.generativeai as genai  # lazy import — only needed for PDFs

        genai.configure(api_key=api_key)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        encoded = base64.b64encode(pdf_bytes).decode("utf-8")

        prompt = """You are a financial data extraction assistant.
Analyze the provided document (Annual Report, Bank Statement, or GST Return) and extract
the following financial metrics. Return ONLY a valid JSON object — no markdown, no explanation.

Required JSON schema:
{
  "company_name": "<string or empty>",
  "revenue": <integer or 0>,
  "total_debt": <integer or 0>,
  "operating_cash_flow": <integer or 0>,
  "gst_sales": <integer or 0>,
  "bank_inflows": <integer or 0>,
  "promoter_pledge_percent": <float or 0.0>
}

Rules:
- All monetary values must be in the same unit as the document (do NOT convert).
- If a metric is not found, use 0 or 0.0.
- Return only the JSON object.
"""

        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(
            [
                {"mime_type": "application/pdf", "data": encoded},
                prompt,
            ]
        )

        raw = response.text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

        data = json.loads(raw)
        return {
            "company_name": data.get("company_name", ""),
            "metrics": {
                "revenue": int(data.get("revenue", 0)),
                "debt": int(data.get("total_debt", 0)),
                "cash_flow": int(data.get("operating_cash_flow", 0)),
                "gst_sales": int(data.get("gst_sales", 0)),
                "bank_inflows": int(data.get("bank_inflows", 0)),
                "promoter_pledge_percent": float(data.get("promoter_pledge_percent", 0.0)),
            },
        }

    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini PDF parse failed for '%s': %s", pdf_path.name, exc)
        return {"company_name": "", "metrics": {}}


# ---------------------------------------------------------------------------
# 5. Financial Triangulation — Fraud Rules Engine
# ---------------------------------------------------------------------------

def detect_revenue_anomalies(metrics: FinancialMetrics) -> list[str]:
    """
    Run triangulation fraud rules against the extracted metrics.

    Rules implemented:
    ┌──────────────────────────────────────────────────────────────────────────┐
    │ Rule 1 — Revenue Inflation Risk                                          │
    │   If bank_inflows < 50% of revenue, the reported revenue is likely       │
    │   inflated vs. actual cash movement. Flag as "Revenue Inflation Risk".   │
    │                                                                           │
    │ Rule 2 — GST-Revenue Mismatch                                            │
    │   If gst_sales < 70% of revenue (and gst_sales > 0), the company may    │
    │   be under-reporting to tax authorities vs. audited books.               │
    │                                                                           │
    │ Rule 3 — High Promoter Pledge                                            │
    │   Promoter pledge > 50% signals distress / collateral concentration.     │
    └──────────────────────────────────────────────────────────────────────────┘
    """
    flags: list[str] = []

    # Rule 1: Core triangulation rule (mandatory per spec)
    if metrics.revenue > 0 and metrics.bank_inflows < (0.5 * metrics.revenue):
        flags.append("Revenue Inflation Risk")
        logger.warning(
            "FRAUD FLAG — Revenue Inflation Risk: bank_inflows=%d < 50%% of revenue=%d",
            metrics.bank_inflows,
            metrics.revenue,
        )

    # Rule 2: GST vs Audited Revenue mismatch
    if metrics.gst_sales > 0 and metrics.revenue > 0:
        if metrics.gst_sales < (0.7 * metrics.revenue):
            flags.append("GST-Revenue Mismatch")
            logger.warning(
                "FRAUD FLAG — GST-Revenue Mismatch: gst_sales=%d < 70%% of revenue=%d",
                metrics.gst_sales,
                metrics.revenue,
            )

    # Rule 3: High promoter pledge
    if metrics.promoter_pledge_percent > 50.0:
        flags.append("High Promoter Pledge Risk")
        logger.warning(
            "FRAUD FLAG — High Promoter Pledge: %.1f%% shares pledged",
            metrics.promoter_pledge_percent,
        )

    if not flags:
        logger.info("Triangulation: No fraud flags detected.")

    return flags


# ---------------------------------------------------------------------------
# 6. Main Orchestrator
# ---------------------------------------------------------------------------

def _merge_metrics(base: dict, overlay: dict) -> dict:
    """Merge two metric dicts — overlay values take precedence over 0-defaults."""
    merged = dict(base)
    for k, v in overlay.items():
        if v:  # only overwrite if the overlay has a non-zero value
            merged[k] = v
    return merged


def run_ingestor(upload_folder_path: str, output_json_path: str) -> CompanyReport:
    """
    Main callable entry point for the Data Ingestor module.

    Parameters
    ----------
    upload_folder_path : str
        Path to the folder containing financial documents
        (CSV, XLSX, PDF — any mix of Annual Reports, Bank Statements, GST Returns).
    output_json_path : str
        Path where the validated JSON report will be written.

    Returns
    -------
    CompanyReport
        Pydantic-validated report object (also written to output_json_path).
    """
    upload_dir = Path(upload_folder_path)
    if not upload_dir.exists():
        raise FileNotFoundError(f"Upload folder not found: {upload_folder_path}")

    # ---- Collect files ------------------------------------------------------
    supported_extensions = {".csv", ".xlsx", ".xls", ".pdf"}
    files = [
        f for f in upload_dir.iterdir()
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]

    if not files:
        logger.warning("No supported files found in '%s'. Returning empty report.", upload_folder_path)

    logger.info("Found %d file(s) to process: %s", len(files), [f.name for f in files])

    # ---- Parse files --------------------------------------------------------
    combined_metrics: dict[str, float] = {
        "revenue": 0,
        "debt": 0,
        "cash_flow": 0,
        "gst_sales": 0,
        "bank_inflows": 0,
        "promoter_pledge_percent": 0.0,
    }
    company_name = ""

    for file in files:
        ext = file.suffix.lower()
        if ext == ".pdf":
            parsed = parse_pdf_with_gemini(file)
        else:
            parsed = parse_structured_file(file)

        # Capture company name from the first file that provides one
        if not company_name and parsed.get("company_name"):
            company_name = parsed["company_name"]

        # Merge metrics — non-zero values from later files override earlier zeros
        file_metrics = parsed.get("metrics", {})
        combined_metrics = _merge_metrics(combined_metrics, file_metrics)

    # ---- Build Pydantic model -----------------------------------------------
    metrics_obj = FinancialMetrics(
        revenue=int(combined_metrics.get("revenue", 0)),
        debt=int(combined_metrics.get("debt", 0)),
        cash_flow=int(combined_metrics.get("cash_flow", 0)),
        gst_sales=int(combined_metrics.get("gst_sales", 0)),
        bank_inflows=int(combined_metrics.get("bank_inflows", 0)),
        promoter_pledge_percent=float(combined_metrics.get("promoter_pledge_percent", 0.0)),
    )

    # ---- Run Fraud Triangulation Engine -------------------------------------
    fraud_flags = detect_revenue_anomalies(metrics_obj)

    # ---- Validate & Serialize -----------------------------------------------
    report = CompanyReport(
        company_name=company_name or Path(upload_folder_path).name,
        metrics=metrics_obj,
        fraud_flags=fraud_flags,
    )

    output_path = Path(output_json_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info("Report written to: %s", output_path)

    return report
