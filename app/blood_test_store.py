"""
Blood test persistence and PDF-to-structured-data extraction.

Scans the blood_tests/ folder for PDF files, extracts biomarker data using
GPT-4o, normalises units to canonical form, and caches results in blood_tests.json.
"""

import asyncio
import json
import re
import uuid
from pathlib import Path

import pdfplumber
from openai import AsyncOpenAI

from app.config import settings
from app.blood_test_units import to_canonical

PDFS_DIR = Path(__file__).parent.parent / "blood_tests"
STORE_PATH = Path(__file__).parent.parent / "blood_tests.json"

_client = AsyncOpenAI(api_key=settings.openai_api_key)

_EXTRACT_PROMPT = """\
You are a medical lab report parser. Extract all blood test results from the text below.

Return ONLY valid JSON (no markdown fences, no prose) with this exact structure:
{
  "lab": "<lab name>",
  "date": "<YYYY-MM-DD>",
  "country": "<2-letter ISO country code>",
  "biomarkers": [
    {
      "display_name": "<name exactly as shown in report>",
      "canonical_name": "<lowercase_underscore standard name e.g. ferritin, hemoglobin, tsh, vitamin_d, ldl>",
      "value": <number>,
      "unit": "<unit string>",
      "ref_low": <number or null>,
      "ref_high": <number or null>
    }
  ]
}

Rules:
- Include every measured value that has a numeric result.
- For reference ranges written as e.g. "3.5 - 5.0", set ref_low=3.5 ref_high=5.0.
- For one-sided ranges like "<5.0", set ref_low=null ref_high=5.0.
- If no reference range is given, set both to null.
- canonical_name must be a plain lowercase string with underscores only (no special chars).
- value must be a JSON number, not a string.

Lab report text:
"""


# ---------------------------------------------------------------------------
# JSON store helpers
# ---------------------------------------------------------------------------

def load_tests() -> list[dict]:
    if STORE_PATH.exists():
        try:
            return json.loads(STORE_PATH.read_text())["tests"]
        except Exception:
            return []
    return []


def _save_tests(tests: list[dict]) -> None:
    STORE_PATH.write_text(json.dumps({"tests": tests}, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _extract_pdf_text(path: Path) -> str:
    """Extract all text from a PDF using pdfplumber."""
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# GPT extraction
# ---------------------------------------------------------------------------

async def _parse_with_gpt(text: str) -> dict:
    """Send PDF text to GPT-4o and return parsed test dict."""
    response = await _client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "user", "content": _EXTRACT_PROMPT + text}
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def _normalise_test(parsed: dict, source_file: str) -> dict:
    """Apply canonical unit conversion and compute in_range for each biomarker."""
    biomarkers = []
    for bm in parsed.get("biomarkers", []):
        canonical_name = (bm.get("canonical_name") or "").lower().strip()
        value = bm.get("value")
        unit = bm.get("unit") or ""
        ref_low = bm.get("ref_low")
        ref_high = bm.get("ref_high")

        if value is None:
            continue

        canon_val, canon_unit = to_canonical(canonical_name, float(value), unit)

        # Recompute in_range against canonical values of ref bounds
        in_range: bool | None = None
        if ref_low is not None or ref_high is not None:
            low_c = to_canonical(canonical_name, float(ref_low), unit)[0] if ref_low is not None else None
            high_c = to_canonical(canonical_name, float(ref_high), unit)[0] if ref_high is not None else None
            below = canon_val < low_c if low_c is not None else False
            above = canon_val > high_c if high_c is not None else False
            in_range = not (below or above)

        biomarkers.append({
            "display_name": bm.get("display_name", canonical_name),
            "canonical_name": canonical_name,
            "value": value,
            "unit": unit,
            "canonical_value": canon_val,
            "canonical_unit": canon_unit,
            "ref_low": ref_low,
            "ref_high": ref_high,
            "in_range": in_range,
        })

    date_str = parsed.get("date", "")
    lab_slug = re.sub(r"[^a-z0-9]+", "-", (parsed.get("lab") or "unknown").lower()).strip("-")
    test_id = f"{date_str}-{lab_slug}" if date_str else str(uuid.uuid4())[:8]

    return {
        "id": test_id,
        "source_file": source_file,
        "date": date_str,
        "lab": parsed.get("lab", ""),
        "country": parsed.get("country", ""),
        "biomarkers": biomarkers,
    }


# ---------------------------------------------------------------------------
# Main sync entry point
# ---------------------------------------------------------------------------

async def sync_new_pdfs() -> int:
    """
    Scan PDFS_DIR for PDFs not yet in blood_tests.json.
    Parse each new one via GPT and persist.
    Returns the number of new tests added.
    """
    PDFS_DIR.mkdir(exist_ok=True)
    tests = load_tests()
    known_files = {t["source_file"] for t in tests}

    new_pdfs = [
        p for p in sorted(PDFS_DIR.glob("*.pdf"))
        if p.name not in known_files
    ]

    if not new_pdfs:
        return 0

    async def _process(pdf_path: Path) -> dict | None:
        try:
            text = _extract_pdf_text(pdf_path)
            if not text.strip():
                return None
            parsed = await _parse_with_gpt(text)
            return _normalise_test(parsed, pdf_path.name)
        except Exception as e:
            # Log but don't crash the whole sync
            print(f"[blood_test_store] Failed to parse {pdf_path.name}: {e}")
            return None

    results = await asyncio.gather(*[_process(p) for p in new_pdfs])
    added = [r for r in results if r is not None]

    if added:
        tests.extend(added)
        tests.sort(key=lambda t: t.get("date", ""), reverse=True)
        _save_tests(tests)

    return len(added)
