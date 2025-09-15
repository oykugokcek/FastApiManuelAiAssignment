import base64


def test_get_user_by_id_and_404(client, created_user):
    u = created_user
    r = client.get(f"/users/{u['id']}")
    assert r.status_code == 200
    r404 = client.get("/users/999")
    assert r404.status_code == 404

def test_get_user_invalid_id_400(client):
    r = client.get("/users/abc")
    assert r.status_code == 400

def test_update_inactive_user_returns_unchanged(client, unique):
    username = unique("cee")
    u = client.post("/users", json={"username": username, "email": "c@c.com", "password": "p@ssw0rd", "age": 26}).json()
    # deactivate
    b64 = base64.b64encode(f"{username}:p@ssw0rd".encode()).decode()
    client.delete(f"/users/{u['id']}", headers={"Authorization": f"Basic {b64}"})
    # login + update attempt
    token = client.post("/login", json={"username": username, "password": "p@ssw0rd"}).json()["token"]
    r = client.put(f"/users/{u['id']}", json={"age": 99}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["is_active"] is False
    assert r.json()["age"] == 26  # değişmemeli
