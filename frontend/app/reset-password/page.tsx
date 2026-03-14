"use client";
export const dynamic = "force-dynamic";
// app/reset-password/page.tsx
// User lands here after clicking the reset link in their email.
// Supabase has already exchanged the token in /auth/callback and set a session.
// Fallback: if hash-fragment flow was used, we pick up tokens from sessionStorage.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff, ArrowRight, Loader2, CheckCircle2, AlertCircle, ShieldAlert } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

/* ─── Password strength ─────────────────────────────────────────────────── */
function PasswordStrength({ password }: { password: string }) {
  if (!password) return null;
  const checks = [
    { label: "8+ characters",    pass: password.length >= 8    },
    { label: "Uppercase letter", pass: /[A-Z]/.test(password)  },
    { label: "Lowercase letter", pass: /[a-z]/.test(password)  },
    { label: "Number or symbol", pass: /[\d\W]/.test(password) },
  ];
  const score  = checks.filter(c => c.pass).length;
  const colors = ["", "#ef4444", "#f59e0b", "#3b82f6", "#2dd4a0"];
  const levels = ["", "Weak", "Fair", "Good", "Strong"];
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ display: "flex", gap: 4, marginBottom: 8 }}>
        {[1,2,3,4].map(i => (
          <div key={i} style={{ flex:1, height:3, borderRadius:99, background: i <= score ? colors[score] : "#1a2820", transition:"background .3s" }} />
        ))}
      </div>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <div style={{ display:"flex", flexWrap:"wrap" as const, gap:"4px 12px" }}>
          {checks.map(c => (
            <span key={c.label} style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:10.5, fontWeight:500, color: c.pass ? "#2dd4a0" : "#3d5e50", display:"flex", alignItems:"center", gap:4, transition:"color .2s" }}>
              <span style={{ fontSize:10 }}>{c.pass ? "✓" : "·"}</span>{c.label}
            </span>
          ))}
        </div>
        {score > 0 && <span style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:10.5, fontWeight:700, color:colors[score], marginLeft:8 }}>{levels[score]}</span>}
      </div>
    </div>
  );
}

/* ─── Password input ────────────────────────────────────────────────────── */
function PasswordField({ label, value, onChange, placeholder, autoComplete, error }: {
  label: string; value: string; onChange: (v: string) => void;
  placeholder?: string; autoComplete?: string; error?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
      <label style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:12, color:"#6a9080", fontWeight:600, letterSpacing:".04em" }}>{label}</label>
      <div style={{ position:"relative" }}>
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete={autoComplete}
          style={{ width:"100%", boxSizing:"border-box" as const, padding:"12px 44px 12px 16px", borderRadius:12, background:"#0c1710", border:`1px solid ${error ? "#ef4444" : "#1a2820"}`, color:"#e8f5f0", fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:14, outline:"none", transition:"border-color .2s" }}
          onFocus={e => { if (!error) e.target.style.borderColor = "#2dd4a040"; }}
          onBlur={e  => { if (!error) e.target.style.borderColor = "#1a2820"; }}
        />
        <button type="button" onClick={() => setShow(s => !s)}
          style={{ position:"absolute", right:14, top:"50%", transform:"translateY(-50%)", background:"none", border:"none", cursor:"pointer", color:"#3d5e50", padding:0, display:"flex" }}>
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
      {error && <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:11, color:"#ef4444", marginTop:2 }}>{error}</p>}
    </div>
  );
}

