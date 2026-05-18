#!/usr/bin/env python3
"""Update send_logs (and linked jobs) with last known event from a Brevo CSV export.

For each unique message-ID in the CSV:
  - Finds the matching send_log record (by provider_message_id, or fallback to_email)
  - Upgrades send_log status + timestamp (rank-guarded — never downgrade)
  - Applies the correct job status action:
      delivered / opened  → jobs.status = 'sent'
      soft_bounce         → jobs.status = 'cover_generated'  (back to cover-ready for resend)
      hard_bounce/blocked → jobs.status = 'bounced'
      deferred/error      → no job change

Run from project root:
    python backend/scripts/update_send_log_events.py [--dry-run] <csv_path>
"""

import asyncio
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

CSV_DATE_FMT = "%d-%m-%Y %H:%M:%S"

# Maps CSV st_text → (db_status, timestamp_column_or_None, job_action)
# job_action: 'sent' | 'cover_ready' | 'bounced' | None
EVENT_MAP = {
    "Sent":             ("sent",         "sent_at",       "sent"),
    "Delivered":        ("delivered",    "delivered_at",  "sent"),
    "Opened":           ("opened",       "opened_at",     "sent"),
    "First opening":    ("opened",       "opened_at",     "sent"),
    "Loaded by proxy":  ("opened",       "opened_at",     "sent"),
    # Soft bounce: skip send_log update entirely (None ts_col, status kept as-is via
    # a sentinel that the rank guard will always skip). Job is reset to cover_generated
    # and its send_log record is deleted so resend can proceed with a clean slate.
    "Soft bounce":      ("soft_bounced", None,            "cover_ready"),
    "Hard bounce":      ("bounced",      None,            "bounced"),
    "Blocked":          ("blocked",      None,            "bounced"),
    "Unsubscribed":     ("unsubscribed", None,            "bounced"),
    "Deferred":         ("deferred",     None,            None),
    "Error":            ("failed",       None,            None),
    "Spam":             ("spam",         None,            "bounced"),
}

# Lower rank = lower precedence; send_log never goes backwards
STATUS_RANK = {
    "queued":       0,
    "deferred":     1,
    "soft_bounced": 1,
    "sent":         2,
    "delivered":    3,
    "opened":       4,
    "clicked":      5,
    # terminal negatives — don't overwrite these with positive events
    "bounced":      6,
    "blocked":      6,
    "spam":         6,
    "unsubscribed": 6,
    "failed":       6,
}

# Jobs whose status we must NEVER overwrite (hard terminals)
JOB_HARD_TERMINAL = {"bounced", "error", "filtered"}


def parse_csv(csv_path: str) -> dict:
    """Return {mid: best_row} keeping only the latest-timestamp row per message-id."""
    best: dict = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            event = row.get("st_text", "").strip()
            if event not in EVENT_MAP:
                continue
            mid = row.get("mid", "").strip()
            if not mid:
                continue
            ts_str = row.get("ts", "").strip()
            try:
                ts = datetime.strptime(ts_str, CSV_DATE_FMT)
            except ValueError:
                continue
            if mid not in best or ts > best[mid]["_ts"]:
                best[mid] = {**row, "_ts": ts}
    return best


