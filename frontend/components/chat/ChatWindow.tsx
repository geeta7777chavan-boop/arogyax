"use client";
// components/chat/ChatWindow.tsx

import { useState, useRef, useEffect, FormEvent } from "react";
import {
  Send, Loader2, Pill, Trash2, Banknote, CreditCard,
  History, MessageSquare, FileCheck, Upload, Bell, X, ChevronDown, ChevronUp,
} from "lucide-react";
import { useChat } from "@/hooks/useChat";
import MessageBubble from "./MessageBubble";
import VoiceButton from "./VoiceButton";
import OrderHistory from "./OrderHistory";
import PrescriptionUpload from "./PrescriptionUpload";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const SUGGESTIONS = [
  "I need 2 boxes of NORSAN Omega-3",
  "Can I get Paracetamol 500mg?",
  "Order Panthenol Spray for me",
  "Do I need a prescription for Ramipril?",
];

type PaymentMethod = "cash_on_delivery" | "online_mock";
type PanelTab      = "chat" | "history";

interface RxMedicine {
  name:      string;
  generic?:  string;
  dosage?:   string;
  quantity?: string;
  notes:     string | null;
}

interface RefillAlert {
  medicine_name:    string;
  product_id:       number;
  last_purchase:    string;
  predicted_runout: string;
  days_until:       number;
  urgency:          "overdue" | "today" | "urgent" | "soon" | "ok";
  is_rx:            boolean;
  dosage_frequency: string;
  friendly_message: string;
}

