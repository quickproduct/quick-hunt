# AI Job Hunter Bot

An automated job application bot that scrapes job listings, discovers HR emails, generates personalized cover letters via LLM, and sends applications — all with a Next.js dashboard and full observability.

```
Architecture:
┌─────────────────────────────────────────────────────┐
│  Next.js Dashboard (port 3000)                      │
│  ├── Job listing & filtering                        │
│  ├── Cover letter preview & editing                 │
│  └── Send history & webhook tracking                │
├─────────────────────────────────────────────────────┤
│  FastAPI REST API (port 8000)                       │
│  ├── /candidates  /jobs  /search  /send             │
│  ├── /webhooks/resend  /stats                       │
│  └── Local structured logging (backend/logs/)       │
├─────────────────────────────────────────────────────┤
│  Celery Workers (4 queues)                          │
│  ├── scraping   — Naukri/Indeed/Glassdoor/etc       │
│  ├── cover_letter — LLM embedding + cover gen       │
│  ├── email_send  — Resend/SMTP                      │
│  └── Beat scheduler — every 3 hours                 │
├─────────────────────────────────────────────────────┤
│  PostgreSQL (pgvector) │ Redis │ MinIO (S3)          │
└─────────────────────────────────────────────────────┘
```

## Prerequisites

- Docker Desktop (or Docker + Docker Compose)
- 4 GB free RAM
- Optional: OpenAI API key or Ollama running locally

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url> ai-job-hunter
cd ai-job-hunter
cp infra/.env.example infra/.env
```

Edit `infra/.env` — at minimum set:
- `ADMIN_API_KEY` (any secret string)
- `LLM_PROVIDER=groq` with `GROQ_API_KEY`, or `ollama` for local
- `EMAIL_PROVIDER=resend` with `RESEND_API_KEY`, or `smtp` with Gmail app password

### 2. Start all services

```bash
make -f infra/Makefile build
make -f infra/Makefile up
```

### 3. Run database migrations

```bash
make -f infra/Makefile migrate
```

### 4. Install Playwright (for scraping)

```bash
make -f infra/Makefile playwright-install
```

### 5. Create your candidate profile

```bash
make -f infra/Makefile demo-candidate
```

Or via API:
```bash
curl -X POST http://localhost:8000/candidates \
  -H "X-API-Key: change-me-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Your Name",
    "email": "you@gmail.com",
    "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
    "years_experience": 4,
    "target_roles": ["Backend Engineer", "Python Developer"],
    "target_locations": ["Bangalore", "Remote"],
    "bio": "Brief professional bio..."
  }'
```

### 6. Upload your resume

```bash
curl -X PUT http://localhost:9001 ...  # MinIO console at http://localhost:9001
# Or set resume_url to an S3/HTTP link in the candidate update
```

### 7. Trigger your first job search

```bash
curl -X POST http://localhost:8000/search \
  -H "X-API-Key: change-me-secret" \
  -H "Content-Type: application/json" \
  -d '{
    "job_titles": ["Python Developer", "Backend Engineer"],
    "locations": ["Bangalore"],
    "portals": ["naukri", "indeed"],
    "max_results_per_portal": 20,
    "candidate_id": "<id from step 5>",
    "auto_generate_covers": true
  }'
```

## URLs

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:3000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Flower (Celery) | http://localhost:5555 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (admin/admin) |
| MinIO Console | http://localhost:9001 (minioadmin/minioadmin) |

## Development Commands

```bash
make -f infra/Makefile test           # Run all tests
make -f infra/Makefile test-unit      # Unit tests only
make -f infra/Makefile test-coverage  # With HTML coverage report
make -f infra/Makefile lint           # flake8
make -f infra/Makefile format         # black
make -f infra/Makefile logs           # Follow all container logs
make -f infra/Makefile shell-api      # Bash in API container
make -f infra/Makefile shell-db       # psql in postgres container
make -f infra/Makefile demo-stats     # Fetch stats from API
```

## Configuration

See `infra/.env.example` for all environment variables with descriptions.

Key settings:
- `LLM_PROVIDER=groq|ollama` — LLM for cover letters and embeddings
- `VECTOR_DB_PROVIDER=local|pgvector|pinecone` — Vector storage
- `EMAIL_PROVIDER=resend|smtp` — Email sending
- `RESPECT_ROBOTS_TXT=true` — Always enabled by default

## Portal Support

| Portal | Method | Rate Limit |
|--------|--------|------------|
| Naukri | Playwright | 8 req/min |
| Indeed | Playwright | 6 req/min |
| Glassdoor | Playwright (proxy recommended) | 5 req/min |
| LinkedIn | Public search (ToS-safe) | 10 req/min |
| AngelList/Wellfound | Playwright | 6 req/min |

## Legal Notice

Web scraping may violate the Terms of Service of job portals.
This project is intended for **personal job hunting only**, not commercial use.

- LinkedIn scraping is explicitly against LinkedIn's ToS. This project uses only
  public search endpoints for LinkedIn. Apply for the official Jobs API at
  https://developer.linkedin.com/product-catalog
- This system respects `robots.txt` automatically (`RESPECT_ROBOTS_TXT=true` by default)
- Per-portal rate limits are enforced to avoid overloading servers
- The authors are not responsible for misuse
- **Use official APIs wherever available**

## Architecture Details

## Project Layout

- `backend/` contains the FastAPI API, Celery workers, tests, migrations, scripts, shared Python dependencies, and log files.
- `frontend/` contains the Next.js dashboard app.
- `infra/` contains Dockerfiles, Docker Compose, environment files, Prometheus, Logstash, and the shared Makefile.
- `docs/` contains the main README, deep technical documentation, setup guides, and license text.

### Scraping Pipeline
1. `POST /search` → creates `SearchTask` record → dispatches `scrape_portal_task` to Celery `scraping` queue
2. Worker runs portal adapter (Playwright headless browser)
3. Deduplicates via SHA-256 hash before DB insert
4. Discovers HR email (from job text → company website → Hunter.io)
5. Saves `Job` record, dispatches `generate_embedding_task`
6. If `auto_generate_covers=true`, dispatches `generate_cover_letter_task`

### Cover Letter Generation
Uses a structured 3-paragraph prompt:
- **Para 1**: Hook — specific interest in company and role
- **Para 2**: Alignment — 2-3 matching skills
- **Para 3**: Closing — call to action

Rules: under 250 words, no "I am writing to apply", no salutation/sign-off.

### Email Sending
`POST /jobs/{id}/send` → Celery `email_send` queue → fetches resume from R2 → sends via Resend/SMTP → updates `SendLog` → webhook updates status (delivered/opened/clicked/bounced).

## License

MIT — see [LICENSE](LICENSE)