async def run(csv_path: str, dry_run: bool):
    import asyncpg
    from services.api.core.config import get_settings

    settings = get_settings()
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(pg_url)

    best_events = parse_csv(csv_path)
    print(f"CSV: {len(best_events)} unique message-IDs with a known last event\n")

    matched_by_mid    = 0
    matched_by_email  = 0
    skipped_rank      = 0
    send_log_updated  = 0
    jobs_sent         = 0
    jobs_cover_ready  = 0
    jobs_bounced      = 0
    not_found         = 0

    try:
        for mid, row in best_events.items():
            event      = row["st_text"].strip()
            new_status, ts_col, job_action = EVENT_MAP[event]
            event_ts   = row["_ts"]
            hr_email   = row.get("email", "").strip()

            # ── 1. Match send_log ──────────────────────────────────────────
            db_row = await conn.fetchrow(
                "SELECT id, job_id, status FROM send_logs WHERE provider_message_id=$1 LIMIT 1",
                mid,
            )
            if db_row:
                matched_by_mid += 1
            else:
                if not hr_email:
                    not_found += 1
                    continue
                db_row = await conn.fetchrow(
                    """SELECT id, job_id, status FROM send_logs
                       WHERE to_email=$1
                       ORDER BY sent_at DESC NULLS LAST LIMIT 1""",
                    hr_email,
                )
                if db_row:
                    matched_by_email += 1
                else:
                    not_found += 1
                    print(f"  NOT FOUND: mid={mid[:44]} email={hr_email}")
                    continue

            record_id      = db_row["id"]
            job_id         = db_row["job_id"]
            current_status = db_row["status"] or "queued"
            current_rank   = STATUS_RANK.get(current_status, 0)
            new_rank       = STATUS_RANK.get(new_status, 0)

            # ── 2. Update send_log (rank-guarded) ─────────────────────────
            if new_rank > current_rank:
                set_clause = f"status=$1"
                params     = [new_status]
                if ts_col:
                    set_clause += f", {ts_col}=$2"
                    params.append(event_ts)
                params.append(record_id)

                if dry_run:
                    ts_info = f" {ts_col}={event_ts}" if ts_col else ""
                    print(
                        f"  [DRY] send_log {record_id} | {hr_email} | "
                        f"{current_status} → {new_status}{ts_info}"
                    )
                else:
                    await conn.execute(
                        f"UPDATE send_logs SET {set_clause} WHERE id=${len(params)}",
                        *params,
                    )
                send_log_updated += 1
            else:
                skipped_rank += 1

            # ── 3. Update job status ───────────────────────────────────────
            if job_id and job_action:
                job_row = await conn.fetchrow(
                    "SELECT id, status FROM jobs WHERE id=$1", job_id
                )
                if not job_row:
                    continue

                current_job_status = job_row["status"]

                if job_action == "cover_ready":
                    # Soft bounce: reset job to cover_generated and DELETE the send_log
                    # record so there is no blocking entry in _ACTIVE_SEND_STATUSES.
                    # Skip only if job is already a hard terminal (bounced/error/filtered).
                    if current_job_status not in JOB_HARD_TERMINAL:
                        if dry_run:
                            print(
                                f"  [DRY] job {job_id} | {current_job_status} "
                                f"→ cover_generated + delete send_log {record_id}"
                            )
                        else:
                            await conn.execute(
                                "UPDATE jobs SET status='cover_generated' WHERE id=$1",
                                job_id,
                            )
                            await conn.execute(
                                "DELETE FROM send_logs WHERE id=$1", record_id
                            )
                        jobs_cover_ready += 1

                elif job_action == "bounced":
                    if current_job_status not in JOB_HARD_TERMINAL:
                        if dry_run:
                            print(
                                f"  [DRY] job {job_id} | {current_job_status} → bounced"
                            )
                        else:
                            await conn.execute(
                                "UPDATE jobs SET status='bounced' WHERE id=$1", job_id
                            )
                        jobs_bounced += 1

                elif job_action == "sent":
                    # Only fix if job is stuck before terminal
                    if current_job_status not in JOB_HARD_TERMINAL | {"sent"}:
                        if dry_run:
                            print(
                                f"  [DRY] job {job_id} | {current_job_status} → sent"
                            )
                        else:
                            await conn.execute(
                                "UPDATE jobs SET status='sent' WHERE id=$1", job_id
                            )
                        jobs_sent += 1

    finally:
        await conn.close()

    print()
    print("=" * 62)
    print(f"  Unique message-IDs in CSV          : {len(best_events)}")
    print(f"  Matched by provider_message_id     : {matched_by_mid}")
    print(f"  Matched by to_email (fallback)     : {matched_by_email}")
    print(f"  Not found in DB                    : {not_found}")
    print(f"  Skipped send_log (higher status)   : {skipped_rank}")
    print(f"  {'Would update' if dry_run else 'Updated'} send_logs                : {send_log_updated}")
    print(f"  {'Would set' if dry_run else 'Set'} jobs → sent               : {jobs_sent}")
    print(f"  {'Would reset' if dry_run else 'Reset'} jobs → cover_generated  : {jobs_cover_ready}  ← soft-bounce resend")
    print(f"  {'Would set' if dry_run else 'Set'} jobs → bounced            : {jobs_bounced}")
    if dry_run:
        print()
        print("  Re-run without --dry-run to apply.")
    print("=" * 62)


def main():
    args    = sys.argv[1:]
    dry_run = "--dry-run" in args
    args    = [a for a in args if a != "--dry-run"]

    csv_path = args[0] if args else str(
        Path.home() / "Downloads" / "logs-10864905-1776888017278.csv"
    )

    if not Path(csv_path).exists():
        print(f"ERROR: CSV not found at {csv_path}")
        sys.exit(1)

    print(f"CSV path : {csv_path}")
    print(f"Dry run  : {dry_run}\n")
    asyncio.run(run(csv_path, dry_run))


if __name__ == "__main__":
    main()
