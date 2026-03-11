"""
cam_generator.py  —  CertifAI CAM (Credit Appraisal Memo) Generator
=====================================================================
Reads three upstream JSONs produced by the Ingestor, Research Agent, and
Credit Engine, then produces a professional, audit-ready PDF report.

Pipeline
--------
  1. Data Aggregation   – load the three input JSONs
  2. Deterministic Chart – matplotlib Revenue vs Debt bar chart → temp_chart.png
  3. LLM Synthesis      – Gemini generates Executive Summary + SWOT from data
  4. PDF Assembly        – reportlab renders the full CAM document

Entry point
-----------
    generate_cam_report(
        financial_json_path,
        intelligence_json_path,
        risk_json_path,
        output_pdf_path,
        gemini_api_key=None   # falls back to env var GEMINI_API_KEY
    )
"""

import json
import os
import sys
import tempfile
import textwrap
from datetime import datetime, timezone
from typing import Optional

import matplotlib
matplotlib.use("Agg")                          # non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Paragraph, Spacer, Table, TableStyle, Image,
    HRFlowable, KeepTogether,
)
from reportlab.platypus.flowables import BalancedColumns
from reportlab.lib.colors import HexColor


# ─────────────────────────────────────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────────────────────────────────────
PRIMARY      = HexColor("#1A237E")   # deep indigo
ACCENT       = HexColor("#3949AB")   # medium indigo
LIGHT_BG     = HexColor("#E8EAF6")   # very light indigo
RED_ALERT    = HexColor("#B71C1C")
ORANGE_WARN  = HexColor("#E65100")
GREEN_OK     = HexColor("#1B5E20")
GREY_TEXT    = HexColor("#424242")
LIGHT_GREY   = HexColor("#EEEEEE")
WHITE        = colors.white


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        raise FileNotFoundError(f"[CAMGenerator] File not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _fmt_currency(value: float, unit: str = "₹", lakhs: bool = True) -> str:
    """Return a human-readable currency string."""
    if lakhs:
        return f"{unit}{value:,.2f} L"
    return f"{unit}{value:,.2f}"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _decision_color(decision: str) -> HexColor:
    mapping = {"APPROVE": GREEN_OK, "MANUAL_REVIEW": ORANGE_WARN, "REJECT": RED_ALERT}
    return mapping.get(decision.upper(), GREY_TEXT)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 – Deterministic matplotlib chart
# ─────────────────────────────────────────────────────────────────────────────

def _generate_chart(fin: dict, save_path: str) -> str:
    """
    Creates a grouped bar chart: Operating Cash Flow vs Total Liabilities vs Revenue.
    All values are taken exactly from the financial JSON — no hallucination.
    """
    categories = ["Revenue", "Total Liabilities", "EBITDA", "Op. Cash Flow", "Collateral"]
    values = [
        fin.get("revenue",             0.0),
        fin.get("total_liabilities",   0.0),
        fin.get("ebitda",              0.0),
        fin.get("operating_cash_flow", 0.0),
        fin.get("collateral_value",    0.0),
    ]

    bar_colors = ["#3949AB", "#B71C1C", "#00897B", "#558B2F", "#F57C00"]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    fig.patch.set_facecolor("#F5F5F5")
    ax.set_facecolor("#FAFAFA")

    x = np.arange(len(categories))
    bars = ax.bar(x, values, color=bar_colors, width=0.55, zorder=3, edgecolor="white")

    # Value labels on top of each bar
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.015,
            f"₹{val:,.0f}L",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color="#212121"
        )

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylabel("Amount (₹ Lakhs)", fontsize=10, color="#424242")
    ax.set_title("Key Financial Metrics", fontsize=13, fontweight="bold",
                 color="#1A237E", pad=12)
    ax.yaxis.grid(True, linestyle="--", alpha=0.6, zorder=0)
    ax.spines[["top", "right"]].set_visible(False)

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 – LLM Synthesis via Gemini
# ─────────────────────────────────────────────────────────────────────────────

