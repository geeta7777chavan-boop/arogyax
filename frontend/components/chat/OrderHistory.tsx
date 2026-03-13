"use client";
// components/chat/OrderHistory.tsx

import { useEffect, useState } from "react";
import { Package, RefreshCw,
         ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { getPatientHistory } from "@/lib/api";

interface OrderRecord {
  id?:                    string;
  patient_id:             string;
  purchase_date:          string;
  medicine_name?:         string;
  name?:                  string;
  quantity?:              number;
  Quantity?:              number;
  total_price?:           number;
  Total_Price?:           number;
  dosage_frequency?:      string;
  prescription_required?: string | boolean;
}

interface Props {
  patientId: string;
  onReorder: (medicineName: string) => void;
  refreshKey?: number;
}

// ── Date grouping helpers ──────────────────────────────────────────────────────
function parseDate(dateStr: string): Date {
  // Handle the ISO format properly - if it has T but no timezone (e.g., "2026-03-07T14:30:00"),
  // JavaScript parses it as UTC. We need to parse it as local time instead.
  if (dateStr.includes("T") && !dateStr.endsWith("Z") && !dateStr.includes("+")) {
    const localStr = dateStr.replace("T", " ");
    return new Date(localStr);
  }
  return new Date(dateStr);
}

function getDateGroup(dateStr: string): string {
  const today     = new Date();
  const orderDate  = parseDate(dateStr);
  today.setHours(0, 0, 0, 0);
  orderDate.setHours(0, 0, 0, 0);
  const diffDays = Math.round((today.getTime() - orderDate.getTime()) / (1000 * 60 * 60 * 24));

  if (diffDays === 0)  return "Today";
  if (diffDays === 1)  return "Yesterday";
  if (diffDays <= 7)   return "This Week";
  if (diffDays <= 30)  return "This Month";
  // Older — show month + year
  return orderDate.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

function groupByDate(orders: OrderRecord[]): { label: string; orders: OrderRecord[] }[] {
  // Sort newest first
  const sorted = [...orders].sort(
    (a, b) => parseDate(b.purchase_date).getTime() - parseDate(a.purchase_date).getTime()
  );

  const groups: { label: string; orders: OrderRecord[] }[] = [];
  let currentLabel = "";

  for (const order of sorted) {
    const label = getDateGroup(order.purchase_date);
    if (label !== currentLabel) {
      groups.push({ label, orders: [] });
      currentLabel = label;
    }
    groups[groups.length - 1].orders.push(order);
  }
  return groups;
}

function formatTime(dateStr: string): string {
  // purchase_date may or may not have a time component.
  // Only show time if the string contains a time component (T or space + digits).
  if (!dateStr) return "";
  
  // Check for time component: T in ISO format or space + time pattern
  const hasTime = dateStr.includes("T") || /\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(dateStr);
  if (!hasTime) return "";
  
  // Handle the ISO format properly - if it has T but no timezone (e.g., "2026-03-07T14:30:00"),
  // JavaScript parses it as UTC. We need to parse it as local time instead.
  let date: Date;
  const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):?(\d{2})?/);
  if (isoMatch) {
    // Parse as local time by constructing the date manually
    const [, year, month, day, hour, minute] = isoMatch;
    date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day), parseInt(hour), parseInt(minute));
  } else if (dateStr.includes("T") && !dateStr.endsWith("Z") && !dateStr.includes("+")) {
    // Replace T with space and parse as local time
    const localStr = dateStr.replace("T", " ");
    date = new Date(localStr);
  } else {
    date = new Date(dateStr);
  }
  
  // Check if date is valid
  if (isNaN(date.getTime())) return "";
  
  return date.toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit",
  });
}

function formatFullDate(dateStr: string): string {
  return parseDate(dateStr).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric",
  });
}

// ── Component ──────────────────────────────────────────────────────────────────
export default function OrderHistory({ patientId, onReorder, refreshKey }: Props) {
  const [history, setHistory] = useState<OrderRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => { loadData(); }, [patientId, refreshKey]);

  async function loadData() {
    setLoading(true);
    try {
      const hist = await getPatientHistory(patientId);
      setHistory(hist.history || []);
    } catch {
      // non-critical
    } finally {
      setLoading(false);
    }
  }

  const groups = groupByDate(history);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-40 text-ink-muted text-sm font-mono">
        <RefreshCw size={14} className="animate-spin mr-2" /> Loading history...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="px-4 py-3 border-b border-white/5 bg-surface-1 shrink-0">
        <span className="text-xs font-mono font-semibold text-brand-400 uppercase tracking-widest">
          Orders ({history.length})
        </span>
      </div>

      {/* ── Content ─────────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {history.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-ink-muted text-sm font-body">
            <Package size={20} className="mb-2 opacity-40" />
            No order history yet
          </div>
        ) : groups.map(group => (
          <div key={group.label}>
            {/* Date group header */}
            <div className="sticky top-0 z-10 px-4 py-1.5 bg-surface-0/90 backdrop-blur-sm
                            border-b border-white/5">
              <span className="text-[10px] font-mono font-semibold text-brand-400 uppercase tracking-widest">
                {group.label}
              </span>
            </div>

            {/* Orders in group */}
            <div className="divide-y divide-white/5">
              {group.orders.map((order, i) => {
                const key      = `${group.label}-${i}`;
                const isOpen   = expanded === key;
                const qty      = order.quantity   ?? order.Quantity   ?? 1;
                const price    = order.total_price ?? order.Total_Price;
                const name     = order.medicine_name ?? order.name ?? "Unknown";
                const timeStr  = formatTime(order.purchase_date);
                const fullDate = formatFullDate(order.purchase_date);

                return (
                  <div key={key} className="px-4 py-3 hover:bg-surface-2/40 transition-colors">
                    <div
                      className="w-full text-left cursor-pointer"
                      onClick={() => setExpanded(isOpen ? null : key)}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-semibold text-ink-primary font-display truncate">
                            {name}
                          </p>
                          <p className="text-[10px] text-ink-muted font-mono mt-0.5">
                            {fullDate}{timeStr ? ` · ${timeStr}` : ""} · Qty: {qty}
                            {price !== undefined && ` · €${Number(price).toFixed(2)}`}
                          </p>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          <button
                            onClick={e => { e.stopPropagation(); onReorder(name); }}
                            className="flex items-center gap-1 text-[10px] font-mono text-brand-400
                                       bg-brand-400/10 border border-brand-400/20 rounded-full
                                       px-2 py-0.5 hover:bg-brand-400/20 transition-colors"
                          >
                            <RotateCcw size={9} />
                            Reorder
                          </button>
                          {isOpen
                            ? <ChevronUp   size={11} className="text-ink-muted" />
                            : <ChevronDown size={11} className="text-ink-muted" />
                          }
                        </div>
                      </div>
                    </div>

                    {/* Expanded detail */}
                    {isOpen && (
                      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] font-mono
                                      bg-surface-0 rounded-lg p-2.5 border border-white/5">
                        <span className="text-ink-muted">Dosage</span>
                        <span className="text-ink-secondary">{order.dosage_frequency || "—"}</span>
                        <span className="text-ink-muted">Prescription</span>
                        <span className="text-ink-secondary">
                          {order.prescription_required === "Yes" || order.prescription_required === true
                            ? "Required" : "Not required"}
                        </span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

