def test_geometry_home_and_login(app_client):
    client = app_client

    # geometry home page returns JSON and does not require templates
    r = client.get("/api/geometry/")
    assert r.status_code == 200
    assert r.json().get("message") == "Geometry modeling home page"

    # simple login GET endpoint
    r2 = client.get("/api/user/login")
    assert r2.status_code == 200
    assert r2.json() == {"login": "login"}
