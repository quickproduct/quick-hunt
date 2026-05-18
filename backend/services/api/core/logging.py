"""Backward-compatibility shim — logging is now in services.common.logging."""
from services.common.logging import (  # noqa: F401
    add_standard_context,
    configure_logging,
    log_exception,
)
