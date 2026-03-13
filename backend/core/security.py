"""
core/security.py
================
JWT verification dependency for protected routes.
Supabase issues JWTs — we verify them here.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency — validates the Supabase JWT.
    Usage:  async def my_route(user = Depends(verify_token)):
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token.",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def get_current_patient_id(user: dict = Depends(verify_token)) -> str:
    """Extract patient_id (stored in JWT sub or metadata)."""
    return user.get("sub", user.get("patient_id", "anonymous"))