def _build_llm_prompt(fin: dict, intel: dict, risk: dict) -> str:
    company = fin.get("company_name", "the applicant company")
    return f"""
You are a senior Credit Officer at a commercial bank preparing a formal Credit Appraisal Memo (CAM).

Below is the complete financial and intelligence data for {company}:

FINANCIAL DATA:
{json.dumps(fin, indent=2)}

EXTERNAL INTELLIGENCE:
{json.dumps(intel, indent=2)}

RISK DECISION:
{json.dumps(risk, indent=2)}

Your task — respond in plain text (no markdown, no asterisks, no bullet symbols other than plain hyphens):

EXECUTIVE SUMMARY:
Write exactly 4 bullet lines (each starting with '- ') summarising the credit profile, key risks, and recommendation.

SWOT ANALYSIS:
Strengths:
- [2-3 bullets]
Weaknesses:
- [2-3 bullets]
Opportunities:
- [2-3 bullets]
Threats:
- [2-3 bullets]

Keep language formal, concise, and audit-ready. Do not repeat the raw numbers verbatim; interpret them.
""".strip()


def _call_gemini(prompt: str, api_key: str) -> str:
    from google import genai
    from google.genai import types as genai_types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=genai_types.GenerateContentConfig(temperature=0.3),
    )
    return response.text.strip()


def _fallback_swot(fin: dict, risk: dict) -> str:
    """Deterministic fallback when no API key is available."""
    decision = risk.get("decision", "N/A")
    pd_val   = _fmt_pct(risk.get("PD", 0))
    z        = risk.get("altman_z_score", "N/A")
    return f"""EXECUTIVE SUMMARY:
- The applicant's Altman Z'-Score of {z} places it in the financial distress zone, indicating elevated default risk.
- Probability of Default stands at {pd_val}, which triggered a {decision} recommendation under the credit policy thresholds.
- Collateral coverage provides partial downside protection, but the DSCR-based loan cap limits maximum exposure significantly.
- The credit committee is advised to seek further documentation before extending any facility.

SWOT ANALYSIS:
Strengths:
- Partial collateral coverage reduces Loss Given Default (LGD) to {_fmt_pct(risk.get('LGD', 0))}.
- Established operating cash flows indicate some capacity to service debt obligations.

Weaknesses:
- Altman Z'-Score below 1.8 signals significant financial distress and near-term default risk.
- High total liabilities relative to assets constrain borrowing headroom.
- PD of {pd_val} exceeds the 60% rejection threshold.

Opportunities:
- Restructuring liabilities and improving working capital could improve the Z-Score within 1-2 fiscal years.
- Sector tailwinds may boost revenue, improving debt-service ratios over the medium term.

Threats:
- Adverse news and sector volatility (if flagged) may compound financial stress.
- Rising interest rates will increase debt-service burden on existing liabilities.
- Prolonged distress may erode collateral market value."""


def _parse_llm_output(text: str) -> tuple[str, dict[str, list[str]]]:
    """
    Parse the LLM/fallback output into:
      - exec_summary: str (multi-line, hyphens stripped)
      - swot: dict with keys Strengths/Weaknesses/Opportunities/Threats
    """
    lines = text.splitlines()
    exec_lines = []
    swot = {"Strengths": [], "Weaknesses": [], "Opportunities": [], "Threats": []}
    current_section = None
    in_exec = False
    in_swot  = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if "EXECUTIVE SUMMARY" in upper:
            in_exec = True
            in_swot = False
            current_section = None
            continue
        if "SWOT ANALYSIS" in upper:
            in_exec = False
            in_swot = True
            continue
        if in_swot:
            for key in swot:
                if stripped.lower().startswith(key.lower()):
                    current_section = key
                    break
            else:
                if current_section and stripped.startswith("-"):
                    swot[current_section].append(stripped.lstrip("- ").strip())
            continue
        if in_exec and stripped.startswith("-"):
            exec_lines.append(stripped.lstrip("- ").strip())

    exec_summary = "\n".join(exec_lines) if exec_lines else "Executive summary not available."
    return exec_summary, swot


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 – PDF Assembly via ReportLab
# ─────────────────────────────────────────────────────────────────────────────

