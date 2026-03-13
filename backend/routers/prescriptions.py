"""
routers/prescriptions.py
=========================
POST /prescription/upload           — upload image → PrescriptoAI → store
GET  /prescription/{id}             — retrieve stored prescription
GET  /prescription/patient/{pid}    — list all prescriptions for a patient
"""

import uuid
from datetime import date
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from core.database import supabase
from services.prescription_ocr import process_prescription

router = APIRouter(prefix="/prescription", tags=["Prescriptions"])

ALLOWED_TYPES = {
    "image/jpeg", "image/jpg", "image/png",
    "image/webp", "image/tiff", "application/pdf",
}
MAX_SIZE_MB = 15


def _truncate(val: Optional[str], max_len: int = 1000) -> Optional[str]:
    """Truncate string values to prevent database VARCHAR overflow."""
    if val is None:
        return None
    return val[:max_len] if len(val) > max_len else val


@router.post("/upload")
async def upload_prescription(
    patient_id: str        = Form(...),
    image:      UploadFile = File(...),
):
    """
    Upload a prescription image.
    Calls PrescriptoAI API for extraction (handles English, Hindi, Marathi natively).
    Stores result in Supabase and returns structured data.
    """

    # ── Validate file ─────────────────────────────────────────────────────────
    content_type = image.content_type or ""
    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{content_type}'. Upload JPEG, PNG, WebP, or PDF.",
        )

    image_bytes = await image.read()
    size_mb     = len(image_bytes) / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max is {MAX_SIZE_MB} MB.",
        )

    # ── Call PrescriptoAI ─────────────────────────────────────────────────────
    parsed   = process_prescription(image_bytes, image.filename or "prescription.jpg")

    # ── Unpack result ─────────────────────────────────────────────────────────
    medicines    = parsed.get("medicines", [])
    med_names    = [m["name"] for m in medicines if m.get("name")]
    is_valid     = parsed.get("is_valid", False)
    ocr_success  = parsed.get("ocr_success", False)
    doctor_name  = parsed.get("doctor_name")
    doctor_lic   = parsed.get("doctor_license")
    clinic_name  = parsed.get("clinic_name")
    clinic_addr  = parsed.get("clinic_address")
    rx_date      = parsed.get("date")
    diagnosis    = parsed.get("diagnosis")
    vital_signs  = parsed.get("vital_signs", {})
    tests        = parsed.get("tests", [])
    notes        = parsed.get("notes")

    # ── Store in Supabase ─────────────────────────────────────────────────────
    # Truncate string fields to prevent VARCHAR(20) overflow errors
    prescription_id = str(uuid.uuid4())
    try:
        supabase.table("prescriptions").insert({
            "id":                prescription_id,
            "patient_id":        patient_id.upper(),
            "upload_date":       date.today().isoformat(),
            "filename":          _truncate(image.filename or "prescription.jpg", 255),
            "file_size_kb":      round(len(image_bytes) / 1024, 1),
            "raw_ocr_text":      _truncate(parsed.get("raw_text", ""), 5000),
            "ocr_success":       ocr_success,
            "is_valid":          is_valid,
            "confidence":        parsed.get("confidence", 0.0),
            # Patient
            "patient_name":      _truncate(parsed.get("patient_name"), 255),
            # Doctor
            "doctor_name":       _truncate(doctor_name, 255),
            "doctor_license":    _truncate(doctor_lic, 100),
            # Clinic
            "clinic_name":       _truncate(clinic_name, 255),
            # Prescription
            "prescription_date": _truncate(rx_date, 50),
            "diagnosis":         _truncate(diagnosis, 2000),
            "medicines":         medicines,
            "language":          _truncate(parsed.get("language", "auto"), 50),
            "error":             _truncate(parsed.get("error"), 1000),
        }).execute()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store prescription: {e}")

    # ── Build user-facing message ─────────────────────────────────────────────
    if not ocr_success:
        message = (
            "⚠️ We couldn't read this prescription. "
            "Please ensure the image is clear and well-lit, then try again."
        )
    elif not med_names:
        message = (
            "⚠️ Prescription uploaded but no medicine names were detected. "
            "A pharmacist will review it manually. You can still proceed."
        )
    else:
        med_list    = ", ".join(med_names[:3])
        if len(med_names) > 3:
            med_list += f" and {len(med_names) - 3} more"
        doctor_part = f" Prescribed by {doctor_name}." if doctor_name else ""
        clinic_part = f" ({clinic_name})" if clinic_name else ""
        message = (
            f"✅ Prescription verified.{doctor_part}{clinic_part} "
            f"Medicines found: {med_list}."
        )

    return {
        "prescription_id":   prescription_id,
        "is_valid":          is_valid,
        "ocr_success":       ocr_success,
        "confidence":        round(parsed.get("confidence", 0.0), 2),
        "language":          parsed.get("language", "auto"),
        "message":           message,

        # Structured data for frontend prescription preview card
        "patient_name":      parsed.get("patient_name"),
        "doctor_name":       doctor_name,
        "doctor_license":    doctor_lic,
        "doctor_specialty":  parsed.get("doctor_specialty"),
        "clinic_name":       clinic_name,
        "clinic_address":    clinic_addr,
        "prescription_date": rx_date,
        "diagnosis":         diagnosis,
        "vital_signs":       vital_signs,
        "tests":             tests,
        "notes":             notes,
        "medicines":         medicines,

        # True = allow prescription_uploaded=true in next chat request
        "use_in_chat":       is_valid and ocr_success,
    }


@router.get("/patient/{patient_id}")
def get_patient_prescriptions(patient_id: str, limit: int = 20):
    """List all prescriptions for a patient, newest first."""
    resp = (
        supabase.table("prescriptions")
        .select("id,upload_date,filename,is_valid,confidence,"
                "doctor_name,clinic_name,medicines,diagnosis,language")
        .eq("patient_id", patient_id.upper())
        .order("upload_date", desc=True)
        .limit(limit)
        .execute()
    )
    return {
        "patient_id":    patient_id.upper(),
        "count":         len(resp.data or []),
        "prescriptions": resp.data or [],
    }


@router.get("/{prescription_id}")
def get_prescription(prescription_id: str):
    """Get full details of a single prescription."""
    resp = (
        supabase.table("prescriptions")
        .select("*")
        .eq("id", prescription_id)
        .single()
        .execute()
    )
    if not resp.data:
        raise HTTPException(status_code=404, detail="Prescription not found.")
    return resp.data