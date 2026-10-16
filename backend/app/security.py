"""Password hashing and JWT helpers.

Password hashing uses stdlib hashlib.pbkdf2_hmac (pure Python / C stdlib,
no third-party C extension) because Cloudflare Python Workers run on
Pyodide and packages with native extensions (e.g. bcrypt) are not
guaranteed to have WASM wheels available. PBKDF2-SHA256 with a high
iteration count is an accepted, secure KDF for this purpose.
"""

import hashlib
import hmac
import os
import time
import base64
import json

PBKDF2_ITERATIONS = 390_000
JWT_ALG = "HS256"
JWT_TTL_SECONDS = 60 * 30  # 30 minutes


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, hash_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
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
