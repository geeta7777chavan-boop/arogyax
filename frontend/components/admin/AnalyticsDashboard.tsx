"use client";
// components/admin/AnalyticsDashboard.tsx

import { useState, useEffect, useRef } from "react";
import {
  TrendingUp, ShoppingBag, Euro, Users,
  Bell, Package, ShieldCheck, RefreshCw,
  ArrowUpRight, ArrowDownRight, Minus,
} from "lucide-react";
import { clsx } from "clsx";
import { getAnalyticsSummary } from "@/lib/api";

// ── Types ─────────────────────────────────────────────────────────────────────
interface DayPoint  { date: string; label: string; orders: number; revenue: number }
interface TopMed    { name: string; count: number; revenue: number }
interface FreqItem  { label: string; count: number }
interface KPIs {
  total_orders:    number;
  total_revenue:   number;
  unique_patients: number;
  pending_alerts:  number;
  low_stock_items: number;
  safety_rate:     number;
}
interface Analytics {
  kpis:             KPIs;
  orders_over_time: DayPoint[];
  top_medicines:    TopMed[];
  freq_breakdown:   FreqItem[];
  rx_vs_otc:        { rx: number; otc: number };
  agent_actions:    Record<string, number>;
}

// ── Palette pulled from globals.css ──────────────────────────────────────────
const C = {
  brand:   "#2dd4a0",
  brand2:  "#10b981",
  amber:   "#f59e0b",
  red:     "#f87171",
  blue:    "#60a5fa",
  purple:  "#a78bfa",
  surface2:"#192620",
  surface3:"#1f3129",
  ink2:    "#8aada0",
  ink3:    "#4a6b5e",
};

// ── Mini sparkline (SVG) ──────────────────────────────────────────────────────
function Sparkline({ data, color = C.brand, height = 40 }: {
  data: number[]; color?: string; height?: number;
}) {
  if (!data.length) return null;
  const w = 120;
  const max = Math.max(...data, 1);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = height - (v / max) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(" ");
  const fill = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = height - (v / max) * (height - 4) - 2;
    return `${x},${y}`;
  });
  const area = `${fill[0].split(",")[0]},${height} ` + fill.join(" ") + ` ${fill[fill.length-1].split(",")[0]},${height}`;
  return (
    <svg width={w} height={height} className="overflow-visible">
      <defs>
        <linearGradient id={`sg-${color.replace("#","")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon points={area} fill={`url(#sg-${color.replace("#","")})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5"
        strokeLinecap="round" strokeLinejoin="round" />
      {/* Last dot */}
      {fill.length > 0 && (() => {
        const [lx, ly] = fill[fill.length - 1].split(",").map(Number);
        return <circle cx={lx} cy={ly} r="2.5" fill={color} />;
      })()}
    </svg>
  );
}

// ── KPI Card ─────────────────────────────────────────────────────────────────
function KpiCard({ label, value, sub, icon, color, sparkData, trend }: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  color: string;
  sparkData?: number[];
  trend?: "up" | "down" | "neutral";
}) {
  const TrendIcon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;
  const trendColor = trend === "up" ? "text-emerald-400" : trend === "down" ? "text-red-400" : "text-gray-500";

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/5 bg-surface-1 p-5
                    hover:border-white/10 transition-all duration-300 group">
      {/* Glow */}
      <div className="absolute -top-6 -right-6 w-24 h-24 rounded-full blur-2xl opacity-10 transition-opacity
                      group-hover:opacity-20"
           style={{ background: color }} />

      <div className="flex items-start justify-between mb-4">
        <div className="w-9 h-9 rounded-xl flex items-center justify-center"
             style={{ background: `${color}18`, border: `1px solid ${color}30` }}>
          <span style={{ color }}>{icon}</span>
        </div>
        {trend && (
          <span className={clsx("flex items-center gap-0.5 text-[11px] font-mono", trendColor)}>
            <TrendIcon size={11} />
          </span>
        )}
      </div>

      <div className="flex items-end justify-between">
        <div>
          <p className="text-[11px] text-ink-muted font-mono uppercase tracking-widest mb-1">{label}</p>
          <p className="text-2xl font-display font-bold text-ink-primary leading-none">{value}</p>
          {sub && <p className="text-[11px] text-ink-muted font-mono mt-1">{sub}</p>}
        </div>
        {sparkData && <Sparkline data={sparkData} color={color} />}
      </div>
    </div>
  );
}

