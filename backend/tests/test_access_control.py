from tests.conftest import login


def test_viewer_can_list_own_dealership_vehicles(client):
    _, headers = login(client, "viewer1@northgate.test")
    resp = client.get("/api/vehicles", headers=headers)
    assert resp.status_code == 200
    ids = {v["id"] for v in resp.json()}
    assert ids == {"veh-north-1", "veh-north-2"}


def test_viewer_cannot_edit_vehicle(client):
    _, headers = login(client, "viewer1@northgate.test")
    resp = client.patch(
        "/api/vehicles/veh-north-1",
        headers=headers,
        json={"make": "Toyota", "model": "Camry", "year": 2022, "status": "sold", "version": 1},
    )
    assert resp.status_code == 403

    # Rejected write must leave stored data unchanged.
    check = client.get("/api/vehicles/veh-north-1", headers=headers)
    assert check.json()["status"] == "available"
    assert check.json()["version"] == 1


def test_admin_can_edit_own_dealership_vehicle(client):
    _, headers = login(client, "admin1@northgate.test")
    resp = client.patch(
        "/api/vehicles/veh-north-1",
        headers=headers,
        json={"make": "Toyota", "model": "Camry", "year": 2022, "status": "sold", "version": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "sold"
    assert body["version"] == 2


def test_admin_cannot_read_other_dealership_vehicle(client):
    _, headers = login(client, "admin1@northgate.test")
    resp = client.get("/api/vehicles/veh-lake-1", headers=headers)
    assert resp.status_code == 403


def test_admin_cannot_update_other_dealership_vehicle(client):
    _, headers = login(client, "admin1@northgate.test")
    resp = client.patch(
        "/api/vehicles/veh-lake-1",
        headers=headers,
        json={"make": "Subaru", "model": "Outback", "year": 2022, "status": "sold", "version": 1},
    )
    assert resp.status_code == 403

    _, lake_headers = login(client, "admin1@lakeside.test")
    check = client.get("/api/vehicles/veh-lake-1", headers=lake_headers)
    assert check.json()["status"] == "available"
    assert check.json()["version"] == 1


def test_missing_authentication_on_all_protected_routes(client):
    assert client.get("/api/vehicles").status_code == 401
    assert client.get("/api/vehicles/veh-north-1").status_code == 401
    assert client.patch(
        "/api/vehicles/veh-north-1",
        json={"make": "x", "model": "y", "year": 2020, "status": "available", "version": 1},
    ).status_code == 401
