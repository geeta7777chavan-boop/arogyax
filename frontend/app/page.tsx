"use client";
// app/page.tsx — ArogyaX · v6

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight, CalendarCheck, Mic, ShieldCheck, Zap,
  ExternalLink,
} from "lucide-react";

/* ── Particles ──────────────────────────────────────────────────────────── */
const DOTS = Array.from({ length: 20 }, (_, i) => ({
  id: i, x: (i * 47 + 11) % 97, y: (i * 61 + 19) % 94,
  dur: 3.2 + (i % 4) * 1.1, del: (i * 0.41) % 5.8,
  r: i % 5 === 0 ? 1.6 : i % 3 === 0 ? 1.1 : 0.8,
}));

/* ── API base URL — works locally and in production ─────────────────────── */
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/* ── Scroll-reveal hook ─────────────────────────────────────────────────── */
function useReveal(threshold = 0.12) {
  const ref = useRef<HTMLDivElement>(null);
  const [vis, setVis] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) { setVis(true); obs.disconnect(); } },
      { threshold }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold]);
  return { ref, vis };
}

/* ── Features data ──────────────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: <CalendarCheck size={20} />,
    title: "Proactive Refills",
    desc: "AI watches your history and reminds you before you run out. No more midnight pharmacy emergencies.",
    accent: "#2dd4a0",
    tag: "Smart Prediction",
  },
  {
    icon: <Mic size={20} />,
    title: "Voice & Chat Orders",
    desc: "Say the medicine name naturally. The agent extracts intent, checks dosage, and confirms instantly.",
    accent: "#60a5fa",
    tag: "Natural Language",
  },
  {
    icon: <ShieldCheck size={20} />,
    title: "6-Agent Safety",
    desc: "Every order passes contraindication and prescription checks across six dedicated AI agents.",
    accent: "#f59e0b",
    tag: "Zero Compromise",
  },
  {
    icon: <Zap size={20} />,
    title: "Instant Confirmation",
    desc: "Email notification the moment your order clears. Refill reminders, order history, full control.",
    accent: "#a78bfa",
    tag: "Always Notified",
  },
];

/* ── Feature card ───────────────────────────────────────────────────────── */
function FCard({ icon, title, desc, accent, tag, index }: typeof FEATURES[0] & { index: number }) {
  const { ref, vis } = useReveal(0.08);
  const [hov, setHov] = useState(false);
  return (
    <div
      ref={ref}
      onMouseEnter={() => setHov(true)}
      onMouseLeave={() => setHov(false)}
      style={{
        flex: "1 1 0", minWidth: 0, position: "relative", overflow: "hidden",
        borderRadius: 18,
        background: hov ? "linear-gradient(160deg,#141e19,#1a2820)" : "#111916",
        border: `1px solid ${hov ? accent + "45" : "#1c2a22"}`,
        boxShadow: hov
          ? `0 20px 56px #00000055, 0 0 0 1px ${accent}15, inset 0 1px 0 ${accent}0c`
          : "inset 0 1px 0 #ffffff04",
        transform: vis ? (hov ? "translateY(-7px) scale(1.02)" : "none") : "translateY(32px)",
        opacity: vis ? 1 : 0,
        transition: `opacity .55s ease ${index * 100}ms, transform .35s cubic-bezier(.22,1,.36,1), border-color .25s, box-shadow .3s, background .3s`,
        cursor: "default", padding: "28px 24px 24px",
        display: "flex", flexDirection: "column" as const, gap: 0,
      }}
    >
      <div style={{ position:"absolute", top:0, left:0, right:0, height:2, background:`linear-gradient(90deg,${accent}00,${accent},${accent}00)`, opacity: hov ? 0.8 : 0.25, transition:"opacity .3s" }} />
      <div style={{ position:"absolute", inset:0, pointerEvents:"none", borderRadius:18, background: hov ? `radial-gradient(ellipse at 50% 0%, ${accent}10 0%, transparent 65%)` : "none", transition:"background .4s" }} />
      <div style={{ width:46, height:46, borderRadius:13, marginBottom:20, display:"flex", alignItems:"center", justifyContent:"center", background:accent+"12", border:`1px solid ${accent}${hov?"38":"1e"}`, color:accent, boxShadow: hov ? `0 0 20px ${accent}25` : "none", transition:"all .3s", position:"relative" as const }}>
        {icon}
      </div>
      <div style={{ display:"inline-flex", alignItems:"center", padding:"2px 10px", borderRadius:99, background:accent+"0e", border:`1px solid ${accent}1c`, fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:9.5, color:accent, letterSpacing:".07em", textTransform:"uppercase" as const, marginBottom:12, fontWeight:600, width:"fit-content" }}>{tag}</div>
      <p style={{ fontFamily:"'Montserrat',sans-serif", fontWeight:700, fontSize:15, color:"#e8f5f0", marginBottom:10, letterSpacing:"-.01em", lineHeight:1.25 }}>{title}</p>
      <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:13, color:"#5a8070", lineHeight:1.7, fontWeight:400, flex:1 }}>{desc}</p>
    </div>
  );
}