// ── Orders + Revenue line chart (SVG) ────────────────────────────────────────
function OrdersChart({ data, view }: { data: DayPoint[]; view: "orders" | "revenue" | "combined" }) {
  const [hovered, setHovered] = useState<number | null>(null);
  const W = 100, H = 80; // viewBox units (%)
  if (!data.length) return null;

  const maxOrders  = Math.max(...data.map(d => d.orders), 1);
  const maxRevenue = Math.max(...data.map(d => d.revenue), 1);

  const orderPts  = data.map((d, i) => ({ x: (i/(data.length-1))*W, y: H-(d.orders/maxOrders)*(H-10)-5 }));
  const revPts    = data.map((d, i) => ({ x: (i/(data.length-1))*W, y: H-(d.revenue/maxRevenue)*(H-10)-5 }));

  const pathD = (pts: {x:number,y:number}[]) =>
    pts.map((p, i) => `${i===0?"M":"L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");

  const areaD = (pts: {x:number,y:number}[], color: string) =>
    `${pathD(pts)} L${pts[pts.length-1].x},${H} L${pts[0].x},${H} Z`;

  // Show every other label on small screen
  const showLabel = (i: number) => i % 2 === 0 || i === data.length - 1;

  // Determine which metrics to show based on view
  const showOrders = view === "orders" || view === "combined";
  const showRevenue = view === "revenue" || view === "combined";

  return (
    <div className="relative">
      {/* Tooltip */}
      {hovered !== null && (
        <div className="absolute top-0 left-1/2 -translate-x-1/2 z-10 pointer-events-none
                        bg-surface-3 border border-white/10 rounded-xl px-3 py-2 text-xs font-mono
                        shadow-xl whitespace-nowrap">
          <p className="text-ink-secondary">{data[hovered].label}</p>
          {showOrders && <p className="text-brand-400">{data[hovered].orders} orders</p>}
          {showRevenue && <p className="text-amber-400">€{data[hovered].revenue.toFixed(2)}</p>}
        </div>
      )}

      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: "160px" }}
           preserveAspectRatio="none">
        <defs>
          <linearGradient id="og" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.brand} stopOpacity="0.2" />
            <stop offset="100%" stopColor={C.brand} stopOpacity="0" />
          </linearGradient>
          <linearGradient id="rg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.amber} stopOpacity="0.15" />
            <stop offset="100%" stopColor={C.amber} stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {[0.25, 0.5, 0.75, 1].map(t => (
          <line key={t} x1="0" y1={H - t*(H-10) - 5} x2={W} y2={H - t*(H-10) - 5}
                stroke={C.ink3} strokeWidth="0.3" strokeDasharray="2,3" />
        ))}

        {/* Revenue area - only show when view is revenue or showing both */}
        {showRevenue && (
          <>
            <path d={areaD(revPts, C.amber)} fill="url(#rg)" />
            <path d={pathD(revPts)} fill="none" stroke={C.amber} strokeWidth="0.8"
                  strokeLinecap="round" strokeLinejoin="round" opacity="0.7" />
          </>
        )}

        {/* Orders area - only show when view is orders or showing both */}
        {showOrders && (
          <>
            <path d={areaD(orderPts, C.brand)} fill="url(#og)" />
            <path d={pathD(orderPts)} fill="none" stroke={C.brand} strokeWidth="1"
                  strokeLinecap="round" strokeLinejoin="round" />
          </>
        )}

        {/* Hover targets + dots */}
        {data.map((d, i) => (
          <g key={i}>
            <rect x={(orderPts[i].x - W/data.length/2)} y="0"
                  width={W/data.length} height={H}
                  fill="transparent"
                  onMouseEnter={() => setHovered(i)}
                  onMouseLeave={() => setHovered(null)}
                  style={{ cursor: "crosshair" }} />
            {hovered === i && (
              <>
                <line x1={orderPts[i].x} y1="0" x2={orderPts[i].x} y2={H}
                      stroke="white" strokeWidth="0.3" strokeDasharray="2,2" opacity="0.3" />
                {showOrders && <circle cx={orderPts[i].x} cy={orderPts[i].y} r="1.5" fill={C.brand} />}
                {showRevenue && <circle cx={revPts[i].x} cy={revPts[i].y} r="1.5" fill={C.amber} />}
              </>
            )}
          </g>
        ))}
      </svg>

      {/* X axis labels */}
      <div className="flex justify-between mt-1 px-0.5">
        {data.map((d, i) => (
          <span key={i} className={clsx(
            "text-[9px] font-mono text-ink-muted transition-colors",
            hovered === i ? "text-ink-secondary" : "",
            !showLabel(i) && "invisible"
          )}>
            {d.label.split(" ")[1]}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Horizontal bar chart ──────────────────────────────────────────────────────
function BarChart({ items, color = C.brand }: {
  items: { label: string; value: number; sub?: string }[];
  color?: string;
}) {
  const max = Math.max(...items.map(i => i.value), 1);
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="group">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-body text-ink-secondary truncate max-w-[70%]"
                  title={item.label}>{item.label}</span>
            <div className="flex items-center gap-2">
              {item.sub && <span className="text-[10px] font-mono text-ink-muted">{item.sub}</span>}
              <span className="text-xs font-mono font-semibold" style={{ color }}>{item.value}</span>
            </div>
          </div>
          <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width:      `${(item.value / max) * 100}%`,
                background: `linear-gradient(90deg, ${color}cc, ${color})`,
                transitionDelay: `${i * 80}ms`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Donut chart (SVG) ─────────────────────────────────────────────────────────
function DonutChart({ segments, size = 100 }: {
  segments: { label: string; value: number; color: string }[];
  size?: number;
}) {
  const total  = segments.reduce((s, x) => s + x.value, 0) || 1;
  const r      = 36;
  const cx     = size / 2;
  const cy     = size / 2;
  const circum = 2 * Math.PI * r;

  let cumAngle = -Math.PI / 2;
  const arcs = segments.map(seg => {
    const frac  = seg.value / total;
    const angle = frac * 2 * Math.PI;
    const x1    = cx + r * Math.cos(cumAngle);
    const y1    = cy + r * Math.sin(cumAngle);
    cumAngle   += angle;
    const x2    = cx + r * Math.cos(cumAngle);
    const y2    = cy + r * Math.sin(cumAngle);
    const large = angle > Math.PI ? 1 : 0;
    return { ...seg, frac, x1, y1, x2, y2, large };
  });

  return (
    <div className="flex items-center gap-6">
      <svg width={size} height={size} className="shrink-0">
        {/* Background ring */}
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={C.surface3} strokeWidth="10" />
        {arcs.map((a, i) => (
          <path
            key={i}
            d={`M ${a.x1} ${a.y1} A ${r} ${r} 0 ${a.large} 1 ${a.x2} ${a.y2}`}
            fill="none"
            stroke={a.color}
            strokeWidth="10"
            strokeLinecap="round"
            opacity="0.9"
          />
        ))}
        {/* Center text */}
        <text x={cx} y={cy - 4} textAnchor="middle" fontSize="11"
              fontFamily="JetBrains Mono, monospace" fill="#e8f5f0" fontWeight="700">
          {total}
        </text>
        <text x={cx} y={cy + 9} textAnchor="middle" fontSize="6"
              fontFamily="JetBrains Mono, monospace" fill={C.ink2}>
          total
        </text>
      </svg>
      <div className="space-y-2">
        {segments.map((s, i) => (
          <div key={i} className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full shrink-0" style={{ background: s.color }} />
            <span className="text-xs text-ink-secondary font-body">{s.label}</span>
            <span className="text-xs font-mono ml-auto" style={{ color: s.color }}>
              {s.value} <span className="text-ink-muted">({Math.round(s.value/total*100)}%)</span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Agent pipeline status pills ────────────────────────────────────────────────
function AgentPipeline({ actions }: { actions: Record<string, number> }) {
  const AGENTS = [
    { name: "ConversationalAgent", short: "Conv",  color: C.brand   },
    { name: "SafetyAuditor",       short: "Audit", color: C.blue    },
    { name: "SafetyAgent",         short: "Safety",color: C.amber   },
    { name: "InventoryAgent",      short: "Stock", color: C.purple  },
    { name: "PredictiveAgent",     short: "Pred",  color: "#34d399" },
    { name: "NotificationAgent",   short: "Notif", color: "#fb923c" },
  ];

  const approvals = (actions["APPROVE"] || 0) + (actions["APPROVE_ORDER"] || 0) +
                    (actions["STOCK_VALIDATED"] || 0) + (actions["MULTI_ORDER_APPROVED"] || 0);
  const rejections = (actions["REJECT"] || 0) + (actions["OUT_OF_STOCK"] || 0) +
                     (actions["PRESCRIPTION_REQUIRED"] || 0);
  const total = approvals + rejections || 1;

  return (
    <div className="space-y-4">
      {/* Pipeline flow */}
      <div className="flex items-center gap-1 flex-wrap">
        {AGENTS.map((a, i) => (
          <div key={a.name} className="flex items-center gap-1">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] font-mono"
                 style={{ borderColor: `${a.color}30`, background: `${a.color}0d`, color: a.color }}>
              <span className="w-1.5 h-1.5 rounded-full animate-pulse"
                    style={{ background: a.color }} />
              {a.short}
            </div>
            {i < AGENTS.length - 1 && (
              <span className="text-ink-muted text-xs">→</span>
            )}
          </div>
        ))}
      </div>

      {/* Approve / Reject bar */}
      <div>
        <div className="flex justify-between text-[11px] font-mono mb-1.5">
          <span className="text-emerald-400">✓ {approvals} approved</span>
          <span className="text-red-400">✗ {rejections} rejected</span>
        </div>
        <div className="h-2 bg-surface-3 rounded-full overflow-hidden flex">
          <div className="h-full bg-emerald-500 transition-all duration-700"
               style={{ width: `${(approvals/total)*100}%` }} />
          <div className="h-full bg-red-500/60 flex-1" />
        </div>
      </div>
    </div>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────────
export default function AnalyticsDashboard() {
  const [data,      setData]      = useState<Analytics | null>(null);
  const [loading,   setLoading]   = useState(true);
  const [lastFetch, setLastFetch] = useState<Date | null>(null);
  const [view,      setView]      = useState<"orders" | "revenue" | "combined">("combined");

  async function load() {
    setLoading(true);
    try {
      const data = await getAnalyticsSummary();
      setData(data);
      setLastFetch(new Date());
    } catch (e) {
      console.error("Analytics load failed:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading && !data) return (
    <div className="flex items-center justify-center h-64">
      <div className="flex items-center gap-3 text-ink-muted font-mono text-sm">
        <RefreshCw size={15} className="animate-spin text-brand-400" />
        Loading analytics...
      </div>
    </div>
  );

  if (!data) return (
    <div className="text-center py-12 text-ink-muted font-mono text-sm">
      Failed to load analytics. Check backend connection.
    </div>
  );

  const { kpis, orders_over_time, top_medicines, freq_breakdown, rx_vs_otc, agent_actions } = data;

  const sparkOrders  = orders_over_time.map(d => d.orders);
  const sparkRevenue = orders_over_time.map(d => d.revenue);

  const topMedBars = top_medicines.map(m => ({
    label: m.name,
    value: m.count,
    sub:   `€${m.revenue.toFixed(0)}`,
  }));

  const freqBars = freq_breakdown.slice(0, 5).map(f => ({
    label: f.label,
    value: f.count,
  }));

  const chartData = orders_over_time.map(d => ({
    ...d,
    value: view === "orders" ? d.orders : d.revenue,
  }));

  return (
    <div className="space-y-6 animate-[fadeUp_0.4s_ease_forwards]">

      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display font-bold text-ink-primary text-lg flex items-center gap-2">
            <TrendingUp size={18} className="text-brand-400" />
            Analytics
          </h2>
          {lastFetch && (
            <p className="text-[11px] text-ink-muted font-mono mt-0.5">
              Updated {lastFetch.toLocaleTimeString()}
            </p>
          )}
        </div>
        <button onClick={load} disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono text-brand-400
                     bg-brand-400/10 border border-brand-400/20 rounded-lg hover:bg-brand-400/20
                     transition-colors disabled:opacity-40">
          <RefreshCw size={11} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* ── KPI Cards ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KpiCard label="Total Orders"     value={String(kpis.total_orders)}
          icon={<ShoppingBag size={16} />} color={C.brand}
          sparkData={sparkOrders} trend="up"
          sub={`${kpis.unique_patients} patients`} />

        <KpiCard label="Total Revenue"    value={`€${kpis.total_revenue.toLocaleString("de-DE", { maximumFractionDigits: 0 })}`}
          icon={<Euro size={16} />} color={C.amber}
          sparkData={sparkRevenue} trend="up"
          sub={`avg €${kpis.total_orders ? (kpis.total_revenue/kpis.total_orders).toFixed(2) : "0"}/order`} />

        <KpiCard label="Patients"         value={String(kpis.unique_patients)}
          icon={<Users size={16} />} color={C.blue}
          trend="neutral"
          sub="unique this period" />

        <KpiCard label="Safety Rate"      value={`${kpis.safety_rate}%`}
          icon={<ShieldCheck size={16} />} color="#34d399"
          trend={kpis.safety_rate >= 80 ? "up" : "down"}
          sub="approved / total" />

        <KpiCard label="Refill Alerts"    value={String(kpis.pending_alerts)}
          icon={<Bell size={16} />} color={kpis.pending_alerts > 5 ? C.red : C.amber}
          trend={kpis.pending_alerts > 0 ? "down" : "neutral"}
          sub="pending action" />

        <KpiCard label="Low Stock"        value={String(kpis.low_stock_items)}
          icon={<Package size={16} />} color={kpis.low_stock_items > 3 ? C.red : C.purple}
          trend={kpis.low_stock_items > 0 ? "down" : "neutral"}
          sub="items ≤ 10 units" />
      </div>

      {/* ── Orders / Revenue chart ────────────────────────────────────────────── */}
      <div className="bg-surface-1 border border-white/5 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-display font-semibold text-ink-primary">
            Last 14 Days
          </h3>
          <div className="flex gap-1 bg-surface-2 rounded-lg p-0.5 border border-white/5">
            {(["combined", "orders", "revenue"] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                className={clsx(
                  "px-3 py-1 rounded-md text-[11px] font-mono transition-all",
                  view === v
                    ? "bg-brand-600 text-white shadow"
                    : "text-ink-muted hover:text-ink-secondary"
                )}>
                {v}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 mb-3">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 rounded-full" style={{ background: C.brand }} />
            <span className="text-[10px] font-mono text-ink-muted">Orders</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 rounded-full" style={{ background: C.amber }} />
            <span className="text-[10px] font-mono text-ink-muted">Revenue (€)</span>
          </div>
        </div>

        <OrdersChart data={orders_over_time} view={view} />
      </div>

      {/* ── Bottom row: Top meds + Freq + Rx/OTC + Pipeline ─────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Top medicines */}
        <div className="bg-surface-1 border border-white/5 rounded-2xl p-5">
          <h3 className="text-sm font-display font-semibold text-ink-primary mb-4 flex items-center gap-2">
            <ShoppingBag size={14} className="text-brand-400" />
            Top Medicines
          </h3>
          {topMedBars.length
            ? <BarChart items={topMedBars} color={C.brand} />
            : <p className="text-xs text-ink-muted font-mono text-center py-4">No data</p>}
        </div>

        {/* Rx vs OTC + Dosage freq */}
        <div className="space-y-4">
          {/* Rx vs OTC */}
          <div className="bg-surface-1 border border-white/5 rounded-2xl p-5">
            <h3 className="text-sm font-display font-semibold text-ink-primary mb-4 flex items-center gap-2">
              <ShieldCheck size={14} className="text-amber-400" />
              Rx vs OTC Split
            </h3>
            <DonutChart segments={[
              { label: "Prescription (Rx)", value: rx_vs_otc.rx,  color: C.amber  },
              { label: "Over-the-counter",  value: rx_vs_otc.otc, color: C.brand  },
            ]} />
          </div>

          {/* Dosage frequency */}
          <div className="bg-surface-1 border border-white/5 rounded-2xl p-5">
            <h3 className="text-sm font-display font-semibold text-ink-primary mb-4 flex items-center gap-2">
              <Bell size={14} className="text-purple-400" />
              Dosage Frequency
            </h3>
            {freqBars.length
              ? <BarChart items={freqBars} color={C.purple} />
              : <p className="text-xs text-ink-muted font-mono text-center py-4">No data</p>}
          </div>
        </div>
      </div>

      {/* ── Agent pipeline health ─────────────────────────────────────────────── */}
      <div className="bg-surface-1 border border-white/5 rounded-2xl p-5">
        <h3 className="text-sm font-display font-semibold text-ink-primary mb-4 flex items-center gap-2">
          <ShieldCheck size={14} className="text-brand-400" />
          Agent Pipeline Health
        </h3>
        <AgentPipeline actions={agent_actions} />

        {/* Action breakdown pills */}
        {Object.keys(agent_actions).length > 0 && (
          <div className="flex flex-wrap gap-2 mt-4 pt-4 border-t border-white/5">
            {Object.entries(agent_actions)
              .sort(([,a],[,b]) => b - a)
              .slice(0, 8)
              .map(([action, count]) => {
                const isApprove = action.includes("APPROVE") || action.includes("VALIDATED");
                const isReject  = action.includes("REJECT") || action.includes("STOCK") && !action.includes("VALIDATED");
                const col = isApprove ? C.brand : isReject ? C.red : C.ink2;
                return (
                  <span key={action}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-mono border"
                    style={{ color: col, borderColor: `${col}30`, background: `${col}0d` }}>
                    <span>{count}</span>
                    <span className="opacity-70">{action}</span>
                  </span>
                );
              })}
          </div>
        )}
      </div>

    </div>
  );
}