"""
Test Suite: Stats & Health Endpoints (User Management API)

Goals:
- /stats must be protected (no sensitive data leakage)
- /stats counters should be sane (non-negative ints, monotonic after creation)
- /health should be minimal, stable, and free of secrets
- Uptime should move forward; "memory_users" must not mirror total user count
- Contract gaps are marked with xfail(strict=True) to document current issues
"""

import pytest
import time
from uuid import uuid4

# Adjust or extend if your backend uses different keys
SENSITIVE_KEYS = {
    "session_tokens", "tokens", "token", "user_emails", "emails",
    "passwords", "password", "password_hash", "secrets", "api_keys",
    "authorization", "basic_auth", "bearer_tokens",
}

# ----------------------- Helpers -----------------------

def make_user(client, unique, username=None, email=None, age=22, password="pppppp"):
    """Create a user and return its JSON."""
    if username is None:
        username = unique("u")
    if email is None:
        email = f"{unique('mail')}@e.com"
    r = client.post("/users", json={
        "username": username, "email": email, "password": password, "age": age
    })
    assert r.status_code in (200, 201), r.text
    return r.json()

def contains_sensitive_keys(obj) -> bool:
    """Recursively check if a dict/list contains any sensitive-looking keys."""
    if isinstance(obj, dict):
        keys = {k.lower() for k in obj.keys()}
        if keys & SENSITIVE_KEYS:
            return True
        return any(contains_sensitive_keys(v) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_sensitive_keys(x) for x in obj)
    return False


# ----------------------- /stats: access & leakage -----------------------

@pytest.mark.xfail(strict=True, reason="Stats should be protected: /stats must not be publicly readable")
def test_stats_requires_auth_or_admin(client):
    """
    /stats should require authentication/privilege; anonymous access should be 401/403.
    """
    r = client.get("/stats")
    assert r.status_code in (401, 403)

@pytest.mark.xfail(strict=True, reason="/stats?include_details leaks internal data; should be forbidden or scrubbed")
def test_stats_include_details_must_not_leak_sensitive_fields(client, unique):
    """
    Requesting /stats?include_details=True should not leak session tokens/emails/etc.
    The preferred behavior is to deny (401/403) or return sanitized aggregates.
    """
    uname = unique("s")
    make_user(client, unique, username=uname, email=f"{unique('s')}@s.com")
    token = client.post("/login", json={"username": uname, "password": "pppppp"}).json()["token"]
    r = client.get("/stats", params={"include_details": True})
    # Expect denial OR, if allowed, a sanitized payload
    assert r.status_code in (401, 403), f"details should not be public: {r.status_code} {r.text}"
    body = r.json()
    assert not contains_sensitive_keys(body), f"/stats leaks sensitive keys: {list(body.keys())}"


# ----------------------- /stats: counters & consistency -----------------------

def test_stats_counters_are_non_negative_integers(client):
    """
    /stats counters (if present) should be non-negative integers; uptime may be int/float.
    """
    r = client.get("/stats")
    assert r.status_code == 200, r.text
    body = r.json()

    for key in ("total_users", "active_sessions"):
        if key in body:
            assert isinstance(body[key], int) and body[key] >= 0, f"{key} must be non-negative int"

    if "uptime_seconds" in body:
        assert isinstance(body["uptime_seconds"], (int, float)) and body["uptime_seconds"] >= 0

def test_stats_total_users_monotonic_after_creation(client, unique):
    """
    Creating a new user should not decrease the reported total_users counter.
    (We only require monotonic non-decrease to be robust against parallel tests.)
    """
    before = client.get("/stats").json()
    before_count = before.get("total_users")

    make_user(client, unique)  # create one more user

    after = client.get("/stats").json()
    after_count = after.get("total_users")

    if before_count is not None and after_count is not None:
        assert after_count >= before_count, f"total_users decreased: {before_count} -> {after_count}"


# ----------------------- /health: minimal, non-sensitive, stable -----------------------

def test_health_is_minimal_and_non_sensitive(client):
    """
    /health should return 200 and contain a minimal status field, without secrets.
    """
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()

    assert any(k in body for k in ("status", "ok", "healthy")), "health should expose an overall status field"
    assert not contains_sensitive_keys(body), f"/health leaks sensitive keys: {list(body.keys())}"

def test_health_uptime_moves_forward(client):
    """
    If uptime_seconds is exposed, it should be monotonic non-decreasing across calls.
    """
    r1 = client.get("/health")
    assert r1.status_code == 200
    t1 = r1.json().get("uptime_seconds")

    time.sleep(0.01)  # tiny gap; we don't assume real seconds resolution
    r2 = client.get("/health")
    assert r2.status_code == 200
    t2 = r2.json().get("uptime_seconds")

    if isinstance(t1, (int, float)) and isinstance(t2, (int, float)):
        assert t2 >= t1, f"uptime_seconds went backwards: {t1} -> {t2}"

def test_health_memory_users_is_not_total_users_count(client):
    """
    Regression guard from your note: health.memory_users must not mirror stats.total_users.
    This ensures the health payload doesn't accidentally expose user counts as 'memory' stats.
    """
    st = client.get("/stats").json()
    hl = client.get("/health").json()
    if "total_users" in st and "memory_users" in hl:
        assert st["total_users"] != hl["memory_users"], \
            "health.memory_users must not equal stats.total_users"


# ----------------------- Optional: DB status contract -----------------------

@pytest.mark.xfail(strict=True, reason="Health should expose DB connectivity explicitly (db: ok)")
def test_health_reports_db_status_if_app_has_db(client):
    """
    Preferred contract: /health contains a 'db' flag (True/'ok') indicating DB connectivity.
    """
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "db" in body and body["db"] in (True, "ok"), "health should expose DB connectivity"
