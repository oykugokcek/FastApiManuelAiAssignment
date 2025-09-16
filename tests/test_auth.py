"""
Test Suite: User Management API (FastAPI)
Purpose:
- Authentication (Bearer/Basic) and object-level authorization checks
- Session expiry (token expiry)
- Consistency of delete/update flows

Notes:
- For design consistency, requiring Bearer for DELETE is preferable (currently Basic is used).
- `xfail(strict=True)` will make the test suite fail loudly when the behavior is fixed intentionally.
"""

import pytest
import base64
from datetime import timedelta
import os
import uuid

# --- Helpers --------------------------------------------------------------

def bearer(t):  # Simplifies repeated header setup
    return {"Authorization": f"Bearer {t}"}


def basic(u, p):
    return {"Authorization": "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()}





# --- Existing tests (with clearer English descriptions) ------------------

def test_login_and_bearer_update(client, created_user):
    """After login, a user should be able to update their own profile using Bearer token (200)."""
    u = created_user
    # Use seeded password if running against seed data, otherwise default test password
    import os
    pw = "secret123"
    if os.environ.get("TESTS_USE_SEED_DATA", "0") == "1":
        pw = u.get("password", pw)
    r_login = client.post("/login", json={"username": u["username"], "password": pw})
    assert r_login.status_code == 200, r_login.text
    token = r_login.json()["token"]

    r = client.put(f"/users/{u['id']}", json={"age": 30}, headers=bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["age"] == 30


def test_delete_requires_basic_not_bearer(client, unique):
    """
    DELETE should reject Bearer auth (401) and accept Basic auth (200).
    Note: This design choice is debatable; consider standardizing on one scheme.
    """
    username = unique("alice")
    u = client.post("/users", json={"username": username, "email": "a@a.com", "password": "secret123", "age": 22}).json()
    token = client.post("/login", json={"username": username, "password": "secret123"}).json()["token"]

    # Wrong auth: Bearer
    r_wrong = client.delete(f"/users/{u['id']}", headers=bearer(token))
    assert r_wrong.status_code == 401

    # Correct auth: Basic
    r_ok = client.delete(f"/users/{u['id']}", headers=basic(username, "secret123"))
    assert r_ok.status_code == 200


@pytest.mark.xfail(strict=True, reason="Object-level authorization is missing: users can delete other users")
def test_user_cannot_delete_another_user(client, unique):
    """User B should not be able to delete user A (403)."""
    a_username = unique("a")
    b_username = unique("b")
    a = client.post("/users", json={"username": a_username, "email": "a@a.com", "password": "pass123", "age": 33}).json()
    b = client.post("/users", json={"username": b_username, "email": "b@b.com", "password": "pass123", "age": 34}).json()
    r = client.delete(f"/users/{a['id']}", headers=basic(b_username, "pass123"))
    assert r.status_code == 403


@pytest.mark.xfail(strict=True, reason="Token expiry is not enforced")
def test_expired_session_still_works_on_update(client, created_user):
    """An expired token should be rejected when attempting to update (401)."""
    u = created_user
    import os
    pw = "secret123"
    if os.environ.get("TESTS_USE_SEED_DATA", "0") == "1":
        pw = u.get("password", pw)
    r_login = client.post("/login", json={"username": u["username"], "password": pw})
    token = r_login.json()["token"]

    # Move the expiry into the past (ideal approach: monkeypatch `now()` but we mutate the session directly here)
    import importlib
    main = importlib.import_module("main")
    main.sessions[token]["expires_at"] = main.sessions[token]["created_at"] - timedelta(hours=1)

    r = client.put(f"/users/{u['id']}", json={"age":31}, headers=bearer(token))
    assert r.status_code == 401


# --- Additional suggested tests ------------------------------------------

def test_update_requires_bearer_token(client, created_user):
    """Attempting to update without a Bearer token should return 401."""
    u = created_user
    r = client.put(f"/users/{u['id']}", json={"age": 40})  # no Authorization
    assert r.status_code == 401


@pytest.mark.xfail(strict=True, reason="Object-level authorization is missing: users can update others")
def test_user_cannot_update_other_user(client, unique):
    """User X should not be able to update user Y using a Bearer token (403)."""
    x_username = unique("x")
    y_username = unique("y")
    x = client.post("/users", json={"username": x_username, "email": "x@x.com", "password": "pass123", "age": 20}).json()
    y = client.post("/users", json={"username": y_username, "email": "y@y.com", "password": "pass123", "age": 21}).json()
    t = client.post("/login", json={"username": x_username, "password": "pass123"}).json()["token"]
    r = client.put(f"/users/{y['id']}", json={"age": 99}, headers=bearer(t))
    assert r.status_code == 403


@pytest.mark.parametrize(
    "mode,reason",
    [
        (None, "missing header"),
        ("wrong", "wrong password"),
    ],
)
def test_delete_unauthorized_variants(client, unique, mode, reason):
    """Unauthorized variants for DELETE should return 401 (missing/wrong Basic)."""
    username = unique("alice")
    u = client.post("/users", json={"username": username, "email": "a2@a.com", "password": "secret123", "age": 22}).json()
    if mode == "wrong":
        hdr = {"Authorization": "Basic " + base64.b64encode(f"{username}:WRONG".encode()).decode()}
    else:
        hdr = {}
    r = client.delete(f"/users/{u['id']}", headers=hdr or {})
    assert r.status_code == 401, f"should be 401 for {reason}"


def test_delete_nonexistent_user_returns_404(client, unique):
    """Deleting a non-existent user should return 404 (or 400 depending on design)."""
    # Try with valid Basic auth
    username = unique("c")
    client.post("/users", json={"username": username, "email": "c@c.com", "password": "p", "age": 25})
    r = client.delete("/users/999999", headers=basic(username, "p"))
    assert r.status_code in (404, 400), "Prefer 404; standardize according to API design."


@pytest.mark.xfail(strict=True, reason="Duplicate username/email checks are missing")
def test_cannot_register_duplicate_username_or_email(client, unique):
    """Registering the same username/email twice should be rejected (409 or 422/400)."""
    base = unique("dup")
    payload = {"username": base, "email": "dup@d.com", "password": "p", "age": 30}
    r1 = client.post("/users", json=payload)
    assert r1.status_code in (200, 201)
    r2 = client.post("/users", json=payload)
    assert r2.status_code in (409, 422, 400)


@pytest.mark.parametrize(
    "payload",
    [
        {"username":"badmail","email":"not-an-email","password":"p","age":30},
        {"username":"negage","email":"n@n.com","password":"p","age":-1},
    ],
)
def test_invalid_registration_payloads(client, unique, payload):
    """Invalid registration fields should return 422 (validation) or 400."""
    # ensure usernames are unique when running with seeded data
    p = payload.copy()
    p["username"] = unique(p["username"])
    r = client.post("/users", json=p)
    assert r.status_code in (400, 422)
    assert "detail" in r.json()