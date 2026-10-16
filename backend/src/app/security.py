"""Password hashing and JWT helpers.

Password hashing uses a hand-rolled PBKDF2-HMAC-SHA256 (stdlib hmac +
hashlib only, no third-party C extension) because Cloudflare Python
Workers run on Pyodide and packages with native extensions (e.g. bcrypt)
are not guaranteed to have WASM wheels available. hashlib.pbkdf2_hmac
itself isn't usable either: it's backed by OpenSSL's EVP bindings
(_hashlib), which the Workers Pyodide build does not expose
(AttributeError: module 'hashlib' has no attribute 'pbkdf2_hmac'), so we
implement the RFC 2898 loop ourselves on top of hashlib.sha256/hmac,
which are available.

Iteration count is intentionally far below the usual PBKDF2 recommendation
(e.g. 390,000+) because Cloudflare's free plan hard-caps CPU time at 10ms
per request, and this pure-Python loop (no C-accelerated pbkdf2_hmac) is
slow under Pyodide. This is a known, documented tradeoff for this
assessment deployment -- see README "Known limitations".
"""

import hashlib
import hmac
import os
import time
import base64
import json

PBKDF2_ITERATIONS = 2_000
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 60 * 30  # 30 minutes


def _pbkdf2_hmac_sha256(password: bytes, salt: bytes, iterations: int, dklen: int = 32) -> bytes:
    """RFC 2898 PBKDF2 using HMAC-SHA256, single block (dklen <= 32)."""
    u = hmac.new(password, salt + (1).to_bytes(4, "big"), hashlib.sha256).digest()
    t = int.from_bytes(u, "big")
    for _ in range(iterations - 1):
        u = hmac.new(password, u, hashlib.sha256).digest()
        t ^= int.from_bytes(u, "big")
    return t.to_bytes(32, "big")[:dklen]


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = _pbkdf2_hmac_sha256(password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = _pbkdf2_hmac_sha256(password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_jwt(payload: dict, secret: str, ttl_seconds: int = JWT_TTL_SECONDS) -> str:
    now = int(time.time())
    header = {"alg": JWT_ALG, "typ": "JWT"}
    body = {**payload, "iat": now, "exp": now + ttl_seconds}
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64url_encode(json.dumps(body, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


class JWTError(Exception):
    pass


def decode_jwt(token: str, secret: str) -> dict:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError:
        raise JWTError("malformed token")

    signing_input = f"{header_b64}.{body_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual_sig = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected_sig, actual_sig):
        raise JWTError("invalid signature")

    body = json.loads(_b64url_decode(body_b64))
    if body.get("exp") is not None and int(time.time()) >= int(body["exp"]):
        raise JWTError("token expired")
    return body
