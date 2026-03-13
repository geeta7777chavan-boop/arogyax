"use client";
// components/chat/RefillAlertBanner.tsx
// Inline refill reminder card shown in chat after an order

import { useState } from "react";
import { Bell, X, RotateCcw, ChevronRight, Clock } from "lucide-react";
import { clsx } from "clsx";

export interface RefillAlert {
  medicine:   string;
  days_until: number;   // negative = already overdue
  refill_due: string;   // YYYY-MM-DD
}

interface Props {
  alerts:    RefillAlert[];
  onReorder: (medicine: string) => void;
  onDismiss: () => void;
}

function urgency(days: number) {
  if (days <= 0)  return { border: "border-red-500/40",    bg: "bg-red-500/10",    dot: "bg-red-400",    text: "text-red-300",    badge: "bg-red-500/20 text-red-300",    label: "Overdue"   };
  if (days <= 3)  return { border: "border-orange-500/40", bg: "bg-orange-500/10", dot: "bg-orange-400", text: "text-orange-300", badge: "bg-orange-500/20 text-orange-300", label: `${days}d left` };
  if (days <= 7)  return { border: "border-yellow-500/40", bg: "bg-yellow-500/10", dot: "bg-yellow-400", text: "text-yellow-300", badge: "bg-yellow-500/20 text-yellow-300", label: `${days}d left` };
  return              { border: "border-brand-400/30",   bg: "bg-brand-400/5",   dot: "bg-brand-400",  text: "text-brand-300",  badge: "bg-brand-400/10 text-brand-400",   label: `${days}d left` };
}

function dueText(days: number, med: string) {
  if (days <= 0)  return `${med} — supply may have run out`;
  if (days === 1) return `${med} — last day of supply`;
  if (days <= 3)  return `${med} — only ${days} days left`;
  return              `${med} — refill in ${days} days`;
}

export default function RefillAlertBanner({ alerts, onReorder, onDismiss }: Props) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed || alerts.length === 0) return null;

  return (
    <div className="rounded-2xl border border-brand-400/20 bg-surface-1 overflow-hidden w-full max-w-sm">

      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/5 bg-brand-400/5">
        <div className="flex items-center gap-1.5">
          <Bell size={11} className="text-brand-400" />
          <span className="text-[10px] font-mono text-brand-400 font-semibold uppercase tracking-wider">
            Refill Reminder{alerts.length > 1 ? "s" : ""}
          </span>
          <span className="text-[10px] font-mono text-ink-muted">
            · WhatsApp sent ✓
          </span>
        </div>
        <button
          onClick={() => { setDismissed(true); onDismiss(); }}
          className="text-ink-muted hover:text-ink-secondary transition-colors p-0.5 rounded"
        >
          <X size={11} />
        </button>
      </div>

      {/* Alert rows */}
      <div className="divide-y divide-white/5">
        {alerts.slice(0, 4).map((alert, i) => {
          const u = urgency(alert.days_until);
          return (
            <div key={i} className={clsx("flex items-center justify-between px-3 py-2.5", u.bg)}>
              <div className="flex items-center gap-2 min-w-0">
                <span className={clsx("w-1.5 h-1.5 rounded-full shrink-0 animate-pulse", u.dot)} />
                <div className="min-w-0">
                  <p className={clsx("text-xs font-body truncate", u.text)}>
                    {dueText(alert.days_until, alert.medicine)}
                  </p>
                  {alert.refill_due && (
                    <p className="text-[10px] text-ink-muted font-mono flex items-center gap-1 mt-0.5">
                      <Clock size={9} /> Due {alert.refill_due}
                    </p>
                  )}
                </div>
              </div>
              <button
                onClick={() => onReorder(alert.medicine)}
                className={clsx(
                  "flex items-center gap-1 ml-2 shrink-0 px-2 py-1 rounded-lg text-[10px]",
                  "font-mono border transition-all hover:scale-105",
                  u.badge, u.border,
                )}
              >
                <RotateCcw size={9} />
                Reorder
                <ChevronRight size={9} />
              </button>
            </div>
          );
        })}
      </div>

      {/* Footer hint */}
      <div className="px-3 py-1.5 border-t border-white/5">
        <p className="text-[10px] text-ink-muted font-mono">
          Tap Reorder or say the medicine name to reorder
        </p>
      </div>
    </div>
  );
}
