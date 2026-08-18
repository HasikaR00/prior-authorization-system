"""
================================================================================
ISOLATED PDF TEXT & OCR FIELD EXTRACTION MODULE
================================================================================
This module extracts candidate Prior Authorization (PA) fields from uploaded
PDF documents using PyMuPDF (text-based PDFs) and Tesseract OCR (scanned PDFs).

IMPORTANT & MANDATORY:
- This module is STRICTLY for text extraction only.
- It DOES NOT write to any database.
- It DOES NOT call decision_engine.py.
- It DOES NOT create pa_request or pa_decision_log records.
- It DOES NOT invent or hallucinate missing information.
================================================================================
"""

import re
import os
import io
import shutil
import logging
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)

# Try importing PyMuPDF (fitz)
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF (fitz) is not installed.")

# Try importing pytesseract & PIL
try:
    import pytesseract
    from PIL import Image

    # Configure system Tesseract binary path on Windows if needed
    tess_cmd = shutil.which("tesseract")
    if not tess_cmd:
        common_win_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in common_win_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    logger.warning("pytesseract or Pillow is not installed.")


def extract_raw_text_from_pdf(pdf_bytes: bytes) -> Tuple[str, str, bool]:
    """
    Extracts raw text from PDF bytes.
    First attempts PyMuPDF text extraction. If extracted text is under threshold,
    falls back to Tesseract OCR (rendering pages as images).
    
    Returns:
        (extracted_text, extraction_method, ocr_used)
    """
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF is not installed on the system.")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_pages = []

    for page in doc:
        page_text = page.get_text("text") or ""
        text_pages.append(page_text)

    combined_text = "\n".join(text_pages).strip()

    # If PyMuPDF yields sufficient text (> 40 chars), use text extraction
    if len(combined_text) >= 40:
        doc.close()
        return combined_text, "TEXT", False

    # Otherwise, fallback to Tesseract OCR if available
    if TESSERACT_AVAILABLE:
        try:
            ocr_pages = []
            for page in doc:
                # Render page to high-res pixmap (300 DPI = zoom 4.16)
                pix = page.get_pixmap(dpi=300)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                page_ocr_text = pytesseract.image_to_string(img)
                ocr_pages.append(page_ocr_text)

            doc.close()
            ocr_text = "\n".join(ocr_pages).strip()
            if ocr_text:
                return ocr_text, "OCR", True
        except Exception as ocr_err:
            logger.error(f"Tesseract OCR failed: {ocr_err}")
            doc.close()

    doc.close()
    return combined_text, "TEXT", False