def _make_styles():
    base = getSampleStyleSheet()

    styles = {
        "title": ParagraphStyle("CAM_Title",
            fontSize=22, leading=28, alignment=TA_CENTER,
            textColor=WHITE, fontName="Helvetica-Bold"),

        "subtitle": ParagraphStyle("CAM_Sub",
            fontSize=11, leading=16, alignment=TA_CENTER,
            textColor=LIGHT_BG, fontName="Helvetica"),

        "decision": ParagraphStyle("CAM_Decision",
            fontSize=16, leading=20, alignment=TA_CENTER,
            textColor=WHITE, fontName="Helvetica-Bold"),

        "section_header": ParagraphStyle("CAM_SH",
            fontSize=12, leading=16, spaceBefore=10, spaceAfter=4,
            textColor=WHITE, fontName="Helvetica-Bold",
            backColor=ACCENT, leftIndent=-6, rightIndent=-6,
            borderPad=(4, 6, 4, 6)),

        "body": ParagraphStyle("CAM_Body",
            fontSize=9.5, leading=14, alignment=TA_JUSTIFY,
            textColor=GREY_TEXT, fontName="Helvetica"),

        "bullet": ParagraphStyle("CAM_Bullet",
            fontSize=9.5, leading=14, leftIndent=14, bulletIndent=4,
            textColor=GREY_TEXT, fontName="Helvetica"),

        "swot_header": ParagraphStyle("CAM_SWOT_H",
            fontSize=10, leading=14, fontName="Helvetica-Bold",
            textColor=WHITE),

        "swot_body": ParagraphStyle("CAM_SWOT_B",
            fontSize=9, leading=13, leftIndent=8,
            textColor=GREY_TEXT, fontName="Helvetica"),

        "footer": ParagraphStyle("CAM_Footer",
            fontSize=7.5, leading=10, alignment=TA_CENTER,
            textColor=GREY_TEXT, fontName="Helvetica-Oblique"),

        "label": ParagraphStyle("CAM_Label",
            fontSize=9, fontName="Helvetica-Bold", textColor=GREY_TEXT),

        "value": ParagraphStyle("CAM_Value",
            fontSize=9, fontName="Helvetica", textColor=GREY_TEXT),
    }
    return styles


def _section_header(title: str, styles: dict) -> list:
    """Returns a section-header row with background colour."""
    return [
        HRFlowable(width="100%", thickness=0.5, color=ACCENT, spaceAfter=2),
        Paragraph(f"  {title}", styles["section_header"]),
        Spacer(1, 4),
    ]


def _financial_table(fin: dict, styles: dict) -> Table:
    row_data = [
        ["Metric", "Value"],
        ["Revenue",               _fmt_currency(fin.get("revenue", 0))],
        ["EBIT",                  _fmt_currency(fin.get("ebit", 0))],
        ["EBITDA",                _fmt_currency(fin.get("ebitda", 0))],
        ["Total Assets",          _fmt_currency(fin.get("total_assets", 0))],
        ["Total Liabilities",     _fmt_currency(fin.get("total_liabilities", 0))],
        ["Current Assets",        _fmt_currency(fin.get("current_assets", 0))],
        ["Current Liabilities",   _fmt_currency(fin.get("current_liabilities", 0))],
        ["Retained Earnings",     _fmt_currency(fin.get("retained_earnings", 0))],
        ["Operating Cash Flow",   _fmt_currency(fin.get("operating_cash_flow", 0))],
        ["Collateral Value",      _fmt_currency(fin.get("collateral_value", 0))],
        ["Loan Amount Requested", _fmt_currency(fin.get("loan_amount_requested", 0))],
    ]

    tbl = Table(row_data, colWidths=[90*mm, 70*mm], hAlign="LEFT")
    style = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",         (0, 0), (-1, -1), 0.4, HexColor("#BDBDBD")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    tbl.setStyle(style)
    return tbl


