"""The BFF's identity boundary.

The portal signs { userId, expiresAt } as an HS256 JWT with SESSION_SECRET (see
chat-portal src/lib/session.ts). This service shares that secret and reads the
logged-in user id straight out of the token. The login itself stays in the
portal; the BFF only consumes the identity.
"""

import jwt
from fastapi import Header, HTTPException

from .config import SESSION_SECRET


def verify_portal_token(token: str | None) -> str | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, SESSION_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    user_id = payload.get("userId")
    return user_id if isinstance(user_id, str) else None


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer ") :]
    return None


async def require_user(authorization: str | None = Header(default=None)) -> str:
    user_id = verify_portal_token(bearer_token(authorization))
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user_id
