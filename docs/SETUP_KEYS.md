# API Keys Setup Guide

Step-by-step guide to get every key needed for your `infra/.env` file.
After completing each section, copy the value into your `infra/.env`.

---

## 1. Neon — PostgreSQL Database

**Key:** `DATABASE_URL`

1. Go to **https://console.neon.tech**
2. Sign up / Log in
3. Click **"New Project"** → give it a name (e.g. `job-hunter`) → click **Create**
4. On the project dashboard, click **"Connection string"** (top of the page)
5. In the dropdown, select driver **"asyncpg"** (or pick "psycopg2" and manually replace `postgresql://` with `postgresql+asyncpg://`)
6. Copy the full connection string — it looks like:
   ```
   postgresql+asyncpg://user:password@ep-xxx-yyy.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
7. Paste into `infra/.env`:
   ```
   DATABASE_URL=postgresql+asyncpg://user:password@ep-xxx-yyy.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

> **Note:** Make sure `?sslmode=require` is at the end — Neon requires SSL.

---

## 2. Upstash — Redis (Celery broker + result backend)

**Keys:** `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

1. Go to **https://console.upstash.com**
2. Sign up / Log in
3. Click **"Create Database"**
   - Name: `job-hunter`
   - Type: **Regional** (pick the region closest to your Neon DB region)
   - Enable **TLS** ✓
4. After creation, click on your database → go to the **"Details"** tab
5. Find the section **"REST API"** or **"Connect"** — look for the **"rediss://"** URL (with double-s)
6. Copy the URL — it looks like:
   ```
   rediss://default:AxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxY@your-endpoint.upstash.io:6379
   ```
7. Paste the **same URL** into all three keys in `infra/.env`:
   ```
   REDIS_URL=rediss://default:Axxx...@your-endpoint.upstash.io:6379
   CELERY_BROKER_URL=rediss://default:Axxx...@your-endpoint.upstash.io:6379
   CELERY_RESULT_BACKEND=rediss://default:Axxx...@your-endpoint.upstash.io:6379
   ```

> **Important:** Use `rediss://` (double-s), NOT `redis://`. The double-s means TLS is enabled.

---

## 3. Groq — LLM API

**Key:** `GROQ_API_KEY`

1. Go to **https://console.groq.com/keys**
2. Sign up / Log in (free tier available)
3. Click **"Create API Key"**
   - Name: `job-hunter`
4. Copy the key — it starts with `gsk_`
5. Paste into `infra/.env`:
   ```
   GROQ_API_KEY=gsk_your_key_here
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

**Available models** (paste one into `GROQ_MODEL`):
| Model | Speed | Best for |
|---|---|---|
| `llama-3.3-70b-versatile` | Fast | Cover letters (recommended) |
| `llama-3.1-8b-instant` | Very fast | Quick drafts |
| `mixtral-8x7b-32768` | Fast | Long context |
| `gemma2-9b-it` | Fast | Lightweight tasks |

---

## 4. Resend — Email Sending

**Keys:** `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `RESEND_WEBHOOK_SECRET`

### 4a. API Key

1. Go to **https://resend.com**
2. Sign up / Log in
3. In the sidebar, click **"API Keys"**
4. Click **"Create API Key"**
   - Name: `job-hunter`
   - Permission: **Full access** (or "Sending access")
5. Copy the key — it starts with `re_`
6. Paste into `infra/.env`:
   ```
   RESEND_API_KEY=re_your_key_here
   ```

### 4b. Verify a Sending Domain

`RESEND_FROM_EMAIL` must come from a domain you verify in Resend.

1. In the sidebar, click **"Domains"**
2. Click **"Add Domain"** → enter your domain (e.g. `yourdomain.com`)
3. Resend will show you **DNS records** to add (MX, TXT, DKIM)
4. Log in to your domain registrar (GoDaddy / Namecheap / Cloudflare / etc.) and add those DNS records
5. Come back to Resend and click **"Verify"** — wait a few minutes
6. Once verified, set in `infra/.env`:
   ```
   RESEND_FROM_EMAIL=jobs@yourdomain.com
   RESEND_FROM_NAME=Job Application Bot
   ```

> **No domain?** Use Resend's shared domain for testing: `onboarding@resend.dev` (only sends to your verified email).

### 4c. Webhook Signing Secret

This lets the app verify that webhook events actually come from Resend.

1. In the sidebar, click **"Webhooks"**
2. Click **"Add Endpoint"**
   - URL: `https://your-api-host.com/webhooks/resend`
   - Events to subscribe: check all `email.*` events
3. After creating, click on the webhook → find **"Signing Secret"**
4. Copy the secret — it starts with `whsec_`
5. Paste into `infra/.env`:
   ```
   RESEND_WEBHOOK_SECRET=whsec_your_secret_here
   ```

