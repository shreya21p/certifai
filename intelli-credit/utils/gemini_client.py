# utils/gemini_client.py
"""
Gemini API client with:
  - Multi-key rotation across separate GCP projects
  - Model cascade: gemini-2.5-flash-lite → gemini-2.0-flash → gemini-1.5-flash
  - Exponential backoff: 2s → 4s → 8s → 16s → 32s → 60s
  - MD5 prompt cache (identical prompts never hit the API twice)
  - JSON extraction helper with fence stripping
"""

import google.generativeai as genai
import time, json, hashlib, os
import streamlit as st
from pathlib import Path

# ── Key pool ──────────────────────────────────────────────────────
# Each key must come from a SEPARATE Google Cloud project.
# Creating 4 keys in the same project gives identical quota — useless.
# Use st.secrets in production, os.getenv for local dev.
def _load_keys() -> list[str]:
    keys = []
    for name in ["GEMINI_KEY_1", "GEMINI_KEY_2",
                 "GEMINI_KEY_3", "GEMINI_KEY_4", "GEMINI_API_KEY"]:
        v = os.getenv(name)
        if v and v not in keys:
            keys.append(v)
    try:
        for name in ["GEMINI_KEY_1", "GEMINI_KEY_2",
                     "GEMINI_KEY_3", "GEMINI_KEY_4", "GEMINI_API_KEY"]:
            v = st.secrets.get(name)
            if v and v not in keys:
                keys.append(v)
    except Exception:
        pass
    return keys or []

API_KEYS = _load_keys()

# Model cascade — Flash-Lite has the most generous free quota
MODEL_CASCADE = [
    "gemini-2.5-flash-lite-preview-06-17",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]

# ── Prompt cache ──────────────────────────────────────────────────
CACHE_DIR = Path("./data/llm_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()

def _read_cache(text: str) -> str | None:
    p = CACHE_DIR / f"{_cache_key(text)}.json"
    if p.exists():
        return json.loads(p.read_text())["r"]
    return None

def _write_cache(text: str, response: str) -> None:
    p = CACHE_DIR / f"{_cache_key(text)}.json"
    p.write_text(json.dumps({"r": response}))

# ── Core call ─────────────────────────────────────────────────────
def call_gemini(
    prompt: str,
    system_prompt: str = "",
    use_cache: bool = True,
    max_retries: int = 6,
) -> str:
    if not API_KEYS:
        st.error("❌ No Gemini API keys configured. "
                 "Add GEMINI_API_KEY to .env or st.secrets.")
        st.stop()

    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    if use_cache:
        cached = _read_cache(full)
        if cached:
            return cached

    last_error = None
    n_keys = len(API_KEYS)

    for model_name in MODEL_CASCADE:
        for attempt in range(max_retries):
            key = API_KEYS[attempt % n_keys]
            try:
                genai.configure(api_key=key)
                model    = genai.GenerativeModel(model_name)
                response = model.generate_content(full)
                result   = response.text
                if use_cache:
                    _write_cache(full, result)
                return result

            except Exception as e:
                last_error = e
                is_rate = any(x in str(e).lower() for x in
                              ["429", "quota", "rate", "resource_exhausted",
                               "too many"])
                if is_rate:
                    wait = min(2 ** attempt, 60)
                    st.warning(
                        f"⏳ Rate limit — key {(attempt % n_keys)+1}/{n_keys}, "
                        f"model {model_name}, attempt {attempt+1}/{max_retries}. "
                        f"Waiting {wait}s…"
                    )
                    time.sleep(wait)
                else:
                    break  # non-rate error: try next model immediately

        st.warning(f"⚠ Exhausted retries on {model_name}. Trying next model…")

    st.error(f"❌ All models and keys exhausted. Last error: {last_error}")
    if st.button("🔄 Retry", key=f"retry_{id(last_error)}"):
        st.rerun()
    raise last_error


def call_gemini_json(
    prompt: str,
    system_prompt: str = "",
    use_cache: bool = True,
) -> dict:
    """Calls Gemini and returns parsed JSON dict, stripping markdown fences."""
    raw = call_gemini(prompt, system_prompt, use_cache)
    clean = raw.strip()
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
        clean = clean.rsplit("```", 1)[0]
    return json.loads(clean.strip())
