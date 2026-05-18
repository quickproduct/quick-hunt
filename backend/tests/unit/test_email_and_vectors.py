"""Unit tests for email formatting, vector operations, and cosine similarity."""
import asyncio
import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ai.vector_adapter import LocalVectorAdapter, cosine_similarity
from services.sender.email_adapter import EmailPayload, BrevoAdapter
from services.sender.template import render_html, render_plain


# ------------------------------------------------------------------ #
# Brevo adapter tests (replaces non-existent ResendAdapter)            #
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_brevo_send_success():
    payload = EmailPayload(
        to_email="hr@company.com",
        subject="Application for Engineer",
        html_body="<p>Hello</p>",
        plain_body="Hello",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"messageId": "brevo_test-message-id-123"}

    adapter = BrevoAdapter.__new__(BrevoAdapter)
    adapter._api_key = "test_key"
    adapter._from_email = "bot@test.com"
    adapter._from_name = "Test Bot"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await adapter.send(payload)

    assert result == "brevo_test-message-id-123"


@pytest.mark.asyncio
async def test_brevo_send_with_attachment():
    attachment_bytes = b"%PDF-1.4 fake pdf content"
    payload = EmailPayload(
        to_email="hr@company.com",
        subject="Application",
        html_body="<p>Hi</p>",
        plain_body="Hi",
        attachment_bytes=attachment_bytes,
        attachment_filename="resume.pdf",
    )
    captured_body = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"messageId": "brevo_msg-456"}

    async def capture_post(url, json=None, headers=None):
        captured_body.update(json or {})
        return mock_response

    adapter = BrevoAdapter.__new__(BrevoAdapter)
    adapter._api_key = "test_key"
    adapter._from_email = "bot@test.com"
    adapter._from_name = "Bot"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = capture_post
        mock_cls.return_value = mock_client

        await adapter.send(payload)

    assert "attachment" in captured_body
    assert len(captured_body["attachment"]) == 1
    att = captured_body["attachment"][0]
    assert att["name"] == "resume.pdf"
    decoded = base64.b64decode(att["content"])
    assert decoded == attachment_bytes


@pytest.mark.asyncio
async def test_brevo_raises_on_error():
    payload = EmailPayload(
        to_email="hr@company.com",
        subject="Application",
        html_body="<p>Hi</p>",
        plain_body="Hi",
    )
    mock_response = MagicMock()
    mock_response.status_code = 422
    mock_response.text = "Unprocessable Entity"

    adapter = BrevoAdapter.__new__(BrevoAdapter)
    adapter._api_key = "test_key"
    adapter._from_email = "bot@test.com"
    adapter._from_name = "Bot"

    with patch("httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="Brevo error 422"):
            await adapter.send(payload)


# ------------------------------------------------------------------ #
# Email template tests                                                 #
# ------------------------------------------------------------------ #

class _Candidate:
    name = "Alice Wong"
    skills = ["Python", "Django"]
    years_experience = 5
    bio = "Full stack developer"


class _Job:
    job_title = "Python Developer"
    company = "Startup Inc"
    location = "Remote"
    cover_letter = "Opening para.\n\nMiddle para.\n\nClosing para."


def test_render_email_all_fields():
    html = render_html(_Job.cover_letter, _Candidate(), _Job())
    plain = render_plain(_Job.cover_letter, _Candidate(), _Job())
    assert "Alice Wong" in html
    assert "Alice Wong" in plain
    assert "Opening para" in html
    assert "Closing para" in plain


def test_render_email_default_salutation():
    html = render_html(_Job.cover_letter, _Candidate(), _Job())
    assert "Dear Sir" not in html
    assert "Dear Madam" not in html


def test_render_email_multiline_cover_becomes_paragraphs():
    html = render_html(_Job.cover_letter, _Candidate(), _Job())
    assert "<p>" in html
    assert html.count("<p>") >= 3


def test_render_email_html_is_valid_structure():
    html = render_html(_Job.cover_letter, _Candidate(), _Job())
    assert "<!DOCTYPE html>" in html
    assert "<html" in html
    assert "</html>" in html
    assert "<body" in html


# ------------------------------------------------------------------ #
# Local vector store tests                                             #
# ------------------------------------------------------------------ #

@pytest.mark.asyncio
async def test_local_vector_upsert_and_query():
    store = LocalVectorAdapter(path="/tmp/test_vectors_query.json")
    store._store = {}

    v1 = [1.0, 0.0, 0.0]
    v2 = [0.0, 1.0, 0.0]
    await store.upsert("id1", v1, {"job_id": "job1"})
    await store.upsert("id2", v2, {"job_id": "job2"})

    results = await store.query([0.9, 0.1, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0]["id"] == "id1"


@pytest.mark.asyncio
async def test_local_vector_delete():
    store = LocalVectorAdapter(path="/tmp/test_vectors_delete.json")
    store._store = {}

    await store.upsert("del1", [1.0, 0.0], {"job_id": "j1"})
    assert "del1" in store._store

    await store.delete("del1")
    assert "del1" not in store._store


# ------------------------------------------------------------------ #
# Cosine similarity tests                                              #
# ------------------------------------------------------------------ #

def test_cosine_similarity_identical():
    v = [1.0, 2.0, 3.0]
    assert abs(cosine_similarity(v, v) - 1.0) < 1e-9


def test_cosine_similarity_orthogonal():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 1.0, 0.0]
    assert abs(cosine_similarity(a, b) - 0.0) < 1e-9


def test_cosine_similarity_zero_vector():
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert cosine_similarity(a, b) == 0.0


# ------------------------------------------------------------------ #
# Placeholder email detection tests                                    #
# ------------------------------------------------------------------ #

class TestIsPlaceholderEmail:
    def setup_method(self):
        from services.common.placeholder_emails import is_placeholder_email
        self.is_placeholder = is_placeholder_email

    def test_shine_exact_match(self):
        assert self.is_placeholder("shinetest12345@gmail.com") is True

    def test_shine_case_insensitive(self):
        assert self.is_placeholder("ShineTest12345@Gmail.Com") is True

    def test_indeed_domains(self):
        assert self.is_placeholder("hr@in.indeed.com") is True
        assert self.is_placeholder("contact@indeed.com") is True
        assert self.is_placeholder("hr@indeedmail.com") is True

    def test_disposable_service(self):
        assert self.is_placeholder("temp_xyz@wishtempuser.com") is True

    def test_image_filename_simple(self):
        assert self.is_placeholder("logo@2x.png") is True

    def test_image_filename_retina_with_hash(self):
        assert self.is_placeholder("ladder-bookshelf-and-person@2x-434b82.webp") is True

    def test_image_filename_retina_with_dimensions(self):
        assert self.is_placeholder("Office-coordination@2x-1024x913.png") is True

    def test_image_filename_retina_scaled(self):
        assert self.is_placeholder("Comply-Homepage-Hero@2x-scaled.png") is True

    def test_image_filename_compressed_avif(self):
        assert self.is_placeholder("ai-category-card-video-gen@2x.compressed-abc123.avif") is True

    def test_image_filename_double_retina(self):
        assert self.is_placeholder("2x@2x.png") is True

    def test_css_filename(self):
        assert self.is_placeholder("_@astro.Cg3iubj1.css") is True

    def test_real_emails_pass(self):
        assert self.is_placeholder("hr@google.com") is False
        assert self.is_placeholder("careers@company.com") is False
        assert self.is_placeholder("john.doe@example.org") is False

    def test_none_returns_false(self):
        assert self.is_placeholder(None) is False

    def test_empty_string_returns_false(self):
        assert self.is_placeholder("") is False
