import time
import re
import os
import streamlit as st
from google import genai
from google.genai import types
from dotenv import load_dotenv
from pathlib import Path

# Resolve .env from project root (two levels up: utils/ -> project root)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

# Support both GEMINI_API_KEY and GOOGLE_API_KEY
_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not _api_key:
    print("⚠️  No Gemini API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY in .env")

# gemini-2.0-flash-lite has a much higher free-tier quota than gemini-2.0-flash
MODEL_NAME = "gemini-2.0-flash-lite"


def _get_client():
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not key:
        raise ValueError("No Gemini API key found. Set GEMINI_API_KEY in .env")
    return genai.Client(api_key=key)


def _parse_retry_delay(err_str: str) -> int | None:
    """Extract retryDelay seconds from a 429 error message, e.g. 'retry in 39s'."""
    match = re.search(r"retry[^\d]*(\d+)", err_str, re.IGNORECASE)
    if match:
        return int(match.group(1)) + 2  # add 2s buffer
    return None


def call_gemini_with_retry(contents, max_retries=3, response_mime_type=None):
    config = None
    if response_mime_type:
        config = types.GenerateContentConfig(
            response_mime_type=response_mime_type
        )

    for attempt in range(max_retries):
        try:
            client = _get_client()
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            is_rate_limit = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

            if attempt < max_retries - 1:
                if is_rate_limit:
                    # Honour the retry delay the API tells us
                    wait = _parse_retry_delay(err_str) or (2 ** attempt * 10)
                    st.warning(f"⏳ Rate limit hit. Waiting {wait}s before retry (attempt {attempt+1}/{max_retries})...")
                else:
                    wait = 2 ** attempt  # standard exponential backoff
                    st.warning(f"API call failed (attempt {attempt+1}). Retrying in {wait}s... Error: {e}")
                time.sleep(wait)
            else:
                st.error(f"API call failed after {max_retries} attempts. Please retry manually.")
                if st.button("🔄 Retry Now", key=f"retry_gemini_{time.time()}_{attempt}"):
                    st.rerun()
                raise e

