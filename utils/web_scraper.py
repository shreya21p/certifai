from ddgs import DDGS

def gather_web_context(company_name: str, sector: str, cin: str = None) -> dict:
    results = {}

    try:
        with DDGS() as ddgs:
            # Search 1: General company news
            results["news"] = list(ddgs.text(
                f"{company_name} India news 2024 2025",
                max_results=8
            ))

            # Search 2: Legal/default risk
            results["legal"] = list(ddgs.text(
                f"{company_name} lawsuit OR NCLT OR default OR recovery OR court India",
                max_results=8
            ))

            # Search 3: Sector outlook
            results["sector"] = list(ddgs.text(
                f"{sector} industry India outlook 2025 RBI regulations headwinds",
                max_results=6
            ))

            # Search 4: Promoter background
            results["promoter"] = list(ddgs.text(
                f"{company_name} promoter director background India",
                max_results=5
            ))

            # Search 5: MCA / ROC filings
            results["mca"] = list(ddgs.text(
                f"{company_name} MCA ROC filing annual return director disqualification India",
                max_results=5
            ))

            # Search 6: GST compliance
            results["gst"] = list(ddgs.text(
                f"{company_name} GST notice OR GSTR mismatch OR fake ITC OR GST evasion India",
                max_results=5
            ))
    except Exception as e:
        print(f"Error gathering web context from DuckDuckGo: {e}")
        # In case of failure, try to populate empty lists so the rest of the flow doesn't break
        for key in ["news", "legal", "sector", "promoter", "mca", "gst"]:
            if key not in results:
                results[key] = []

    def flatten(items):
        if not items:
            return ""
        return " | ".join([
            f"{r.get('title', '')}. {r.get('body', '')}"
            for r in items
        ])

    return {
        "news_context": flatten(results.get("news", [])),
        "legal_context": flatten(results.get("legal", [])),
        "sector_context": flatten(results.get("sector", [])),
        "promoter_context": flatten(results.get("promoter", [])),
        "mca_context": flatten(results.get("mca", [])),
        "gst_context": flatten(results.get("gst", []))
    }
