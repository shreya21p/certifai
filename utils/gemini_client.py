"""
Gemini API client — Intelli-Credit
Features:
  - Multi-key rotation across separate GCP projects
  - Model cascade: gemini-2.5-flash-lite-preview-06-17 → gemini-2.0-flash → gemini-1.5-flash
  - Exponential backoff: 2s → 4s → 8s → 16s → 32s → 60s per attempt (6 retries per model)
  - MD5 prompt cache: identical prompts never hit the API twice
  - JSON helper with automatic markdown fence stripping
  - call_gemini_with_retry() shim for backward compatibility
"""

import time, json, hashlib, os
import streamlit as st
from google import genai
from google.genai import types
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (two levels up: utils/ -> project root)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

# ── Key pool ──────────────────────────────────────────────────────
# IMPORTANT: each key must come from a SEPARATE Google Cloud project.
# Keys from the same project share the same quota — useless for rotation.
def _load_keys() -> list:
    keys = []
    for name in ["GEMINI_KEY_1", "GEMINI_KEY_2",
                 "GEMINI_KEY_3", "GEMINI_KEY_4",
                 "GEMINI_API_KEY", "GOOGLE_API_KEY"]:
        v = os.getenv(name)
        if v and v not in keys:
            keys.append(v)
    try:
        for name in ["GEMINI_KEY_1", "GEMINI_KEY_2",
                     "GEMINI_KEY_3", "GEMINI_KEY_4",
                     "GEMINI_API_KEY", "GOOGLE_API_KEY"]:
            v = st.secrets.get(name)
            if v and v not in keys:
                keys.append(v)
    except Exception:
        pass
    return keys

API_KEYS = _load_keys()

# Model cascade — stable models only, ordered by quota generosity
MODEL_CASCADE = [
    "gemini-2.5-flash",       # 10 RPM, 250 RPD, best quality
    "gemini-2.5-flash-lite",  # 15 RPM, 1000 RPD, high volume
    "gemini-1.5-flash",       # older but stable fallback
]

# ── Prompt cache ──────────────────────────────────────────────────
CACHE_DIR = Path("./data/llm_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _read_cache(text: str):
    p = CACHE_DIR / f"{_cache_key(text)}.json"
    if p.exists():
        return json.loads(p.read_text())["r"]
    return None


def _write_cache(text: str, response: str):
    p = CACHE_DIR / f"{_cache_key(text)}.json"
    p.write_text(json.dumps({"r": response}))


# ── Core call ─────────────────────────────────────────────────────
def call_gemini(
    prompt: str,
    system_prompt: str = "",
    use_cache: bool = True,
    max_retries: int = 6,
    response_mime_type: str = None,
) -> str:
    """
    Call the Gemini API with multi-key rotation, model cascade, and exponential backoff.

    Args:
        prompt:       The user prompt.
        system_prompt: Optional system-level instruction prepended to the prompt.
        use_cache:    If True, check MD5 cache before calling the API and write on success.
        max_retries:  Number of retry attempts per model before cascading.

    Returns:
        The model's text response.
    """
    if not API_KEYS:
        st.error(
            "❌ No Gemini API keys found.\n\n"
            "Add `GEMINI_API_KEY` to your `.env` file or Streamlit secrets.\n"
            "For best results add 4 keys from 4 separate GCP projects:\n"
            "`GEMINI_KEY_1`, `GEMINI_KEY_2`, `GEMINI_KEY_3`, `GEMINI_KEY_4`"
        )
        st.stop()

    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    if use_cache:
        cached = _read_cache(full)
        if cached:
            return cached

    last_error = None
    n = len(API_KEYS)

    for model_name in MODEL_CASCADE:
        for attempt in range(max_retries):
            key = API_KEYS[attempt % n]
            try:
                client   = genai.Client(api_key=key)
                cfg      = types.GenerateContentConfig(
                    response_mime_type=response_mime_type
                ) if response_mime_type else None
                response = client.models.generate_content(
                    model=model_name,
                    contents=full,
                    config=cfg,
                )
                result = response.text
                if use_cache:
                    _write_cache(full, result)
                return result

            except Exception as e:
                last_error = e
                is_rate = any(x in str(e).lower() for x in [
                    "429", "quota", "rate", "resource_exhausted", "too many"
                ])
                if is_rate:
                    wait = min(4 ** (attempt + 1), 60)  # 4s → 16s → 60s
                    st.warning(
                        f"⏳ Rate limit hit — key {(attempt % n) + 1}/{n}, "
                        f"model `{model_name}`, attempt {attempt + 1}/{max_retries}. "
                        f"Retrying in {wait}s…"
                    )
                    time.sleep(wait)
                else:
                    # Non-rate error on this model — skip to next model immediately
                    break

        st.warning(f"⚠ All retries exhausted on `{model_name}`. Trying next model…")

    st.error(
        f"❌ All {n} key(s) and {len(MODEL_CASCADE)} models exhausted.\n"
        f"Last error: `{last_error}`\n\n"
        f"**Fix options:**\n"
        f"- Add billing at aistudio.google.com (free, unlocks Tier 1)\n"
        f"- Add more keys from separate GCP projects to `.env`"
    )
    if st.button("🔄 Retry", key=f"retry_{abs(hash(str(last_error)))}"):
        st.rerun()
    raise last_error


def call_gemini_json(
    prompt: str,
    system_prompt: str = "",
    use_cache: bool = True,
) -> dict:
    """Calls Gemini and returns parsed JSON dict, stripping markdown fences."""
    raw = call_gemini(prompt, system_prompt, use_cache,
                      response_mime_type="application/json")
    clean = raw.strip()
    if not clean:
        raise ValueError("Gemini returned empty response")
    if clean.startswith("```"):
        clean = "\n".join(clean.split("\n")[1:])
        clean = clean.rsplit("```", 1)[0]
        
    # Find JSON object if buried in text
    import re
    match = re.search(r'\{.*\}', clean, re.DOTALL)
    if match:
        clean = match.group()
        
    return json.loads(clean.strip())


# ── Compatibility shim ────────────────────────────────────────────
# Existing callers use call_gemini_with_retry(contents, response_mime_type=...)
# where `contents` is a list of strings / dicts.  This shim flattens that
# into a single prompt string and delegates to call_gemini(), preserving all
# retry / rotation / caching behaviour introduced above.
def call_gemini_with_retry(
    contents,
    max_retries: int = 6,
    response_mime_type: str = None,
) -> str:
    """
    Backward-compatible wrapper around call_gemini().

    `contents` may be:
      - a list of strings  → joined with newlines
      - a list of dicts    → text parts extracted and joined
                            (handles both {"role":..,"parts":[..]} and {"text":..})
      - anything else      → str()-cast
    """
    parts = []
    if isinstance(contents, list):
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # Handle {"role": "user", "parts": ["text"]} format
                raw_parts = item.get("parts", [])
                if isinstance(raw_parts, list):
                    for p in raw_parts:
                        if isinstance(p, str):
                            parts.append(p)
                        elif isinstance(p, dict):
                            parts.append(p.get("text", str(p)))
                elif isinstance(raw_parts, str):
                    parts.append(raw_parts)
                # Also handle direct {"text": "..."} key
                if "text" in item and isinstance(item["text"], str):
                    parts.append(item["text"])
            elif isinstance(item, bytes):
                # Binary data (images etc.) — skip, cannot send as plain text
                pass
    else:
        parts.append(str(contents))

    prompt = "\n\n".join(p for p in parts if p.strip())
    return call_gemini(prompt, use_cache=True, max_retries=max_retries,
                       response_mime_type=response_mime_type)