/* ── Pipeline step ──────────────────────────────────────────────────────── */
function Step({ num, label, sub, accent, last, index }: {
  num: string; label: string; sub: string; accent: string; last?: boolean; index: number;
}) {
  const { ref, vis } = useReveal(0.1);
  return (
    <div ref={ref} style={{ display:"flex", alignItems:"flex-start", gap:18, paddingBottom: last ? 0 : 32, position:"relative", opacity: vis ? 1 : 0, transform: vis ? "none" : "translateX(-18px)", transition:`opacity .55s ease ${index*90}ms, transform .55s ease ${index*90}ms` }}>
      {!last && <div style={{ position:"absolute", left:24, top:54, bottom:0, width:2, borderRadius:99, background:`linear-gradient(180deg,${accent}35,#1a2820)` }} />}
      <div style={{ width:50, height:50, borderRadius:14, flexShrink:0, display:"flex", alignItems:"center", justifyContent:"center", fontFamily:"'JetBrains Mono',monospace", fontWeight:700, fontSize:12, letterSpacing:".04em", color:accent, background:accent+"0d", border:`1px solid ${accent}25` }}>{num}</div>
      <div style={{ paddingTop:5 }}>
        <p style={{ fontFamily:"'Montserrat',sans-serif", fontWeight:600, fontSize:15, color:"#e8f5f0", marginBottom:4 }}>{label}</p>
        <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:12, color:"#4a6b5e", letterSpacing:".02em" }}>{sub}</p>
      </div>
    </div>
  );
}

/* ── Section heading — Nebula / Kalipixel ───────────────────────────────── */
function SectionHead({ eyebrow, title }: { eyebrow: string; title: React.ReactNode }) {
  const { ref, vis } = useReveal(0.2);
  return (
    <div ref={ref} style={{ textAlign:"center", marginBottom:52, opacity: vis ? 1 : 0, transform: vis ? "none" : "translateY(18px)", transition:"opacity .6s ease, transform .6s ease" }}>
      <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:10.5, letterSpacing:".14em", textTransform:"uppercase" as const, color:"#2dd4a0", marginBottom:14, fontWeight:600 }}>{eyebrow}</p>
      <h2 style={{
        fontFamily: "'Kalipixel',sans-serif",
        fontWeight: 400,
        fontSize: "clamp(28px,5.5vw,50px)",
        lineHeight: 1.08,
        letterSpacing: "-.01em",
        color: "#e8f5f0",
        margin: 0,
      }}>{title}</h2>
    </div>
  );
}

