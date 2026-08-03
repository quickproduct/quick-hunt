import pytest
from pydantic import ValidationError

from services.api.routers.send import DirectSendRequest, MAX_DIRECT_SEND_EMAILS


def _emails(count: int) -> list[str]:
    return [f"hr{index}@example.com" for index in range(count)]


def test_direct_send_request_accepts_1000_email_addresses():
    request = DirectSendRequest(
        candidate_id="candidate-id",
        hr_emails=_emails(MAX_DIRECT_SEND_EMAILS),
    )

    assert len(request.hr_emails) == MAX_DIRECT_SEND_EMAILS


def test_direct_send_request_rejects_more_than_1000_email_addresses():
    with pytest.raises(ValidationError, match="at most 1000 items"):
        DirectSendRequest(
            candidate_id="candidate-id",
            hr_emails=_emails(MAX_DIRECT_SEND_EMAILS + 1),
        )
