# 🏦 Intelli-Credit — AI-Powered Corporate Credit Underwriting

> From Raw PDF to Credit Appraisal Memo in minutes. Built with Streamlit + Gemini 2.0.

[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-red)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://python.org)

---

## 🚀 One-Command Deploy (Streamlit Cloud)

1. Fork this repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Set **Main file**: `app.py`
4. Add secrets in **Advanced settings**:
   ```toml
   GEMINI_API_KEY = "your-key-here"
   GOOGLE_API_KEY = "your-key-here"
   ```
5. Click **Deploy**

---

## 🖥️ Run Locally

```bash
git clone https://github.com/shreya21p/certifai.git
cd certifai
pip install -r requirements.txt
streamlit run app.py
```

---

## 📋 Pipeline Modules

| Module | File | Description |
|--------|------|-------------|
| 1 | `pages/01_ingestor.py` | Entity onboarding, document upload, AI classification, data extraction, fraud detection |
| 2 | `pages/02_research.py` | OSINT research, web scraping, sector analysis, document triangulation |
| 3 | `pages/03_recommendation.py` | Altman Z-Score, PD/LGD, interest rate, forensic fraud dashboard |
| 4 | `pages/04_cam.py` | Multi-agent CAM generation, HITL review, PDF/Word export, version control |

---

## 🎯 Demo Scenarios (No Documents Needed)

From `app.py` landing page, load any of:

- 🟢 **ABC Manufacturing** — APPROVE (clean profile)
- 🟡 **XYZ Traders** — MANUAL REVIEW (GST mismatch)
- 🔴 **PQR Real Estate** — REJECT (NCLT + critical fraud flags)

---

## 🔑 Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `GOOGLE_API_KEY` | Alternative Google API key |
| `DATABRICKS_ENABLED` | `true` to enable Databricks integration |
| `DATABRICKS_HOST` | Databricks workspace URL |
| `DATABRICKS_TOKEN` | Databricks PAT token |

---

## 📦 Key Dependencies

```
streamlit, google-genai, docling, reportlab, python-docx,
matplotlib, plotly, streamlit-agraph, pyyaml, pandas
```

---

## 📁 Output Files

All outputs written to `./data/`:
- `extraction_payload.json` — Module 1 output
- `research_payload.json` — Module 2 output
- `recommendation_payload.json` — Module 3 output
- `CAM_{company}_{date}.pdf` — Final CAM (PDF)
- `CAM_{company}_{date}.docx` — Final CAM (Word)
- `cam_audit_log.json` — Version history

---

*Intelli-Credit © 2025 | Built for India's corporate credit ecosystem*
