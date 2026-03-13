<div align="center">

# 🌿 ArogyaX

### AI-Powered Pharmacy Agent — Smarter Refills, Safer Orders, Zero Hassle

[![Next.js](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110-009688?style=flat-square&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-agentic-4B8BBE?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![Supabase](https://img.shields.io/badge/Supabase-auth%20%2B%20db-3ECF8E?style=flat-square&logo=supabase)](https://supabase.com)
[![Groq](https://img.shields.io/badge/Groq-Llama%203.3%2070B-F55036?style=flat-square)](https://groq.com)
[![Langfuse](https://img.shields.io/badge/Langfuse-observability-8B5CF6?style=flat-square)](https://langfuse.com)

> Built for the **Hackathon** · Trusted Care, Always There

</div>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Getting Started](#-getting-started)
  - [Prerequisites](#prerequisites)
  - [Backend Setup](#backend-setup)
  - [Frontend Setup](#frontend-setup)
  - [Supabase Setup](#supabase-setup)
- [Environment Variables](#-environment-variables)
- [Agent Pipeline](#-agent-pipeline)
- [Screenshots](#-screenshots)
- [API Reference](#-api-reference)

---

## 🌟 Overview

**ArogyaX** is a conversational pharmacy AI that lets patients order medicines through natural voice or text, enforces medication safety through a 6-agent pipeline, and proactively manages prescription refills — all with full observability via Langfuse.

Built as a hackathon project demonstrating how agentic AI can transform healthcare delivery — from a patient typing *"I need something for my headache"* to a confirmed, safety-checked order with email notification in under 3 seconds.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎙️ **Voice & Chat Ordering** | Natural language input via text or Whisper Large v3 Turbo voice transcription |
| 🔁 **Proactive Refills** | AI monitors order history and surfaces refill reminders before you run out |
| 🛡️ **6-Agent Safety Pipeline** | Every order passes contraindication, prescription, and category checks |
| 📧 **Email Notifications** | Instant SendGrid confirmation on order placement and dispatch |
| 📊 **Admin Analytics Dashboard** | Real-time KPI cards, inventory alerts, order trends, decision ledger |
| 🔐 **Full Auth Flow** | Supabase-powered signup, login, forgot password, role-based routing |
| 🔭 **Langfuse Observability** | Full trace visibility on every agent call, latency, and token usage |

---

## 🏗️ Architecture

```
User (Voice / Text)
        │
        ▼
┌───────────────────┐
│   Next.js 15      │  ← Patient Chat UI, Admin Dashboard, Auth
│   Frontend        │
└────────┬──────────┘
         │ REST API
         ▼
┌───────────────────┐
│   FastAPI         │  ← /chat, /voice, /order/confirm, /history
│   Backend         │
└────────┬──────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│           LangGraph Agent Pipeline       │
│                                          │
│  refill_analyzer → conversational        │
│       → safety_auditor → safety          │
│       → inventory → predictive           │
│       → notification                     │
└────────┬────────────────────────────────┘
         │
    ┌────┴─────────────────┐
    │                      │
    ▼                      ▼
Supabase DB           Langfuse
(products,            (traces,
 orders, users)        metrics)
```

---

## 🛠️ Tech Stack

### Frontend
- **Next.js 15** — App Router, Server Components
- **TypeScript** — full type safety
- **Supabase SSR** — auth with cookie-based sessions, role-based routing
- **Geist + Plus Jakarta Sans** — modern font stack

### Backend
- **FastAPI** — async REST API
- **LangGraph** — stateful multi-agent orchestration
- **Llama 3.3 70B** via **Groq** — ultra-fast LLM inference
- **Whisper Large v3 Turbo** via **Groq** — voice transcription
- **Langfuse** — LLM observability and tracing

### Infrastructure
- **Supabase** — PostgreSQL database + Auth + Row Level Security
- **SendGrid** — transactional email (order confirmations, password reset)
- **n8n** — workflow automation for notifications

---

## 📁 Project Structure

```
ArogyaX/
├── frontend/                          # Next.js 15 app
│   ├── app/
│   │   ├── page.tsx                   # Landing page
│   │   ├── auth/
│   │   │   ├── page.tsx               # Login / Signup / Forgot Password
│   │   │   └── callback/route.ts      # Supabase auth callback handler
│   │   ├── chat/page.tsx              # Patient chat interface
│   │   ├── admin/page.tsx             # Admin dashboard
│   │   └── reset-password/page.tsx    # Password reset form
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx         # Main chat UI
│   │   │   ├── CartReview.tsx         # Order confirmation UI
│   │   │   ├── OrderHistory.tsx       # Past orders
│   │   │   └── RefillAlertBanner.tsx  # Proactive refill alerts
│   │   └── admin/
│   │       ├── AnalyticsDashboard.tsx # KPI charts and metrics
│   │       ├── InventoryTable.tsx     # Live inventory management
│   │       ├── AlertsPanel.tsx        # Low stock / safety alerts
│   │       └── DecisionLedger.tsx     # Agent decision audit log
│   ├── hooks/
│   │   ├── useChat.ts                 # Chat state management
│   │   └── useVoice.ts                # Voice recording + transcription
│   ├── lib/
│   │   ├── api.ts                     # Backend API calls
│   │   └── supabase/
│   │       ├── client.ts              # Browser Supabase client
│   │       └── server.ts              # Server Supabase client
│   ├── middleware.ts                  # Route protection + session refresh
│   └── types/index.ts                 # Shared TypeScript types
│
├── backend/                           # FastAPI + LangGraph
│   ├── agents/
│   │   ├── graph.py                   # LangGraph pipeline definition
│   │   ├── state.py                   # Shared agent state schema
│   │   ├── conversational_agent.py    # Intent extraction + dialogue
│   │   ├── safety_auditor_agent.py    # Pre-safety category check
│   │   ├── safety_agent.py            # Contraindication + Rx check
│   │   ├── inventory_agent.py         # Stock validation
│   │   ├── predictive_agent.py        # Refill prediction
│   │   └── notification_agent.py      # Email dispatch
│   ├── routers/
│   │   ├── router_orders.py           # POST /chat, /voice, /order/confirm
│   │   ├── router_history.py          # GET /history, /analytics
│   │   ├── router_inventory.py        # GET/PATCH /inventory
│   │   └── router_alerts.py           # GET /alerts
│   ├── models/
│   │   └── order.py                   # Pydantic request/response models
│   ├── core/
│   │   └── config.py                  # Environment config
│   ├── observability/
│   │   └── langfuse_client.py         # Langfuse trace setup
│   └── main.py                        # FastAPI app entry point
│
├── supabase_auth_setup.sql            # One-time DB setup (triggers, profiles)
├── AUTH_GUIDE.md                      # Auth setup walkthrough
├── .gitignore
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- A [Supabase](https://supabase.com) project (free tier works)
- A [Groq](https://console.groq.com) API key (free tier)
- A [Langfuse](https://langfuse.com) account (free tier)
- A [SendGrid](https://sendgrid.com) account for emails (free tier)

---

### Backend Setup

```bash
# 1. Navigate to backend
cd backend

# 2. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill environment variables
cp .env.example .env
# Edit .env with your keys (see Environment Variables section)

# 5. Start the FastAPI server
uvicorn main:app --reload --port 8000
```

API docs available at: `http://localhost:8000/docs`

---

### Frontend Setup

```bash
# 1. Navigate to frontend
cd frontend

# 2. Install dependencies
npm install

# 3. Copy and fill environment variables
cp .env.example .env.local
# Edit .env.local with your Supabase keys

# 4. Start the development server
npm run dev
```

App available at: `http://localhost:3000`

---

### Supabase Setup

**1. Run the auth setup SQL**

Go to **Supabase Dashboard → SQL Editor** and run the contents of `supabase_auth_setup.sql`. This creates:
- `public.profiles` table with role-based access
- `public.users` table with patient records
- Triggers to auto-populate both on signup

**2. Configure Authentication settings**

In **Supabase Dashboard → Authentication → Settings**:
- Set **Site URL** to `http://localhost:3000`
- Add `http://localhost:3000/auth/callback` to **Redirect URLs**
- Disable **Email confirmations** for local development

**3. Configure SMTP (for password reset emails)**

In **Supabase Dashboard → Authentication → SMTP**:
```
Host:     smtp.sendgrid.net
Port:     587
Username: apikey
Password: SG.xxxxxxxxxxxxxxxx   ← your SendGrid API key
Sender:   your-verified@email.com
```

**4. Update the Password Reset email template**

In **Supabase Dashboard → Authentication → Email Templates → Reset Password**, set the link to:
```
{{ .SiteURL }}/auth/callback?token_hash={{ .TokenHash }}&type=recovery&next=/reset-password
```

**5. Promote a user to admin**

```sql
UPDATE public.profiles
SET role = 'admin'
WHERE id = (SELECT id FROM auth.users WHERE email = 'your@email.com');
```

---

## 🔐 Environment Variables

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Backend (`backend/.env`)

```env
# Groq
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx

# Supabase
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Langfuse
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com

# SendGrid
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxx
SENDGRID_FROM_EMAIL=your-verified@email.com

# App
BACKEND_URL=http://localhost:8000
```

---

## 🤖 Agent Pipeline

Every order request flows through 6 dedicated agents in sequence:

```
1. refill_analyzer      Checks if this looks like a refill vs new order
        ↓
2. conversational       Extracts medicine name, quantity, intent via LLM
        ↓
3. safety_auditor       Pre-check: does medicine category match complaint?
        ↓
4. safety               Contraindication check + prescription requirement
        ↓
5. inventory            Validates stock, resolves pack sizes, confirms price
        ↓
6. predictive           Calculates next refill date, sets reminder
        ↓
7. notification         Sends SendGrid email confirmation to patient
```

Each agent writes structured decisions to the **Decision Ledger** in Supabase, visible in the Admin Dashboard under the Audit tab.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Send a text message to the agent pipeline |
| `POST` | `/voice` | Upload audio, transcribe + process |
| `POST` | `/order/confirm` | Confirm a pending cart order |
| `GET` | `/history/{patient_id}` | Fetch order history for a patient |
| `GET` | `/history/analytics/summary` | Admin analytics summary |
| `GET` | `/inventory` | List all products with stock levels |
| `PATCH` | `/inventory/{product_id}` | Update stock quantity |
| `GET` | `/alerts` | Fetch active low-stock and safety alerts |

Full interactive docs: `http://localhost:8000/docs`

---

## 🏆 Hackathon

Built for **HACKFUSION-3** in the Healthcare AI track.

**Team:** Meowth

**Theme:** Agentic AI for accessible, safe pharmacy care

---

<div align="center">

Made with 🌿 by the ArogyaX team · *Trusted Care, Always There*

</div>
