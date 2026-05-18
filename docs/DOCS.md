# AI Job Hunter — Complete Documentation

> A production-ready, multi-tenant SaaS job application automation platform that runs entirely on local Docker containers. Scrapes 8 job portals, discovers HR emails, scores jobs with AI, generates personalised cover letters via LangGraph, and manages applications through a Next.js dashboard — with a Claude MCP admin console for real-time system management.

---

## Table of Contents

1. [Project Summary](#1-project-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Tech Stack & Versions](#3-tech-stack--versions)
4. [Folder & File Structure](#4-folder--file-structure)
5. [Services Deep Dive](#5-services-deep-dive)
6. [AI Flow](#6-ai-flow)
7. [Job Automation Flow (End-to-End)](#7-job-automation-flow-end-to-end)
8. [Database Schema](#8-database-schema)
9. [Celery Tasks & Beat Schedule](#9-celery-tasks--beat-schedule)
10. [API Reference](#10-api-reference)
11. [Configuration (infra/.env)](#11-configuration-infraenv)
12. [Infrastructure & Docker](#12-infrastructure--docker)
13. [MCP Admin Console](#13-mcp-admin-console)
14. [Logging & Observability](#14-logging--observability)
15. [Running the Project](#15-running-the-project)
16. [Development Guide](#16-development-guide)

---

## 1. Project Summary

**AI Job Hunter** automates the entire job application lifecycle for software developers as a **multi-tenant SaaS platform**. Everything runs inside local Docker containers — no external databases, no managed message queues.

```
Scrape Jobs → Score with AI → Discover HR Emails → Generate Cover Letters → Send Applications → Track Delivery
```

Configure your candidate profile once (skills, target roles, target locations), and the system:

- Searches **8 active job portals** every 2 hours for matching roles
- Scores each job 0–100 using LangChain structured output (Groq `llama-3.3-70b-versatile`)
- Filters out irrelevant jobs below a configurable score threshold (default: 60)
- Crawls company websites and uses DuckDuckGo + Hunter.io + Snov.io to discover HR emails
- Generates a personalised cover letter using a LangGraph workflow + Groq
- Attaches your resume (Cloudflare R2 or local path) and sends the application via Brevo/Mailtrap/SMTP
- Tracks opens, clicks, and delivery via webhooks
- Exposes a **Next.js dashboard** (port 3001) and a **REST API** (port 8001)
- Provides a **Claude MCP admin console** for real-time system monitoring

> **Auto-send is disabled by default** (`AUTO_SEND_ENABLED=false`). All applications require manual approval via the dashboard or the MCP console.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Docker Compose (local)                            │
│                                                                          │
│  ┌──────────┐   ┌──────────────────────────────────────────┐  ┌───────┐ │
│  │  API     │   │        Celery Workers (11 types)          │  │ Dash  │ │
│  │ FastAPI  │   │  scraping-bulk  ×2 ──→ RabbitMQ          │  │Next.js│ │
│  │  :8001   │   │  scraping-rt    ×2 ──→ RabbitMQ          │  │ :3001 │ │
│  └────┬─────┘   │  enrichment     ×3 ──→ RabbitMQ          │  └───────┘ │
│       │         │  maintenance    ×1 ──→ Redis              │            │
│  ┌────┴─────┐   │  cover-bulk     ×2 ──→ Redis              │            │
│  │  Beat    │   │  cover-ranking  ×2 ──→ Redis              │            │
│  │Scheduler │   │  cover-gen      ×3 ──→ Redis              │            │
│  └──────────┘   │  cover-workflow ×2 ──→ Redis              │            │
│                 │  cover-batch    ×1 ──→ Redis              │            │
│  ┌───────────┐  │  email          ×2 ──→ Redis              │            │
│  │  Flower   │  └──────────────────────────────────────────┘            │
│  │   :5555   │                                                           │
│  └───────────┘                                                           │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │  Local Infrastructure                                            │    │
│  │  PostgreSQL 16 (pgvector) │ RabbitMQ 3.13 │ Redis 7 │ Ollama   │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌─────────────────────┐   ┌──────────────────┐                         │
│  │  docker-agent       │   │  alembic          │                         │
│  │  (Redis sidecar)    │   │  (migrations)     │                         │
│  └─────────────────────┘   └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
                │                               │
        ┌───────▼──────┐              ┌─────────▼────────┐
        │ Cloudflare R2│              │   Groq API        │
        │ (Resumes PDF)│              │  (LLM inference)  │
        └──────────────┘              └──────────────────┘
                │
        ┌───────▼──────┐
        │  Brevo/SMTP  │
        │ (Email send) │
        └──────────────┘

MCP Admin Console (Claude Desktop / Claude Code):
  FastMCP → job-hunter-admin server → 19 tool modules → API :8001 + Redis + RabbitMQ
```

**Data Flow:**
1. Beat scheduler dispatches tasks every 2h (scrape) / 15min (enrichment) / 4h (cover refresh) to RabbitMQ and Redis
2. Scraping workers consume from RabbitMQ queues; AI/email workers consume from Redis queues
3. Scraped jobs → PostgreSQL 16 (pgvector); vectors stored locally in JSON or pgvector
4. LangGraph workflow: score ≥ threshold → cover letter → manual approval gate → send
5. Email send via Brevo/Mailtrap/SMTP; delivery events tracked via webhooks
6. Structured JSON logs written to `backend/logs/` (rotated at 50 MB)
7. Langfuse (optional) captures all LLM traces

---

## 3. Tech Stack & Versions

### Python Backend

| Package | Version | Purpose |
|---------|---------|---------|
| Python | 3.11 | Runtime |
| FastAPI | 0.111.0 | REST API framework |
| Uvicorn | 0.29.0 | ASGI server |
| SQLAlchemy | 2.0.30 | Async ORM |
| asyncpg | 0.29.0 | PostgreSQL async driver |
| pgvector | 0.3.6 | PostgreSQL vector extension client |
| Alembic | 1.13.1 | Database migrations |
| Pydantic | 2.9.2 | Data validation & serialisation |
| Celery | 5.4.0 | Distributed task queue |
| Flower | 2.0.1 | Celery monitoring UI |
| Redis | 5.0.4 | Cache, result backend, rate limiting |
| boto3 | 1.34.100 | S3/Cloudflare R2 client |
| httpx | 0.27.0 | Async HTTP client |
| structlog | 24.1.0 | Structured JSON logging |
| openai | 1.30.1 | Groq API (OpenAI-compatible SDK) |
| langchain-core | 0.2.43 | LangChain framework |
| langchain-groq | 0.1.9 | Groq LLM integration |
| langgraph | 0.2.27 | Workflow state machine |
| langchain-community | 0.2.16 | Community integrations |
| langfuse | >=4.0.0 | LLM observability (optional) |
| pypdf | 4.3.1 | Resume PDF parsing |
| Playwright | 1.50.0 | Browser automation (scraping) |
| BeautifulSoup4 | 4.12.3 | HTML parsing |
| lxml | 5.2.1 | XML/HTML processing |
| python-jose | 3.3.0 | JWT tokens |
| passlib | 1.7.4 | Password hashing |
| razorpay | 1.4.2 | Billing / subscriptions |
| prometheus-client | 0.20.0 | Metrics exposure |
| prometheus-fastapi-instrumentator | latest | FastAPI request metrics |
| ollama | 0.2.1 | Local embedding client |
| dnspython | 2.6.1 | DNS lookups for email discovery |

### Frontend

| Package | Version | Purpose |
|---------|---------|---------|
| Next.js | 14.2.3 | React framework (App Router) |
| React | 18.3.1 | UI library |
| TypeScript | 5 | Type safety |
| Tailwind CSS | 3.4.3 | Utility-first CSS |
| Axios | 1.7.2 | HTTP client |
| Recharts | 2.12.7 | Dashboard charts |
| Lucide React | 0.379.0 | Icon library |
| date-fns | 3.6.0 | Date utilities |
| react-hot-toast | 2.4.1 | Toast notifications |
| Framer Motion | latest | Animations |

### Infrastructure (all local Docker)

| Service | Image | Purpose |
|---------|-------|---------|
| PostgreSQL 16 | `pgvector/pgvector:pg16` | Primary database with vector search |
| RabbitMQ 3.13 | `rabbitmq:3.13-management-alpine` | High-volume scraping task broker |
| Redis 7 | `redis:7-alpine` | Result backend, cache, AI/email task broker |
| Ollama | `ollama/ollama:latest` | Local LLM for embeddings (nomic-embed-text) |
| Watchtower | `containrrr/watchtower:1.7.1` | Container restart monitor |

### External Services (optional)

| Service | Purpose |
|---------|---------|
| Groq API | LLM inference (cover letters, scoring) — required |
| Brevo / Mailtrap / SMTP | Email sending — one required |
| Cloudflare R2 | Resume PDF storage — optional (local fallback exists) |
| Hunter.io | HR email discovery — optional |
| Snov.io | HR email discovery — optional |
| Langfuse | LLM trace observability — optional |
| Razorpay | Billing — optional |

### LLM & AI

| Provider | Model | Purpose |
|----------|-------|---------|
| Groq | llama-3.3-70b-versatile | Job scoring, cover letters, company name extraction |
| Ollama (local) | nomic-embed-text (768d) | Text embeddings — no API key needed |
| LangGraph | — | Application workflow state machine |
| Langfuse | — | LLM trace observability (optional) |

---

## 4. Folder & File Structure

```
ai-job-hunter/
│
├── backend/                          # Python backend code, tests, migrations, logs
│   ├── services/                     # Import root for all Python services
│   │   ├── api/                      # FastAPI REST backend (port 8001)
│   │   │   ├── core/                 # DB, auth, cache, security, dependencies, config
│   │   │   │   └── config.py         # All settings (Pydantic BaseSettings)
│   │   │   ├── models/db.py          # SQLAlchemy ORM (11 tables, multi-tenant)
│   │   │   ├── repositories/         # Data access layer
│   │   │   ├── routers/              # 13 endpoint groups
│   │   │   ├── schemas/              # Pydantic request/response models
│   │   │   └── services/             # Business logic (auth, billing, admin)
│   │   ├── ai/                       # AI/ML tasks + LangGraph workflow
│   │   │   ├── tasks.py              # Cover letter, embedding, workflow Celery tasks
│   │   │   ├── scoring.py            # Rule-based pre-filter + LangChain LLM scoring
│   │   │   ├── workflow.py           # LangGraph state machine (score→cover→approve→send)
│   │   │   ├── langchain_adapter.py  # LangChain + Groq integration
│   │   │   ├── llm_adapter.py        # LLM provider abstraction (Groq / Ollama)
│   │   │   ├── vector_adapter.py     # Vector DB (pgvector / local JSON)
│   │   │   ├── rate_limiter.py       # Redis sliding-window rate limiter (Groq RPM)
│   │   │   ├── resume_parser.py      # Resume PDF parsing (pypdf)
│   │   │   ├── cover_letter.py       # Cover letter generation logic
│   │   │   ├── observability.py      # Langfuse tracing (optional)
│   │   │   └── schemas.py            # Pydantic output models (JobRelevanceScore, etc.)
│   │   ├── common/                   # Shared utilities
│   │   │   ├── logging.py            # Structlog JSON config with rotation
│   │   │   ├── async_utils.py        # Async context managers
│   │   │   ├── batch_publisher.py    # Batch task publishing
│   │   │   ├── cron_monitor.py       # Cron execution tracking (pre/post state)
│   │   │   ├── cron_validators.py    # Cron schedule validation
│   │   │   └── placeholder_emails.py # Filter test/placeholder email addresses
│   │   ├── scraper/                  # Job scraping Celery tasks + portal adapters
│   │   │   ├── celery_app.py         # Celery config (hybrid RabbitMQ + Redis)
│   │   │   ├── tasks.py              # Scraping, enrichment, maintenance tasks
│   │   │   ├── base_adapter.py       # Abstract adapter (HTTP, dedup, email extraction)
│   │   │   ├── date_filter.py        # Posted-date parsing and filtering
│   │   │   ├── task_dispatcher.py    # Task routing logic
│   │   │   └── adapters/             # 8 active + 18 disabled portal adapters (see §5.2)
│   │   └── sender/                   # Email sending Celery tasks
│   │       ├── tasks.py              # send_application_email_task, retry logic
│   │       ├── email_adapter.py      # Brevo / Mailtrap / SMTP adapters + factory
│   │       ├── template.py           # HTML + plain-text email rendering
│   │       └── resume_fetcher.py     # Fetch PDF from R2 or local path
│   ├── alembic/                      # 27 database migrations
│   ├── tests/                        # Unit and integration tests
│   │   ├── unit/                     # Parser, email, vector, MCP tool tests
│   │   └── integration/              # Full API integration tests
│   ├── scripts/                      # Utility scripts
│   │   ├── diagnose_hr_emails.py     # Debug HR email discovery pipeline
│   │   └── update_send_log_events.py # Backfill send_log events
│   ├── logs/                         # Structured JSON log files (runtime)
│   ├── resumes/                      # Local resume storage (dev fallback)
│   ├── requirements-shared.txt       # Shared Python dependencies
│   ├── alembic.ini                   # Alembic config
│   └── pytest.ini                    # Pytest configuration
│
├── frontend/                         # Frontend applications
│   └── dashboard/                    # Next.js 14 dashboard (App Router, port 3001)
│       ├── app/                      # 18 route modules (pages)
│       ├── components/               # Reusable React components
│       ├── hooks/                    # Custom React hooks
│       ├── lib/                      # API client + helpers
│       └── package.json
│
├── mcp/                              # Claude MCP admin console
│   ├── admin_server.py               # FastMCP server entry point
│   ├── config.py                     # MCP config (API URL, Redis, RabbitMQ, timeouts)
│   ├── claude_desktop_config_snippet.json
│   ├── requirements.txt              # mcp[sse], fastmcp
│   └── tools/                        # 19 tool modules
│
├── infra/                            # Docker, env files, operational config
│   ├── .env                          # Active environment values (gitignored)
│   ├── .env.example                  # Template with all required variables
│   ├── docker-compose.yml            # Full local dev orchestration
│   ├── docker-compose.prod.yml       # VPS production deployment (Nginx + reduced replicas)
│   ├── Makefile                      # Build, run, test, lint commands
│   ├── Dockerfile.api                # Python API image (python:3.11-slim)
│   ├── Dockerfile.worker             # Celery/Playwright worker (heavy, for scraping)
│   ├── Dockerfile.worker.lightweight # Celery worker (no browser, for AI/email)
│   ├── Dockerfile.dashboard          # Next.js multi-stage image (node:20-alpine)
│   ├── worker.config.yml             # Per-worker queue/broker/scale/concurrency config
│   ├── nginx/                        # Nginx reverse proxy config (production)
│   ├── rabbitmq/                     # RabbitMQ plugins + custom config
│   ├── scripts/                      # Deployment & maintenance scripts
│   └── docker_agent.py               # Docker scaling sidecar (Redis-controlled)
│
├── mobile/                           # React Native mobile app
├── docs/                             # Project documentation
└── .claude/                          # Claude Code tooling
    ├── settings.local.json
    ├── worktrees/
    └── schedules/
```

---

## 5. Services Deep Dive

### 5.1 API Service (`backend/services/api/`)

FastAPI application running on Uvicorn at port **8001**. Handles:

- Multi-tenant auth (JWT, signup, email verification, password reset)
- Tenant and user management
- Candidate and job CRUD
- Triggering scrape and email send tasks (dispatches to Celery)
- Aggregated stats for the dashboard
- Webhook ingestion from email providers (Brevo, Mailtrap)
- Billing and subscription management (Razorpay, optional)
- Company blacklist management
- Admin operations (health, cron history, manual task triggers)

**Key design decisions:**
- All DB operations async via SQLAlchemy 2.0 async session
- **Multi-tenant isolation**: every query filters by `tenant_id` from the JWT
- Frequently read data (candidates, stats) Redis-cached (30s–5min TTL)
- All routes protected by JWT Bearer tokens; admin routes additionally check `ADMIN_API_KEY`
- Prometheus metrics at `/metrics`

**Database pool:** Local PostgreSQL uses `pool_recycle=None`, no JIT override. Neon-specific hacks (pool_recycle=240, JIT off, keep-alive pings) only activate when `POSTGRES_LOCAL=false`.

---

### 5.2 Scraper Service (`backend/services/scraper/`)

Celery workers consuming from RabbitMQ. Scrapes job portals, deduplicates, and routes new jobs to the AI pipeline.

#### Active Portal Adapters (8)

| Portal | Technology | Notes |
|--------|-----------|-------|
| **Naukri** | Playwright | Full browser automation |
| **Indeed** | httpx + BeautifulSoup | HTML parsing, rate-limited |
| **Shine** | httpx + BeautifulSoup | Indian job board |
| **Internshala** | httpx + BeautifulSoup | Internships + full-time |
| **RemoteOK** | httpx + BeautifulSoup | Remote jobs |
| **WeWorkRemotely** | httpx + BeautifulSoup | Remote jobs |
| **WorkingNomads** | httpx + BeautifulSoup | Remote/nomad jobs |
| **Jobspresso** | httpx + BeautifulSoup | Remote jobs |

> 18 additional portal adapters exist in `adapters/` (LinkedIn, Glassdoor, AngelList, etc.) but are disabled — not registered in `celery_app.py`. They can be re-enabled by importing them in `get_adapter_registry()`.

#### BaseAdapter contract

```python
class BaseAdapter:
    async def search_jobs(self, query: JobQuery) -> list[RawJob]: ...
    async def parse_job_detail(self, url: str) -> JobDetail: ...
```

Base class also provides:
- HTTP client with browser user-agent, proxy support, robots.txt compliance
- Email extraction & validation (filters junk like Sentry IDs, image URLs)
- Job deduplication via SHA-256 hash (`dedupe_hash`)
- Date filtering (`max_job_age_days`, strict mode)

#### HR Email Discovery Pipeline

When a job has no HR email, `_discover_email_for_job()` tries these steps in order:

```
1. Regex extract from job description text
2. Crawl company_website (tries /contact, /careers, /about, /team)
3. DuckDuckGo search → crawl result pages for email pattern
4. Derive domain from company name → crawl common pages
5. Hunter.io domain search (if HUNTER_API_KEY set, quota: 1/day default)
6. Snov.io domain search (if SNOV_CLIENT_ID set, quota: 2/day default)
7. Guess hr@{domain} as last resort
```

Discovery status tracked per-job: `hr_email_discovery_status` / `hr_email_discovery_attempts` / `hr_email_discovered_at`.

#### Job Deduplication

SHA-256 hash of `"{job_url}:{job_title}:{company}"` stored as `dedupe_hash` with a unique constraint on `(tenant_id, dedupe_hash)`. Duplicates silently skipped.

---

### 5.3 AI Service (`backend/services/ai/`)

Celery workers consuming from Redis queues. Handles all LLM and vector operations.

#### Job Scoring (`scoring.py`)

Two-stage relevance check:
1. **Keyword pre-filter** — positive patterns (PHP, Laravel, full-stack, backend) vs negative (Java, .NET, Ruby, GoLang, Rust, etc.)
2. **LangChain LLM scoring** (Groq, structured output) → `JobRelevanceScore`:
   - `overall_score` (0–100)
   - `skills_match`, `experience_match`, `location_match`, `role_match` subscores
   - `is_php_laravel` flag, `detected_role`, `reasoning`
   - Fallback to neutral score 50 on LLM error

#### LangGraph Workflow (`workflow.py`)

State machine orchestrating the full application pipeline:

```
Nodes: analyze_job → score_job → generate_cover_letter → require_approval → send / discard

Routing:
  score ≥ score_threshold → generate_cover_letter → require_approval gate
  score < score_threshold → discard (status = "filtered")

Approval gate:
  AUTO_SEND_ENABLED=false (default) → notification to dashboard, wait for human
  AUTO_SEND_ENABLED=true → auto-dispatch send task

Redis checkpoint: 24h TTL for human-in-the-loop approval state
```

#### LLM Provider (`llm_adapter.py`)

- **Groq** — OpenAI Python SDK pointed at `api.groq.com`. Default model: `llama-3.3-70b-versatile`. Rate-limited via Redis sliding window (10 RPM free tier; multi-key round-robin for higher throughput).
- **Ollama** — Local container. Used for embeddings (`nomic-embed-text`) and optionally text generation.

#### Vector Storage (`vector_adapter.py`)

| Backend | Config value | Notes |
|---------|-------------|-------|
| `local` (default) | `VECTOR_DB_PROVIDER=local` | JSON file at `/tmp/jobhunter_vectors.json` |
| `pgvector` | `VECTOR_DB_PROVIDER=pgvector` | Native pgvector column, cosine similarity |
| `pinecone` | `VECTOR_DB_PROVIDER=pinecone` | Requires `PINECONE_API_KEY` |

#### Langfuse Observability (`observability.py`)

Optional. Set `LANGFUSE_ENABLED=true` + keys to activate. All Groq calls are traced: prompt, response, model, latency, token usage, tagged by tenant/candidate/task.

---

### 5.4 Sender Service (`backend/services/sender/`)

Celery workers consuming from Redis queues. Handles email rendering and delivery.

#### Email Adapters

| Adapter | Config value | Use case |
|---------|-------------|---------|
| **Brevo** | `EMAIL_PROVIDER=brevo` | Production transactional email, webhooks |
| **Mailtrap** | `EMAIL_PROVIDER=mailtrap` | Sandbox testing (emails never leave) |
| **SMTP** | `EMAIL_PROVIDER=smtp` | Fallback (Gmail, custom SMTP) |

#### Send Deduplication

Checks for active send statuses (`queued`, `sent`, `deferred`, `delivered`, `opened`, `clicked`) before dispatching. Duplicate sends for the same job are skipped.

#### Retry Logic

Max 3 retries with 120-second delay. A dedicated `jh_email_retry` queue separates retries from fresh sends.

#### Templates

Cover letter can be:
- **Per-candidate template** (`cover_letter_template` column) — `[Job Title]` + `[Company Name]` placeholders
- **Static cover letter** (`static_cover_letter` column) — no placeholders, zero LLM calls
- **LLM-generated** via LangGraph workflow (when neither of the above is set)

---

### 5.5 Dashboard (`frontend/dashboard/`)

Next.js 14 (App Router) frontend at port **3001**.

**Pages:**
- `/auth` — Login, signup, email verification, password reset
- `/onboarding` — New user/tenant setup
- `/dashboard` — Stats with Recharts (jobs by status, by portal, email funnel)
- `/jobs` — Paginated job list (filter by status, portal, HR email, cover, score)
- `/jobs/[id]` — Job detail: cover letter preview, score breakdown, send/approve buttons
- `/search` — Trigger manual scrape
- `/candidates` — Candidate CRUD, resume upload
- `/logs` — Email send history with delivery status
- `/direct-send` — Manual email send (outside scrape pipeline)
- `/billing` — Subscription management (Razorpay)
- `/blacklist` — Company blacklist
- `/settings` — User and workspace settings
- `/profile` — User profile
- `/users` — Team member management

---

### 5.6 MCP Admin Console (`mcp/`)

A FastMCP server exposing the entire stack as Claude tools. See [Section 13](#13-mcp-admin-console).

---

## 6. AI Flow

### 6.1 Job Scoring

```
New job saved to DB
      │
      ▼
dispatch_job_to_ai_pipeline()
      │
      ▼
Keyword pre-filter (positive: PHP/Laravel/etc, negative: Java/.NET/etc)
  ├── Fails → UPDATE status="filtered", is_php_python=false, stop
  └── Passes → LangChain structured output scoring (Groq)
                  │
                  ▼
          JobRelevanceScore {
            overall_score: 0–100,
            skills_match, exp_match, location_match, role_match,
            is_php_laravel: bool, detected_role, reasoning
          }
          UPDATE jobs SET relevance_score, score_breakdown
                  │
              ┌───┴───┐
       score < threshold   score ≥ threshold
              │                  │
       discard (filtered)  LangGraph workflow
```

### 6.2 Cover Letter Generation

```
generate_cover_letter_node (LangGraph)
      │
      ├─ candidate.static_cover_letter? → use as-is (zero LLM calls)
      ├─ candidate.cover_letter_template?
      │    ├─ company known? → fill placeholders (zero LLM calls)
      │    └─ company unknown? → Groq call (~20 tokens) to extract name, then fill
      └─ neither → Full LangChain generation via Groq
                   Output: CoverLetterOutput { subject, opening, body, closing }
      │
      ▼
UPDATE jobs SET cover_letter, status="cover_generated"
```

Refresh: `refresh_cover_letters_task` runs every 4 hours to regenerate covers for jobs with HR emails.

### 6.3 Embedding Generation

```
Job title + description (first 8000 chars)
      │
      ▼
Ollama (local): POST /api/embeddings → nomic-embed-text (768 dims)
      │
      ▼
Stored in selected backend (local JSON / pgvector)
+ Embedding record saved to PostgreSQL
```

### 6.4 AI Model Summary

| Component | Model | Token usage |
|-----------|-------|-------------|
| Job scoring | LangChain → Groq llama-3.3-70b-versatile | ~200 tokens/job |
| Cover letter | LangGraph + LangChain → Groq | ~500 tokens/letter |
| Company name extraction | Groq | ~20 tokens/call (only when company unknown) |
| Embeddings | Ollama nomic-embed-text (local) | Zero API tokens |

---

## 7. Job Automation Flow (End-to-End)

```
┌─────────────────────────────────────────────────────────────────┐
│  EVERY 2 HOURS — scheduled_scrape (Beat)                        │
│                                                                 │
│  For each active Tenant → Candidate:                            │
│    For each target_role × target_location:                      │
│      For each of 8 active portals:                              │
│        dispatch → scrape_jobs_task()  [jh_scraping_bulk]        │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  scrape_jobs_task(portal, query, candidate_id, tenant_id)       │
│                                                                 │
│  1. adapter.search_jobs(query) → list of (title, company, url)  │
│  2. For each result (Semaphore(3) concurrency):                 │
│     a. Compute dedupe_hash → skip if exists                     │
│     b. adapter.parse_job_detail(url) → full job detail          │
│     c. Date filter (max_job_age_days=60)                        │
│     d. INSERT into jobs (status="new")                          │
│  3. dispatch_job_to_ai_pipeline(job_id)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  AI PIPELINE                                                    │
│                                                                 │
│  1. Keyword pre-filter → filtered or continue                   │
│  2. LLM scoring (Groq, structured output) → 0–100              │
│  3. score < score_threshold → status="filtered", stop           │
│     score ≥ threshold → LangGraph workflow                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  EVERY 15 MIN — backfill_hr_email_task  [jh_scraping_enrichment]│
│                                                                 │
│  Fetch 100 jobs WHERE hr_email IS NULL                          │
│  _discover_email_for_job() → 7-step pipeline                    │
│  UPDATE jobs SET hr_email, hr_email_discovery_status            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  EVERY 15 MIN — fill_missing_covers_task  [jh_cover_letter_bulk]│
│  EVERY 4 HOURS — refresh_cover_letters_task                     │
│                                                                 │
│  generate_cover_letter_task(job_id, candidate_id)               │
│  → template fill / LLM generate via LangGraph                   │
│  UPDATE jobs SET cover_letter, status="cover_generated"         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  APPROVAL GATE (LangGraph require_approval_node)                │
│                                                                 │
│  AUTO_SEND_ENABLED=false (default):                             │
│    → Dashboard notification → human approves → workflow resumes │
│  AUTO_SEND_ENABLED=true:                                        │
│    → dispatch send_application_email_task immediately           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  send_application_email_task  [jh_email_send]                   │
│                                                                 │
│  1. Load Job + Candidate from DB                                │
│  2. Resolve HR email (inline discovery if still missing)        │
│  3. Check for duplicate active send status (skip if exists)     │
│  4. Render HTML + plain-text email via template.py              │
│  5. Fetch resume PDF from R2 or local resumes/ directory        │
│  6. Send via Brevo / Mailtrap / SMTP                            │
│  7. INSERT into send_logs (status="sent")                       │
│  8. UPDATE jobs SET status="sent"                               │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  WEBHOOKS  POST /webhooks/brevo  POST /webhooks/mailtrap        │
│                                                                 │
│  delivered → UPDATE send_logs SET delivered_at, status          │
│  opened    → UPDATE send_logs SET opened_at, status             │
│  clicked   → UPDATE send_logs SET clicked_at, status            │
│  bounced   → UPDATE send_logs SET status="bounced"              │
│  spam      → UPDATE send_logs SET status="spam"                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Database Schema

All tables include `tenant_id` (UUID FK) for multi-tenant isolation. Every query filters by tenant.

**Extensions required:** `uuid-ossp`, `vector` (pgvector).

### SaaS Tables

#### `tenants`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `name` | VARCHAR | |
| `slug` | VARCHAR | Unique |
| `plan` | VARCHAR | free / pro / premium |
| `status` | VARCHAR | active / suspended |
| `requires_approval` | BOOLEAN | Manual approval before send |
| `auto_send` | BOOLEAN | Auto-send when score passes |
| `score_threshold` | INTEGER | Min relevance score (default 60) |
| `created_at` | DATETIME | |

#### `users`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `email` | VARCHAR | Unique |
| `hashed_password` | VARCHAR | bcrypt |
| `is_verified` | BOOLEAN | |
| `is_active` | BOOLEAN | |
| `role` | VARCHAR | owner / admin / member |
| `verification_token` | VARCHAR | |
| `reset_token` | VARCHAR | |
| `reset_token_expires` | DATETIME | |
| `created_at` | DATETIME | |

#### `memberships`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK | |
| `tenant_id` | UUID FK | |
| `role` | VARCHAR | |
| `created_at` | DATETIME | |

#### `billing_subscriptions`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `plan` | VARCHAR | |
| `status` | VARCHAR | active / past_due / cancelled / trialing |
| `provider` | VARCHAR | razorpay |
| `provider_sub_id` | VARCHAR | |
| `current_period_end` | DATETIME | |
| `created_at` | DATETIME | |

#### `usage_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `user_id` | UUID FK | |
| `action_type` | VARCHAR | send / generate / score |
| `log_metadata` | JSON | |
| `created_at` | DATETIME | |

#### `notifications`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `user_id` | UUID FK | |
| `tenant_id` | UUID FK | |
| `type` | VARCHAR | |
| `message` | TEXT | |
| `is_read` | BOOLEAN | |
| `created_at` | DATETIME | |

### Core Business Tables

#### `candidates`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `name` | VARCHAR(200) | |
| `email` | VARCHAR(200) | Unique per tenant |
| `skills` | JSON | Array of strings |
| `years_experience` | INTEGER | |
| `resume_url` | VARCHAR(500) | R2 path or local filename |
| `target_roles` | JSON | e.g. ["PHP Developer", "Laravel Developer"] |
| `target_locations` | JSON | e.g. ["Remote", "Bangalore"] |
| `bio` | TEXT | Used for vector-based ranking |
| `cover_letter_template` | TEXT | Template with [Job Title] / [Company Name] |
| `static_cover_letter` | TEXT | Static fallback (no placeholders, no LLM) |
| `linkedin_url` | VARCHAR | |
| `github_url` | VARCHAR | |
| `is_active` | BOOLEAN | Default true |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | |

#### `jobs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `candidate_id` | UUID FK | |
| `job_title` | VARCHAR | |
| `company` | VARCHAR | |
| `location` | VARCHAR | |
| `job_description` | TEXT | |
| `job_url` | VARCHAR | |
| `posted_date` | DATETIME | |
| `scraped_at` | DATETIME | |
| `updated_at` | DATETIME | |
| `hr_email` | VARCHAR | |
| `hr_email_discovery_status` | VARCHAR | pending / found / not_found / skipped |
| `hr_email_discovery_attempts` | INTEGER | |
| `hr_email_discovered_at` | DATETIME | |
| `company_website` | VARCHAR | |
| `recruiter_name` | VARCHAR | |
| `source_portal` | VARCHAR | naukri / indeed / shine / … |
| `status` | VARCHAR | new → filtered → cover_generated → sent → bounced / error |
| `dedupe_hash` | VARCHAR(64) | Unique per tenant (SHA-256) |
| `salary_min/max` | FLOAT | |
| `salary_currency` | VARCHAR | |
| `job_type` | VARCHAR | |
| `experience_required` | VARCHAR | |
| `raw_data` | JSON | Portal-specific raw payload |
| `relevance_score` | FLOAT | Overall AI score (0–100) |
| `score_breakdown` | JSON | 4 subscores + reasoning |
| `is_php_python` | BOOLEAN | Keyword pre-filter result |
| `cover_letter` | TEXT | Generated cover letter |
| `cover_letter_generated_at` | DATETIME | |

**Indexes:** 15+ covering `status`, `candidate_id`, `tenant_id`, `dedupe_hash` (unique per tenant), `source_portal`, `scraped_at`, `relevance_score`, composite `(tenant_id, status, scraped_at)`, partial indexes on HR discovery fields.

#### `embeddings`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `job_id` | UUID FK (unique) | |
| `vector_id` | VARCHAR | |
| `embedding_source` | VARCHAR | ollama |
| `embedding_model` | VARCHAR | nomic-embed-text |
| `embedding_json` | JSON | Float array (768 dims) |
| `created_at` | DATETIME | |

#### `send_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `job_id` | UUID FK | |
| `candidate_id` | UUID FK | |
| `to_email` | VARCHAR | |
| `subject` | VARCHAR | |
| `body_snippet` | TEXT | First 500 chars |
| `status` | VARCHAR | queued → sent → delivered / opened / clicked / bounced / spam / error |
| `provider` | VARCHAR | brevo / mailtrap / smtp |
| `provider_message_id` | VARCHAR | For webhook correlation |
| `sent_at` | DATETIME | |
| `delivered_at` | DATETIME | Set by webhook |
| `opened_at` | DATETIME | Set by webhook |
| `clicked_at` | DATETIME | Set by webhook |
| `error_message` | TEXT | |
| `response_webhook_payload` | JSON | Raw webhook body |
| `retry_count` | INTEGER | |

### Operational Tables

#### `blacklisted_companies`

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `tenant_id` | UUID FK | |
| `company_name` | VARCHAR | |
| `reason` | TEXT | |
| `created_at` | DATETIME | |

#### `cron_runs`

Tracks every scheduled task execution:

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `task_name` | VARCHAR | |
| `celery_task_id` | VARCHAR | |
| `started_at` / `ended_at` | DATETIME | |
| `duration_ms` | INTEGER | |
| `status` | VARCHAR | running / success / failure |
| `error_summary` | TEXT | |
| `error_traceback` | TEXT | |
| `pre_state` | JSON | Row counts / queue depths before task |
| `post_state` | JSON | Same snapshot after task |
| `steps` | JSON | Per-step progress |
| `triggered_by` | VARCHAR | beat / manual |
| `worker_host` | VARCHAR | |

#### `direct_send_log`

Separate table for manual sends initiated from the dashboard (outside the automated pipeline).

---

## 9. Celery Tasks & Beat Schedule

### Scheduled Tasks (Beat)

| Task | Queue | Interval | Purpose |
|------|-------|----------|---------|
| `scheduled_scrape` | `jh_scraping_bulk` | Every 2h | All tenants × candidates × portals |
| `refresh_cover_letters_task` | `jh_cover_letter_bulk` | Every 4h | Regenerate covers for jobs with HR emails |
| `backfill_hr_email_task` | `jh_scraping_enrichment` | Every 15min | HR email discovery (batch 100) |
| `fill_missing_covers_task` | `jh_cover_letter_bulk` | Every 15min | First-time cover generation (batch 50) |
| `cleanup_old_jobs_task` | `jh_jobs_maintenance` | Every 7 days | Delete jobs beyond retention window |
| `purge_irrelevant_jobs_task` | `jh_jobs_maintenance` | Every 15min | Delete keyword-irrelevant jobs |

> Auto-send tasks (`retry_failed_sends`, `dispatch_ready_to_send`, `auto_approve_pending`) are disabled (`AUTO_SEND_ENABLED=false`). Manual sends via the dashboard are always available.

### On-Demand Tasks (API-triggered)

| Task | Queue | Trigger |
|------|-------|---------|
| `scrape_jobs_task` | `jh_scraping_realtime` | POST /search |
| `dispatch_job_to_ai_pipeline` | `jh_cover_letter_workflow` | After job saved |
| `generate_embedding_task` | `jh_cover_letter_generation` | After job scored |
| `generate_cover_letter_task` | `jh_cover_letter_generation` | POST /jobs/{id}/generate_cover |
| `rank_jobs_task` | `jh_cover_letter_ranking` | Manual |
| `send_application_email_task` | `jh_email_send` | POST /jobs/{id}/send |

### Worker Architecture (11 types)

```
RabbitMQ broker — high-volume scraping:
  jh_scraping_bulk       → worker-scraping-bulk   (×2)
  jh_scraping_realtime   → worker-scraping-rt      (×2)
  jh_scraping_enrichment → worker-enrichment       (×3)

Redis broker — AI, email, maintenance:
  jh_jobs_maintenance         → worker-maintenance    (×1)
  jh_cover_letter_bulk        → worker-cover-bulk     (×2)
  jh_cover_letter_ranking     → worker-cover-ranking  (×2)
  jh_cover_letter_generation  → worker-cover-gen      (×3)
  jh_cover_letter_workflow    → worker-cover-workflow (×2)
  jh_cover_letter_batch       → worker-cover-batch    (×1, locked)
  jh_email_send + jh_email_retry → worker-email       (×2)
```

**Worker settings:** `prefetch_multiplier=1`, soft time limit 600s, hard limit 720s.
Result backend: always Redis.

---

## 10. API Reference

All endpoints (except `/auth/*` and `/health`) require: `Authorization: Bearer <JWT_TOKEN>`

### Auth

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/signup` | Create account + tenant |
| POST | `/auth/login` | Login → JWT tokens |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/verify-email` | Email verification |
| POST | `/auth/forgot-password` | Send reset link |
| POST | `/auth/reset-password` | Reset with token |

### Tenants & Users

| Method | Path | Description |
|--------|------|-------------|
| GET | `/tenants/me` | Current tenant settings |
| PUT | `/tenants/me` | Update (score_threshold, auto_send, etc.) |
| GET | `/users/me` | Current user profile |
| PUT | `/users/me` | Update profile |
| GET | `/users` | List workspace members |

### Candidates

| Method | Path | Description |
|--------|------|-------------|
| POST | `/candidates` | Create candidate |
| GET | `/candidates` | List active candidates (cached 5 min) |
| GET | `/candidates/{id}` | Single candidate |
| PUT | `/candidates/{id}` | Update candidate |
| POST | `/candidates/{id}/resume` | Upload resume to R2 |

### Jobs

| Method | Path | Query params | Description |
|--------|------|-------------|-------------|
| GET | `/jobs` | `status`, `portal`, `company`, `has_hr_email`, `has_cover`, `candidate_id`, `min_score`, `limit`, `offset` | Paginated job list |
| GET | `/jobs/{id}` | — | Job detail + cover letter + score breakdown |
| PATCH | `/jobs/{id}` | — | Update job status |
| POST | `/jobs/{id}/generate_cover` | — | Trigger cover letter generation |
| POST | `/jobs/bulk_generate_cover` | `candidate_id` | Bulk cover generation |
| POST | `/jobs/{id}/send` | `dry_run=true` | Send email (or dry-run preview) |

### Send Logs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/send-logs` | List send logs (`job_id`, `status`, `limit`, `offset`) |
| POST | `/send-logs/{id}/retry` | Retry a failed send |

### Search

| Method | Path | Description |
|--------|------|-------------|
| POST | `/search` | Trigger scrape (`{titles, locations, portals, candidate_id, max_results}`) |
| GET | `/search/tasks` | List search tasks |
| GET | `/search/tasks/{id}` | Task status + progress |

### Stats & Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/stats` | Dashboard metrics (cached 30s) |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |

### Webhooks

| Method | Path | Description |
|--------|------|-------------|
| POST | `/webhooks/brevo` | Brevo delivery/open/click events |
| POST | `/webhooks/mailtrap` | Mailtrap delivery/open/click events |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/cron-runs` | Cron execution history |
| POST | `/admin/trigger/{task_name}` | Manually trigger a scheduled task |

### Billing (optional)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/billing/plans` | Available plans |
| POST | `/billing/subscribe` | Create subscription |
| GET | `/billing/subscription` | Current status |
| POST | `/webhooks/razorpay` | Razorpay payment events |

### Blacklist

| Method | Path | Description |
|--------|------|-------------|
| GET | `/blacklist` | List blacklisted companies |
| POST | `/blacklist` | Add company |
| DELETE | `/blacklist/{id}` | Remove company |

---

## 11. Configuration (infra/.env)

Copy `infra/.env.example` to `infra/.env` and fill in your values.

```bash
# ── App ───────────────────────────────────────────────────────────────────────
ENVIRONMENT=development
ADMIN_API_KEY=your_generated_admin_secret
SECRET_KEY=your_generated_jwt_secret
LOG_LEVEL=INFO
LOG_DIR=backend/logs
LOG_TO_FILE=true
LOG_ROTATION_MB=50

# ── Database (local Docker PostgreSQL) ────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://jobhunter:jobhunter@postgres:5432/jobhunter
POSTGRES_LOCAL=true
# Cloud alternative (Neon): set POSTGRES_LOCAL=false and use Neon connection string

# ── Redis (local Docker) ──────────────────────────────────────────────────────
REDIS_URL=redis://redis:6379
CELERY_RESULT_BACKEND=redis://redis:6379

# ── RabbitMQ (local Docker) ───────────────────────────────────────────────────
RABBITMQ_URL=amqp://jobhunter:jobhunter@rabbitmq:5672/
# Redis fallback only if RABBITMQ_URL is empty:
CELERY_BROKER_URL=redis://redis:6379

# ── LLM (Groq) ────────────────────────────────────────────────────────────────
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_RPM=10           # requests/min (free tier = 10)
GROQ_TPM=12000        # tokens/min (informational)
GROQ_API_KEYS=        # comma-separated for multi-key round-robin

# ── Embeddings (Ollama, local Docker) ─────────────────────────────────────────
OLLAMA_HOST=http://ollama:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

# ── Vector DB ─────────────────────────────────────────────────────────────────
VECTOR_DB_PROVIDER=local          # local | pgvector | pinecone
PINECONE_API_KEY=                 # only needed if VECTOR_DB_PROVIDER=pinecone
PINECONE_ENV=us-east-1-aws
PINECONE_INDEX=job-embeddings

# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_PROVIDER=brevo              # brevo | mailtrap | smtp
EMAIL_TEST_OVERRIDE=              # redirect all sends here for testing

# Brevo (production):
BREVO_API_KEY=your_brevo_api_key
BREVO_FROM_EMAIL=jobs@yourdomain.com
BREVO_FROM_NAME=Job Application Bot
BREVO_WEBHOOK_SECRET=

# Mailtrap (sandbox):
# EMAIL_PROVIDER=mailtrap
# MAILTRAP_API_KEY=...
# MAILTRAP_SANDBOX=true
# MAILTRAP_INBOX_ID=123456

# SMTP fallback:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_USE_TLS=true

# ── Storage (Cloudflare R2) ────────────────────────────────────────────────────
S3_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
S3_BUCKET_NAME=jobhunter-resumes
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_REGION=auto

# ── Scraper ───────────────────────────────────────────────────────────────────
PROXY_URL=
RESPECT_ROBOTS_TXT=true
DEFAULT_CRAWL_DELAY_SECONDS=2.0
MAX_JOB_AGE_DAYS=60              # skip jobs older than this

# ── HR Email Discovery ─────────────────────────────────────────────────────────
SNOV_CLIENT_ID=
SNOV_CLIENT_SECRET=
HUNTER_DAILY_QUOTA=1             # Hunter.io searches/day (free: ~1/day)
SNOV_DAILY_QUOTA=2               # Snov.io searches/day (free: ~2/day)

# ── AI Workflow ───────────────────────────────────────────────────────────────
LANGCHAIN_ENABLED=true
SCORE_THRESHOLD=60               # min relevance score to proceed (0–100)
SEMANTIC_FILTER_ENABLED=false    # LangChain semantic PHP/Laravel filter (extra LLM call)
AUTO_SEND_ENABLED=false          # false = require manual approval; true = auto-send

# ── Langfuse (optional LLM observability) ────────────────────────────────────
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# ── JWT Auth ──────────────────────────────────────────────────────────────────
JWT_SECRET=change-me-jwt-secret-32-chars-minimum
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=7

# ── Billing (Razorpay, optional) ──────────────────────────────────────────────
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=
```

---

## 12. Infrastructure & Docker

### Services (docker-compose.yml)

| Container | Image | Port | Role |
|-----------|-------|------|------|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | PostgreSQL with pgvector |
| `rabbitmq` | `rabbitmq:3.13-management-alpine` | 5672 / 15672 | Message broker + management UI |
| `redis` | `redis:7-alpine` | 6379 | Cache + result backend |
| `ollama` | `ollama/ollama:latest` | 11434 | Local LLM for embeddings |
| `api` | `Dockerfile.api` | 8001 | FastAPI REST API |
| `dashboard` | `Dockerfile.dashboard` | 3001 | Next.js frontend |
| `worker-scraping-bulk` ×2 | `Dockerfile.worker` | — | Scraping (RabbitMQ) |
| `worker-scraping-rt` ×2 | `Dockerfile.worker` | — | Realtime scraping (RabbitMQ) |
| `worker-enrichment` ×3 | `Dockerfile.worker` | — | HR email discovery (RabbitMQ) |
| `worker-maintenance` ×1 | `Dockerfile.worker.lightweight` | — | Cleanup (Redis) |
| `worker-cover-bulk` ×2 | `Dockerfile.worker.lightweight` | — | Cover backfill (Redis) |
| `worker-cover-ranking` ×2 | `Dockerfile.worker.lightweight` | — | Job ranking (Redis) |
| `worker-cover-gen` ×3 | `Dockerfile.worker.lightweight` | — | Cover generation (Redis) |
| `worker-cover-workflow` ×2 | `Dockerfile.worker.lightweight` | — | LangGraph workflow (Redis) |
| `worker-cover-batch` ×1 | `Dockerfile.worker.lightweight` | — | Batch processing (Redis) |
| `worker-email` ×2 | `Dockerfile.worker.lightweight` | — | Email send + retry (Redis) |
| `beat` | `Dockerfile.worker` | — | Celery beat scheduler |
| `flower` | `Dockerfile.worker` | 5555 | Celery monitoring UI |
| `alembic` | `Dockerfile.api` | — | One-shot migration runner |
| `docker-agent` | `Dockerfile.api` | — | Docker scaling sidecar |
| `watchtower` | `containrrr/watchtower:1.7.1` | — | Container restart monitor |

### Production Deployment (docker-compose.prod.yml)

Optimised for a **4 CPU / 8 GB RAM VPS**:
- **Nginx reverse proxy** — port 80; routes `/api/*` → FastAPI, `/` → Next.js
- Code baked into images at build time (no source volume mounts)
- Worker replicas reduced to 1 (scale manually via `--scale` or docker-agent)
- `restart: always` on all containers

### Dockerfile Notes

**`Dockerfile.api`** (`python:3.11-slim`) — API and alembic:
- `uvicorn services.api.main:app --host 0.0.0.0 --port 8001`
- `PYTHONPATH=/app/backend`

**`Dockerfile.worker`** (`mcr.microsoft.com/playwright/python:v1.50.0-jammy`) — scraping workers:
- Chromium, Firefox, WebKit + Playwright browsers
- Used for: worker-scraping-bulk, worker-scraping-rt, worker-enrichment, beat, flower

**`Dockerfile.worker.lightweight`** (`python:3.11-slim`) — AI/email/maintenance workers:
- No browser dependencies
- Used for: all cover-letter, email, maintenance workers

**`Dockerfile.dashboard`** (`node:20-alpine`, multi-stage):
- Stages: deps → builder → runner
- Build arg: `NEXT_PUBLIC_ADMIN_API_KEY`
- Non-root `nextjs` user (uid 1001)
- `next start` on port 3001

### Scaling Workers

```bash
# Scale specific worker types
docker compose -f infra/docker-compose.yml up -d \
  --scale worker-scraping-bulk=4 \
  --scale worker-enrichment=5 \
  --scale worker-cover-gen=4
```

Or via Makefile targets (see `infra/Makefile`).

---

## 13. MCP Admin Console

A FastMCP server (`mcp/admin_server.py`) that exposes the entire AI Job Hunter stack as Claude tools. Use it in Claude Desktop or Claude Code to monitor and manage the system via natural language.

### Setup

```bash
# Install MCP dependencies
pip install -r mcp/requirements.txt
```

Add to your Claude Desktop `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "job-hunter-admin": {
      "command": "/path/to/project/.venv/bin/python",
      "args": ["/path/to/project/mcp/admin_server.py"],
      "env": {
        "JH_API_URL": "http://localhost:8001",
        "JH_ADMIN_API_KEY": "your-admin-api-key",
        "JH_REDIS_URL": "redis://localhost:6379/0",
        "JH_RABBITMQ_URL": "http://localhost:15672",
        "JH_RABBITMQ_USER": "jobhunter",
        "JH_RABBITMQ_PASS": "jobhunter"
      }
    }
  }
}
```

A ready-to-paste snippet is in `mcp/claude_desktop_config_snippet.json`.

### Tool Modules (19 total)

| Module | Purpose |
|--------|---------|
| `health.py` | Overall system health check |
| `logs.py` | Inspect and search structured log files |
| `queues.py` | RabbitMQ queue depth + worker status + queue purge |
| `cron.py` | Scheduled task execution history + detail |
| `features.py` | Feature flag management |
| `docker_tools.py` | Scale/restart Docker containers |
| `actions.py` | Trigger tasks: scrape, enrich, generate covers, send |
| `database.py` | DB health + row counts per table |
| `redis_tools.py` | Redis key inspection |
| `system.py` | CPU, memory, disk stats |
| `pipeline.py` | Job pipeline funnel progress |
| `jobs.py` | Search, update, delete job records |
| `candidates.py` | Candidate profile management |
| `analytics.py` | Email funnel stats + open/click rates |
| `blacklist.py` | Company blacklist operations |
| `scripts.py` | Ad-hoc DB correction and maintenance scripts |
| `_base.py` | Base HTTPClient tool class |
| `_http.py` | HTTP utilities + retry logic |

### Example Usage

```
"How many jobs are in the pipeline right now?"
"Scale up the enrichment workers to 5"
"Show me the last 10 failed cron runs"
"Trigger an email discovery run for 100 jobs"
"What's the email open rate this week?"
"Which companies are on the blacklist?"
```

---

## 14. Logging & Observability

### Structured Logging (structlog)

All services write structured JSON logs. Every event includes:

```json
{
  "event": "scrape_task_started",
  "service": "scraper-rabbit",
  "environment": "development",
  "hostname": "428cd220930e",
  "level": "info",
  "logger": "services.scraper.tasks",
  "timestamp": "2026-05-10T08:10:28.123456Z",
  "task_id": "abc123",
  "portal": "naukri",
  "tenant_id": "uuid-..."
}
```

Log files: `backend/logs/app.log` (all events), `backend/logs/errors.log` (errors only). Rotated at 50 MB.

### Cron Execution Tracking

Every scheduled task is wrapped in `CronMonitor` which captures:
- **Pre/post state**: row counts, queue depths before and after
- **Step-by-step progress**: jobs scraped, emails found, covers generated
- **duration_ms**, **status** (success / failure), full error traceback on failure

Browse via `/admin/cron-runs` API or the MCP `cron.py` tool.

### Langfuse (Optional LLM Observability)

Set `LANGFUSE_ENABLED=true` to activate. Traces every Groq API call:
- Prompt + response captured
- Token usage and estimated cost
- Latency per call
- Tagged by `tenant_id`, `candidate_id`, task type

### Prometheus Metrics

FastAPI exposes `/metrics`:
- HTTP request count (method × path × status)
- HTTP request latency histogram

### Flower (Celery Monitoring)

Access at http://localhost:5555:
- Real-time queue depth per queue
- Worker heartbeats and pool status
- Task history, results, error messages

### Viewing Logs Locally

```bash
# Stream all JSON logs (pretty-printed)
tail -f backend/logs/app.log | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
        print(f\"[{d.get('service','?'):20}] [{d.get('level','?'):5}] {d.get('event','?')}\")
    except: pass
"

# Errors only
tail -f backend/logs/errors.log | jq '{service, event, exc_type, exc_message}'

# Filter by service
tail -f backend/logs/app.log | jq 'select(.service=="beat")'

# Filter by tenant
tail -f backend/logs/app.log | jq 'select(.tenant_id=="your-uuid")'
```

---

## 15. Running the Project

### Prerequisites

- Docker Desktop (macOS/Linux) or Docker Engine + Compose v2
- `infra/.env` configured (copy from `infra/.env.example`, fill in GROQ_API_KEY + email provider)

### First-time Setup

```bash
# 1. Clone and enter project
git clone <repo> ai-job-hunter
cd ai-job-hunter

# 2. Copy and configure environment
cp infra/.env.example infra/.env
# Edit infra/.env — minimum required:
#   GROQ_API_KEY, BREVO_API_KEY + BREVO_FROM_EMAIL (or mailtrap/smtp creds)
#   ADMIN_API_KEY, SECRET_KEY, JWT_SECRET

# 3. Build all images
make -f infra/Makefile build

# 4. Start infrastructure (postgres, rabbitmq, redis, ollama)
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d postgres rabbitmq redis ollama

# 5. Pull the Ollama embedding model
docker exec ollama ollama pull nomic-embed-text

# 6. Run database migrations
make -f infra/Makefile migrate

# 7. Start all services
make -f infra/Makefile up
```

### Service URLs

| Service | URL |
|---------|-----|
| API | http://localhost:8001 |
| API docs (Swagger) | http://localhost:8001/docs |
| Dashboard | http://localhost:3001 |
| Flower (Celery) | http://localhost:5555 |
| RabbitMQ management | http://localhost:15672 (user: jobhunter / jobhunter) |
| Prometheus metrics | http://localhost:8001/metrics |

### Start Specific Services

```bash
# API + core workers only (no dashboard)
docker compose -f infra/docker-compose.yml --env-file infra/.env \
  up -d api worker-scraping-bulk worker-scraping-rt worker-enrichment \
         worker-cover-gen worker-cover-workflow worker-email beat flower

# Dashboard only
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d dashboard

# Full stack
make -f infra/Makefile up
```

### Common Operations

```bash
# View logs (all services)
docker compose -f infra/docker-compose.yml logs -f

# View specific service
docker compose -f infra/docker-compose.yml logs -f worker-cover-gen

# Scale workers
docker compose -f infra/docker-compose.yml up -d \
  --scale worker-scraping-bulk=4 --scale worker-cover-gen=4

# Restart beat scheduler
docker compose -f infra/docker-compose.yml restart beat

# Run migrations
docker compose -f infra/docker-compose.yml exec api \
  alembic -c backend/alembic.ini upgrade head
```

### Trigger a Manual Scrape

```bash
# First login to get a JWT
TOKEN=$(curl -s -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "yourpassword"}' \
  | jq -r '.access_token')

# Trigger scrape
curl -X POST http://localhost:8001/search \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "your-candidate-uuid",
    "job_titles": ["PHP Developer", "Laravel Developer"],
    "locations": ["Remote", "Bangalore"],
    "portals": ["naukri", "indeed", "shine"],
    "max_results_per_portal": 20
  }'
```

### Send an Application (Manual)

```bash
# Dry run (preview without sending)
curl -X POST "http://localhost:8001/jobs/{job_id}/send?dry_run=true" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "your-candidate-uuid"}'

# Actually send
curl -X POST "http://localhost:8001/jobs/{job_id}/send" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"candidate_id": "your-candidate-uuid"}'
```

---

## 16. Development Guide

### Running Tests

```bash
# All tests
PYTHONPATH=backend python -m pytest -c backend/pytest.ini backend/tests/

# Unit tests
PYTHONPATH=backend python -m pytest -c backend/pytest.ini backend/tests/unit/ -v

# Integration tests
PYTHONPATH=backend python -m pytest -c backend/pytest.ini backend/tests/integration/ -v

# With coverage
PYTHONPATH=backend python -m pytest -c backend/pytest.ini backend/tests/ \
  --cov=services --cov-report=term

# Via Makefile
make -f infra/Makefile test
make -f infra/Makefile test-unit
make -f infra/Makefile test-coverage
```

### Database Migrations

```bash
# Create a new migration
docker compose -f infra/docker-compose.yml exec api \
  alembic -c backend/alembic.ini revision --autogenerate -m "add column xyz"

# Apply
docker compose -f infra/docker-compose.yml exec api \
  alembic -c backend/alembic.ini upgrade head

# Rollback one step
docker compose -f infra/docker-compose.yml exec api \
  alembic -c backend/alembic.ini downgrade -1
```

### Enabling a Disabled Portal Adapter

1. Open `backend/services/scraper/celery_app.py`
2. Find `get_adapter_registry()` at the bottom of the file
3. Uncomment or add the import and registry entry:
   ```python
   from services.scraper.adapters.linkedin import LinkedInAdapter
   return { ..., "linkedin": LinkedInAdapter }
   ```
4. Add the portal name to `VALID_PORTALS`
5. Restart scraping workers

### Adding a New Portal Adapter

1. Create `backend/services/scraper/adapters/myportal.py`
2. Inherit from `BaseAdapter`, implement `search_jobs()` and `parse_job_detail()`
3. Register in `celery_app.py` → `get_adapter_registry()`
4. Add to `VALID_PORTALS`

### Adding a New Email Provider

1. Create adapter class in `email_adapter.py` implementing `send()` → returns message ID
2. Register in `get_email_adapter()` factory switch
3. Add provider fields to `config.py` (`Settings` class) and `infra/.env.example`

### Changing the LLM Model

Set `GROQ_MODEL` in `infra/.env`:
```
GROQ_MODEL=llama-3.1-8b-instant        # Faster, cheaper
GROQ_MODEL=llama-3.3-70b-versatile     # Default, best quality
```

Restart AI workers:
```bash
docker compose -f infra/docker-compose.yml restart worker-cover-gen worker-cover-workflow beat
```

### Adjusting Score Threshold

`SCORE_THRESHOLD` (0–100) in `infra/.env`. Jobs below this are marked `filtered`.

```
SCORE_THRESHOLD=50    # Permissive
SCORE_THRESHOLD=60    # Default
SCORE_THRESHOLD=75    # Strict
```

### Multi-tenant API

All API routes are tenant-scoped via JWT:

```bash
# 1. Sign up
curl -X POST http://localhost:8001/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "pass", "tenant_name": "My Workspace"}'

# 2. Login → get JWT
curl -X POST http://localhost:8001/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "pass"}'

# 3. Use JWT on all requests
curl -H "Authorization: Bearer <token>" http://localhost:8001/candidates
```

### MCP Development

```bash
# Run server locally (stdio, for Claude Desktop)
python mcp/admin_server.py

# Add a new tool: create mcp/tools/mytool.py
# with functions decorated @mcp.tool()
# then import and register in mcp/admin_server.py
```