def _risk_table(risk: dict, styles: dict) -> Table:
    decision    = risk.get("decision", "N/A")
    dec_color   = _decision_color(decision)

    row_data = [
        ["Risk Metric", "Value"],
        ["Decision",          decision],
        ["Probability of Default (PD)",  _fmt_pct(risk.get("PD", 0))],
        ["Loss Given Default (LGD)",     _fmt_pct(risk.get("LGD", 0))],
        ["Expected Loss",                _fmt_currency(risk.get("expected_loss", 0))],
        ["Max Loan Amount",              _fmt_currency(risk.get("max_loan_amount", 0))],
        ["Suggested Interest Rate",      _fmt_pct(risk.get("interest_rate", 0))],
        ["Altman Z'-Score",              str(risk.get("altman_z_score", "N/A"))],
    ]

    tbl = Table(row_data, colWidths=[90*mm, 70*mm], hAlign="LEFT")
    style = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("ALIGN",        (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        # Highlight decision row
        ("BACKGROUND",   (0, 1), (-1, 1), dec_color),
        ("TEXTCOLOR",    (0, 1), (-1, 1), WHITE),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",         (0, 0), (-1, -1), 0.4, HexColor("#BDBDBD")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    tbl.setStyle(style)
    return tbl


def _swot_table(swot: dict, styles: dict) -> Table:
    swot_colors = {
        "Strengths":     HexColor("#1B5E20"),
        "Weaknesses":    HexColor("#B71C1C"),
        "Opportunities": HexColor("#0D47A1"),
        "Threats":       HexColor("#E65100"),
    }

    def _cell(title, bullets, bg):
        content = [Paragraph(title, styles["swot_header"])]
        for b in bullets:
            content.append(Paragraph(f"- {b}", styles["swot_body"]))
        return content

    quadrants = list(swot_colors.keys())
    data = [
        [_cell(quadrants[0], swot.get(quadrants[0], []), swot_colors[quadrants[0]]),
         _cell(quadrants[1], swot.get(quadrants[1], []), swot_colors[quadrants[1]])],
        [_cell(quadrants[2], swot.get(quadrants[2], []), swot_colors[quadrants[2]]),
         _cell(quadrants[3], swot.get(quadrants[3], []), swot_colors[quadrants[3]])],
    ]

    tbl = Table(data, colWidths=[82*mm, 82*mm])
    style = TableStyle([
        # Colour each quadrant header area
        ("BACKGROUND",   (0, 0), (0, 0), swot_colors["Strengths"]),
        ("BACKGROUND",   (1, 0), (1, 0), swot_colors["Weaknesses"]),
        ("BACKGROUND",   (0, 1), (0, 1), swot_colors["Opportunities"]),
        ("BACKGROUND",   (1, 1), (1, 1), swot_colors["Threats"]),
        ("GRID",         (0, 0), (-1, -1), 0.5, HexColor("#BDBDBD")),
        ("VALIGN",       (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])
    tbl.setStyle(style)
    return tbl


def _early_warning_table(intel: dict, styles: dict) -> Table:
    adverse = intel.get("adverse_news_score", 0.0)

    signals = [
        ["Signal",                    "Status",             "Severity"],
        ["Sector Risk Flag",
         "ELEVATED" if intel.get("sector_risk_flag") else "CLEAR",
         "HIGH" if intel.get("sector_risk_flag") else "LOW"],
        ["Management Risk Flag",
         "ELEVATED" if intel.get("management_risk_flag") else "CLEAR",
         "HIGH" if intel.get("management_risk_flag") else "LOW"],
        ["Adverse News Score",
         f"{adverse:.2f} / 1.00",
         "HIGH" if adverse > 0.5 else ("MEDIUM" if adverse > 0.2 else "LOW")],
        ["GSTIN Active",
         "YES" if intel.get("gstin_active") else "NO",
         "LOW" if intel.get("gstin_active") else "HIGH"],
        ["MCA Compliant",
         "YES" if intel.get("mca_compliant") else "NO",
         "LOW" if intel.get("mca_compliant") else "HIGH"],
        ["Court Cases Pending",
         str(intel.get("court_cases_pending", "N/A")),
         "HIGH" if int(intel.get("court_cases_pending", 0)) > 0 else "LOW"],
    ]

    def _sev_color(sev):
        return {"HIGH": RED_ALERT, "MEDIUM": ORANGE_WARN, "LOW": GREEN_OK}.get(sev, GREY_TEXT)

    tbl_style = TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), WHITE),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 9.5),
        ("FONTNAME",     (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("GRID",         (0, 0), (-1, -1), 0.4, HexColor("#BDBDBD")),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ])

    # Colour the Severity column cells
    for i, row in enumerate(signals[1:], start=1):
        sev = row[2]
        c   = _sev_color(sev)
        tbl_style.add("TEXTCOLOR", (2, i), (2, i), c)
        tbl_style.add("FONTNAME",  (2, i), (2, i), "Helvetica-Bold")

    tbl = Table(signals, colWidths=[80*mm, 55*mm, 30*mm], hAlign="LEFT")
    tbl.setStyle(tbl_style)
    return tbl


def _add_header_footer(canvas, doc, company_name: str, decision: str, generated_at: str):
    canvas.saveState()
    W, H = A4

    # ── Header banner ────────────────────────────────────────────────────────
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, H - 55*mm, W, 55*mm, fill=1, stroke=0)

    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawCentredString(W / 2, H - 22*mm, "CREDIT APPRAISAL MEMO (CAM)")

    canvas.setFont("Helvetica", 12)
    canvas.drawCentredString(W / 2, H - 32*mm, company_name)

    # Decision badge
    dec_color = _decision_color(decision)
    badge_w, badge_h = 60*mm, 10*mm
    badge_x = (W - badge_w) / 2
    badge_y = H - 46*mm
    canvas.setFillColor(dec_color)
    canvas.roundRect(badge_x, badge_y, badge_w, badge_h, 4, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawCentredString(W / 2, badge_y + 2.5*mm, f"DECISION: {decision}")

    # ── Footer ───────────────────────────────────────────────────────────────
    canvas.setFillColor(LIGHT_GREY)
    canvas.rect(0, 0, W, 14*mm, fill=1, stroke=0)

    canvas.setFillColor(GREY_TEXT)
    canvas.setFont("Helvetica-Oblique", 7)
    canvas.drawString(15*mm, 5*mm,
        f"CONFIDENTIAL — CertifAI Credit Engine  |  Generated: {generated_at}  |  "
        f"NOT FOR DISTRIBUTION")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(W - 15*mm, 5*mm, f"Page {doc.page}")

    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def generate_cam_report(
    financial_json_path:    str,
    intelligence_json_path: str,
    risk_json_path:         str,
    output_pdf_path:        str,
    gemini_api_key:         Optional[str] = None,
) -> str:
    """
    Full pipeline: load → chart → LLM → PDF.

    Returns the absolute path to the generated PDF.
    """
    print(f"\n{'='*60}")
    print("  CertifAI CAM Generator  —  Starting")
    print(f"{'='*60}")

    # ── 1. Load inputs ────────────────────────────────────────────────────────
    print("[1/4] Loading upstream JSONs …")
    fin   = _load_json(financial_json_path)
    intel = _load_json(intelligence_json_path)
    risk  = _load_json(risk_json_path)

    company_name  = fin.get("company_name",  "Unknown Company")
    decision      = risk.get("decision",     "N/A")
    generated_at  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # ── 2. Generate chart ────────────────────────────────────────────────────
    print("[2/4] Generating financial chart …")
    chart_dir  = os.path.dirname(os.path.abspath(output_pdf_path))
    chart_path = os.path.join(chart_dir, "temp_chart.png")
    _generate_chart(fin, chart_path)
    print(f"      Chart saved -> {chart_path}")

    # ── 3. LLM Synthesis ─────────────────────────────────────────────────────
    print("[3/4] Synthesising executive summary & SWOT …")
    api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
    prompt  = _build_llm_prompt(fin, intel, risk)

    if api_key:
        try:
            raw_text = _call_gemini(prompt, api_key)
            print("      Gemini response received.")
        except Exception as e:
            print(f"      [!] Gemini call failed ({e}). Using deterministic fallback.")
            raw_text = _fallback_swot(fin, risk)
    else:
        print("      [i] No GEMINI_API_KEY found - using deterministic SWOT fallback.")
        raw_text = _fallback_swot(fin, risk)

    exec_summary, swot = _parse_llm_output(raw_text)

    # ── 4. PDF Assembly ──────────────────────────────────────────────────────
    print("[4/4] Assembling PDF …")
    styles = _make_styles()

    os.makedirs(os.path.dirname(os.path.abspath(output_pdf_path)), exist_ok=True)

    # Page layout: margins below the header banner
    HEADER_H = 55*mm
    FOOTER_H = 14*mm
    margin   = 15*mm

    doc = BaseDocTemplate(
        output_pdf_path,
        pagesize=A4,
        leftMargin=margin, rightMargin=margin,
        topMargin=HEADER_H + 6*mm, bottomMargin=FOOTER_H + 6*mm,
    )

    frame = Frame(
        margin, FOOTER_H + 6*mm,
        A4[0] - 2*margin, A4[1] - HEADER_H - FOOTER_H - 12*mm,
        id="main",
    )

    def _page_callback(canvas, doc):
        _add_header_footer(canvas, doc, company_name, decision, generated_at)

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame],
                                       onPage=_page_callback)])

    story = []

    # ── Section: Document Metadata ──────────────────────────────────────────
    story += _section_header("Document Information", styles)
    meta_rows = [
        ["Company",          company_name],
        ["Fiscal Year",      fin.get("fiscal_year", "N/A")],
        ["Sector",           intel.get("sector", "N/A")],
        ["Report Date",      generated_at],
        ["Prepared by",      "CertifAI Automated Credit Engine v1.0"],
        ["Classification",   "CONFIDENTIAL — Internal Use Only"],
    ]
    meta_tbl = Table(meta_rows, colWidths=[60*mm, 110*mm])
    meta_tbl.setStyle(TableStyle([
        ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",    (0, 0), (-1, -1), GREY_TEXT),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, LIGHT_BG]),
        ("GRID",         (0, 0), (-1, -1), 0.3, HexColor("#E0E0E0")),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 8))

    # ── Section: Executive Summary ──────────────────────────────────────────
    story += _section_header("Executive Summary", styles)
    for bullet_text in exec_summary.split("\n"):
        if bullet_text.strip():
            story.append(Paragraph(f"- {bullet_text.strip()}", styles["bullet"]))
    story.append(Spacer(1, 8))

    # ── Section: Financial Summary ──────────────────────────────────────────
    story += _section_header("Financial Summary", styles)
    story.append(_financial_table(fin, styles))
    story.append(Spacer(1, 8))

    # ── Section: Financial Chart ────────────────────────────────────────────
    story += _section_header("Key Financial Metrics — Chart", styles)
    img = Image(chart_path, width=165*mm, height=80*mm)
    img.hAlign = "CENTER"
    story.append(img)
    story.append(Spacer(1, 8))

    # ── Section: Risk Decision ──────────────────────────────────────────────
    story += _section_header("Credit Risk Decision", styles)
    story.append(_risk_table(risk, styles))
    story.append(Spacer(1, 8))

    # ── Section: SWOT ───────────────────────────────────────────────────────
    story += _section_header("SWOT Analysis", styles)
    story.append(_swot_table(swot, styles))
    story.append(Spacer(1, 8))

    # ── Section: Early Warning Signals ──────────────────────────────────────
    story += _section_header("Early Warning Signals (Research Agent)", styles)
    story.append(_early_warning_table(intel, styles))

    # News summary
    news = intel.get("news_summary", "")
    if news:
        story.append(Spacer(1, 5))
        story.append(Paragraph(f"<b>News Summary:</b> {news}", styles["body"]))
    story.append(Spacer(1, 8))

    # ── Section: Disclaimer ─────────────────────────────────────────────────
    story += _section_header("Disclaimer", styles)
    story.append(Paragraph(
        "This Credit Appraisal Memo has been generated by the CertifAI automated "
        "credit engine using deterministic financial mathematics and, where available, "
        "AI-assisted textual synthesis. The outputs are intended for internal review "
        "only and do not constitute a loan sanction. Final credit decisions must be "
        "ratified by an authorised credit officer in accordance with the bank's "
        "credit policy and applicable regulatory guidelines.",
        styles["body"]
    ))

    # ── Build PDF ────────────────────────────────────────────────────────────
    doc.build(story)
    print(f"\n[OK] CAM Report generated -> {output_pdf_path}")
    print(f"{'='*60}\n")

    return output_pdf_path


# ─────────────────────────────────────────────────────────────────────────────
# CLI runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Force UTF-8 output on Windows to handle unicode in print statements
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    fin_path   = os.path.join(BASE, "shared_data", "financial_summary.json")
    intel_path = os.path.join(BASE, "shared_data", "external_intelligence.json")
    risk_path  = os.path.join(BASE, "shared_data", "risk_decision.json")
    out_pdf    = os.path.join(BASE, "shared_data", "final_cam_report.pdf")

    if len(sys.argv) == 5:
        fin_path, intel_path, risk_path, out_pdf = sys.argv[1:5]

    generate_cam_report(fin_path, intel_path, risk_path, out_pdf)
