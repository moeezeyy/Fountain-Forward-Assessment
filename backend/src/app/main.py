import os
import uuid

from fastapi import FastAPI, Depends, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field

from .db import d1_first, d1_all, d1_run
from .deps import get_current_user, require_admin, CurrentUser, SESSION_COOKIE
from .security import hash_password, verify_password, create_jwt

app = FastAPI(title="Dealership Inventory API")


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """CORS driven by app.state.allowed_origins, set at request time via
    configure() -- the Workers runtime only exposes env vars through
    self.env, not os.environ, so this can't be read at import time."""

    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        allowed = getattr(app.state, "allowed_origins", None) or os.environ.get(
            "ALLOWED_ORIGIN", "*"
        ).split(",")

        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        if origin and (origin in allowed or "*" in allowed):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        if request.method == "OPTIONS":
            # "*" is treated as a literal string (not a wildcard) by browsers
            # for credentialed requests, so these must be explicit values
            # rather than "*", or the preflight is rejected client-side.
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
            requested_headers = request.headers.get("access-control-request-headers")
            response.headers["Access-Control-Allow-Headers"] = requested_headers or "Content-Type"
        return response


app.add_middleware(DynamicCORSMiddleware)


def configure(db, jwt_secret: str, allowed_origin: str = "*") -> None:
    """Wire runtime dependencies (D1 binding, JWT secret, CORS origin) into app state."""
    app.state.db = db
    app.state.jwt_secret = jwt_secret
    app.state.allowed_origins = allowed_origin.split(",")


# ---------- Schemas ----------

class LoginRequest(BaseModel):
    email: str
    password: str


class VehicleUpdateRequest(BaseModel):
    make: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=64)
    year: int = Field(ge=1900, le=2100)
    status: str
    version: int = Field(description="Version the client started editing from")


ALLOWED_STATUSES = {"available", "sold", "pending"}


# ---------- Health ----------

@app.get("/api/health")
async def health():
    # Intentionally exposes no configuration, secrets, or internal details.
    return {"status": "ok"}


# ---------- Auth ----------

@app.post("/api/auth/login")
async def login(body: LoginRequest, response: Response):
    db = app.state.db
    user = await d1_first(db, "SELECT * FROM users WHERE email = ?", body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid email or password")

    token = create_jwt(
        {"sub": user["id"], "tv": user["token_version"]},
        app.state.jwt_secret,
    )
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 30,
        path="/",
    )
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "dealership_id": user["dealership_id"],
    }


@app.post("/api/auth/logout")
async def logout(response: Response, user: CurrentUser = Depends(get_current_user)):
    db = app.state.db
    # Bumping token_version invalidates every previously issued JWT for this
    # user immediately, even ones that have not expired yet.
    await d1_run(db, "UPDATE users SET token_version = token_version + 1 WHERE id = ?", user.id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "logged out"}


@app.get("/api/auth/me")
async def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "dealership_id": user.dealership_id,
    }


# ---------- Vehicles ----------

@app.get("/api/vehicles")
async def list_vehicles(user: CurrentUser = Depends(get_current_user)):
    db = app.state.db
    rows = await d1_all(
        db,
        "SELECT id, dealership_id, make, model, year, status, version, updated_at "
        "FROM vehicles WHERE dealership_id = ? ORDER BY make, model",
        user.dealership_id,
    )
    return rows


@app.get("/api/vehicles/{vehicle_id}")
async def get_vehicle(vehicle_id: str, user: CurrentUser = Depends(get_current_user)):
    db = app.state.db
    vehicle = await d1_first(
        db,
        "SELECT id, dealership_id, make, model, year, status, version, updated_at "
        "FROM vehicles WHERE id = ?",
        vehicle_id,
    )
    if vehicle is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    if vehicle["dealership_id"] != user.dealership_id:
        raise HTTPException(status_code=403, detail="vehicle belongs to another dealership")
    return vehicle


@app.patch("/api/vehicles/{vehicle_id}")
async def update_vehicle(
    vehicle_id: str,
    body: VehicleUpdateRequest,
    user: CurrentUser = Depends(get_current_user),
):
    require_admin(user)

    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}")

    db = app.state.db

    # Single atomic conditional UPDATE: the WHERE clause enforces dealership
    # scoping AND the optimistic-concurrency version check in one statement,
    # so there is no read-then-write gap a concurrent request can exploit.
    meta = await d1_run(
        db,
        "UPDATE vehicles SET make = ?, model = ?, year = ?, status = ?, "
        "version = version + 1, updated_at = datetime('now') "
        "WHERE id = ? AND dealership_id = ? AND version = ?",
        body.make, body.model, body.year, body.status,
        vehicle_id, user.dealership_id, body.version,
    )

    if meta.get("changes", 0) == 1:
        updated = await d1_first(
            db,
            "SELECT id, dealership_id, make, model, year, status, version, updated_at "
            "FROM vehicles WHERE id = ?",
            vehicle_id,
        )
        return updated

    # The conditional write affected zero rows. Figure out why, purely to
    # return an accurate error -- the write decision above was already final.
    existing = await d1_first(
        db,
        "SELECT dealership_id, version FROM vehicles WHERE id = ?",
        vehicle_id,
    )
    if existing is None:
        raise HTTPException(status_code=404, detail="vehicle not found")
    if existing["dealership_id"] != user.dealership_id:
        raise HTTPException(status_code=403, detail="vehicle belongs to another dealership")

    raise HTTPException(
        status_code=409,
        detail={
            "message": "vehicle was modified by someone else; refresh and retry",
            "current_version": existing["version"],
        },
    )
