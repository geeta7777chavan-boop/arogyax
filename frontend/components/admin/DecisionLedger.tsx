"use client";
// components/admin/DecisionLedger.tsx

import { useState, useEffect } from "react";
import { getDecisions } from "@/lib/api";
import type { Decision } from "@/types";
import { Shield, CheckCircle, XCircle, AlertTriangle, Zap, Package, Bell, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { format, parseISO } from "date-fns";
import { clsx } from "clsx";

const AGENT_ICONS: Record<string, React.ReactNode> = {
  ConversationalAgent: <Zap size={12} />,
  SafetyAgent:        <Shield size={12} />,
  InventoryAgent:     <Package size={12} />,
  PredictiveAgent:    <Bell size={12} />,
  NotificationAgent:  <Bell size={12} />,
  AdminAction:        <CheckCircle size={12} />,
  SeedAgent:          <CheckCircle size={12} />,
};

const ACTION_COLOR: Record<string, string> = {
  APPROVE:              "text-brand-400 bg-brand-400/10 border-brand-400/20",
  APPROVE_ORDER:        "text-brand-400 bg-brand-400/10 border-brand-400/20",
  REJECT:               "text-red-400 bg-red-400/10 border-red-400/20",
  LOW_STOCK_ALERT:      "text-yellow-400 bg-yellow-400/10 border-yellow-400/20",
  STOCK_RESERVED:       "text-blue-400 bg-blue-400/10 border-blue-400/20",
  REFILL_ALERT_CREATED: "text-purple-400 bg-purple-400/10 border-purple-400/20",
  NOTIFICATIONS_SENT:   "text-cyan-400 bg-cyan-400/10 border-cyan-400/20",
  DATA_LOADED:          "text-ink-secondary bg-surface-2 border-white/10",
};

function ActionBadge({ action }: { action: string }) {
  const cls = ACTION_COLOR[action] || "text-ink-secondary bg-surface-2 border-white/10";
  return (
    <span className={clsx("inline-flex items-center px-2 py-0.5 rounded-full border text-[10px] font-mono font-bold tracking-wide", cls)}>
      {action}
    </span>
  );
}

function DecisionRow({ d }: { d: Decision }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-white/5 rounded-xl overflow-hidden">
      {/* Row header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-surface-1 hover:bg-surface-2 transition-colors text-left"
      >
        <span className="text-ink-muted flex-shrink-0">
          {AGENT_ICONS[d.agent_name] || <Shield size={12} />}
        </span>
        <span className="text-xs font-mono text-ink-secondary w-36 flex-shrink-0 truncate">
          {d.agent_name}
        </span>
        <ActionBadge action={d.action} />
        <p className="flex-1 text-xs text-ink-secondary font-body truncate ml-2">{d.reason}</p>
        <span className="text-[10px] font-mono text-ink-muted flex-shrink-0 ml-2">
          {format(parseISO(d.created_at), "HH:mm:ss")}
        </span>
        {expanded ? <ChevronUp size={13} className="text-ink-muted flex-shrink-0" /> : <ChevronDown size={13} className="text-ink-muted flex-shrink-0" />}
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-white/5 p-4 bg-surface-0 space-y-3">
          <p className="text-xs text-ink-primary font-body leading-relaxed">{d.reason}</p>
          <div className="grid grid-cols-2 gap-3">
            {d.input_payload && (
              <div>
                <p className="text-[10px] font-mono text-ink-muted mb-1">INPUT</p>
                <pre className="text-[10px] font-mono text-ink-secondary bg-surface-1 border border-white/5 rounded-lg p-2 overflow-auto max-h-32">
                  {JSON.stringify(d.input_payload, null, 2)}
                </pre>
              </div>
            )}
            {d.output_payload && (
              <div>
                <p className="text-[10px] font-mono text-ink-muted mb-1">OUTPUT</p>
                <pre className="text-[10px] font-mono text-ink-secondary bg-surface-1 border border-white/5 rounded-lg p-2 overflow-auto max-h-32">
                  {JSON.stringify(d.output_payload, null, 2)}
                </pre>
              </div>
            )}
          </div>

        </div>
      )}
    </div>
  );
}

export default function DecisionLedger() {
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [filter,    setFilter]    = useState("");

  async function load() {
    setLoading(true);
    try {
      const { decisions } = await getDecisions({ limit: 100 });
      setDecisions(decisions);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  const filtered = filter
    ? decisions.filter(d =>
        d.agent_name.toLowerCase().includes(filter.toLowerCase()) ||
        d.action.toLowerCase().includes(filter.toLowerCase()) ||
        d.reason.toLowerCase().includes(filter.toLowerCase())
      )
    : decisions;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Filter by agent, action, or reason..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
          className="flex-1 bg-surface-2 border border-white/5 focus:border-brand-400/40 rounded-xl px-4 py-2.5 text-sm text-ink-primary placeholder-ink-muted font-body focus:outline-none transition-colors"
        />
        <button onClick={load}
          className="p-2.5 bg-surface-2 border border-white/5 rounded-xl text-ink-secondary hover:text-brand-400 transition-colors">
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="space-y-2">
        {loading && <p className="text-xs text-ink-muted font-mono text-center py-8">Loading decisions...</p>}
        {!loading && filtered.length === 0 && (
          <p className="text-xs text-ink-muted font-mono text-center py-8">No decisions found.</p>
        )}
        {filtered.map(d => <DecisionRow key={d.id} d={d} />)}
      </div>
      <p className="text-xs text-ink-muted font-mono">{filtered.length} decisions</p>
    </div>
  );
}