/* ─── Main page ─────────────────────────────────────────────────────────── */
export default function ResetPasswordPage() {
  const router   = useRouter();
  const supabase = createClient();

  const [ready,     setReady]     = useState(false);   // session verified
  const [invalid,   setInvalid]   = useState(false);   // link expired / bad
  const [password,  setPassword]  = useState("");
  const [confirm,   setConfirm]   = useState("");
  const [loading,   setLoading]   = useState(false);
  const [success,   setSuccess]   = useState(false);
  const [globalErr, setGlobalErr] = useState("");
  const [errors,    setErrors]    = useState<Record<string,string>>({});

  /* ── On mount: ensure we have a valid recovery session ─────────────── */
  useEffect(() => {
    async function init() {
      // Case 1: PKCE flow — session already set by /auth/callback server route
      const { data: { session } } = await supabase.auth.getSession();
      if (session) { setReady(true); return; }

      // Case 2: Hash-fragment / implicit flow — tokens stored in sessionStorage
      // by the client-side HTML snippet in /auth/callback
      const accessToken  = sessionStorage.getItem("sb_access_token");
      const refreshToken = sessionStorage.getItem("sb_refresh_token");
      if (accessToken) {
        sessionStorage.removeItem("sb_access_token");
        sessionStorage.removeItem("sb_refresh_token");
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken ?? "",
        });
        if (!error) { setReady(true); return; }
      }

      // No valid session — link is expired or was already used
      setInvalid(true);
    }
    init();
  }, []);

  function validate() {
    const e: Record<string,string> = {};
    if (password.length < 8)      e.password = "Password must be at least 8 characters";
    if (password !== confirm)      e.confirm  = "Passwords do not match";
    return e;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setGlobalErr("");
    const errs = validate();
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setLoading(true);
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) throw error;
      setSuccess(true);
      setTimeout(() => router.replace("/auth?mode=login"), 3000);
    } catch (err: any) {
      setGlobalErr(err?.message ?? "Something went wrong. Please request a new reset link.");
    } finally {
      setLoading(false);
    }
  }

  /* ── Loading state ───────────────────────────────────────────────────── */
  if (!ready && !invalid) {
    return (
      <PageWrapper>
        <div style={{ textAlign:"center", padding:"24px 0" }}>
          <Loader2 size={28} style={{ color:"#2dd4a0", animation:"spin .8s linear infinite", margin:"0 auto 16px", display:"block" }} />
          <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:14, color:"#4a6b5e" }}>Verifying your reset link…</p>
        </div>
      </PageWrapper>
    );
  }

  /* ── Invalid / expired link ──────────────────────────────────────────── */
  if (invalid) {
    return (
      <PageWrapper>
        <div style={{ textAlign:"center", padding:"8px 0" }}>
          <div style={{ width:56, height:56, borderRadius:"50%", background:"#1a0c0c", border:"1px solid #ef444430", display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 24px", color:"#ef4444" }}>
            <ShieldAlert size={24} />
          </div>
          <h2 style={{ fontFamily:"'Syne',sans-serif", fontWeight:800, fontSize:22, color:"#e8f5f0", marginBottom:12, letterSpacing:"-.02em" }}>
            Link expired
          </h2>
          <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:14, color:"#5a8070", lineHeight:1.7 }}>
            This password reset link has expired or already been used.<br />
            Reset links are valid for <strong style={{ color:"#8aada0" }}>1 hour</strong>.
          </p>
          <Link href="/auth?mode=forgot"
            style={{ display:"inline-flex", alignItems:"center", gap:8, marginTop:28, padding:"11px 28px", borderRadius:12, background:"linear-gradient(135deg,#059669,#2dd4a0)", color:"#051a0e", fontFamily:"'Syne',sans-serif", fontWeight:700, fontSize:14, textDecoration:"none" }}>
            Request a new link <ArrowRight size={14} />
          </Link>
        </div>
      </PageWrapper>
    );
  }

  /* ── Success screen ──────────────────────────────────────────────────── */
  if (success) {
    return (
      <PageWrapper>
        <div style={{ textAlign:"center", padding:"8px 0" }}>
          <div style={{ width:60, height:60, borderRadius:"50%", background:"#2dd4a012", border:"1px solid #2dd4a030", display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 24px", color:"#2dd4a0" }}>
            <CheckCircle2 size={28} />
          </div>
          <h2 style={{ fontFamily:"'Syne',sans-serif", fontWeight:800, fontSize:22, color:"#e8f5f0", marginBottom:12, letterSpacing:"-.02em" }}>
            Password updated!
          </h2>
          <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:14, color:"#5a8070", lineHeight:1.7 }}>
            Your password has been changed successfully.<br />
            You can now log in with your new password.
          </p>
          <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:12, color:"#3d5e50", marginTop:12 }}>
            Redirecting to login in a moment…
          </p>
          <Link href="/auth?mode=login"
            style={{ display:"inline-flex", alignItems:"center", gap:8, marginTop:24, padding:"11px 28px", borderRadius:12, background:"linear-gradient(135deg,#059669,#2dd4a0)", color:"#051a0e", fontFamily:"'Syne',sans-serif", fontWeight:700, fontSize:14, textDecoration:"none" }}>
            Go to Log In <ArrowRight size={14} />
          </Link>
        </div>
      </PageWrapper>
    );
  }

  /* ── Set new password form ───────────────────────────────────────────── */
  return (
    <PageWrapper>
      <div style={{ marginBottom:28 }}>
        <h1 style={{ fontFamily:"'Syne',sans-serif", fontWeight:800, fontSize:24, color:"#e8f5f0", letterSpacing:"-.03em", marginBottom:8 }}>
          Set new password
        </h1>
        <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:13, color:"#4a6b5e", lineHeight:1.6 }}>
          Choose a strong password. At least 8 characters with a mix of letters, numbers, and symbols.
        </p>
      </div>

      {globalErr && (
        <div style={{ display:"flex", alignItems:"flex-start", gap:10, padding:"12px 14px", borderRadius:10, background:"#1a0c0c", border:"1px solid #ef444430", marginBottom:22 }}>
          <AlertCircle size={15} style={{ color:"#ef4444", flexShrink:0, marginTop:1 }} />
          <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:13, color:"#fca5a5", margin:0 }}>{globalErr}</p>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display:"flex", flexDirection:"column", gap:18 }}>
        <div>
          <PasswordField label="New Password" value={password} onChange={setPassword}
            placeholder="Min. 8 characters" autoComplete="new-password" error={errors.password} />
          <PasswordStrength password={password} />
        </div>

        <div>
          <PasswordField label="Confirm New Password" value={confirm} onChange={setConfirm}
            placeholder="Repeat your password" autoComplete="new-password" error={errors.confirm} />
          {confirm.length > 0 && !errors.confirm && (
            <p style={{ fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:11, color: password === confirm ? "#2dd4a0" : "#4a6b5e", marginTop:6, display:"flex", alignItems:"center", gap:4 }}>
              {password === confirm
                ? <><span>✓</span> Passwords match</>
                : <><span>·</span> Passwords don't match yet</>}
            </p>
          )}
        </div>

        <button type="submit" disabled={loading}
          style={{ marginTop:4, display:"flex", alignItems:"center", justifyContent:"center", gap:9, padding:"13px 0", borderRadius:13, background: loading ? "#0d3326" : "linear-gradient(135deg,#059669,#2dd4a0)", color:"#051a0e", border:"none", fontFamily:"'Syne',sans-serif", fontWeight:700, fontSize:15, cursor: loading ? "not-allowed" : "pointer", transition:"all .2s", boxShadow: loading ? "none" : "0 4px 24px #2dd4a028" }}>
          {loading
            ? <><Loader2 size={16} style={{ animation:"spin .8s linear infinite" }} /> Updating password…</>
            : <>Update Password <ArrowRight size={15} /></>
          }
        </button>
      </form>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </PageWrapper>
  );
}

