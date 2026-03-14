"""
main.py
=======
FastAPI application entrypoint.

Start:
    python run.py          (from D:/Agent/)
    uvicorn main:app --reload --port 8000  (from D:/Agent/backend/)
"""

import os
import sys
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

# Optional: APScheduler for daily refill scans
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    SchedulerAvailable = True
except ImportError:
    SchedulerAvailable = False
    AsyncIOScheduler = None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ── Ensure backend/ is always on sys.path ─────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from core.config import settings

# ── Groq connection test ──────────────────────────────────────────────────────
from langchain_groq import ChatGroq
try:
    ChatGroq(model=settings.GROQ_LLM_MODEL, api_key=settings.GROQ_API_KEY).invoke("ping")
    print("    Groq LLM    : ✅ connected")
except Exception as e:
    print(f"    Groq LLM    : ❌ FAILED — {e}")

# ── Import every router directly (no __init__.py dependency) ──────────────────
from routers.orders        import router as orders_router
from routers.inventory     import router as inventory_router
from routers.history       import router as history_router
from routers.alerts        import router as alerts_router
from routers.decisions     import router as decisions_router
from routers.webhooks      import router as webhooks_router
from routers.prescriptions import router as prescriptions_router


# ── Scheduler for automatic refill checks ─────────────────────────────────────
scheduler = AsyncIOScheduler() if AsyncIOScheduler else None

async def run_daily_refill_scan():
    """Daily task to scan for medications due for refill and send emails."""
    from services.email_service import run_proactive_refill_scan
    print("\n[Scheduler] Running daily proactive refill scan...")
    try:
        result = run_proactive_refill_scan(alert_days=7)
        print(f"[Scheduler] Refill scan complete: {result}")
    except Exception as e:
        print(f"[Scheduler] Refill scan failed: {e}")


# ── Timeout Middleware ────────────────────────────────────────────────────────
class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=120.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                {"detail": "Request timed out. The AI pipeline took too long — please try again."},
                status_code=504,
            )


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"\n🚀  ArogyaX backend starting — env: {settings.APP_ENV}")
    print(f"    Supabase       : {settings.SUPABASE_URL}")
    print(f"    LLM model      : {settings.GROQ_LLM_MODEL}")
    print(f"    Whisper        : {settings.GROQ_WHISPER_MODEL}")
    print(f"    Langfuse       : {settings.LANGFUSE_HOST}")
    print(f"    Mock webhooks  : {settings.MOCK_WEBHOOKS}")
    print(f"    PrescriptoAI   : {'✅ configured' if getattr(settings,'PRESCRIPTO_API_KEY','') else '❌ PRESCRIPTO_API_KEY not set'}")
    print(f"    WhatsApp       : {'✅ enabled' if settings.twilio_enabled else '⚠️  disabled (check .env)'}")
    print(f"    Email          : {'✅ enabled' if settings.ENABLE_EMAIL_NOTIFICATIONS else '⚠️  disabled'}")

    if settings.ENABLE_EMAIL_NOTIFICATIONS and scheduler:
        scheduler.add_job(run_daily_refill_scan, 'cron', hour=9, minute=0)
        scheduler.start()
        print(f"    Refill Scanner : ✅ Scheduled daily at 9 AM\n")
    else:
        print(f"    Refill Scanner : ⚠️  disabled (email notifications off)\n")

    yield

    if scheduler:
        scheduler.shutdown()
    print("\n👋  ArogyaX backend shutting down.")


# ── CORS origins ──────────────────────────────────────────────────────────────
# Reads FRONTEND_URL from environment so production URL is set via Railway
# env vars without changing code.
#
# Railway env var to add:
#   FRONTEND_URL = https://arogyax.vercel.app   (your actual Vercel URL)

_frontend_url = os.getenv("FRONTEND_URL", "")

ALLOWED_ORIGINS = [
    # Local development
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    # Production — injected via FRONTEND_URL env var on Railway
    *([_frontend_url] if _frontend_url else []),
]

# Allow all Vercel preview + production URLs via regex
# Handles: arogyax-2bt1.vercel.app AND arogyax-2bt1-xyz-prachi.vercel.app
import re as _re

def _is_allowed_origin(origin: str) -> bool:
    if origin in ALLOWED_ORIGINS:
        return True
    if _re.match(r"https://arogyax.*\.vercel\.app$", origin):
        return True
    return False


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "ArogyaX — AI Pharmacy API",
    description = (
        "Multi-agent pharmacy backend.\n\n"
        "**Agents:** Conversational → Safety → Inventory → Predictive → Notification\n\n"
        "**OCR:** PrescriptoAI (cloud, multilingual)\n\n"
        "**Observability:** Every decision logged to `/decisions` and Langfuse.\n\n"
        "**Auto-Refill:** Daily scan for medication refills at 9 AM."
    ),
    version  = "1.0.0",
    lifespan = lifespan,
    docs_url = "/docs",
    redoc_url= "/redoc",
)

# ── Middleware (TimeoutMiddleware must wrap everything) ───────────────────────
app.add_middleware(TimeoutMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # handled by allow_origin_regex below
    allow_origin_regex = r"https://arogyax.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials = False,   # must be False when allow_origins=["*"]
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── Register routers ──────────────────────────────────────────────────────────
app.include_router(orders_router)
app.include_router(inventory_router)
app.include_router(history_router)
app.include_router(prescriptions_router)
app.include_router(alerts_router)
app.include_router(decisions_router)
app.include_router(webhooks_router)

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def root():
    return {
        "service": "ArogyaX AI Pharmacy",
        "status" : "running",
        "version": "1.0.0",
        "docs"   : "/docs",
    }

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "env": settings.APP_ENV}

# ── Manual Refill Scan Trigger (for testing) ─────────────────────────────────
@app.post("/admin/trigger-refill-scan", tags=["Admin"])
async def trigger_refill_scan(alert_days: int = 7):
    """Manually trigger the proactive refill scan for testing."""
    from services.email_service import run_proactive_refill_scan

    if not settings.ENABLE_EMAIL_NOTIFICATIONS:
        return {"status": "disabled", "message": "Set ENABLE_EMAIL_NOTIFICATIONS=true in .env"}

    try:
        result = run_proactive_refill_scan(alert_days=alert_days)
        return {
            "status" : "success",
            "message": f"Checked {result.get('total_checked', 0)} patients",
            "result" : result,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin/scheduler-status", tags=["Admin"])
def scheduler_status():
    """Get scheduler status."""
    if not scheduler:
        return {
            "scheduler_running"          : False,
            "jobs_count"                 : 0,
            "jobs"                       : [],
            "scheduler_available"        : False,
            "email_notifications_enabled": settings.ENABLE_EMAIL_NOTIFICATIONS,
        }
    jobs = scheduler.get_jobs()
    return {
        "scheduler_running"          : scheduler.running,
        "jobs_count"                 : len(jobs),
        "jobs"                       : [
            {
                "id"      : j.id,
                "name"    : j.name,
                "next_run": str(j.next_run_time) if j.next_run_time else None,
            }
            for j in jobs
        ],
        "scheduler_available"        : True,
        "email_notifications_enabled": settings.ENABLE_EMAIL_NOTIFICATIONS,
    }
    }