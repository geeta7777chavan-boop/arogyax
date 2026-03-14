"use client";
// components/chat/OrderConfirmed.tsx
// Shown after user clicks "Place Order" — full confirmation card

import { CheckCircle, Package, ExternalLink, Mail } from "lucide-react";
import type { OrderResponse } from "@/types";
import { format, addDays } from "date-fns";

interface Props {
  response:      OrderResponse;
  paymentMethod: "cash_on_delivery" | "online_mock";
}

export default function OrderConfirmed({ response, paymentMethod }: Props) {
  const medicine    = response.product_name ?? "Medicine";
  const qty         = response.quantity     ?? 1;
  const totalPrice  = response.total_price  ?? null;
  const orderId     = response.order_id;
  const dosage      = response.dosage       ?? null;
  const deliveryDate = format(addDays(new Date(), 2), "EEEE, MMM d");

  const shortId = orderId
    ? "ORD-" + orderId.replace(/-/g, "").toUpperCase().slice(0, 8)
    : null;

  return (
    <div className="w-full max-w-sm rounded-2xl border border-brand-400/20 bg-brand-400/5 overflow-hidden shadow-lg">

      {/* Header */}
      <div className="px-4 py-4 flex items-center gap-3 border-b border-brand-400/10">
        <div className="w-10 h-10 rounded-full bg-brand-400/15 border border-brand-400/30 flex items-center justify-center shrink-0">
          <CheckCircle size={20} className="text-brand-400" />
        </div>
        <div>
          <p className="text-sm font-display font-bold text-ink-primary">Order Confirmed!</p>
          {shortId && (
            <p className="text-xs text-brand-400 font-mono">#{shortId}</p>
          )}
        </div>
        {response.langfuse_trace_id && (
          <a
            href="https://cloud.langfuse.com"
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto flex items-center gap-1 text-[10px] text-ink-muted hover:text-brand-400 transition-colors font-mono"
          >
            <ExternalLink size={10} /> trace
          </a>
        )}
      </div>

      {/* Item row */}
      <div className="px-4 py-4 bg-surface-0/40 mx-3 mt-3 rounded-xl border border-white/5">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-base font-bold text-ink-primary font-display">
              {medicine}
            </p>
            <p className="text-sm text-ink-muted font-mono mt-1.5">
              {dosage && `${dosage} · `}Quantity: {qty}
            </p>
          </div>
          {totalPrice !== null && (
            <p className="text-base font-bold text-ink-primary font-mono">
              €{totalPrice.toFixed(2)}
            </p>
          )}
        </div>
      </div>

      {/* Delivery */}
      <div className="px-4 py-3 flex items-center gap-2">
        <Package size={13} className="text-brand-400 shrink-0" />
        <p className="text-xs text-ink-secondary font-mono">
          Estimated delivery: <span className="text-brand-400 font-semibold">{deliveryDate}</span>
        </p>
      </div>

      {/* Status badges */}
      <div className="px-4 pb-3 flex flex-wrap gap-2">
        {["Inventory Updated", "Warehouse Notified", "Confirmation Sent"].map(label => (
          <span
            key={label}
            className="flex items-center gap-1 text-[10px] font-mono text-brand-400 bg-brand-400/10 border border-brand-400/20 rounded-full px-2.5 py-1"
          >
            <CheckCircle size={9} />
            {label}
          </span>
        ))}
        {response.new_stock_level !== null && response.new_stock_level !== undefined && (
          <span className="flex items-center gap-1 text-[10px] font-mono text-ink-muted bg-surface-2 border border-white/5 rounded-full px-2.5 py-1">
            Stock: {response.new_stock_level} left
          </span>
        )}
      </div>

      {/* Email notification banner */}
      <div className="mx-3 mb-3 rounded-xl border border-brand-400/15 px-4 py-3 flex items-start gap-3"
           style={{ background: "rgba(45,212,160,0.06)" }}>
        <div className="w-7 h-7 rounded-full bg-brand-400/15 flex items-center justify-center shrink-0 mt-0.5">
          <Mail size={13} className="text-brand-400" />
        </div>
        <div>
          <p className="text-xs font-semibold text-ink-primary mb-1">
            Confirmation email on its way 📬
          </p>
          <p className="text-[11px] text-ink-muted leading-relaxed">
            We've sent your order details to your registered email address.
            If it doesn't arrive within a few minutes, please check your{" "}
            <span className="text-brand-400 font-medium">Spam</span> or{" "}
            <span className="text-brand-400 font-medium">Promotions</span> folder —
            it may have landed there.
          </p>
        </div>
      </div>

      {/* Payment */}
      <div className="px-4 pb-4">
        <p className="text-[10px] text-ink-muted font-mono">
          {paymentMethod === "cash_on_delivery"
            ? "💵 Cash on Delivery — pay when your order arrives"
            : "💳 Online payment confirmed"}
        </p>
      </div>

    </div>
  );
}