def extract_pa_fields_from_text(raw_text: str) -> Dict[str, Optional[str]]:
    """
    Parses candidate PA fields from raw extracted document text using
    label matching and pattern regex. Does NOT invent missing information.
    """
    fields: Dict[str, Optional[str]] = {
        "patient_id": None,
        "patient_name": None,
        "birthdate": None,
        "gender": None,
        "state": None,
        "payer_name": None,
        "requested_hcpcs": None,
        "diagnosis_icd10": None,
        "ordering_provider": None,
        "signed_order_date": None,
        "urgency": None,
        "clinical_rationale": None,
    }

    # 1. Patient ID (UUID regex: 8-4-4-4-12 hex or explicit Patient ID/Member ID label)
    uuid_match = re.search(r'\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b', raw_text)
    if uuid_match:
        fields["patient_id"] = uuid_match.group(1).lower()
    else:
        pid_label = re.search(r'(?:Patient\s*ID|Patient\s*Identifier|Member\s*ID|Patient\s*UUID)\s*[:=\-]\s*([A-Za-z0-9\-]+)', raw_text, re.IGNORECASE)
        if pid_label:
            fields["patient_id"] = pid_label.group(1).strip()

    # 2. Patient Name
    pname_match = re.search(r'(?:Patient\s*Name|Name\s*of\s*Patient|Member\s*Name)\s*[:=\-]\s*([A-Za-z\s,\.\'-]+?)(?=\n|DOB|Date|Gender|ID|Age|$)', raw_text, re.IGNORECASE)
    if pname_match:
        name_val = pname_match.group(1).strip()
        if len(name_val) >= 2 and not any(kw in name_val.lower() for kw in ["hcpcs", "icd", "provider", "date"]):
            fields["patient_name"] = name_val

    # 3. Birthdate
    dob_match = re.search(r'(?:DOB|Date\s*of\s*Birth|Birthdate|Birth\s*Date)\s*[:=\-]\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', raw_text, re.IGNORECASE)
    if dob_match:
        dob_raw = dob_match.group(1).strip()
        if "/" in dob_raw:
            parts = dob_raw.split("/")
            if len(parts) == 3:
                m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
                dob_raw = f"{y}-{m}-{d}"
        fields["birthdate"] = dob_raw

    # 4. Gender
    gender_match = re.search(r'(?:Gender|Sex)\s*[:=\-]\s*(Female|Male|F|M)\b', raw_text, re.IGNORECASE)
    if gender_match:
        g_raw = gender_match.group(1).upper()
        fields["gender"] = "Female" if g_raw in ["FEMALE", "F"] else "Male"

    # 5. State
    state_match = re.search(r'(?:State|Patient\s*State)\s*[:=\-]\s*([A-Z]{2})\b', raw_text, re.IGNORECASE)
    if state_match:
        fields["state"] = state_match.group(1).upper()

    # 6. Payer / Insurance Name
    payer_match = re.search(r'(?:Insurance|Payer|Insurance\s*Company|Plan\s*Name)\s*[:=\-]\s*([A-Za-z0-9\s,\.\'-]+?)(?=\n|Member|ID|Policy|$)', raw_text, re.IGNORECASE)
    if payer_match:
        fields["payer_name"] = payer_match.group(1).strip()

    # 7. Requested HCPCS / CPT Code (5 alphanumeric, e.g. Q5107, 67028, 87641, J0897, 20610, J1740, J1745)
    hcpcs_label_match = re.search(r'(?:Requested\s*Service|HCPCS|HCPCS\s*Code|CPT|CPT\s*Code|Procedure\s*Code|Procedure)\s*[:=\-]\s*([A-Za-z0-9]{5})\b', raw_text, re.IGNORECASE)
    if hcpcs_label_match:
        fields["requested_hcpcs"] = hcpcs_label_match.group(1).upper()
    else:
        standalone_hcpcs = re.search(r'\b([J|Q|A|C|E|G|K|L|M|P|R|V]\d{4}|\d{5})\b', raw_text)
        if standalone_hcpcs:
            fields["requested_hcpcs"] = standalone_hcpcs.group(1).upper()

    # 8. Diagnosis ICD-10 Code (e.g. C18.8, C17.0, C33, M17.0, C79.51, K50.00, H40.10X1)
    icd10_label_match = re.search(r'(?:Diagnosis|ICD-10|ICD-10-CM|Diagnosis\s*Code)\s*[:=\-]\s*([A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?)\b', raw_text, re.IGNORECASE)
    if icd10_label_match:
        fields["diagnosis_icd10"] = icd10_label_match.group(1).upper()
    else:
        standalone_icd10 = re.search(r'\b([A-Z][0-9]{2}\.[0-9A-Z]{1,4})\b', raw_text)
        if standalone_icd10:
            fields["diagnosis_icd10"] = standalone_icd10.group(1).upper()

    # 9. Ordering Provider / Physician
    prov_match = re.search(r'(?:Ordering\s*Physician|Ordering\s*Provider|Physician|Provider)\s*[:=\-]\s*([A-Za-z0-9\s,\.\'-]+?)(?=\n|Order\s*Date|Date|NPI|Phone|$)', raw_text, re.IGNORECASE)
    if prov_match:
        fields["ordering_provider"] = prov_match.group(1).strip()
    else:
        dr_match = re.search(r'\b(Dr\.\s+[A-Za-z\s\.\'-]+)\b', raw_text)
        if dr_match:
            fields["ordering_provider"] = dr_match.group(1).strip()

    # 10. Signed Order Date
    date_match = re.search(r'(?:Order\s*Date|Signed\s*Order\s*Date|Signed\s*Date|Date\s*of\s*Order)\s*[:=\-]\s*(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', raw_text, re.IGNORECASE)
    if date_match:
        d_raw = date_match.group(1).strip()
        if "/" in d_raw:
            parts = d_raw.split("/")
            if len(parts) == 3:
                m, d, y = parts[0].zfill(2), parts[1].zfill(2), parts[2]
                d_raw = f"{y}-{m}-{d}"
        fields["signed_order_date"] = d_raw

    # 11. Urgency / Priority
    urgency_match = re.search(r'(?:Urgency|Priority)\s*[:=\-]\s*(EMERGENT|URGENT|HIGH|ROUTINE|LOW)\b', raw_text, re.IGNORECASE)
    if urgency_match:
        fields["urgency"] = urgency_match.group(1).upper()

    # 12. Clinical Rationale
    rationale_match = re.search(r'(?:Clinical\s*Rationale|Reason\s*for\s*Request|Medical\s*Necessity|Clinical\s*Reason|Rationale)\s*[:=\-]\s*([\s\S]+?)(?=\n\n[A-Z][a-z]+:|\Z)', raw_text, re.IGNORECASE)
    if rationale_match:
        rat_text = rationale_match.group(1).strip()
        fields["clinical_rationale"] = rat_text[:1500] # Limit to reasonable size

    return fields


def parse_and_extract_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Primary handler for PDF field extraction.
    
    Returns structured response dict:
    {
      "success": True/False,
      "extraction_method": "TEXT" / "OCR",
      "ocr_used": bool,
      "fields": {...},
      "fields_extracted": [...],
      "fields_missing": [...],
      "extraction_success": bool
    }
    """
    try:
        raw_text, method, ocr_used = extract_raw_text_from_pdf(pdf_bytes)

        if not raw_text or len(raw_text.strip()) == 0:
            return {
                "success": False,
                "extraction_method": method,
                "ocr_used": ocr_used,
                "error": "Unable to extract readable text or images from this document.",
                "fields": {},
                "fields_extracted": [],
                "fields_missing": [
                    "patient_id", "patient_name", "birthdate", "gender", "state",
                    "payer_name", "requested_hcpcs", "diagnosis_icd10",
                    "ordering_provider", "signed_order_date", "urgency", "clinical_rationale"
                ],
                "extraction_success": False
            }

        extracted_fields = extract_pa_fields_from_text(raw_text)

        fields_extracted = [k for k, v in extracted_fields.items() if v is not None and str(v).strip() != ""]
        fields_missing = [k for k, v in extracted_fields.items() if v is None or str(v).strip() == ""]

        return {
            "success": True,
            "extraction_method": method,
            "ocr_used": ocr_used,
            "fields": extracted_fields,
            "fields_extracted": fields_extracted,
            "fields_missing": fields_missing,
            "extraction_success": len(fields_extracted) > 0
        }

    except Exception as e:
        logger.error(f"Error extracting PDF text/fields: {e}")
        return {
            "success": False,
            "extraction_method": "FAILED",
            "ocr_used": False,
            "error": f"Document extraction failed: {str(e)}",
            "fields": {},
            "fields_extracted": [],
            "fields_missing": [],
            "extraction_success": False
        }
