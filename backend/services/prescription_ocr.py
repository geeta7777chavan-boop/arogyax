"""
services/prescription_ocr.py
==============================
PrescriptoAI-powered prescription analysis.
NO PaddleOCR. NO local ML models.

Confirmed working:
  field name : "prescription"
  auth header: "Authorization: Bearer <key>"
  endpoint   : POST /api/v1/prescription/extract

Real response schema (from Shraddha Clinic test):
{
  "success": true,
  "data": {
    "patient":  { name, age, gender, address, phone },
    "doctor":   { name, qualification, specialization, registrationNumber, phone, email },
    "clinic":   { name, address, phone, email, website },
    "prescription": {
      "date", "prescriptionId", "diagnosis",
      "vitalSigns": { bloodPressure, temperature, pulse, weight },
      "medications": [ { name, genericName, dosage, frequency, duration, instructions, notes } ],
      "tests": [],
      "notes", "followUp"
    }
  },
  "type": "standard",
  "metadata": { filename, fileSize, mimeType }
}
"""

import sys
import json
import httpx
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.config import settings

EXTRACT_URL  = "https://www.prescriptoai.com/api/v1/prescription/extract"
VALIDATE_URL = "https://www.prescriptoai.com/api/v1/prescription/validate"
TIMEOUT      = 45   # PrescriptoAI can be slow on first request


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.PRESCRIPTO_API_KEY}",
        "Accept":        "application/json",
    }


def _extract(image_bytes: bytes, filename: str) -> dict:
    """POST /api/v1/prescription/extract — field name is 'prescription'."""
    ext  = Path(filename).suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png",  ".pdf":  "application/pdf"}.get(ext, "image/jpeg")
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(
                EXTRACT_URL,
                headers=_headers(),
                files={"prescription": (filename, image_bytes, mime)},
            )
        print(f"[PrescriptoAI] extract → HTTP {resp.status_code}")
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        try:
            err = resp.json().get("error") or resp.json().get("message") or resp.text[:200]
        except Exception:
            err = resp.text[:200]
        return {"success": False, "error": f"HTTP {resp.status_code}: {err}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _validate(medicine_names: list) -> dict:
    """POST /api/v1/prescription/validate."""
    if not medicine_names:
        return {"success": True, "data": {}}
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                VALIDATE_URL,
                headers={**_headers(), "Content-Type": "application/json"},
                json={"medicines": medicine_names},
            )
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        return {"success": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_medications(raw: list) -> list:
    """
    Normalize PrescriptoAI medication objects.
    Each item: { name, genericName, dosage, frequency, duration, instructions, notes }
    """
    result = []
    for m in raw:
        if not isinstance(m, dict):
            continue
        name = m.get("name") or m.get("genericName")
        if not name:
            continue
        result.append({
            "name":        name,
            "generic":     m.get("genericName"),
            "dosage":      m.get("dosage"),
            "frequency":   m.get("frequency"),
            "duration":    m.get("duration"),
            "notes":       m.get("instructions") or m.get("notes"),
            "validated":   None,   # filled by validate step
        })
    return result


def process_prescription(image_bytes: bytes, filename: str = "prescription.jpg") -> dict:
    """
    Full pipeline: upload → extract → validate → normalize.
    Return shape matches what router_prescriptions.py expects.
    """
    print(f"\n[PrescriptoAI] Processing '{filename}' ({len(image_bytes)//1024} KB)...")

    api_key = getattr(settings, "PRESCRIPTO_API_KEY", "")
    if not api_key:
        return _fail("PRESCRIPTO_API_KEY not set in .env")

    # ── Step 1: Extract ───────────────────────────────────────────────────────
    result = _extract(image_bytes, filename)
    if not result["success"]:
        return _fail(result["error"])

    api      = result["data"]                        # full response
    data     = api.get("data", {})                   # unwrap "data" key
    rx       = data.get("prescription", {})          # prescription sub-object
    patient  = data.get("patient",  {})
    doctor   = data.get("doctor",   {})
    clinic   = data.get("clinic",   {})

    # ── Step 2: Parse medications ─────────────────────────────────────────────
    raw_meds  = rx.get("medications") or []
    medicines = _parse_medications(raw_meds)
    med_names = [m["name"] for m in medicines]

    print(f"[PrescriptoAI] ✅ {len(medicines)} medicines: {med_names}")
    print(f"[PrescriptoAI]    Doctor : {doctor.get('name')} ({doctor.get('registrationNumber')})")
    print(f"[PrescriptoAI]    Clinic : {clinic.get('name')}")
    print(f"[PrescriptoAI]    Date   : {rx.get('date')}")

    # ── Step 3: Validate medicines ────────────────────────────────────────────
    if med_names:
        val = _validate(med_names)
        if val["success"]:
            val_results = (val.get("data") or {}).get("results") or []
            for i, vr in enumerate(val_results):
                if i < len(medicines):
                    medicines[i]["validated"] = vr.get("valid", True)

    # ── Step 4: Build unified result ──────────────────────────────────────────
    is_valid   = len(medicines) > 0
    confidence = 0.95 if medicines else 0.4

    return {
        # Patient
        "patient_name":    patient.get("name") or None,
        "patient_age":     patient.get("age")  or None,
        "patient_gender":  patient.get("gender") or None,
        "patient_phone":   patient.get("phone") or None,

        # Doctor
        "doctor_name":     doctor.get("name"),
        "doctor_license":  doctor.get("registrationNumber"),
        "doctor_specialty":doctor.get("specialization"),

        # Clinic
        "clinic_name":     clinic.get("name"),
        "clinic_address":  clinic.get("address"),

        # Prescription
        "date":            rx.get("date"),
        "diagnosis":       rx.get("diagnosis") or None,
        "notes":           rx.get("notes") or None,
        "follow_up":       rx.get("followUp") or None,
        "vital_signs":     rx.get("vitalSigns") or {},
        "tests":           rx.get("tests") or [],

        # Medicines
        "medicines":       medicines,
        "is_valid":        is_valid,
        "confidence":      confidence,
        "language":        "auto",     # PrescriptoAI handles multilingual natively

        # Raw for audit
        "ocr_success":     True,
        "raw_text":        json.dumps(data, ensure_ascii=False)[:3000],
        "error":           None,
    }


def _fail(msg: str) -> dict:
    print(f"[PrescriptoAI] ❌ {msg}")
    return {
        "patient_name": None, "patient_age": None, "patient_gender": None,
        "patient_phone": None, "doctor_name": None, "doctor_license": None,
        "doctor_specialty": None, "clinic_name": None, "clinic_address": None,
        "date": None, "diagnosis": None, "notes": None, "follow_up": None,
        "vital_signs": {}, "tests": [], "medicines": [],
        "is_valid": False, "confidence": 0.0, "language": "unknown",
        "ocr_success": False, "raw_text": "", "error": msg,
    }