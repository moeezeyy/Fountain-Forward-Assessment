import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest
from fastapi.testclient import TestClient

from app.main import app, configure
from app.security import hash_password
from tests.fake_d1 import FakeD1

SEED_PASSWORD = "Passw0rd!"
JWT_SECRET = "test-secret-do-not-use-in-prod"


def seed(db: FakeD1):
    pw = hash_password(SEED_PASSWORD)
    db.execute_script(
        f"""
        INSERT INTO dealerships (id, name) VALUES
            ('dealership-north', 'Northgate Motors'),
            ('dealership-lake', 'Lakeside Auto');

        INSERT INTO users (id, dealership_id, email, password_hash, role, token_version) VALUES
            ('user-north-admin1', 'dealership-north', 'admin1@northgate.test', '{pw}', 'admin', 1),
            ('user-north-admin2', 'dealership-north', 'admin2@northgate.test', '{pw}', 'admin', 1),
            ('user-north-viewer1', 'dealership-north', 'viewer1@northgate.test', '{pw}', 'viewer', 1),
            ('user-lake-admin1', 'dealership-lake', 'admin1@lakeside.test', '{pw}', 'admin', 1),
            ('user-lake-viewer1', 'dealership-lake', 'viewer1@lakeside.test', '{pw}', 'viewer', 1);

        INSERT INTO vehicles (id, dealership_id, make, model, year, status, version) VALUES
            ('veh-north-1', 'dealership-north', 'Toyota', 'Camry', 2022, 'available', 1),
            ('veh-north-2', 'dealership-north', 'Honda', 'Civic', 2021, 'available', 1),
            ('veh-lake-1', 'dealership-lake', 'Subaru', 'Outback', 2022, 'available', 1);
        """
    )


@pytest.fixture()
def client():
    db = FakeD1()
    seed(db)
    configure(db, JWT_SECRET)
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = SEED_PASSWORD):
    """Logs in and returns (response, auth_headers).

    The session cookie is set with Secure=True (required for real HTTPS
    deployments). TestClient talks to the ASGI app over plain http, and
    httpx's cookie jar will not re-send a Secure cookie on an insecure
    connection -- so we extract the cookie value and pass it explicitly as
    a header on subsequent requests instead of relying on jar persistence.
    """
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    token = resp.cookies.get("session")
    headers = {"Cookie": f"session={token}"} if token else {}
    return resp, headers
