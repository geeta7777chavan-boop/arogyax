"""
core/config.py
==============
Single source of truth for all environment variables.
Import `settings` anywhere in the backend.
"""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────────
    SUPABASE_URL:         str
    SUPABASE_ANON_KEY:    str
    SUPABASE_SERVICE_KEY: str
    SUPABASE_JWT_SECRET:  str = ""

    # ── Groq ──────────────────────────────────────────────────────────────────
    GROQ_API_KEY:        str
    GROQ_LLM_MODEL:      str = "llama-3.3-70b-versatile"
    GROQ_WHISPER_MODEL:  str = "whisper-large-v3-turbo"

    # ── Langfuse ──────────────────────────────────────────────────────────────
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_HOST:       str = "https://cloud.langfuse.com"

    # ── FastAPI ───────────────────────────────────────────────────────────────
    APP_ENV:         str = "development"
    APP_PORT:        int = 8000
    APP_HOST:        str = "0.0.0.0"
    SECRET_KEY:      str = "change-me-in-production"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # ── PrescriptoAI ─────────────────────────────────────────────────────────
    PRESCRIPTO_API_KEY: str = ""

    # ── Twilio WhatsApp ───────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID:    str = ""
    TWILIO_AUTH_TOKEN:     str = ""
    TWILIO_FROM_NUMBER:    str = ""
    TWILIO_WHATSAPP_FROM:  str = "whatsapp:+14155238886"

    # ── Alert recipients ──────────────────────────────────────────────────────
    ADMIN_PHONE_NUMBER:  str = ""
    USER_PHONE_FALLBACK: str = ""

    # ── Email — Gmail SMTP (primary) ──────────────────────────────────────────
    # Get App Password: myaccount.google.com → Security → App passwords
    EMAIL_FROM:          str = "arogyax213@gmail.com"
    EMAIL_FROM_NAME:     str = "ArogyaX"
    GMAIL_APP_PASSWORD:  str = ""   # 16-char Google App Password (local dev)
    RESEND_API_KEY:      str = ""   # re_xxxxxxxx — production (Railway/Render)

    # ── SendGrid (kept for fallback / legacy — not used if GMAIL_APP_PASSWORD set) ──
    SENDGRID_API_KEY:  str = ""
    GMAIL_SMTP_USER:   str = ""
    GMAIL_SMTP_PASS:   str = ""
    SMTP_PORT:         int = 587

    # ── Webhooks ──────────────────────────────────────────────────────────────
    WAREHOUSE_WEBHOOK_URL:    str  = ""
    WAREHOUSE_WEBHOOK_SECRET: str  = "mock-secret"
    MOCK_WEBHOOKS:            bool = True

    # ── Feature flags ─────────────────────────────────────────────────────────
    ENABLE_VOICE:               bool = True
    ENABLE_WHATSAPP:            bool = True
    ENABLE_EMAIL_NOTIFICATIONS: bool = True

    # ── Thresholds ────────────────────────────────────────────────────────────
    LOW_STOCK_THRESHOLD:     int = 10
    REFILL_ALERT_DAYS:       int = 7
    REFILL_ALERT_DAYS_AHEAD: int = 30

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def twilio_enabled(self) -> bool:
        return bool(
            self.ENABLE_WHATSAPP
            and self.TWILIO_ACCOUNT_SID
            and self.TWILIO_AUTH_TOKEN
            and self.TWILIO_WHATSAPP_FROM
        )

    class Config:
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        extra    = "ignore"


settings = Settings()