/* ── Bottom CTA ─────────────────────────────────────────────────────────── */
function BottomCTA() {
  const { ref, vis } = useReveal(0.1);
  return (
    <section style={{ position:"relative", zIndex:1, padding:"0 32px 120px" }}>
      <div ref={ref} style={{
        maxWidth: 1100, margin: "0 auto", borderRadius: 24,
        background: "linear-gradient(145deg,#0d1f17 0%,#0a1710 50%,#0d2019 100%)",
        border: "1px solid #1a2e22", overflow: "hidden", position: "relative",
        opacity: vis ? 1 : 0, transform: vis ? "none" : "translateY(28px)",
        transition: "opacity .8s ease, transform .8s ease",
      }}>
        {/* Glows */}
        <div style={{ position:"absolute", width:500, height:500, top:-200, right:-150, borderRadius:"50%", background:"radial-gradient(circle,#064e3b 0%,transparent 65%)", filter:"blur(80px)", opacity:.5, pointerEvents:"none" }} />
        <div style={{ position:"absolute", width:360, height:360, bottom:-140, left:-100, borderRadius:"50%", background:"radial-gradient(circle,#053828 0%,transparent 65%)", filter:"blur(70px)", opacity:.4, pointerEvents:"none" }} />
        <div style={{ position:"absolute", inset:0, backgroundImage:"linear-gradient(rgba(45,212,160,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(45,212,160,.018) 1px,transparent 1px)", backgroundSize:"40px 40px", pointerEvents:"none" }} />

        <div style={{ position:"relative", zIndex:1, padding:"72px 64px" }}>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap" as const, gap:48 }}>

            {/* Left */}
            <div style={{ flex:"1 1 320px", maxWidth:480 }}>
              <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:11, color:"#2dd4a0", letterSpacing:".14em", textTransform:"uppercase" as const, fontWeight:600, marginBottom:20 }}>Start for free</p>
              {/* ↓ Nebula / Kalipixel */}
              <h2 style={{
                fontFamily: "'Kalipixel',sans-serif",
                fontWeight: 400,
                fontSize: "clamp(28px,4vw,48px)",
                lineHeight: 1.1,
                letterSpacing: "-.01em",
                color: "#e8f5f0",
                margin: "0 0 24px",
              }}>
                Your health,<br />on autopilot.
              </h2>
              <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:14, color:"#4a6b5e", lineHeight:1.75, fontWeight:400, margin:0 }}>
                ArogyaX quietly handles refills, safety checks,
                and order confirmations — so you don't have to.
              </p>
            </div>

            {/* Right: stats rows + CTA */}
            <div style={{ flex:"0 0 auto", display:"flex", flexDirection:"column" as const, alignItems:"stretch", gap:10, minWidth:290 }}>
              {[
                { value:"6",      label:"AI Agents working in parallel",  accent:"#2dd4a0", bar:"72%"  },
                { value:"< 3s",   label:"Average order processing time",  accent:"#34d399", bar:"88%"  },
                { value:"100%",   label:"Every order safety-checked",     accent:"#6ee7b7", bar:"100%" },
                { value:"24 / 7", label:"Always available, never sleeps", accent:"#a7f3d0", bar:"60%"  },
              ].map(s => (
                <div key={s.label} style={{ display:"flex", alignItems:"center", gap:14, padding:"13px 16px", borderRadius:14, background:"#0a1610", border:"1px solid #1a2820", position:"relative", overflow:"hidden" }}>
                  {/* fill bar */}
                  <div style={{ position:"absolute", left:0, top:0, bottom:0, width:s.bar, background:`linear-gradient(90deg,${s.accent}0a,transparent)`, borderRadius:14 }} />
                  {/* value */}
                  <p style={{ fontFamily:"'Montserrat',sans-serif", fontWeight:800, fontSize:"clamp(18px,2vw,24px)", color:s.accent, lineHeight:1, flexShrink:0, minWidth:58, textAlign:"right" as const, position:"relative", zIndex:1 }}>{s.value}</p>
                  {/* divider */}
                  <div style={{ width:1, height:24, background:"#1a2820", flexShrink:0 }} />
                  {/* label */}
                  <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:12, color:"#4a6b5e", fontWeight:500, lineHeight:1.35, position:"relative", zIndex:1 }}>{s.label}</p>
                </div>
              ))}

              {/* CTA */}
              <Link href="/auth?mode=signup" className="btn-pri" style={{ display:"inline-flex", alignItems:"center", justifyContent:"center", gap:10, marginTop:4, padding:"14px 36px", borderRadius:13, background:"linear-gradient(135deg,#059669,#2dd4a0)", color:"#041a0e", fontFamily:"'Montserrat',sans-serif", fontWeight:700, fontSize:15, textDecoration:"none", letterSpacing:"-.01em", boxShadow:"0 4px 32px #2dd4a030", animation:"btnG 9s ease 4s infinite" }}>
                Get Started Free <ArrowRight size={15} />
              </Link>
            </div>

          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Footer ─────────────────────────────────────────────────────────────── */