// ── Refill Banner component (inline) ─────────────────────────────────────────
function RefillBanner({
  alerts, urgency, onRefill, onDismiss,
}: {
  alerts:    RefillAlert[];
  urgency:   "urgent" | "soon";
  onRefill:  (name: string) => void;
  onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(true);

  const isUrgent = urgency === "urgent";
  const bg    = isUrgent ? "bg-red-950/40 border-red-500/30"  : "bg-amber-950/40 border-amber-500/30";
  const icon  = isUrgent ? "🔴" : "🟡";
  const title = isUrgent ? "Medicines running low!" : "Upcoming refills";
  const badge = isUrgent ? "bg-red-500/20 text-red-300" : "bg-amber-500/20 text-amber-300";
  const btn   = isUrgent ? "bg-red-500 hover:bg-red-600" : "bg-amber-500 hover:bg-amber-600";

  function shortName(n: string) { return n.split(",")[0].trim(); }
  function daysLabel(d: number) {
    if (d < 0)  return `${Math.abs(d)}d overdue`;
    if (d === 0) return "today!";
    return `${d}d left`;
  }

  return (
    <div className={`mx-3 mt-2 mb-1 rounded-xl border overflow-hidden ${bg}`}>
      <div
        className="flex items-center justify-between px-4 py-2.5 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <Bell size={14} className={isUrgent ? "text-red-400" : "text-amber-400"} />
          <span className="font-semibold text-sm text-white">{icon} {title}</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-mono ${badge}`}>
            {alerts.length} med{alerts.length > 1 ? "s" : ""}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {expanded ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
          <button
            onClick={(e) => { e.stopPropagation(); onDismiss(); }}
            className="text-gray-500 hover:text-gray-300 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="border-t border-white/10">
          {alerts.map((alert, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5 border-b border-white/5 last:border-0">
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{shortName(alert.medicine_name)}</p>
                <p className="text-xs text-gray-400 mt-0.5 font-mono">
                  {alert.dosage_frequency} · {daysLabel(alert.days_until)}
                  {alert.is_rx && (
                    <span className="ml-1.5 bg-purple-500/20 text-purple-300 px-1.5 py-0.5 rounded text-xs">Rx</span>
                  )}
                </p>
              </div>
              <button
                onClick={() => onRefill(shortName(alert.medicine_name))}
                className={`ml-3 shrink-0 ${btn} text-white text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors`}
              >
                Refill now
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main ChatWindow ───────────────────────────────────────────────────────────
interface ChatWindowProps {
  patientId:    string;
  patientEmail: string;
  patientName:  string;
}

export default function ChatWindow({ patientId, patientEmail, patientName }: ChatWindowProps) {
  const { messages, loading, sendMessage, sendVoice, clearChat, confirmOrder, addMessage } =
    useChat(patientId, patientEmail, patientName);

  const [input,            setInput]            = useState("");
  const [rxUploaded,       setRxUploaded]       = useState(false);
  const [rxPrescId,        setRxPrescId]        = useState<string | null>(null);
  const [rxMedicines,      setRxMedicines]      = useState<RxMedicine[]>([]);
  const [paymentMethod,    setPaymentMethod]    = useState<PaymentMethod>("cash_on_delivery");
  const [activeTab,        setActiveTab]        = useState<PanelTab>("chat");
  const [showRxUpload,     setShowRxUpload]     = useState(false);
  const [historyRefresh,   setHistoryRefresh]   = useState(0);
  const [refillAlerts,     setRefillAlerts]     = useState<RefillAlert[]>([]);
  const [refillUrgency,    setRefillUrgency]    = useState<"urgent" | "soon">("soon");
  const [showRefillBanner, setShowRefillBanner] = useState(false);
  const [refillChecked,    setRefillChecked]    = useState(false);
  const [pendingRefillSuggestions, setPendingRefillSuggestions] = useState<RefillAlert[]>([]);

  const bottomRef    = useRef<HTMLDivElement>(null);
  const voiceResetRef = useRef<(() => void) | null>(null);

  // ── Proactive refill check on session open ────────────────────────────────
  useEffect(() => {
    if (refillChecked) return;
    setRefillChecked(true);
    let isMounted = true;

    fetch(`${API_BASE}/refill-alerts/check/${patientId}`)
      .then(r => r.json())
      .then(data => {
        if (!isMounted) return;
        if (data.has_alerts && data.alerts?.length > 0) {
          setRefillAlerts(data.alerts);
          setRefillUrgency(data.urgency);
          setShowRefillBanner(true);
          const greetingAlreadyInjected = messages.some(
            m => m.role === "assistant" && m.content?.includes("Before we start")
          );
          if (messages.length === 0 && data.greeting && !greetingAlreadyInjected) {
            setPendingRefillSuggestions(data.alerts);
            injectProactiveGreeting(data.greeting);
          }
        }
      })
      .catch(() => {});

    return () => { isMounted = false; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const isPositiveRefillConfirmation = (text: string): boolean => {
    const positivePatterns = [
      /^yes$/i, /^yes,/i, /^yeah$/i, /^sure$/i,
      /^ok$/i, /^okay$/i, /^please$/i, /^refill$/i,
      /^yes refill/i, /^refill both/i, /^yes both/i,
      /^order both/i, /^get both/i,
    ];
    return positivePatterns.some(p => p.test(text.toLowerCase().trim()));
  };

  function injectProactiveGreeting(text: string) {
    addMessage({
      role:    "assistant",
      content: text,
      meta:    { intent: "PROACTIVE_REFILL", safety_approved: null, order_status: null } as any,
    });
  }

  useEffect(() => {
    if (activeTab === "chat") {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading, activeTab]);

  useEffect(() => {
    if (messages.length === 0) return;
    const last = messages[messages.length - 1];
    if (last.role !== "assistant") return;
    const meta = last.meta as any;

    if (meta?.prescription_rejected === true) setShowRxUpload(true);

    if (meta?.order_status === "approved" || meta?.safety_approved === true) {
      setShowRxUpload(false);
      setHistoryRefresh(prev => prev + 1);
      setShowRefillBanner(false);
      setRefillAlerts([]);
      // Reset voice button after successful order
      voiceResetRef.current?.();
    }
  }, [messages]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userText = input.trim();

    if (pendingRefillSuggestions.length > 0 && isPositiveRefillConfirmation(userText)) {
      setPendingRefillSuggestions([]);
      setShowRefillBanner(false);
      const medicineNames = pendingRefillSuggestions.map(a => a.medicine_name.split(",")[0].trim());
      sendMessage(`I need to order ${medicineNames.join(" and ")}`, rxUploaded, rxMedicines, paymentMethod);
      setInput("");
      setActiveTab("chat");
      return;
    }

    setShowRxUpload(false);
    sendMessage(userText, rxUploaded, rxMedicines, paymentMethod);
    setInput("");
    setActiveTab("chat");
  }

  function handleRefillNow(medicineName: string) {
    setShowRefillBanner(false);
    setRefillAlerts([]);
    setPendingRefillSuggestions([]);
    sendMessage(`I need to order ${medicineName}`, rxUploaded, rxMedicines, paymentMethod);
    setActiveTab("chat");
  }

  function handleReorder(medicineName: string) {
    setInput(`I'd like to reorder ${medicineName}`);
    setActiveTab("chat");
  }

  function handlePrescriptionVerified(prescriptionId: string, medicines: RxMedicine[]) {
    setRxUploaded(true);
    setRxPrescId(prescriptionId);
    setRxMedicines(medicines);
    setShowRxUpload(false);

    let retryMsg: string | null = null;
    for (let i = messages.length - 1; i >= 1; i--) {
      const msg  = messages[i];
      const meta = (msg as any).meta ?? {};
      if (msg.role === "assistant" && meta?.prescription_rejected === true) {
        const prev = messages[i - 1];
        if (prev?.role === "user") retryMsg = prev.content;
        break;
      }
    }
    if (retryMsg) {
      setTimeout(() => sendMessage(retryMsg!, true, medicines, paymentMethod), 600);
    }
  }

  function handleClearChat() {
    clearChat();
    setRxUploaded(false);
    setRxPrescId(null);
    setRxMedicines([]);
    setShowRxUpload(false);
    setInput("");
    setActiveTab("chat");
  }

  function handleClearRx() {
    setRxUploaded(false);
    setRxPrescId(null);
    setRxMedicines([]);
    setShowRxUpload(true);
  }

  function handleConfirmOrder(messageId: string) {
    confirmOrder(messageId).then(() => {
      setHistoryRefresh(prev => prev + 1);
    }).catch(err => {
      console.error("Order confirmation failed:", err);
    });
  }

  function handleVoiceAudio(blob: Blob) {
    // sendVoice(audioBlob, paymentMethod) — correct signature from useChat
    sendVoice(blob, paymentMethod).finally(() => {
      voiceResetRef.current?.();
    });
  }

  return (
    <div className="flex flex-col h-full bg-surface-0 rounded-2xl border border-white/5 overflow-hidden">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-white/5 bg-surface-1">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-brand-600/20 border border-brand-400/30 flex items-center justify-center">
            <Pill size={16} className="text-brand-400" />
          </div>
          <div>
            <h2 className="font-display font-semibold text-ink-primary text-sm">ArogyaX Assistant</h2>
            <p className="text-[11px] text-ink-muted font-mono">Patient: {patientId}</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <button
              onClick={() => setShowRefillBanner(prev => !prev)}
              className={clsx(
                "p-2 transition-colors rounded-lg",
                refillAlerts.length > 0
                  ? "text-amber-400 hover:text-amber-300 hover:bg-amber-400/10"
                  : "text-ink-muted hover:text-ink-secondary hover:bg-surface-2"
              )}
              title={refillAlerts.length > 0 ? "Refill reminders" : "No refill alerts"}
            >
              <Bell size={14} />
              {refillAlerts.length > 0 && (
                <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {refillAlerts.length}
                </span>
              )}
            </button>
            {showRefillBanner && refillAlerts.length === 0 && (
              <div className="absolute right-0 top-full mt-2 w-48 bg-surface-2 border border-white/10 rounded-lg shadow-lg p-3 z-50">
                <p className="text-xs text-ink-muted font-body text-center">No refill alerts</p>
              </div>
            )}
          </div>
          <span className="flex items-center gap-1.5 text-[11px] text-brand-400 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse-slow" />
            online
          </span>
          <button
            onClick={handleClearChat}
            className="p-2 text-ink-muted hover:text-red-400 transition-colors rounded-lg hover:bg-red-400/10"
            title="Clear chat"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* ── Tab bar ─────────────────────────────────────────────────────────── */}
      <div className="flex border-b border-white/5 bg-surface-1">
        <button
          onClick={() => setActiveTab("chat")}
          className={clsx(
            "flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-mono font-medium transition-colors",
            activeTab === "chat" ? "text-brand-400 border-b-2 border-brand-400" : "text-ink-muted hover:text-ink-secondary"
          )}
        >
          <MessageSquare size={12} /> Chat
        </button>
        <button
          onClick={() => { setActiveTab("history"); setHistoryRefresh(prev => prev + 1); }}
          className={clsx(
            "flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-mono font-medium transition-colors",
            activeTab === "history" ? "text-brand-400 border-b-2 border-brand-400" : "text-ink-muted hover:text-ink-secondary"
          )}
        >
          <History size={12} /> Order History
        </button>
      </div>

      {/* ── Refill Banner ────────────────────────────────────────────────────── */}
      {activeTab === "chat" && showRefillBanner && refillAlerts.length > 0 && (
        <RefillBanner
          alerts    = {refillAlerts}
          urgency   = {refillUrgency}
          onRefill  = {handleRefillNow}
          onDismiss = {() => setShowRefillBanner(false)}
        />
      )}

      {/* ── History panel ───────────────────────────────────────────────────── */}
      {activeTab === "history" && (
        <div className="flex-1 overflow-hidden">
          <OrderHistory patientId={patientId} onReorder={handleReorder} refreshKey={historyRefresh} />
        </div>
      )}

      {/* ── Chat panel ──────────────────────────────────────────────────────── */}
      {activeTab === "chat" && (
        <>
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin">

            {messages.length === 0 && !showRefillBanner && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div>
                  <p className="font-display text-3xl text-ink-primary font-semibold">
                    Welcome{patientName ? `, ${patientName.split(" ")[0]}` : ""}! 👋
                  </p>
                  <p className="font-display text-xl text-ink-primary font-semibold mt-3">
                    How can I help you today?
                  </p>
                  <p className="text-ink-secondary text-sm font-body mt-2">
                    Ask me for any medicine by name, dose, or description — or use your voice.
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-2 w-full max-w-md mt-6">
                  {SUGGESTIONS.map(s => (
                    <button
                      key={s}
                      onClick={() => sendMessage(s, rxUploaded, rxMedicines, paymentMethod)}
                      className="px-3 py-2.5 text-left text-xs text-ink-secondary bg-surface-2
                                 hover:bg-surface-3 border border-white/5 hover:border-brand-400/30
                                 rounded-xl transition-all font-body"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(msg => (
              <MessageBubble
                key={msg.id}
                message={msg}
                paymentMethod={paymentMethod}
                onConfirm={handleConfirmOrder}
                onReorder={(med) => {
                  setInput(`I'd like to reorder ${med}`);
                  setTimeout(() => {
                    sendMessage(`I'd like to reorder ${med}`, rxUploaded, rxMedicines, paymentMethod);
                    setInput("");
                  }, 300);
                }}
              />
            ))}

            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-surface-3 border border-brand-400/20
                                flex items-center justify-center text-xs font-display font-bold text-brand-400">
                  Rx
                </div>
                <div className="bg-surface-2 border border-white/5 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-brand-400" />
                  <span className="text-xs text-ink-secondary font-mono">Agents processing...</span>
                </div>
              </div>
            )}

            {showRxUpload && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-surface-3 border border-brand-400/20
                                flex items-center justify-center text-xs font-display font-bold
                                text-brand-400 shrink-0 mt-1">
                  Rx
                </div>
                <div className="flex-1 max-w-sm">
                  <PrescriptionUpload
                    patientId={patientId}
                    onVerified={handlePrescriptionVerified}
                    onDismiss={() => setShowRxUpload(false)}
                  />
                </div>
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* ── Options bar ──────────────────────────────────────────────────── */}
          <div className="px-5 py-3 border-t border-white/5 bg-surface-1 space-y-2">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-ink-muted font-mono w-24 shrink-0">Payment:</span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPaymentMethod("cash_on_delivery")}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-body border transition-all",
                    paymentMethod === "cash_on_delivery"
                      ? "bg-brand-600 border-brand-500 text-white"
                      : "bg-surface-2 border-white/5 text-ink-secondary hover:border-brand-400/30"
                  )}
                >
                  <Banknote size={12} /> Cash on Delivery
                </button>
                <button
                  onClick={() => setPaymentMethod("online_mock")}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-body border transition-all",
                    paymentMethod === "online_mock"
                      ? "bg-brand-600 border-brand-500 text-white"
                      : "bg-surface-2 border-white/5 text-ink-secondary hover:border-brand-400/30"
                  )}
                >
                  <CreditCard size={12} /> Online (Mock)
                </button>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[11px] text-ink-muted font-mono w-24 shrink-0">Prescription:</span>
              {rxUploaded ? (
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs
                                  bg-green-500/10 border border-green-500/20 text-green-400 font-mono">
                    <FileCheck size={11} /> Verified
                    {rxMedicines.length > 0 && (
                      <span className="ml-1 opacity-60">
                        ({rxMedicines.length} med{rxMedicines.length > 1 ? "s" : ""})
                      </span>
                    )}
                  </div>
                  <button
                    onClick={handleClearRx}
                    className="text-[10px] text-ink-muted hover:text-ink-secondary font-mono underline underline-offset-2 transition-colors"
                  >
                    Change
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowRxUpload(prev => !prev)}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-body border transition-all",
                    showRxUpload
                      ? "bg-brand-600 border-brand-500 text-white"
                      : "bg-surface-2 border-white/5 text-ink-secondary hover:border-brand-400/30"
                  )}
                >
                  <Upload size={11} /> Upload Prescription
                </button>
              )}
            </div>
          </div>

          {/* ── Input bar ────────────────────────────────────────────────────── */}
          <form onSubmit={handleSubmit} className="px-4 pb-4 pt-2">
            <div className="flex items-end gap-2 bg-surface-2 border border-white/5
                            focus-within:border-brand-400/40 rounded-2xl p-2 transition-all">
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSubmit(e as any);
                  }
                }}
                placeholder="Type a medicine name or describe what you need..."
                rows={1}
                className="flex-1 bg-transparent text-sm text-ink-primary placeholder-ink-muted
                           font-body resize-none focus:outline-none px-2 py-1.5 min-h-[36] max-h-[120]"
              />
              <div className="flex items-center gap-2 shrink-0">
                <VoiceButton
                  onAudioReady={handleVoiceAudio}
                  onReady={(reset) => { voiceResetRef.current = reset; }}
                  disabled={loading}
                />
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className={clsx(
                    "w-11 h-11 rounded-xl flex items-center justify-center transition-all",
                    input.trim() && !loading
                      ? "bg-brand-500 hover:bg-brand-600 text-white shadow-lg shadow-brand-500/30"
                      : "bg-surface-3 text-ink-muted cursor-not-allowed"
                  )}
                >
                  {loading
                    ? <Loader2 size={16} className="animate-spin" />
                    : <Send size={16} />
                  }
                </button>
              </div>
            </div>
          </form>
        </>
      )}
    </div>
  );
}