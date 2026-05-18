from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from services.api.core.config import get_settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def api_key_auth(api_key: str = Security(_api_key_header)) -> str:
    """Dependency: validates X-API-Key header against ADMIN_API_KEY setting."""
    settings = get_settings()
    if not api_key or api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
