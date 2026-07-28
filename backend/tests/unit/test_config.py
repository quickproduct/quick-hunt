import pytest
from pydantic import ValidationError

from services.api.core.config import Settings


def _production_settings(**overrides):
    values = {
        "environment": "production",
        "admin_api_key": "admin-key-for-tests",
        "secret_key": "secret-key-for-tests",
        "jwt_secret": "jwt-secret-for-tests",
        "email_provider": "smtp",
        "frontend_url": "http://localhost:3001",
    }
    values.update(overrides)
    return Settings(**values)


def test_private_production_without_billing_allows_local_frontend_url():
    settings = _production_settings()

    assert settings.frontend_url == "http://localhost:3001"


def test_production_billing_requires_public_frontend_callback_url():
    with pytest.raises(ValidationError, match="Razorpay billing requires"):
        _production_settings(
            razorpay_key_id="rzp_test_key",
            razorpay_key_secret="razorpay-secret",
            razorpay_webhook_secret="razorpay-webhook-secret",
        )


def test_production_billing_accepts_public_frontend_callback_url():
    settings = _production_settings(
        frontend_url="https://hunt.example.com",
        razorpay_key_id="rzp_test_key",
        razorpay_key_secret="razorpay-secret",
        razorpay_webhook_secret="razorpay-webhook-secret",
    )

    assert settings.frontend_url == "https://hunt.example.com"
