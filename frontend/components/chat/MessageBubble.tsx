"use client";
// components/chat/MessageBubble.tsx

import { useState } from "react";
import { clsx } from "clsx";
import { XCircle, AlertTriangle } from "lucide-react";
import type { ChatMessage } from "@/types";
import { format } from "date-fns";
import CartReview        from "./CartReview";
import OrderConfirmed    from "./OrderConfirmed";
import RefillAlertBanner from "./RefillAlertBanner";
import type { RefillAlert } from "./RefillAlertBanner";

interface Props {
  message:       ChatMessage;
  paymentMethod: "cash_on_delivery" | "online_mock";
  onConfirm:     (messageId: string) => void;
  onReorder?:    (medicine: string) => void;
}

// ── Helper: Clean up AI response text ────────────────────────────────────────
function cleanAIResponse(text: string): string {
  if (!text) return "";
  // Remove **** highlighting markers
  let cleaned = text.replace(/\*\*\*/g, "");
  // Clean up double asterisks (bold markers) that might be unbalanced
  cleaned = cleaned.replace(/\*\*/g, "");
  // Clean up extra whitespace but preserve line breaks
  cleaned = cleaned.replace(/[ \t]+/g, " ");
  // Remove empty lines at start/end but preserve structure
  cleaned = cleaned.trim();
  return cleaned;
}

// ── Parse refill alerts out of message meta ───────────────────────────────────
function parseRefillAlerts(meta: any): RefillAlert[] {
  if (!meta?.refill_alert) return [];

  // Full patterns from predictive_agent (best case)
  const patterns = meta.refill_patterns as any[] | undefined;
  if (Array.isArray(patterns) && patterns.length > 0) {
    return patterns
      .filter(p => typeof p.days_until_refill === "number" && p.days_until_refill <= 30)
      .map(p => ({
        medicine:   p.medicine_name || p.medicine || "",
        days_until: p.days_until_refill ?? 7,
        refill_due: p.predicted_refill_date || p.refill_due || "",
      }));
  }

  // Fallback: single alert from top-level state fields
  if (meta.refill_medicine) {
    let days_until = 7;
    try {
      const due  = new Date(meta.refill_due_date);
      const now  = new Date();
      days_until = Math.round((due.getTime() - now.getTime()) / 86_400_000);
    } catch {}
    return [{
      medicine:   meta.refill_medicine,
      days_until,
      refill_due: meta.refill_due_date || "",
    }];
  }

  return [];
}

// ── Status badge ──────────────────────────────────────────────────────────────
function StatusBadge({ status }: { status?: string | null }) {
  if (!status || status === "approved") return null;

  const styles: Record<string, { cls: string; label: string; Icon: any }> = {
    rejected:            { cls: "text-red-400 bg-red-400/10 border-red-400/20",          label: "Rejected",      Icon: XCircle       },
    needs_clarification: { cls: "text-yellow-400 bg-yellow-400/10 border-yellow-400/20", label: "Clarifying...", Icon: AlertTriangle  },
    pending:             { cls: "text-blue-400 bg-blue-400/10 border-blue-400/20",       label: "Pending",       Icon: AlertTriangle  },
  };
  const s = styles[status];
  if (!s) return null;

  return (
    <div className="flex items-center justify-between w-full">
      <span className={clsx(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-mono font-medium",
        s.cls
      )}>
        <s.Icon size={11} /> {s.label}
      </span>
    </div>
  );
}


export default function MessageBubble({ message, paymentMethod, onConfirm, onReorder }: Props) {
  const isUser = message.role === "user";
  const meta   = message.meta as any;
  const [refillDismissed, setRefillDismissed] = useState(false);

  const refillAlerts   = isUser ? [] : parseRefillAlerts(meta);
  const showRefill     = refillAlerts.length > 0 && !refillDismissed;
  const hasStatusBadge = !isUser && meta?.order_status && meta.order_status !== "approved";

  function handleReorder(med: string) {
    onReorder?.(med);
  }

  // ── Rx avatar ─────────────────────────────────────────────────────────────
  const RxAvatar = (
    <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                    text-xs font-display font-bold mt-1 bg-surface-3 text-brand-400
                    border border-brand-400/20">
      Rx
    </div>
  );

  const UserAvatar = (
    <div className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center
                    text-xs font-display font-bold mt-1 bg-brand-600 text-white">
      P
    </div>
  );

  // ── Approved orders → cart / confirmation ─────────────────────────────────
  if (!isUser && meta?.order_status === "approved") {
    const pm = (meta.payment_method as "cash_on_delivery" | "online_mock") ?? paymentMethod;

    return (
      <div className="flex gap-3 animate-fade-up">
        {RxAvatar}
        <div className="flex flex-col gap-2 items-start max-w-[78%] w-full">

        {/* Agent text reply - clean up any AI formatting markers */}
          <div className="px-4 py-3 rounded-2xl rounded-tl-sm text-sm leading-relaxed
                          font-body whitespace-pre-wrap bg-surface-2 text-ink-primary border border-white/5">
            {cleanAIResponse(message.content)}
          </div>

          {/* Cart or confirmed card */}
          {message.cartState === "confirmed"
            ? <OrderConfirmed response={meta} paymentMethod={pm} />
            : <CartReview response={meta} paymentMethod={pm} onPlaceOrder={async () => onConfirm(message.id)} />
          }

          {/* Refill alert banner (shown after approved order) */}
          {showRefill && (
            <RefillAlertBanner
              alerts={refillAlerts}
              onReorder={handleReorder}
              onDismiss={() => setRefillDismissed(true)}
            />
          )}

          <span className="text-[10px] text-ink-muted font-mono px-1">
            {format(message.timestamp, "HH:mm")}
          </span>
        </div>
      </div>
    );
  }

  // ── Standard bubble ───────────────────────────────────────────────────────
  return (
    <div className={clsx("flex gap-3 animate-fade-up", isUser ? "flex-row-reverse" : "flex-row")}>
      {isUser ? UserAvatar : RxAvatar}

      <div className={clsx(
        "max-w-[78%] flex flex-col gap-2",
        isUser ? "items-end" : "items-start"
      )}>
        {/* Message text - clean up any AI formatting markers */}
        <div className={clsx(
          "px-4 py-3 rounded-2xl text-sm leading-relaxed font-body whitespace-pre-wrap",
          isUser
            ? "bg-brand-600 text-white rounded-tr-sm"
            : "bg-surface-2 text-ink-primary border border-white/5 rounded-tl-sm"
        )}>
          {cleanAIResponse(message.content)}
        </div>

        {/* Refill banner for non-approved messages (e.g. proactive scan after reorder) */}
        {showRefill && (
          <RefillAlertBanner
            alerts={refillAlerts}
            onReorder={handleReorder}
            onDismiss={() => setRefillDismissed(true)}
          />
        )}

        {/* Rejected / clarification badge */}
        {hasStatusBadge && (
          <div className="bg-surface-1 border border-white/5 rounded-xl px-3 py-2
                          text-xs w-full max-w-sm">
            <StatusBadge status={meta.order_status} />
          </div>
        )}

        <span className="text-[10px] text-ink-muted font-mono px-1">
          {format(message.timestamp, "HH:mm")}
        </span>
      </div>
    </div>
  );
}
