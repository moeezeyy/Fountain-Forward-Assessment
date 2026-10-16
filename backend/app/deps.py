from dataclasses import dataclass

from fastapi import Request, HTTPException

from .security import decode_jwt, JWTError
from .db import d1_first

SESSION_COOKIE = "session"


@dataclass
class CurrentUser:
    id: str
    dealership_id: str
    role: str
    email: str


async def get_current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")

    secret = request.app.state.jwt_secret
    try:
        payload = decode_jwt(token, secret)
    except JWTError:
        raise HTTPException(status_code=401, detail="invalid or expired session")

    db = request.app.state.db
    user = await d1_first(db, "SELECT * FROM users WHERE id = ?", payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="user no longer exists")

    # token_version mismatch means the token was issued before a logout /
    # credential change invalidated all prior sessions for this user.
    if int(user["token_version"]) != int(payload.get("tv", -1)):
        raise HTTPException(status_code=401, detail="session invalidated")

    return CurrentUser(
        id=user["id"],
        dealership_id=user["dealership_id"],
        role=user["role"],
        email=user["email"],
    )


def require_admin(user: CurrentUser) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="administrator role required")