/* ─── Page wrapper ──────────────────────────────────────────────────────── */
function PageWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ minHeight:"100dvh", background:"#0a0f0d", display:"flex", alignItems:"center", justifyContent:"center", padding:"32px 16px", position:"relative", overflow:"hidden" }}>
      <div style={{ position:"fixed", inset:0, pointerEvents:"none" }}>
        <div style={{ position:"absolute", width:500, height:500, borderRadius:"50%", filter:"blur(90px)", background:"radial-gradient(circle,#0d4430 0%,transparent 65%)", top:-160, left:-140, opacity:.45 }} />
        <div style={{ position:"absolute", width:360, height:360, borderRadius:"50%", filter:"blur(80px)", background:"radial-gradient(circle,#064e3b 0%,transparent 65%)", bottom:-100, right:-80, opacity:.35 }} />
      </div>

      <div style={{ position:"relative", zIndex:1, width:"100%", maxWidth:420 }}>
        <Link href="/" style={{ display:"block", textAlign:"center", marginBottom:32, textDecoration:"none" }}>
          <span style={{ fontFamily:"'Necosmic','Syne',sans-serif", fontSize:28, background:"linear-gradient(148deg,#e8f5f0 8%,#2dd4a0 46%,#059669 100%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent", backgroundClip:"text" }}>
            ArogyaX
          </span>
        </Link>

        <div style={{ background:"#0e1812", border:"1px solid #1a2820", borderRadius:20, padding:"36px 32px", boxShadow:"0 24px 80px #00000050" }}>
          {children}
        </div>

        <p style={{ textAlign:"center", marginTop:20, fontFamily:"'Plus Jakarta Sans',sans-serif", fontSize:11, color:"#2a3e34" }}>
          Trusted Care, Always There · ArogyaX © 2026
        </p>
      </div>

      <style>{`
        @import url('https://fonts.cdnfonts.com/css/necosmic');
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
        @keyframes spin { to { transform: rotate(360deg); } }
        input::placeholder { color: #2a3e34; }
        input:-webkit-autofill { -webkit-box-shadow: 0 0 0 40px #0c1710 inset !important; -webkit-text-fill-color: #e8f5f0 !important; }
      `}</style>
    </div>
  );
}

