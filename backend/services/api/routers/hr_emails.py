"""HR Email Analysis router — deduplicated registry of all HR emails seen."""
import csv
import io
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import asc, desc, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import HrEmail, Job, SendLog, User
from services.api.schemas.schemas import (
    BrevoImportResult,
    DomainAnalysisRow,
    HrEmailOut,
    HrEmailPatch,
    HrEmailStats,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/hr-emails", tags=["hr-emails"])
Auth = Annotated[User, Depends(get_current_user)]

_VALID_STATUSES = {"unknown", "valid", "invalid", "bounced", "fake"}

_SORT_COLS = {
    "last_seen_at": HrEmail.last_seen_at,
    "send_count": HrEmail.send_count,
    "hard_bounce_count": HrEmail.hard_bounce_count,
    "domain": HrEmail.domain,
    "email": HrEmail.email,
}


@router.get("", response_model=list[HrEmailOut])
async def list_hr_emails(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
    domain: Optional[str] = Query(None),
    validation_status: Optional[str] = Query(None),
    has_bounces: Optional[bool] = Query(None),
    is_placeholder: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    sort_by: str = Query(default="last_seen_at"),
    sort_dir: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    q = select(HrEmail).where(HrEmail.tenant_id == current_user.tenant_id)

    if domain:
        q = q.where(HrEmail.domain.ilike(f"%{domain}%"))
    if validation_status:
        q = q.where(HrEmail.validation_status == validation_status)
    if has_bounces is True:
        q = q.where(
            (HrEmail.hard_bounce_count > 0)
            | (HrEmail.soft_bounce_count > 0)
            | (HrEmail.blocked_count > 0)
            | (HrEmail.spam_count > 0)
        )
    elif has_bounces is False:
        q = q.where(HrEmail.hard_bounce_count == 0)
    if is_placeholder is not None:
        q = q.where(HrEmail.is_placeholder == is_placeholder)
    if search:
        t = f"%{search}%"
        q = q.where((HrEmail.email.ilike(t)) | (HrEmail.domain.ilike(t)))

    sort_col = _SORT_COLS.get(sort_by, HrEmail.last_seen_at)
    q = q.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))
    q = q.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(q)
    return result.scalars().all()


