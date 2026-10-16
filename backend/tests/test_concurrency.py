"""Regression test for the lost-update / concurrent-edit scenario.

Two administrators from the same dealership load veh-north-1 at version=1
and submit different changes using that same starting version. Exactly one
must succeed; the other must receive 409 and must not have overwritten the
winner. See defective_example/ for a demonstration of this test failing
against a non-atomic (read-then-write) implementation.
"""

from tests.conftest import login


def test_concurrent_edits_from_same_starting_version(client):
    _, admin1_headers = login(client, "admin1@northgate.test")
    _, admin2_headers = login(client, "admin2@northgate.test")

    # Both admins "loaded" the vehicle at version 1 and now submit
    # different edits based on that same starting version.
    resp1 = client.patch(
        "/api/vehicles/veh-north-1",
        headers=admin1_headers,
        json={"make": "Toyota", "model": "Camry", "year": 2022, "status": "sold", "version": 1},
    )
    resp2 = client.patch(
        "/api/vehicles/veh-north-1",
        headers=admin2_headers,
        json={"make": "Toyota", "model": "Camry", "year": 2022, "status": "pending", "version": 1},
    )

    statuses = {resp1.status_code, resp2.status_code}
    assert statuses == {200, 409}, f"expected exactly one 200 and one 409, got {resp1.status_code}, {resp2.status_code}"

    winner, loser = (resp1, resp2) if resp1.status_code == 200 else (resp2, resp1)

    assert winner.json()["version"] == 2

    # The conflict response must identify the current version so the
    # frontend can tell the user to refresh.
    assert "current_version" in loser.json()["detail"]
    assert loser.json()["detail"]["current_version"] == 2

    # The stored record must reflect only the winning update -- the loser's
    # field values must never have been written, even transiently.
    final = client.get("/api/vehicles/veh-north-1", headers=admin1_headers).json()
    assert final["version"] == 2
    assert final["status"] == winner.json()["status"]
    assert final["status"] != "pending" or winner.json()["status"] == "pending"


def test_stale_edit_after_someone_else_already_updated_is_rejected(client):
    _, admin1_headers = login(client, "admin1@northgate.test")
    _, admin2_headers = login(client, "admin2@northgate.test")

    first = client.patch(
        "/api/vehicles/veh-north-2",
        headers=admin1_headers,
        json={"make": "Honda", "model": "Civic", "year": 2021, "status": "sold", "version": 1},
    )
    assert first.status_code == 200
    assert first.json()["version"] == 2

    # admin2 still has the stale version=1 in their UI and retries.
    stale = client.patch(
        "/api/vehicles/veh-north-2",
        headers=admin2_headers,
        json={"make": "Honda", "model": "Civic", "year": 2021, "status": "pending", "version": 1},
    )
    assert stale.status_code == 409

    final = client.get("/api/vehicles/veh-north-2", headers=admin1_headers).json()
    assert final["status"] == "sold"
    assert final["version"] == 2
