"use client";
// components/chat/PrescriptionUpload.tsx
// Upload a prescription image → OCR analysis → show parsed result
// Pass prescription_uploaded=true to chat when verified

import { useState, useRef } from "react";
import { Upload, FileCheck, AlertTriangle, X, Pill, User, Stethoscope } from "lucide-react";

interface Medicine {
  name:     string;
  quantity: string;
  dosage:   string;
  duration: string | null;
  notes:    string | null;
}

interface PrescriptionResult {
  prescription_id:   string;
  is_valid:          boolean;
  ocr_success:       boolean;
  confidence:        number;
  message:           string;
  patient_name:      string | null;
  doctor_name:       string | null;
  clinic_name:       string | null;
  prescription_date: string | null;
  diagnosis:         string | null;
  medicines:         Medicine[];
  use_in_chat:       boolean;
}

interface Props {
  patientId:        string;
  onVerified:       (prescriptionId: string, medicines: Medicine[]) => void; // call this to set prescription_uploaded=true with medicines
  onDismiss:        () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function PrescriptionUpload({ patientId, onVerified, onDismiss }: Props) {
  const [file,      setFile]      = useState<File | null>(null);
  const [preview,   setPreview]   = useState<string | null>(null);
  const [loading,   setLoading]   = useState(false);
  const [result,    setResult]    = useState<PrescriptionResult | null>(null);
  const [error,     setError]     = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setResult(null);
    setError(null);
    // Show image preview
    const reader = new FileReader();
    reader.onload = (ev) => setPreview(ev.target?.result as string);
    reader.readAsDataURL(f);
  }

  async function handleUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);

    try {
      const form = new FormData();
      form.append("patient_id", patientId);
      form.append("image", file);

      const resp = await fetch(`${API_BASE}/prescription/upload`, {
        method: "POST",
        body:   form,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail || "Upload failed");
      }

      const data: PrescriptionResult = await resp.json();
      setResult(data);

      // If valid, notify parent immediately
      if (data.use_in_chat) {
        onVerified(data.prescription_id, data.medicines);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-surface-1 border border-white/10 rounded-2xl p-4 w-full max-w-md">

      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <FileCheck size={16} className="text-brand-400" />
          <span className="text-sm font-semibold text-ink-primary font-display">
            Upload Prescription
          </span>
        </div>
        <button onClick={onDismiss} className="text-ink-muted hover:text-ink-primary transition-colors">
          <X size={14} />
        </button>
      </div>

      {/* Drop zone */}
      {!result && (
        <div
          onClick={() => inputRef.current?.click()}
          className="border-2 border-dashed border-white/10 rounded-xl p-6 text-center
                     cursor-pointer hover:border-brand-400/40 hover:bg-brand-400/5 transition-all"
        >
          {preview ? (
            <img src={preview} alt="prescription" className="max-h-40 mx-auto rounded-lg object-contain" />
          ) : (
            <>
              <Upload size={24} className="text-ink-muted mx-auto mb-2" />
              <p className="text-xs text-ink-muted font-body">
                Click to upload prescription<br />
                <span className="text-[10px]">JPEG, PNG, PDF — max 10MB</span>
              </p>
            </>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,application/pdf"
            className="hidden"
            onChange={handleFileChange}
          />
        </div>
      )}

      {/* Upload button */}
      {file && !result && (
        <button
          onClick={handleUpload}
          disabled={loading}
          className="mt-3 w-full py-2 rounded-xl bg-brand-400 text-black text-xs font-semibold
                     font-mono disabled:opacity-50 disabled:cursor-not-allowed
                     hover:bg-brand-300 transition-colors"
        >
          {loading ? "Analyzing prescription..." : "Analyze & Verify"}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="mt-3 flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-xl p-3">
          <AlertTriangle size={13} className="text-red-400 mt-0.5 shrink-0" />
          <p className="text-xs text-red-300 font-body">{error}</p>
        </div>
      )}

      {/* Result card */}
      {result && (
        <div className="space-y-3">

          {/* Status banner */}
          <div className={`flex items-start gap-2 rounded-xl p-3 border ${
            result.use_in_chat
              ? "bg-green-500/10 border-green-500/20"
              : "bg-yellow-500/10 border-yellow-500/20"
          }`}>
            {result.use_in_chat
              ? <FileCheck size={13} className="text-green-400 mt-0.5 shrink-0" />
              : <AlertTriangle size={13} className="text-yellow-400 mt-0.5 shrink-0" />
            }
            <p className={`text-xs font-body ${result.use_in_chat ? "text-green-300" : "text-yellow-300"}`}>
              {result.message}
            </p>
          </div>

          {/* Parsed fields */}
          {result.use_in_chat && (
            <div className="bg-surface-0 rounded-xl border border-white/5 divide-y divide-white/5">

              {/* Patient / Doctor */}
              {(result.patient_name || result.doctor_name) && (
                <div className="grid grid-cols-2 gap-2 p-3">
                  {result.patient_name && (
                    <div className="flex items-start gap-1.5">
                      <User size={11} className="text-ink-muted mt-0.5 shrink-0" />
                      <div>
                        <p className="text-[9px] text-ink-muted font-mono uppercase">Patient</p>
                        <p className="text-xs text-ink-primary font-body">{result.patient_name}</p>
                      </div>
                    </div>
                  )}
                  {result.doctor_name && (
                    <div className="flex items-start gap-1.5">
                      <Stethoscope size={11} className="text-ink-muted mt-0.5 shrink-0" />
                      <div>
                        <p className="text-[9px] text-ink-muted font-mono uppercase">Doctor</p>
                        <p className="text-xs text-ink-primary font-body">{result.doctor_name}</p>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Medicines */}
              {result.medicines.length > 0 && (
                <div className="p-3 space-y-2">
                  <p className="text-[9px] font-mono text-ink-muted uppercase flex items-center gap-1">
                    <Pill size={9} /> Medicines ({result.medicines.length})
                  </p>
                  {result.medicines.map((med, i) => (
                    <div key={i} className="bg-surface-1 rounded-lg p-2">
                      <p className="text-xs font-semibold text-brand-400 font-display">{med.name}</p>
                      <p className="text-[10px] text-ink-muted font-mono mt-0.5">
                        {[med.dosage, med.quantity, med.duration].filter(Boolean).join(" · ")}
                      </p>
                      {med.notes && (
                        <p className="text-[10px] text-ink-secondary font-body mt-0.5 italic">{med.notes}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2">
            {result.use_in_chat ? (
              <button
                onClick={onDismiss}
                className="flex-1 py-2 rounded-xl bg-brand-400 text-black text-xs font-semibold
                           font-mono hover:bg-brand-300 transition-colors"
              >
                ✅ Use this prescription
              </button>
            ) : (
              <button
                onClick={() => { setResult(null); setFile(null); setPreview(null); }}
                className="flex-1 py-2 rounded-xl bg-surface-2 text-ink-primary text-xs
                           font-mono hover:bg-surface-3 transition-colors border border-white/10"
              >
                Upload a different image
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
