#!/usr/bin/env python3
"""Diagnostic script for HR email pipeline health.

Run from project root:
    python -m backend.scripts.diagnose_hr_emails

Or directly:
    cd backend && python scripts/diagnose_hr_emails.py

Reads DB connection from infra/.env or DATABASE_URL env var.
"""

import asyncio
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path so `services.*` imports work
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)


async def run_diagnostics():
    import asyncpg
    from services.api.core.config import get_settings

    settings = get_settings()
    db_url = settings.database_url

    # asyncpg needs a plain postgres:// URL
    pg_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)

    print("=" * 72)
    print("HR EMAIL PIPELINE DIAGNOSTICS")
    print("=" * 72)

    # 1. Cover-generated jobs missing HR email (THE BOTTLENECK)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
          AND cover_letter IS NOT NULL
    """)
    print(f"\n🔴 Jobs with cover letter but NO HR email (blocked): {row['count']}")

    # 2. Jobs ready to send (cover + HR email)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NOT NULL
          AND cover_letter IS NOT NULL
    """)
    print(f"🟢 Jobs ready to send (cover + HR email):            {row['count']}")

    # 3a. Portal domain placeholder emails (Indeed + disposable services)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email ILIKE '%@in.indeed.com'
           OR hr_email ILIKE '%@indeed.com'
           OR hr_email ILIKE '%@indeedmail.com'
           OR hr_email ILIKE '%@wishtempuser.com'
    """)
    print(f"🟡 Jobs with portal domain placeholder emails:      {row['count']}")

    # 3b. Known exact-match placeholder emails (Shine test, etc.)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE LOWER(hr_email) = 'shinetest12345@gmail.com'
    """)
    print(f"🟡 Jobs with Shine test placeholder email:          {row['count']}")

    # 3c. Image/CSS filename junk emails
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email ~* '\\.(png|jpg|jpeg|gif|svg|webp|avif|css|js)$'
    """)
    print(f"🟡 Jobs with image/CSS filename junk emails:        {row['count']}")

    # 3d. Breakdown by portal
    print("\n── Junk emails by portal ──")
    rows = await conn.fetch("""
        SELECT source_portal,
               CASE
                 WHEN hr_email ILIKE '%@in.indeed.com'
                   OR hr_email ILIKE '%@indeed.com'
                   OR hr_email ILIKE '%@indeedmail.com'
                   OR hr_email ILIKE '%@wishtempuser.com'
                 THEN 'domain_placeholder'
                 WHEN LOWER(hr_email) = 'shinetest12345@gmail.com'
                 THEN 'shine_test'
                 WHEN hr_email ~* '\\.(png|jpg|jpeg|gif|svg|webp|avif|css|js)$'
                 THEN 'image_css_junk'
                 ELSE 'other_junk'
               END AS junk_type,
               COUNT(*) AS count
        FROM jobs
        WHERE hr_email ILIKE '%@in.indeed.com'
           OR hr_email ILIKE '%@indeed.com'
           OR hr_email ILIKE '%@indeedmail.com'
           OR hr_email ILIKE '%@wishtempuser.com'
           OR LOWER(hr_email) = 'shinetest12345@gmail.com'
           OR hr_email ~* '\\.(png|jpg|jpeg|gif|svg|webp|avif|css|js)$'
        GROUP BY source_portal, junk_type
        ORDER BY count DESC
    """)
    for r in rows:
        print(f"  {r['source_portal']:20s} {r['junk_type']:25s} {r['count']:>6d}")

    # 4. Breakdown by status for jobs missing HR email
    print("\n── Jobs missing HR email by status ──")
    rows = await conn.fetch("""
        SELECT status, COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
        GROUP BY status
        ORDER BY count DESC
    """)
    for r in rows:
        print(f"  {r['status']:25s} {r['count']:>6d}")

    # 5. Breakdown by portal for cover_generated jobs missing HR email
    print("\n── Cover-generated jobs missing HR email by portal ──")
    rows = await conn.fetch("""
        SELECT source_portal, COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
        GROUP BY source_portal
        ORDER BY count DESC
        LIMIT 15
    """)
    for r in rows:
        print(f"  {r['source_portal']:25s} {r['count']:>6d}")

    # 6. Jobs with company = 'Unknown' and no HR email
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND (company IS NULL OR LOWER(company) = 'unknown')
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
    """)
    print(f"\n⚠️  Jobs with Unknown company & no HR email:         {row['count']}")

    # 7. Jobs with no company_website and no HR email
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND company_website IS NULL
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
    """)
    print(f"⚠️  Jobs with no company_website & no HR email:      {row['count']}")

    # 8. Jobs with no job_description and no HR email
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND (job_description IS NULL OR job_description = '')
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
    """)
    print(f"⚠️  Jobs with no description & no HR email:          {row['count']}")

    # ── NEW: Data completeness matrix for cover_generated missing HR email ──
    print("\n── Data completeness: cover_generated jobs missing HR email ──")
    rows = await conn.fetch("""
        SELECT
            CASE WHEN company IS NULL OR LOWER(company) = 'unknown' THEN 'NO' ELSE 'YES' END AS has_company,
            CASE WHEN company_website IS NULL THEN 'NO' ELSE 'YES' END AS has_website,
            CASE WHEN job_description IS NULL OR job_description = '' THEN 'NO' ELSE 'YES' END AS has_description,
            CASE WHEN job_url IS NULL OR job_url = '' THEN 'NO' ELSE 'YES' END AS has_url,
            COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
        GROUP BY 1, 2, 3, 4
        ORDER BY count DESC
    """)
    for r in rows:
        print(
            f"  company={r['has_company']:3s}  website={r['has_website']:3s}  "
            f"desc={r['has_description']:3s}  url={r['has_url']:3s}  → {r['count']:>5d} jobs"
        )

    # ── NEW: Discovery attempt distribution ──
    print("\n── Discovery attempt distribution (cover_generated, no HR email) ──")
    rows = await conn.fetch("""
        SELECT
            COALESCE(hr_email_discovery_attempts, 0) AS attempts,
            hr_email_discovery_status,
            COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
        GROUP BY 1, 2
        ORDER BY attempts, hr_email_discovery_status
    """)
    for r in rows:
        status = r['hr_email_discovery_status'] or 'pending'
        print(f"  attempts={r['attempts']:>2d}  status={status:15s}  → {r['count']:>5d} jobs")

    # ── NEW: Unreachable jobs that are cover_generated (permanently stuck) ──
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
          AND hr_email_discovery_status = 'unreachable'
    """)
    print(f"\n🔒 Permanently unreachable (cover_generated, max attempts): {row['count']}")

    # ── NEW: Discovery status breakdown for ALL missing HR email ──
    print("\n── Discovery status for ALL jobs missing HR email ──")
    rows = await conn.fetch("""
        SELECT
            COALESCE(hr_email_discovery_status, 'pending') AS discovery_status,
            COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
        GROUP BY 1
        ORDER BY count DESC
    """)
    for r in rows:
        print(f"  {r['discovery_status']:15s}  → {r['count']:>5d} jobs")

    # ── NEW: Sample jobs that are stuck (show what data they have) ──
    print("\n── Sample stuck jobs (cover_generated, no HR email, newest 10) ──")
    rows = await conn.fetch("""
        SELECT
            id, job_title, company, source_portal,
            company_website,
            LENGTH(job_description) AS desc_length,
            job_url,
            COALESCE(hr_email_discovery_attempts, 0) AS attempts,
            COALESCE(hr_email_discovery_status, 'pending') AS discovery_status
        FROM jobs
        WHERE status = 'cover_generated'
          AND hr_email IS NULL
        ORDER BY scraped_at DESC
        LIMIT 10
    """)
    for r in rows:
        has_web = "✓" if r['company_website'] else "✗"
        has_desc = "✓" if r['desc_length'] and r['desc_length'] > 0 else "✗"
        has_url = "✓" if r['job_url'] else "✗"
        company = (r['company'] or 'Unknown')[:30]
        print(
            f"  [{r['discovery_status']:11s} att={r['attempts']}] "
            f"{company:30s}  portal={r['source_portal']:12s}  "
            f"web={has_web} desc={has_desc} url={has_url}  "
            f"{r['job_title'][:40]}"
        )

    # 9. Recently discovered HR emails (last 24h)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NOT NULL
          AND scraped_at > NOW() - INTERVAL '24 hours'
    """)
    print(f"\n📊 HR emails discovered in last 24h:                 {row['count']}")

    # 10. Total jobs by status
    print("\n── All jobs by status ──")
    rows = await conn.fetch("""
        SELECT status, COUNT(*) AS count
        FROM jobs
        GROUP BY status
        ORDER BY count DESC
    """)
    for r in rows:
        print(f"  {r['status']:25s} {r['count']:>6d}")

    # 11. Average discovery rate (jobs getting hr_email per hour over last 24h)
    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NOT NULL
          AND scraped_at > NOW() - INTERVAL '1 hour'
    """)
    recent_with_email = row["count"]

    row = await conn.fetchrow("""
        SELECT COUNT(*) AS count
        FROM jobs
        WHERE hr_email IS NULL
          AND status NOT IN ('filtered', 'sent', 'bounced', 'error')
    """)
    total_missing = row["count"]

    print(f"\n📈 Current backlog (jobs needing HR email):          {total_missing}")
    if total_missing > 0:
        print(f"📈 At current rate, backlog clear time:              ~{total_missing} jobs remaining")

    await conn.close()

    # ── Redis circuit breaker check ──────────────────────────────────────────
    print("\n" + "=" * 72)
    print("CIRCUIT BREAKER STATE (Redis)")
    print("=" * 72)
    try:
        import redis

        r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=3)

        for task_name in [
            "cover_ready_hr_fetch_task",
            "backfill_hr_emails_task",
            "fix_placeholder_emails_task",
        ]:
            state = r.get(f"cron:circuit:{task_name}:state") or "closed"
            opened_at = r.get(f"cron:circuit:{task_name}:opened_at")
            lock_ttl = r.ttl(f"cron:lock:{task_name}")
            last_run = r.hgetall(f"cron:last_run:{task_name}")

            icon = "🔴" if state == "open" else "🟢" if state == "closed" else "🟡"
            print(f"\n{icon} {task_name}:")
            print(f"  Circuit state: {state}")
            if opened_at:
                print(f"  Opened at: {opened_at}")
            print(f"  Lock TTL: {lock_ttl}s ({'active' if lock_ttl > 0 else 'no lock'})")
            if last_run:
                print(f"  Last run: {last_run.get('last_run', 'N/A')}")
                print(f"  Duration: {last_run.get('duration', 'N/A')}s")

        r.close()
    except Exception as exc:
        print(f"  Could not check Redis: {exc}")

    print("\n" + "=" * 72)
    print("DIAGNOSTICS COMPLETE")
    print("=" * 72)


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
