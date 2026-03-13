"use client";
// hooks/useChat.ts — sends full conversation history with every request

import { useState, useCallback, useRef, useEffect } from "react";
import { sendChatOrder, sendVoiceOrder, confirmOrder as confirmOrderApi } from "@/lib/api";
import type { ChatMessage } from "@/types";

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function useChat(patientId: string, patientEmail: string = "", patientName: string = "") {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);

  // Store patient email and name for order confirmations
  const patientEmailRef = useRef(patientEmail);
  const patientNameRef = useRef(patientName);
  
  // Update refs when props change
  useEffect(() => {
    patientEmailRef.current = patientEmail;
    patientNameRef.current = patientName;
  }, [patientEmail, patientName]);

  // Tracks the last triage suggestion so backend can resolve "yes" confirmations
  const triageSuggestionRef = useRef<string>("");
  // Tracks pending numbered product options so backend can resolve "1"/"2"/"3" replies
  const pendingProductOptionsRef = useRef<any[]>([]);
  // Tracks the product currently in context so PRODUCT_QUERY follow-ups work
  // ("how big is the package?" after an order summary is shown)
  const pendingProductRef = useRef<{ id: string | null; name: string | null }>({
    id: null, name: null,
  });

  // Keep a ref to always-current messages for use inside callbacks
  const messagesRef = useRef<ChatMessage[]>([]);
  messagesRef.current = messages;

  const addMessage = useCallback((msg: Omit<ChatMessage, "id" | "timestamp">) => {
    const full = { ...msg, id: uid(), timestamp: new Date() };
    setMessages(prev => {
      const updated = [...prev, full];
      messagesRef.current = updated;
      return updated;
    });
  }, []);

  // Build history array for the API — all turns except the current one being sent
  const buildHistory = useCallback((excludeLast = false) => {
    const msgs     = messagesRef.current;
    const relevant = excludeLast ? msgs.slice(0, -1) : msgs;
    return relevant
      .filter(m => m.role === "user" || m.role === "assistant")
      .map(m => ({
        role:    m.role as "user" | "assistant",
        content: m.content,
      }));
  }, []);

  // Inject persistent state markers into history so the stateless backend can
  // recover them on every request without needing server-side sessions
  const injectMarkers = useCallback((
    history: { role: "user" | "assistant"; content: string }[]
  ) => {
    // [PENDING_SUGGESTION] — lets classifier resolve "yes" / "sure" confirmations
    const suggestion = triageSuggestionRef.current;
    if (suggestion) {
      history.push({
        role:    "assistant",
        content: `[PENDING_SUGGESTION: ${suggestion}]`,
      });
    }

    // [PENDING_PRODUCT_OPTIONS] — lets agent resolve "1" / "2" / "3" selections
    const options = pendingProductOptionsRef.current;
    if (options.length > 0) {
      history.push({
        role:    "assistant",
        content: `[PENDING_PRODUCT_OPTIONS: ${JSON.stringify(options)}]`,
      });
    }

    // [PENDING_PRODUCT] — lets PRODUCT_QUERY handler know which product is in
    // context so follow-up questions ("how big is it?", "how much per pack?")
    // resolve correctly even though the agent state is stateless between calls.
    const pp = pendingProductRef.current;
    if (pp.id || pp.name) {
      history.push({
        role:    "assistant",
        content: `[PENDING_PRODUCT: ${pp.id ?? ""}|${pp.name ?? ""}]`,
      });
    }

    return history;
  }, []);

  // Update refs from API response — clear everything when an order is approved
  const updateRefs = useCallback((response: any) => {
    if (response.order_status === "approved") {
      // Order completed — wipe all pending state so next message starts fresh
      triageSuggestionRef.current      = "";
      pendingProductOptionsRef.current = [];
      pendingProductRef.current        = { id: null, name: null };
    } else {
      triageSuggestionRef.current      = response.triage_suggestion       ?? "";
      pendingProductOptionsRef.current = response.pending_product_options ?? [];
      // Track the product currently in context for PRODUCT_QUERY follow-ups
      if (response.product_id || response.product_name) {
        pendingProductRef.current = {
          id:   response.product_id   ? String(response.product_id) : null,
          name: response.product_name ?? null,
        };
      }
    }
  }, []);

  const sendMessage = useCallback(async (
    text:                string,
    prescriptionUploaded = false,
    rxMedicines:         any[] = [],
    paymentMethod        = "cash_on_delivery",
  ) => {
    if (!text.trim()) return;
    setError(null);

    // Add user message first so it's in history for the next turn
    addMessage({ role: "user", content: text });
    setLoading(true);

    try {
      const history = injectMarkers(buildHistory(true));

      const response = await sendChatOrder(
        patientId, text, prescriptionUploaded, rxMedicines, paymentMethod, history
      );

      updateRefs(response);

      addMessage({
        role:      "assistant",
        content:   response.final_response,
        meta:      response,
        cartState: response.order_status === "approved" ? "pending_review" : undefined,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Something went wrong. Please try again.";
      setError(msg);
      addMessage({ role: "assistant", content: `⚠️ ${msg}` });
    } finally {
      setLoading(false);
    }
  }, [patientId, addMessage, buildHistory, injectMarkers, updateRefs]);

  const sendVoice = useCallback(async (
    audioBlob:    Blob,
    paymentMethod = "cash_on_delivery",
  ) => {
    setError(null);
    setLoading(true);
    addMessage({ role: "user", content: "🎤 Voice message..." });

    try {
      const history  = injectMarkers(buildHistory(true));
      const response = await sendVoiceOrder(patientId, audioBlob, false, paymentMethod, history);

      updateRefs(response);

      // Update the placeholder voice message with the transcript
      setMessages(prev => {
        const updated     = [...prev];
        const lastUserIdx = [...updated].map((m, i) => ({ m, i }))
          .reverse()
          .find(({ m }) => m.role === "user")?.i;
        if (lastUserIdx !== undefined) {
          updated[lastUserIdx] = { ...updated[lastUserIdx], content: "🎤 Voice order" };
        }
        return updated;
      });

      addMessage({ role: "assistant", content: response.final_response, meta: response });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Voice transcription failed.";
      setError(msg);
      addMessage({ role: "assistant", content: `⚠️ ${msg}` });
    } finally {
      setLoading(false);
    }
  }, [patientId, addMessage, buildHistory, injectMarkers, updateRefs]);

  const confirmOrderCallback = useCallback(async (messageId: string) => {
    const msg = messagesRef.current.find(m => m.id === messageId);
    if (!msg) return;

    const meta = msg.meta as any;
    if (!meta) return;

    // Validate required fields before making API call
    if (!meta.product_id) {
      console.error("Cannot confirm order: missing product_id in message meta");
      setError("Unable to confirm order. Please try again.");
      return;
    }
    if (!meta.product_name) {
      console.error("Cannot confirm order: missing product_name in message meta");
      setError("Unable to confirm order. Please try again.");
      return;
    }
    if (!meta.quantity || meta.quantity < 1) {
      console.error("Cannot confirm order: missing or invalid quantity in message meta");
      setError("Unable to confirm order. Please try again.");
      return;
    }

    // ── Optimistic update: flip to confirmed immediately so UI feels instant ──
    // The API call happens in the background — user sees the confirmation card
    // right away without waiting for the network round trip.
    setMessages(prev =>
      prev.map(m =>
        m.id === messageId ? { ...m, cartState: "confirmed" as const } : m
      )
    );

    // Clear pending product context — order is done
    pendingProductRef.current = { id: null, name: null };

    // ── Fire-and-forget API call ───────────────────────────────────────────────
    // Return a promise that resolves when the API call completes so caller can refresh history
    // Pass patientEmail and patientName for order confirmation emails
    return confirmOrderApi(
      meta.product_id,
      meta.product_name,
      meta.quantity,
      patientId,
      meta.payment_method,
      meta.prescription_uploaded,
      meta.prescription_required ?? false,
      "chat",
      meta.dosage,
      patientEmailRef.current,
      patientNameRef.current
    ).then(() => {
      // Update the message with confirmed status
      setMessages(prev =>
        prev.map(m =>
          m.id === messageId 
            ? { ...m, meta: { ...m.meta, order_confirmed: true } as any, cartState: "confirmed" as const } 
            : m
        )
      );
    }).catch(err => {
      console.error("Failed to confirm order:", err);
      // Revert optimistic update on failure so user can retry
      setMessages(prev =>
        prev.map(m =>
          m.id === messageId ? { ...m, cartState: "pending_review" as const } : m
        )
      );
    });
  }, [patientId]);

  const clearChat = useCallback(() => {
    setMessages([]);
    messagesRef.current              = [];
    triageSuggestionRef.current      = "";
    pendingProductOptionsRef.current = [];
    pendingProductRef.current        = { id: null, name: null };
  }, []);

  return {
    messages,
    loading,
    error,
    sendMessage,
    sendVoice,
    clearChat,
    confirmOrder: confirmOrderCallback,
    addMessage,
  };
}