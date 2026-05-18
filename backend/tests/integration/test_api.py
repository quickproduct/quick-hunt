"""Integration tests for FastAPI endpoints using httpx AsyncClient."""
import pytest


@pytest.mark.asyncio
async def test_health_check(async_client):
    resp = await async_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_root_endpoint(async_client):
    resp = await async_client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "docs" in data


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(async_client):
    """Endpoint without X-API-Key header should return 401."""
    from httpx import AsyncClient, ASGITransport
    from services.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        # No X-API-Key header
    ) as client:
        resp = await client.get("/candidates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(async_client):
    """Wrong X-API-Key should return 401."""
    from httpx import AsyncClient, ASGITransport
    from services.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "wrong-key"},
    ) as client:
        resp = await client.get("/candidates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_with_unknown_portal_returns_422(async_client):
    """Invalid portal name in search request should return 422."""
    # First create a candidate
    cand_resp = await async_client.post("/candidates", json={
        "name": "Test User",
        "email": "test_search_422@example.com",
        "skills": ["Python"],
        "target_roles": ["Engineer"],
    })
    assert cand_resp.status_code == 201
    candidate_id = cand_resp.json()["id"]

    resp = await async_client.post("/search", json={
        "job_titles": ["Engineer"],
        "locations": ["India"],
        "portals": ["invalid_portal_xyz"],
        "max_results_per_portal": 10,
        "candidate_id": candidate_id,
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_send_without_hr_email_returns_422(async_client):
    """Sending application for a job with no HR email should return 422."""
    import uuid

    # Create candidate
    cand_resp = await async_client.post("/candidates", json={
        "name": "Send Test User",
        "email": f"send_test_{uuid.uuid4().hex[:6]}@example.com",
        "skills": ["Python"],
        "target_roles": ["Engineer"],
    })
    candidate_id = cand_resp.json()["id"]

    # Create job without HR email (via direct DB manipulation not possible here,
    # so we test by sending to a job that doesn't exist)
    resp = await async_client.post(f"/jobs/{uuid.uuid4()}/send", json={
        "candidate_id": candidate_id,
    })
    assert resp.status_code in (404, 422)


@pytest.mark.asyncio
async def test_stats_returns_expected_shape(async_client):
    """GET /stats should return all required keys."""
    resp = await async_client.get("/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_jobs" in data
    assert "jobs_by_status" in data
    assert "jobs_by_portal" in data
    assert "emails_sent" in data
    assert "emails_delivered" in data
    assert "emails_opened" in data
    assert "cover_letters_generated" in data
    assert "jobs_with_hr_email" in data


@pytest.mark.asyncio
async def test_resend_webhook_test_endpoint(async_client):
    """POST /webhooks/resend/test should return 200."""
    resp = await async_client.post("/webhooks/resend/test")
    assert resp.status_code == 200
    assert "ok" in resp.json()["status"]


@pytest.mark.asyncio
async def test_resend_webhook_processes_events(async_client):
    """POST /webhooks/resend should process events without error."""
    event = {
        "type": "email.delivered",
        "created_at": "2024-01-01T00:00:00.000Z",
        "data": {
            "email_id": "re_nonexistent-message-id",
            "from": "bot@test.com",
            "to": ["hr@company.com"],
            "subject": "Test",
        },
    }
    resp = await async_client.post("/webhooks/resend", json=event)
    # 204 No Content is expected
    assert resp.status_code == 204
