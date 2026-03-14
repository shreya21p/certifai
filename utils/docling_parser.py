import pdfplumber
import pymupdf                      # fitz — no OpenGL dependency
import pytesseract
import pandas as pd
import base64
import io
from pathlib import Path
from PIL import Image


# ── Tesseract config ────────────────────────────────────────────
# Works on Streamlit Cloud after packages.txt installs tesseract-ocr
TESS_CONFIG = "--oem 3 --psm 6"


def parse_document(file_path: str) -> dict:
    path = Path(file_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _parse_pdf(file_path)
        elif suffix in [".xlsx", ".xls"]:
            return _parse_excel(file_path)
        elif suffix == ".csv":
            return _parse_csv(file_path)
        elif suffix in [".png", ".jpg", ".jpeg"]:
            return _parse_image_file(file_path)
        else:
            return _empty("Unsupported file type: " + suffix)
    except Exception as e:
        return _empty(f"Parse error: {str(e)}")


def _is_text_based_pdf(file_path: str) -> bool:
    """
    Heuristic: if pdfplumber extracts > 100 chars of text from page 1,
    it's a text-based PDF. Otherwise treat as scanned.
    """
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text() or ""
            return len(text.strip()) > 100
    except Exception:
        return False


def _parse_pdf(file_path: str) -> dict:
    # Always try pdfplumber first (fast path)
    result = _parse_pdf_text(file_path)

    # If < 200 chars extracted, PDF is likely protected/image-based — fall to OCR
    if len(result["text"].strip()) < 200:
        import streamlit as st
        st.warning(
            f"Low text yield from pdfplumber ({len(result['text'])} chars) "
            f"— switching to OCR. If Tesseract is not installed, install it with: "
            f"`brew install tesseract` (Mac) or `sudo apt-get install tesseract-ocr` (Linux).",
            icon=":material/warning:"
        )
        try:
            return _parse_pdf_scanned(file_path)
        except Exception as e:
            # Tesseract not installed — return the (empty) pdfplumber result
            st.error(f"OCR fallback failed: {e}. Please install Tesseract and retry.", icon=":material/error:")
            return result

    return result


def _parse_pdf_text(file_path: str) -> dict:
    """Fast path for digital/text PDFs using pdfplumber."""
    text_parts = []
    tables = []

    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
            for raw in page.extract_tables() or []:
                if raw and len(raw) > 1:
                    try:
                        df = pd.DataFrame(raw[1:], columns=raw[0])
                        df = df.dropna(how="all").dropna(axis=1, how="all")
                        if not df.empty:
                            tables.append(df)
                    except Exception:
                        pass

    return {
        "text": "\n\n".join(text_parts),
        "tables": tables,
        "metadata": {"filename": Path(file_path).name,
                     "pages": len(text_parts)},
        "parse_method": "pdfplumber",
        "success": bool(text_parts),
    }


def _parse_pdf_scanned(file_path: str) -> dict:
    """
    OCR path for scanned PDFs.
    Uses pymupdf to render pages to images, then pytesseract for OCR.
    No libGL / OpenCV dependency.
    """
    text_parts = []
    doc = pymupdf.open(file_path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render at 2x zoom for better OCR accuracy
        mat = pymupdf.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csRGB)
        img_bytes = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_bytes))

        # OCR the rendered page image
        ocr_text = pytesseract.image_to_string(
            pil_img,
            config=TESS_CONFIG,
            lang="eng"
        )
        if ocr_text.strip():
            text_parts.append(f"--- Page {page_num + 1} ---\n{ocr_text}")

    doc.close()

    full_text = "\n\n".join(text_parts)
    return {
        "text": full_text,
        "tables": [],          # table extraction from OCR is unreliable; Gemini handles it
        "metadata": {"filename": Path(file_path).name,
                     "pages": len(text_parts),
                     "ocr": True},
        "parse_method": "pymupdf_ocr",
        "success": bool(full_text),
    }


def _parse_excel(file_path: str) -> dict:
    text_parts = []
    tables = []
    xl = pd.ExcelFile(file_path)
    for sheet in xl.sheet_names:
        df = xl.parse(sheet).dropna(how="all").dropna(axis=1, how="all")
        if not df.empty:
            tables.append(df)
            text_parts.append(f"--- Sheet: {sheet} ---\n{df.to_string(index=False)}")
    return {
        "text": "\n\n".join(text_parts),
        "tables": tables,
        "metadata": {"sheets": xl.sheet_names, "filename": Path(file_path).name},
        "parse_method": "pandas_excel",
        "success": bool(tables),
    }


def _parse_csv(file_path: str) -> dict:
    # Always use raw text for messy section-header CSVs
    raw = Path(file_path).read_text(errors="ignore")
    tables = []
    try:
        df = pd.read_csv(file_path).dropna(how="all").dropna(axis=1, how="all")
        if not df.empty:
            tables.append(df)
    except Exception:
        pass
    return {
        "text": raw,
        "tables": tables,
        "metadata": {"filename": Path(file_path).name},
        "parse_method": "pandas_csv",
        "success": True,
    }


def _parse_image_file(file_path: str) -> dict:
    """PNG/JPG — encode as base64 for Gemini vision."""
    with open(file_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()
    return {
        "text": "",
        "tables": [],
        "metadata": {"filename": Path(file_path).name},
        "parse_method": "gemini_vision",
        "success": True,
        "image_b64": image_b64,
        "image_path": file_path,
    }


def _empty(reason: str) -> dict:
    return {
        "text": "", "tables": [], "metadata": {},
        "parse_method": "failed", "success": False, "error": reason,
    }
