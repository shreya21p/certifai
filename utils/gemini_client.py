import time
import os
import streamlit as st
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
gemini_api_key = os.getenv("GEMINI_API_KEY")
if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

try:
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    gemini_model = None
    print(f"Failed to initialize gemini model: {e}")

def call_gemini_with_retry(contents, max_retries=3, response_mime_type=None):
    if not gemini_model:
        raise ValueError("Gemini model not initialized. Check your GEMINI_API_KEY.")
        
    generation_config = {}
    if response_mime_type:
        generation_config["response_mime_type"] = response_mime_type
        
    for attempt in range(max_retries):
        try:
            response = gemini_model.generate_content(
                contents,
                generation_config=generation_config
            )
            return response.text
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                st.warning(f"API call failed (attempt {attempt+1}). Retrying in {wait}s... Error: {e}")
                time.sleep(wait)
            else:
                st.error(f"API call failed after {max_retries} attempts. Please retry manually.")
                if st.button("🔄 Retry Now", key=f"retry_gemini_{time.time()}_{attempt}"):
                    st.rerun()
                raise e