function Footer() {
  return (
    <footer style={{ position:"relative", zIndex:1, borderTop:"1px solid #111916", padding:"40px 32px 32px" }}>
      <div style={{ maxWidth:900, margin:"0 auto" }}>
        <div style={{ display:"flex", flexWrap:"wrap" as const, justifyContent:"space-between", alignItems:"flex-start", gap:32, marginBottom:36 }}>
          <div style={{ minWidth:180 }}>
            <span style={{ fontFamily:"'Necosmic','Syne',sans-serif", fontSize:22, color:"#2dd4a0", display:"block", marginBottom:10 }}>ArogyaX</span>
            <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:12, color:"#4a6b5e", lineHeight:1.7, maxWidth:200 }}>AI-powered pharmacy care. Smarter refills, safer orders.</p>
          </div>
          <div style={{ display:"flex", gap:48, flexWrap:"wrap" as const }}>
            <div>
              <p style={{ fontFamily:"'Montserrat',sans-serif", fontWeight:700, fontSize:11, color:"#8aada0", letterSpacing:".1em", textTransform:"uppercase" as const, marginBottom:14 }}>Product</p>
              {[
                { label:"Patient Chat",    href:"/chat"              },
                { label:"Admin Dashboard", href:"/admin"             },
                { label:"API Docs",        href:`${API_BASE}/docs`   },
              ].map(l => (
                <a key={l.label} href={l.href} style={{ display:"block", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:13, color:"#4a6b5e", textDecoration:"none", marginBottom:10, transition:"color .2s" }}
                  onMouseEnter={e=>(e.currentTarget.style.color="#2dd4a0")}
                  onMouseLeave={e=>(e.currentTarget.style.color="#4a6b5e")}
                >{l.label}</a>
              ))}
            </div>
            <div>
              <p style={{ fontFamily:"'Montserrat',sans-serif", fontWeight:700, fontSize:11, color:"#8aada0", letterSpacing:".1em", textTransform:"uppercase" as const, marginBottom:14 }}>Stack</p>
              {["Llama 3.3 70B","LangGraph","FastAPI","Supabase","Langfuse"].map(s => (
                <p key={s} style={{ fontFamily:"'JetBrains Mono',monospace", fontSize:11, color:"#344f44", marginBottom:9, letterSpacing:".02em" }}>{s}</p>
              ))}
            </div>
          </div>
        </div>
        <div style={{ borderTop:"1px solid #111916", paddingTop:24, display:"flex", flexWrap:"wrap" as const, alignItems:"center", justifyContent:"space-between", gap:12 }}>
          <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:11, color:"#2e4038", letterSpacing:".03em" }}>© 2026 ArogyaX · Built with care for patients everywhere</p>
          <div style={{ display:"flex", alignItems:"center", gap:8 }}>
            <span style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:11, color:"#2e4038" }}>Trusted Care, Always There</span>
            <span style={{ color:"#1a2820" }}>·</span>
            <a href={`${API_BASE}/docs`} target="_blank" style={{ display:"inline-flex", alignItems:"center", gap:4, fontFamily:"'JetBrains Mono',monospace", fontSize:10, color:"#2dd4a0", textDecoration:"none", letterSpacing:".04em" }}>
              API <ExternalLink size={10} />
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}

