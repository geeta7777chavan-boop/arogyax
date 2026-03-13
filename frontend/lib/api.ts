// lib/api.ts — typed wrappers around the FastAPI backend

import axios, { AxiosError } from "axios";
import type { Product, OrderResponse, RefillAlert, Decision, LowStockAlertsResponse } from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 90000,  // 90s — LLM pipeline (classifier + triage + safety + inventory) can take 15–60s
});

// Add response interceptor for better error handling
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.code === 'ERR_NETWORK' || error.code === 'ECONNREFUSED') {
      console.error(`[API Error] Cannot connect to backend at ${API_BASE_URL}. Is the server running?`);
    }
    return Promise.reject(error);
  }
);

type HistoryTurn = { role: "user" | "assistant"; content: string };

// ── Orders ────────────────────────────────────────────────────────────────────

export async function sendChatOrder(
  patientId:            string,
  message:              string,
  prescriptionUploaded  = false,
  rxMedicines:          any[]         = [],
  paymentMethod         = "cash_on_delivery",
  conversationHistory:  HistoryTurn[] = [],
  patientEmail          = "",
  patientName           = "",
): Promise<OrderResponse> {
  const { data } = await api.post<OrderResponse>("/order", {
    patient_id:            patientId,
    message,
    channel:               "chat",
    prescription_uploaded: prescriptionUploaded,
    rx_medicines:          rxMedicines,
    payment_method:        paymentMethod,
    conversation_history:  conversationHistory,
    patient_email:         patientEmail || undefined,
    patient_name:          patientName  || undefined,
  });
  return data;
}

export async function sendVoiceOrder(
  patientId:            string,
  audioBlob:            Blob,
  prescriptionUploaded  = false,
  paymentMethod         = "cash_on_delivery",
  conversationHistory:  HistoryTurn[] = [],
  patientEmail          = "",
  patientName           = "",
): Promise<OrderResponse> {
  const form = new FormData();
  form.append("patient_id",            patientId);
  form.append("prescription_uploaded", String(prescriptionUploaded));
  form.append("payment_method",        paymentMethod);
  form.append("conversation_history",  JSON.stringify(conversationHistory));
  if (patientEmail) form.append("patient_email", patientEmail);
  if (patientName)  form.append("patient_name",  patientName);
  form.append("audio", audioBlob, "recording.webm");

  const { data } = await api.post<OrderResponse>("/order/voice", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function confirmOrder(
  productId:            number,
  productName:          string,
  quantity:             number,
  patientId:            string,
  paymentMethod:        string,
  prescriptionUploaded: boolean,
  prescriptionRequired: boolean,
  channel:              string = "chat",
  dosage:               string = "",
  patientEmail:         string = "",
  patientName:          string = "",
): Promise<OrderResponse> {
  const { data } = await api.post<OrderResponse>("/order/confirm", {
    product_id:            productId,
    product_name:          productName,
    quantity,
    patient_id:            patientId,
    payment_method:        paymentMethod,
    prescription_uploaded: prescriptionUploaded,
    prescription_required: prescriptionRequired,
    channel,
    dosage,
    patient_email:         patientEmail || undefined,
    patient_name:          patientName  || undefined,
  });
  return data;
}

// ── Inventory ─────────────────────────────────────────────────────────────────

export async function getInventory(params?: {
  low_stock?: boolean; search?: string;
}): Promise<Product[]> {
  const { data } = await api.get<Product[]>("/inventory", { params });
  return data;
}

export async function getLowStockAlerts(threshold: number = 10): Promise<LowStockAlertsResponse> {
  const { data } = await api.get<LowStockAlertsResponse>("/inventory/low-stock-alerts", {
    params: { threshold },
  });
  return data;
}

export async function updateStock(productId: number, qty: number): Promise<void> {
  await api.patch(`/inventory/${productId}/stock`, { stock_quantity: qty });
}

// ── Refill Alerts ─────────────────────────────────────────────────────────────

export async function getRefillAlerts(status = "pending") {
  const { data } = await api.get("/refill-alerts", { params: { status } });
  return data;
}

export async function triggerRefillScan() {
  const { data } = await api.post("/refill-alerts/scan");
  return data;
}

export async function dismissAlert(alertId: string): Promise<void> {
  await api.patch(`/refill-alerts/${alertId}`, null, { params: { status: "dismissed" } });
}

// ── Decisions ─────────────────────────────────────────────────────────────────

export async function getDecisions(params?: {
  agent?: string; action?: string; limit?: number;
}) {
  const { data } = await api.get("/decisions", { params });
  return data;
}

// ── History ───────────────────────────────────────────────────────────────────

export async function getPatientHistory(patientId: string) {
  const { data } = await api.get(`/history/${patientId}`);
  return data;
}

export async function getPatientAnalysis(patientId: string) {
  const { data } = await api.get(`/history/${patientId}/analysis`);
  return data;
}

// ── Prescription check ────────────────────────────────────────────────────────

export async function checkPrescription(productId: number) {
  const { data } = await api.post("/prescription-check", { product_id: productId });
  return data;
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export async function getAnalyticsSummary() {
  const { data } = await api.get("/history/analytics/summary");
  return data;
}
