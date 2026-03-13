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
    PRESCRIPTO_API_KEY: str = ""   # sk_live_...

    # ── Twilio WhatsApp ───────────────────────────────────────────────────────
    TWILIO_ACCOUNT_SID:    str  = ""
    TWILIO_AUTH_TOKEN:     str  = ""
    TWILIO_FROM_NUMBER:    str  = ""                        # SMS fallback number
    TWILIO_WHATSAPP_FROM:  str  = "whatsapp:+14155238886"   # sandbox (do not change)

    # ── Alert recipients ──────────────────────────────────────────────────────
    ADMIN_PHONE_NUMBER:    str  = ""   # +91xxxxxxxxxx — WhatsApp/SMS, no prefix
    USER_PHONE_FALLBACK:   str  = ""   # +91xxxxxxxxxx — used if patient has no phone on file

    # ── SendGrid ──────────────────────────────────────────────────────────────
    SENDGRID_API_KEY:  str = ""
    EMAIL_FROM:        str = "noreply@pharmai.in"
    EMAIL_FROM_NAME:   str = "PharmAI"

    # ── SMTP Fallback (Gmail/Outlook) ────────────────────────────────────────
    GMAIL_SMTP_USER:   str = ""
    GMAIL_SMTP_PASS:   str = ""
    SMTP_PORT:         int  = 587


    # ── Webhooks ──────────────────────────────────────────────────────────────
    WAREHOUSE_WEBHOOK_URL:    str  = ""
    WAREHOUSE_WEBHOOK_SECRET: str  = "mock-secret"
    MOCK_WEBHOOKS:            bool = True

    # ── Feature flags ─────────────────────────────────────────────────────────
    ENABLE_VOICE:               bool = True
    ENABLE_WHATSAPP:            bool = True    # ← must be True for WhatsApp to send
    ENABLE_EMAIL_NOTIFICATIONS: bool = True

    # ── Thresholds ────────────────────────────────────────────────────────────
    LOW_STOCK_THRESHOLD:     int = 10    # alert admin when stock drops below N units
    REFILL_ALERT_DAYS:       int = 7     # alert patient when refill due within N days
    REFILL_ALERT_DAYS_AHEAD: int = 30    # predictive_agent scan window

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def twilio_enabled(self) -> bool:
        """
        True only when:
        - ENABLE_WHATSAPP = True  (feature flag)
        - TWILIO_ACCOUNT_SID set
        - TWILIO_AUTH_TOKEN set
        - TWILIO_WHATSAPP_FROM set (for WhatsApp channel)
        """
        return bool(
            self.ENABLE_WHATSAPP
            and self.TWILIO_ACCOUNT_SID
            and self.TWILIO_AUTH_TOKEN
            and self.TWILIO_WHATSAPP_FROM
        )

    class Config:
        # Resolves to D:/Agent/.env regardless of where the process is run from
        env_file = Path(__file__).resolve().parent.parent.parent / ".env"
        extra    = "ignore"


settings = Settings()