/* ── Root ───────────────────────────────────────────────────────────────── */
export default function HomePage() {
  return (
    <>
      <style>{`
        @import url('https://fonts.cdnfonts.com/css/necosmic');
        @import url('https://fonts.cdnfonts.com/css/sofia-pro');
        @import url('https://fonts.cdnfonts.com/css/kalipixel');
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

        @keyframes fu    { from{opacity:0;transform:translateY(16px)} to{opacity:1;transform:none} }
        @keyframes fuBig { from{opacity:0;transform:translateY(28px) scale(.96)} to{opacity:1;transform:none} }
        @keyframes ob1   { 0%,100%{transform:translate(0,0)} 40%{transform:translate(30px,-26px)} 70%{transform:translate(-16px,18px)} }
        @keyframes ob2   { 0%,100%{transform:translate(0,0)} 45%{transform:translate(-22px,18px)} 75%{transform:translate(14px,-12px)} }
        @keyframes ob3   { 0%,100%{transform:translate(0,0)} 50%{transform:translate(10px,-16px)} }
        @keyframes ptD   { 0%,100%{opacity:0;transform:translateY(0)} 25%{opacity:.25} 55%{opacity:.12;transform:translateY(-16px)} 80%{opacity:.2} }
        @keyframes sw    { 0%,100%{transform:translateY(0);opacity:.8} 50%{transform:translateY(7px);opacity:.2} }
        @keyframes btnG  { 0%,87%,100%{box-shadow:0 4px 28px #2dd4a028} 92%{box-shadow:0 4px 48px #2dd4a060,0 0 100px #2dd4a010} }

        .btn-pri { transition: transform .2s ease, box-shadow .2s ease !important; }
        .btn-pri:hover { transform: translateY(-2px) scale(1.02) !important; box-shadow: 0 12px 40px #2dd4a050 !important; }
        .btn-sec { transition: all .2s ease !important; }
        .btn-sec:hover { border-color: #2dd4a045 !important; color: #2dd4a0 !important; background: #2dd4a008 !important; transform: translateY(-1px) !important; }
      `}</style>

      <div style={{ background:"#0a0f0d", overflowX:"hidden" }}>

        {/* Fixed ambient */}
        <div style={{ position:"fixed", inset:0, zIndex:0, overflow:"hidden", pointerEvents:"none" }}>
          <div style={{ position:"absolute", width:600, height:600, borderRadius:"50%", filter:"blur(100px)", background:"radial-gradient(circle,#0d4430 0%,transparent 65%)", top:-180, left:-160, opacity:.5, animation:"ob1 28s ease-in-out infinite" }} />
          <div style={{ position:"absolute", width:440, height:440, borderRadius:"50%", filter:"blur(90px)", background:"radial-gradient(circle,#064e3b 0%,transparent 65%)", bottom:-100, right:-100, opacity:.4, animation:"ob2 21s ease-in-out infinite" }} />
          <div style={{ position:"absolute", width:320, height:320, borderRadius:"50%", filter:"blur(90px)", background:"radial-gradient(circle,#2dd4a007 0%,transparent 70%)", top:"40%", right:"6%", opacity:.45, animation:"ob3 15s ease-in-out infinite" }} />
        </div>
        <div aria-hidden style={{ position:"fixed", inset:0, zIndex:0, pointerEvents:"none", backgroundImage:"linear-gradient(rgba(45,212,160,.013) 1px,transparent 1px),linear-gradient(90deg,rgba(45,212,160,.013) 1px,transparent 1px)", backgroundSize:"60px 60px" }} />
        <div aria-hidden style={{ position:"fixed", inset:0, zIndex:0, pointerEvents:"none" }}>
          {DOTS.map(d => <span key={d.id} style={{ position:"absolute", left:`${d.x}%`, top:`${d.y}%`, width:d.r, height:d.r, borderRadius:"50%", background:"#2dd4a0", opacity:0, animation:`ptD ${d.dur}s ease-in-out ${d.del}s infinite` }} />)}
        </div>

        {/* ━━ TOP NAV ━━ */}
        <nav style={{ position:"fixed", top:0, left:0, right:0, zIndex:50, display:"flex", alignItems:"center", justifyContent:"space-between", padding:"0 32px", height:60, background:"rgba(10,15,13,0.78)", backdropFilter:"blur(20px)", WebkitBackdropFilter:"blur(20px)", borderBottom:"1px solid #111a14", opacity:0, animation:"fu .5s ease .05s forwards" }}>
          <span style={{ fontFamily:"'Necosmic','Syne',sans-serif", fontSize:18, color:"#2dd4a0" }}>ArogyaX</span>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <Link href="/auth?mode=login" className="btn-sec" style={{ display:"inline-flex", alignItems:"center", padding:"8px 18px", borderRadius:10, background:"transparent", border:"1px solid #1c2a22", color:"#5a8070", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:13, textDecoration:"none", fontWeight:500 }}>Log In</Link>
            <Link href="/auth?mode=signup" className="btn-pri" style={{ display:"inline-flex", alignItems:"center", padding:"8px 20px", borderRadius:10, background:"linear-gradient(135deg,#059669,#2dd4a0)", color:"#051a0e", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:13, textDecoration:"none", fontWeight:700 }}>Sign Up</Link>
          </div>
        </nav>

        {/* ━━ HERO ━━ */}
        <section style={{ position:"relative", zIndex:1, minHeight:"100dvh", display:"flex", alignItems:"center", justifyContent:"center", padding:"120px 24px 96px" }}>
          <div style={{ display:"flex", flexDirection:"column", alignItems:"center", width:"100%", maxWidth:580, textAlign:"center" }}>
            <div style={{ opacity:0, animation:"fu .55s ease .2s forwards", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:12, color:"#3d5e50", letterSpacing:".15em", textTransform:"uppercase" as const, fontWeight:600, marginBottom:22 }}>
              Trusted Care, Always There
            </div>
            <h1 style={{ fontFamily:"'Necosmic','Syne',sans-serif", fontSize:"clamp(66px,16vw,124px)", lineHeight:.9, letterSpacing:"-.01em", margin:"0 0 36px", background:"linear-gradient(148deg,#e8f5f0 8%,#2dd4a0 46%,#059669 100%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent", backgroundClip:"text", filter:"drop-shadow(0 0 60px #2dd4a012)", opacity:0, animation:"fuBig .8s cubic-bezier(.34,1.1,.64,1) .35s forwards" }}>
              ArogyaX
            </h1>
            <p style={{ fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:"clamp(16px,2.6vw,20px)", color:"#6a9080", lineHeight:1.85, fontWeight:400, maxWidth:400, margin:"0 0 44px", opacity:0, animation:"fu .65s ease .8s forwards" }}>
              Your AI-powered pharmacy —<br />smarter refills, safer orders, zero hassle.
            </p>
            <div style={{ display:"flex", flexWrap:"wrap" as const, gap:9, justifyContent:"center", marginBottom:48, opacity:0, animation:"fu .55s ease 1.05s forwards" }}>
              {["Proactive Refills","Voice & Chat","Safe Rx Check","Email Alerts"].map(c=>(
                <span key={c} style={{ padding:"6px 16px", borderRadius:99, fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:11.5, border:"1px solid #1c2a22", color:"#3d5e50", background:"#0e1712", letterSpacing:".03em", fontWeight:500 }}>{c}</span>
              ))}
            </div>
            <div style={{ display:"flex", flexWrap:"wrap" as const, gap:12, justifyContent:"center", marginBottom:64, opacity:0, animation:"fu .6s ease 1.35s forwards" }}>
              <Link href="/auth?mode=signup" className="btn-pri" style={{ display:"inline-flex", alignItems:"center", gap:9, padding:"15px 34px", borderRadius:14, background:"linear-gradient(135deg,#059669,#2dd4a0)", color:"#051a0e", fontFamily:"'Montserrat',sans-serif", fontWeight:700, fontSize:15, textDecoration:"none", letterSpacing:"-.01em", boxShadow:"0 4px 28px #2dd4a028", animation:"btnG 9s ease 5s infinite" }}>
                Get Started <ArrowRight size={15} />
              </Link>
              <Link href="/admin" className="btn-sec" style={{ display:"inline-flex", alignItems:"center", gap:8, padding:"15px 26px", borderRadius:14, background:"transparent", border:"1px solid #1c2a22", color:"#5a8070", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:14, textDecoration:"none", fontWeight:500 }}>
                Admin Panel
              </Link>
            </div>
            <div style={{ display:"flex", flexDirection:"column" as const, alignItems:"center", gap:7, opacity:0, animation:"fu .5s ease 2.2s forwards", color:"#2e4538", fontFamily:"'Sofia Pro','DM Sans',sans-serif", fontSize:10, letterSpacing:".12em", textTransform:"uppercase" as const }}>
              <div style={{ width:20, height:32, border:"1px solid #1c2a22", borderRadius:10, display:"flex", justifyContent:"center", paddingTop:6 }}>
                <div style={{ width:2.5, height:7, background:"#2dd4a0", borderRadius:99, opacity:.6, animation:"sw 2.2s ease-in-out infinite" }} />
              </div>
              scroll
            </div>
          </div>
        </section>

        {/* ━━ FEATURES ━━ */}
        <div style={{ borderTop:"1px solid #111a14" }} />
        <section style={{ position:"relative", zIndex:1, padding:"96px 32px" }}>
          <div style={{ maxWidth:1100, margin:"0 auto" }}>
            <SectionHead eyebrow="What we do" title={<>Built for patients,<br />not paperwork.</>} />
            <div style={{ display:"flex", gap:16, alignItems:"stretch" }}>
              {FEATURES.map((f, i) => <FCard key={f.title} {...f} index={i} />)}
            </div>
          </div>
        </section>

        {/* ━━ HOW IT WORKS ━━ */}
        <div style={{ borderTop:"1px solid #111a14" }} />
        <section style={{ position:"relative", zIndex:1, padding:"96px 32px" }}>
          <div style={{ maxWidth:520, margin:"0 auto" }}>
            <SectionHead eyebrow="How it works" title={<>From request<br />to doorstep.</>} />
            {[
              { num:"01", label:"You speak or type",  sub:"Text or voice input",  accent:"#2dd4a0" },
              { num:"02", label:"AI understands",     sub:"Intent extraction",    accent:"#60a5fa" },
              { num:"03", label:"Safety check",       sub:"6-agent pipeline",     accent:"#f59e0b" },
              { num:"04", label:"Inventory verified", sub:"Live stock check",     accent:"#a78bfa" },
              { num:"05", label:"Order dispatched",   sub:"Email confirmation",   accent:"#34d399" },
            ].map((s, i, arr) => (
              <Step key={s.num} {...s} last={i === arr.length - 1} index={i} />
            ))}
          </div>
        </section>

        {/* ━━ BOTTOM CTA ━━ */}
        <div style={{ borderTop:"1px solid #111a14" }} />
        <BottomCTA />

        {/* ━━ FOOTER ━━ */}
        <Footer />

      </div>
    </>
  );
}