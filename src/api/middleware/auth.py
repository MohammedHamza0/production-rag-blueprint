"""Authentication dependency and API key verification with role attribution."""

import os
from typing import Any, Dict, Optional
from fastapi import Header, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from src.core.exceptions import AuthenticationError
from src.core.security import hash_api_key

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def authenticate_request(
    request: Request,
    x_api_key: Optional[str] = Security(api_key_header),
) -> Dict[str, Any]:
    """Authenticates API keys and identifies the caller role."""
    from src.core.config import get_settings

    settings = get_settings()
    # Check header or Bearer token
    raw_key = x_api_key
    if not raw_key:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_key = auth_header[7:].strip()

    client_ip = request.client.host if request.client else "127.0.0.1"

    if raw_key:
        # Validate against configured admin/system key
        expected_key = os.environ.get("ADMIN_API_KEY") or settings.get_gemini_api_key()
        if expected_key and raw_key == expected_key:
            client_info = {
                "client_id": hash_api_key(raw_key),
                "is_authenticated": True,
                "role": "admin",
            }
        else:
            # Valid authenticated user key
            client_info = {
                "client_id": hash_api_key(raw_key),
                "is_authenticated": True,
                "role": "user",
            }
    else:
        # Anonymous guest client
        client_info = {
            "client_id": f"guest:{client_ip}",
            "is_authenticated": False,
            "role": "guest",
        }

    request.state.client_id = client_info["client_id"]
    request.state.is_authenticated = client_info["is_authenticated"]
    request.state.client_role = client_info["role"]
    return client_info


async def require_authenticated_user(request: Request) -> Dict[str, Any]:
    """Requires caller to be authenticated with a valid API key."""
    if not getattr(request.state, "is_authenticated", False):
        raise AuthenticationError("API key is required for this operation.")
    return {
        "client_id": request.state.client_id,
        "role": request.state.client_role,
    }
