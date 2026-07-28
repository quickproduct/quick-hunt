"""Regression tests for tenant boundaries and platform-only operations."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from services.ai.workflow import static_cover_letter_node
from services.api.core import database
from services.api.core.dependencies import (
    PlatformAdmin,
    SEEDED_ADMIN_TENANT_ID,
    get_current_data_user,
)
from services.api.core.security import decode_token, hash_password
from services.api.models.db import (
    SENTINEL_TENANT_ID,
    BillingSubscription,
    BlacklistedCompany,
    Candidate,
    Job,
    Tenant,
    User,
)
from services.api.routers.blacklist import remove_from_blacklist
from services.api.routers.candidates import get_candidate
from services.api.routers.jobs import _apply_job_filters
from services.api.routers.search import trigger_search
from services.api.routers.send import send_application
from services.api.schemas.schemas import SearchRequest, SendRequest
from services.api.services import auth_service, billing_service


def _user(tenant_id: str, role: str = "owner"):
    return SimpleNamespace(tenant_id=tenant_id, role=role)


def _candidate(tenant_id: str) -> Candidate:
    return Candidate(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name="Tenant Candidate",
        email=f"candidate-{uuid.uuid4().hex[:8]}@example.com",
    )


def _job(tenant_id: str, candidate_id: str) -> Job:
    uid = uuid.uuid4().hex
    return Job(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        candidate_id=candidate_id,
        job_title="Python Engineer",
        company="Tenant Company",
        job_url=f"https://example.com/jobs/{uid}",
        source_portal="naukri",
        dedupe_hash=uid,
        hr_email="hr@example.com",
        cover_letter="Hello",
    )


def test_platform_admin_rejects_customer_tenant_admin():
    with pytest.raises(HTTPException) as exc:
        PlatformAdmin(_user(str(uuid.uuid4()), role="admin"))
    assert exc.value.status_code == 403


def test_platform_admin_accepts_internal_service_account():
    user = _user(SENTINEL_TENANT_ID)
    assert PlatformAdmin(user) is user


@pytest.mark.asyncio
async def test_seeded_admin_uses_operational_data_scope():
    admin = _user(SEEDED_ADMIN_TENANT_ID)
    scoped = await get_current_data_user(admin)

    assert scoped.tenant_id == SENTINEL_TENANT_ID
    assert scoped.role == "owner"


@pytest.mark.asyncio
async def test_customer_keeps_own_data_scope():
    customer = _user("tenant-customer")
    assert await get_current_data_user(customer) is customer


@pytest.mark.asyncio
async def test_login_selects_matching_tenant_password(db_session, monkeypatch):
    async def _no_op_store(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auth_service, "_store_refresh_jti", _no_op_store)
    email = "shared@example.com"
    tenants = [
        Tenant(id="login-a", name="Login A", slug="login-a"),
        Tenant(id="login-b", name="Login B", slug="login-b"),
    ]
    users = [
        User(
            id="user-a",
            tenant_id="login-a",
            email=email,
            hashed_password=hash_password("password-a"),
            role="owner",
            is_active=True,
        ),
        User(
            id="user-b",
            tenant_id="login-b",
            email=email,
            hashed_password=hash_password("password-b"),
            role="owner",
            is_active=True,
        ),
    ]
    db_session.add_all([*tenants, *users])
    await db_session.commit()

    tokens = await auth_service.login(db_session, email, "password-b")
    claims = decode_token(tokens.access_token)
    assert claims["sub"] == "user-b"
    assert claims["tenant_id"] == "login-b"


@pytest.mark.asyncio
async def test_candidate_detail_hides_other_tenant(db_session):
    candidate = _candidate("tenant-a")
    db_session.add(candidate)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await get_candidate(candidate.id, _user("tenant-b"), db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_seeded_admin_can_read_operational_candidate(db_session):
    candidate = _candidate(SENTINEL_TENANT_ID)
    db_session.add(candidate)
    await db_session.commit()

    admin = await get_current_data_user(_user(SEEDED_ADMIN_TENANT_ID))
    result = await get_candidate(candidate.id, admin, db_session)
    assert result.id == candidate.id


@pytest.mark.asyncio
async def test_job_filter_returns_only_requested_tenant(db_session):
    candidate_a = _candidate("tenant-a")
    candidate_b = _candidate("tenant-b")
    job_a = _job("tenant-a", candidate_a.id)
    job_b = _job("tenant-b", candidate_b.id)
    db_session.add_all([candidate_a, candidate_b, job_a, job_b])
    await db_session.commit()

    query = _apply_job_filters(
        select(Job),
        tenant_id="tenant-a",
        status=None,
        portal=None,
        company=None,
        has_hr_email=None,
        min_score=None,
        search=None,
        max_score=None,
        has_cover=None,
        job_type=None,
    )
    rows = (await db_session.execute(query)).scalars().all()
    assert [row.id for row in rows] == [job_a.id]


@pytest.mark.asyncio
async def test_search_rejects_other_tenant_candidate(db_session):
    candidate = _candidate("tenant-a")
    db_session.add(candidate)
    await db_session.commit()

    body = SearchRequest(
        job_titles=["Engineer"],
        locations=["India"],
        portals=["naukri"],
        candidate_id=candidate.id,
    )
    with pytest.raises(HTTPException) as exc:
        await trigger_search(body, _user("tenant-b"), db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_send_rejects_other_tenant_job(db_session):
    candidate = _candidate("tenant-a")
    job = _job("tenant-a", candidate.id)
    db_session.add_all([candidate, job])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await send_application(
            job.id,
            SendRequest(candidate_id=candidate.id),
            _user("tenant-b"),
            db_session,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_send_rejects_placeholder_email_before_queue(db_session, monkeypatch):
    candidate = _candidate("tenant-a")
    job = _job("tenant-a", candidate.id)
    job.hr_email = "info@brandbucket.com"
    db_session.add_all([candidate, job])
    await db_session.commit()

    queued = []
    monkeypatch.setattr(
        "services.api.routers.send.celery_app.send_task",
        lambda *args, **kwargs: queued.append((args, kwargs)),
    )

    with pytest.raises(HTTPException) as exc:
        await send_application(
            job.id,
            SendRequest(candidate_id=candidate.id),
            _user("tenant-a"),
            db_session,
        )

    assert exc.value.status_code == 422
    assert "not a valid recruiter inbox" in exc.value.detail
    assert queued == []
    await db_session.refresh(job)
    assert job.hr_email is None


@pytest.mark.asyncio
async def test_static_cover_fallback_stays_within_job_tenant(db_session, monkeypatch):
    candidate_a = _candidate("tenant-a")
    candidate_a.static_cover_letter = "Tenant A cover"
    candidate_b = _candidate("tenant-b")
    candidate_b.static_cover_letter = "Tenant B cover"
    job_b = _job("tenant-b", candidate_b.id)
    db_session.add_all([candidate_a, candidate_b, job_b])
    await db_session.commit()

    class _SessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(database, "get_worker_session_factory", lambda: _SessionContext)

    result = await static_cover_letter_node(
        {
            "job_id": job_b.id,
            "candidate_id": candidate_a.id,
        }
    )

    await db_session.refresh(job_b)
    assert result["cover_letter"] == "Tenant B cover"
    assert job_b.candidate_id == candidate_b.id


@pytest.mark.asyncio
async def test_customer_cannot_delete_global_blacklist_entry(db_session):
    entry = BlacklistedCompany(
        id=str(uuid.uuid4()),
        tenant_id=SENTINEL_TENANT_ID,
        name="Global Block",
    )
    db_session.add(entry)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await remove_from_blacklist(entry.id, _user("tenant-a"), db_session)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_razorpay_webhook_rejects_missing_configuration(db_session, monkeypatch):
    monkeypatch.setattr(
        billing_service,
        "get_settings",
        lambda: SimpleNamespace(razorpay_webhook_secret=""),
    )
    with pytest.raises(HTTPException) as exc:
        await billing_service.handle_webhook(db_session, b"{}", "")
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_payment_link_webhook_is_idempotent(db_session):
    tenant = Tenant(
        id="tenant-billing",
        name="Billing Tenant",
        slug="billing-tenant",
    )
    db_session.add(tenant)
    await db_session.commit()
    event = {
        "payload": {
            "payment_link": {"entity": {"id": "plink_123"}},
        }
    }

    await billing_service._activate_plan(db_session, tenant.id, "pro", event)
    await billing_service._activate_plan(db_session, tenant.id, "pro", event)

    count = await db_session.scalar(
        select(func.count(BillingSubscription.id)).where(
            BillingSubscription.tenant_id == tenant.id
        )
    )
    assert count == 1