> **Local development:** Use [ngrok](https://ngrok.com) to expose your local port: `ngrok http 8000`, then use the ngrok URL as your webhook endpoint.

---

## 5. Cloudflare R2 — File Storage (Resumes)

**Keys:** `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`

### 5a. Create a Bucket

1. Go to **https://dash.cloudflare.com**
2. In the sidebar, click **"R2 Object Storage"**
3. Click **"Create bucket"**
   - Name: `jobhunter-resumes`
   - Location: automatic (or pick closest to you)
4. Click **Create**

### 5b. Get Your Account ID

1. On any Cloudflare dashboard page, look at the **URL** — it contains your Account ID:
   ```
   https://dash.cloudflare.com/ACCOUNT_ID_HERE/r2/...
   ```
   Or find it in **"Account Home"** → right sidebar under "Account ID"
2. Your endpoint will be:
   ```
   https://ACCOUNT_ID_HERE.r2.cloudflarestorage.com
   ```
3. Paste into `infra/.env`:
   ```
   S3_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
   S3_BUCKET_NAME=jobhunter-resumes
   ```

### 5c. Create an API Token

1. In R2, click **"Manage R2 API Tokens"** (top right of the R2 page)
2. Click **"Create API Token"**
   - Token name: `job-hunter`
   - Permissions: **Object Read & Write**
   - Specify bucket: select `jobhunter-resumes`
3. Click **Create API Token**
4. You'll see **"Access Key ID"** and **"Secret Access Key"** — copy both **now** (secret is shown only once)
5. Paste into `infra/.env`:
   ```
   S3_ACCESS_KEY=your_access_key_id
   S3_SECRET_KEY=your_secret_access_key
   S3_REGION=auto
   ```

---

## 6. Hunter.io — HR Email Discovery (Optional)

**Key:** `HUNTER_API_KEY`

Used as a fallback when the scraper can't find an HR email directly.

1. Go to **https://hunter.io**
2. Sign up (free tier: 25 searches/month)
3. Click your avatar → **"API"** in the menu
4. Copy your API key
5. Paste into `infra/.env`:
   ```
   HUNTER_API_KEY=your_hunter_key_here
   ```

> Leave blank to skip — the scraper will still try to find emails directly from job pages.

---

## 7. LinkedIn API (Optional)

**Keys:** `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`

Only needed if you want LinkedIn OAuth for scraping beyond public listings.

1. Go to **https://www.linkedin.com/developers/apps**
2. Click **"Create app"**
   - App name: `Job Hunter`
   - LinkedIn page: your personal/company page
   - App logo: any image
3. After creation, go to the **"Auth"** tab
4. Copy **Client ID** and **Client Secret**
5. Add `http://localhost:8000/auth/linkedin/callback` to **"Authorized redirect URLs"**
6. Paste into `infra/.env`:
   ```
   LINKEDIN_CLIENT_ID=your_client_id
   LINKEDIN_CLIENT_SECRET=your_client_secret
   ```

---

## 8. App Secrets (generate locally)

**Keys:** `ADMIN_API_KEY`, `SECRET_KEY`

These are not from any external service — just generate them yourself.

Run this in your terminal:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Run it twice — use one value for `ADMIN_API_KEY` and another for `SECRET_KEY`:
```
ADMIN_API_KEY=<first output>
SECRET_KEY=<second output>
```

---

## Final Checklist

Copy this to check off each key as you add it to `infra/.env`:

- [ ] `DATABASE_URL` — from Neon console
- [ ] `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` — same Upstash `rediss://` URL
- [ ] `GROQ_API_KEY` — from Groq console
- [ ] `RESEND_API_KEY` — from Resend API Keys page
- [ ] `RESEND_FROM_EMAIL` — your verified domain email in Resend
- [ ] `RESEND_WEBHOOK_SECRET` — from Resend Webhooks page (optional for local dev)
- [ ] `S3_ENDPOINT_URL` — `https://<account_id>.r2.cloudflarestorage.com`
- [ ] `S3_ACCESS_KEY` / `S3_SECRET_KEY` — from Cloudflare R2 API Token
- [ ] `ADMIN_API_KEY` / `SECRET_KEY` — self-generated secrets
- [ ] `HUNTER_API_KEY` — from hunter.io (optional)
- [ ] `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` — from LinkedIn Developers (optional)

---

## Ollama (local embeddings — no key needed)

When `LLM_PROVIDER=groq`, the app uses Ollama locally for generating embeddings.
Groq does not have an embeddings API, so Ollama handles this.

Install and start Ollama:
```bash
# Install: https://ollama.com/download
ollama pull nomic-embed-text   # download the embedding model
ollama serve                   # starts on http://localhost:11434
```

If Ollama is not running, job ranking/similarity features are silently skipped — nothing will crash.
```
OLLAMA_HOST=http://localhost:11434
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```