@router.get("/stats", response_model=HrEmailStats)
async def get_hr_email_stats(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    tid = current_user.tenant_id

    def _count_where(*wheres):
        q = select(func.count(HrEmail.id)).where(HrEmail.tenant_id == tid)
        for w in wheres:
            q = q.where(w)
        return q

    total = (await db.execute(_count_where())).scalar_one()
    valid_count = (await db.execute(_count_where(HrEmail.validation_status == "valid"))).scalar_one()
    bounced_count = (await db.execute(_count_where(HrEmail.validation_status == "bounced"))).scalar_one()
    fake_count = (await db.execute(_count_where(HrEmail.validation_status == "fake"))).scalar_one()
    unknown_count = (await db.execute(_count_where(HrEmail.validation_status == "unknown"))).scalar_one()

    send_sum = (await db.execute(
        select(func.coalesce(func.sum(HrEmail.send_count), 0)).where(HrEmail.tenant_id == tid)
    )).scalar_one()
    delivered_sum = (await db.execute(
        select(func.coalesce(func.sum(HrEmail.delivered_count), 0)).where(HrEmail.tenant_id == tid)
    )).scalar_one()

    domains_with_bounces = (await db.execute(
        select(func.count(func.distinct(HrEmail.domain))).where(
            HrEmail.tenant_id == tid,
            HrEmail.hard_bounce_count > 0,
        )
    )).scalar_one()

    return HrEmailStats(
        total_unique=total,
        valid_count=valid_count,
        valid_pct=round(valid_count / total * 100, 1) if total else 0.0,
        bounced_count=bounced_count,
        bounce_rate=round(bounced_count / total * 100, 1) if total else 0.0,
        fake_count=fake_count,
        unknown_count=unknown_count,
        domains_with_bounces=domains_with_bounces,
        total_sends=send_sum,
        total_delivered=delivered_sum,
    )


@router.get("/domain-analysis", response_model=list[DomainAnalysisRow])
async def get_domain_analysis(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
    sort_by: str = Query(default="bounce_count"),
    sort_dir: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
):
    bounce_expr = (
        HrEmail.hard_bounce_count
        + HrEmail.blocked_count
        + HrEmail.spam_count
    )
    rows = (await db.execute(
        select(
            HrEmail.domain,
            func.count(HrEmail.id).label("email_count"),
            func.coalesce(func.sum(HrEmail.send_count), 0).label("send_count"),
            func.coalesce(func.sum(bounce_expr), 0).label("bounce_count"),
            func.bool_and(HrEmail.mx_valid).label("mx_valid"),
        )
        .where(HrEmail.tenant_id == current_user.tenant_id)
        .group_by(HrEmail.domain)
        .order_by(
            asc("bounce_count") if sort_dir == "asc" else desc("bounce_count")
        )
        .limit(limit)
    )).all()

    return [
        DomainAnalysisRow(
            domain=row.domain,
            email_count=row.email_count,
            send_count=row.send_count,
            bounce_count=row.bounce_count,
            bounce_rate=round(row.bounce_count / row.send_count * 100, 1) if row.send_count else 0.0,
            mx_valid=row.mx_valid,
        )
        for row in rows
    ]


@router.post("/import-brevo-csv", response_model=BrevoImportResult)
async def import_brevo_csv(
    current_user: Auth,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Import a Brevo log CSV export.

    For each message (by `mid`), picks the last chronological event and:
    - Updates the matching SendLog + Job status (if found by provider_message_id)
    - Upserts the HR email address into the hr_emails registry with tallied counters

    For emails with no matching SendLog, they are still added to hr_emails for
    analysis purposes.

    CSV columns expected: st_text, ts, sub, frm, email, tag, mid, link
    """
    from services.common.placeholder_emails import is_placeholder_email

    # ── CSV Event → internal status mapping ──────────────────────────────────
    _CSV_TO_STATUS = {
        "Sent": "sent",
        "Delivered": "delivered",
        "Opened": "opened",
        "First opening": "opened",
        "Loaded by proxy": "delivered",
        "Soft bounce": "soft_bounced",
        "Hard bounce": "bounced",
        "Blocked": "blocked",
        "Deferred": "deferred",
        "Unsubscribed": "unsubscribed",
        "Error": "error",
        "Spam": "spam",
    }
    # These events mark the job as bounced and clear hr_email
    _TERMINAL = {"Hard bounce", "Blocked", "Spam"}
    # Bounce type for hr_emails counter (st_text → bounce_type arg)
    _BOUNCE_TYPE = {
        "Hard bounce": "hard",
        "Blocked": "blocked",
        "Soft bounce": "soft",
        "Spam": "spam",
    }

    # ── Parse CSV ─────────────────────────────────────────────────────────────
    raw = await file.read()
    text = raw.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    # by_mid: mid → list of (ts_dt, st_text, email)
    by_mid: dict[str, list[tuple[datetime, str, str]]] = defaultdict(list)
    # by_email: email → Counter of st_text events
    by_email: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    total_rows = 0
    for row in reader:
        st = row.get("st_text", "").strip()
        ts_str = row.get("ts", "").strip()
        email_addr = row.get("email", "").strip().lower()
        mid = row.get("mid", "").strip()

        if not email_addr or not mid:
            continue

        try:
            ts_dt = datetime.strptime(ts_str, "%d-%m-%Y %H:%M:%S")
        except ValueError:
            ts_dt = datetime.now(timezone.utc).replace(tzinfo=None)

        by_mid[mid].append((ts_dt, st, email_addr))
        by_email[email_addr][st] += 1
        total_rows += 1

    unique_messages = len(by_mid)
    unique_emails = len(by_email)

    # ── Build per-mid "last event" map ───────────────────────────────────────
    # { mid: (ts_dt, st_text, email_addr) }
    last_by_mid: dict[str, tuple[datetime, str, str]] = {}
    for mid, events in by_mid.items():
        last_by_mid[mid] = max(events, key=lambda x: x[0])

    # ── Update SendLog + Job ─────────────────────────────────────────────────
    send_logs_updated = 0
    jobs_updated = 0

    BATCH = 200
    mid_list = list(last_by_mid.keys())

    for batch_start in range(0, len(mid_list), BATCH):
        batch_mids = mid_list[batch_start: batch_start + BATCH]

        # Fetch all send_logs matching these mids in one query
        rows = (await db.execute(
            select(SendLog.id, SendLog.job_id, SendLog.provider_message_id)
            .where(SendLog.provider_message_id.in_(batch_mids))
        )).all()

        for log_row in rows:
            log_id = log_row.id
            job_id = log_row.job_id
            mid_val = log_row.provider_message_id

            ts_dt, st_text, _ = last_by_mid[mid_val]
            new_status = _CSV_TO_STATUS.get(st_text, "sent")

            await db.execute(
                update(SendLog)
                .where(SendLog.id == log_id)
                .values(status=new_status)
            )
            send_logs_updated += 1

            if st_text in _TERMINAL and job_id:
                await db.execute(
                    update(Job)
                    .where(Job.id == job_id)
                    .values(status="bounced", hr_email=None)
                )
                jobs_updated += 1

        await db.commit()

    unmatched_messages = unique_messages - send_logs_updated

    # ── Upsert HrEmail records for every unique email ─────────────────────────
    hr_emails_upserted = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    tid = current_user.tenant_id

    email_list = list(by_email.items())
    for batch_start in range(0, len(email_list), BATCH):
        batch = email_list[batch_start: batch_start + BATCH]
        for email_addr, counts in batch:
            sent = counts.get("Sent", 0)
            delivered = counts.get("Delivered", 0) + counts.get("Loaded by proxy", 0)
            opened = counts.get("Opened", 0) + counts.get("First opening", 0)
            hard_bounce = counts.get("Hard bounce", 0)
            soft_bounce = counts.get("Soft bounce", 0)
            blocked = counts.get("Blocked", 0)
            spam = counts.get("Spam", 0)
            total_bounce = hard_bounce + blocked + spam

            is_ph = is_placeholder_email(email_addr)
            domain = email_addr.rsplit("@", 1)[-1] if "@" in email_addr else email_addr

            if total_bounce > 0:
                val_status = "bounced"
            elif is_ph:
                val_status = "fake"
            elif delivered > 0:
                val_status = "valid"
            else:
                val_status = "unknown"

            # Determine last bounce type for timestamp field
            last_bounce_type = None
            if hard_bounce > 0:
                last_bounce_type = "hard"
            elif blocked > 0:
                last_bounce_type = "blocked"
            elif spam > 0:
                last_bounce_type = "spam"
            elif soft_bounce > 0:
                last_bounce_type = "soft"

            stmt = pg_insert(HrEmail).values(
                id=str(uuid.uuid4()),
                tenant_id=tid,
                email=email_addr,
                domain=domain,
                send_count=sent,
                delivered_count=delivered,
                opened_count=opened,
                hard_bounce_count=hard_bounce,
                soft_bounce_count=soft_bounce,
                blocked_count=blocked,
                spam_count=spam,
                last_bounce_type=last_bounce_type,
                last_bounce_at=now if last_bounce_type else None,
                validation_status=val_status,
                is_placeholder=is_ph,
                first_seen_at=now,
                last_seen_at=now,
            ).on_conflict_do_update(
                constraint="uq_hr_emails_tenant_email",
                set_={
                    # Take max of existing vs CSV values — never go backwards
                    "send_count": func.greatest(HrEmail.send_count, sent),
                    "delivered_count": func.greatest(HrEmail.delivered_count, delivered),
                    "opened_count": func.greatest(HrEmail.opened_count, opened),
                    "hard_bounce_count": func.greatest(HrEmail.hard_bounce_count, hard_bounce),
                    "soft_bounce_count": func.greatest(HrEmail.soft_bounce_count, soft_bounce),
                    "blocked_count": func.greatest(HrEmail.blocked_count, blocked),
                    "spam_count": func.greatest(HrEmail.spam_count, spam),
                    "last_bounce_type": last_bounce_type if last_bounce_type else HrEmail.last_bounce_type,
                    "last_bounce_at": now if last_bounce_type else HrEmail.last_bounce_at,
                    "validation_status": val_status,
                    "last_seen_at": now,
                },
            )
            await db.execute(stmt)
            hr_emails_upserted += 1

        await db.commit()

    logger.info(
        "brevo_csv_imported",
        tenant_id=tid,
        total_rows=total_rows,
        unique_messages=unique_messages,
        unique_emails=unique_emails,
        send_logs_updated=send_logs_updated,
        jobs_updated=jobs_updated,
        hr_emails_upserted=hr_emails_upserted,
    )

    return BrevoImportResult(
        total_rows=total_rows,
        unique_messages=unique_messages,
        unique_emails=unique_emails,
        send_logs_updated=send_logs_updated,
        jobs_updated=jobs_updated,
        hr_emails_upserted=hr_emails_upserted,
        unmatched_messages=unmatched_messages,
    )


@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED)
async def trigger_backfill(current_user: Auth):
    """Enqueue the one-time backfill Celery task to populate hr_emails from existing jobs."""
    from services.scraper.celery_app import celery_app
    task = celery_app.send_task(
        "services.api.tasks.hr_email_tasks.backfill_hr_emails_registry_task",
        kwargs={"tenant_id": current_user.tenant_id},
        queue="jh_scraping_enrichment",
    )
    return {"task_id": task.id, "status": "queued"}


@router.get("/{email_id}", response_model=HrEmailOut)
async def get_hr_email(
    email_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(HrEmail, email_id)
    if not record or record.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="HR email not found")
    return record


@router.post("/{email_id}/validate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_mx_validation(
    email_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    """Enqueue MX validation Celery task for this email's domain."""
    record = await db.get(HrEmail, email_id)
    if not record or record.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="HR email not found")
    from services.scraper.celery_app import celery_app
    task = celery_app.send_task(
        "services.api.tasks.hr_email_tasks.validate_mx_task",
        kwargs={"email_id": email_id},
        queue="jh_scraping_enrichment",
    )
    return {"task_id": task.id, "domain": record.domain}


@router.patch("/{email_id}", response_model=HrEmailOut)
async def update_hr_email(
    email_id: str,
    body: HrEmailPatch,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    """Manually override validation_status for an HR email."""
    record = await db.get(HrEmail, email_id)
    if not record or record.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="HR email not found")
    if body.validation_status is not None:
        if body.validation_status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status. Choose from: {sorted(_VALID_STATUSES)}",
            )
        record.validation_status = body.validation_status
    await db.commit()
    await db.refresh(record)
    return record
