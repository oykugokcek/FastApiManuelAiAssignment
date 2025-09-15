"""
Test Suite: Rate Limiting & Bulk Creation (User Management API)

Goals:
- Enforce per-IP rate limit for POST /users (e.g., 100 requests → subsequent 429)
- Verify that 429 responses include a sensible Retry-After header (if implemented)
- Show isolation: hitting the limit on IP A must not affect IP B
- Ensure bulk creation respects rate limiting (partial success signal)
- Keep assertions resilient to small contract differences:
  - bulk response MAY include an "errors" array; if present, assert its length
  - rate-limit threshold is a constant here; adjust if your backend uses a different value
"""

from uuid import uuid4
from typing import Optional
import pytest

# Adjust this if your backend uses a different threshold
RATE_LIMIT_PER_IP = 100


# ----------------------- Helpers -----------------------

def create_user(client, unique, username: Optional[str] = None, email: Optional[str] = None,
                age: int = 20, ip: Optional[str] = None):
    """Create a single user; optionally set x-real-ip for per-IP rate limiting."""
    if username is None:
        username = unique("u")
    if email is None:
        email = f"{username}@e.com"

    headers = {}
    if ip:
        headers["x-real-ip"] = ip

    return client.post(
        "/users",
        json={"username": username, "email": email, "password": "pppppp", "age": age},
        headers=headers,
    )


def create_many_users(client, unique, count: int, ip: Optional[str] = None, prefix: str = "u"):
    """Create 'count' distinct users; return list of responses."""
    out = []
    for i in range(count):
        username = unique(f"{prefix}{i:03d}")
        r = create_user(client, unique, username=username, email=f"{username}@e.com", age=20, ip=ip)
        out.append(r)
    return out


# ----------------------- Rate limit: single IP -----------------------

def test_create_rate_limit_429_after_threshold_for_same_ip(client, unique):
    """
    After RATE_LIMIT_PER_IP successful creations from the same IP,
    the next request must respond with 429 Too Many Requests.
    """
    ip = "9.9.9.9"

    # First N should pass (200/201)
    initial = create_many_users(client, unique, RATE_LIMIT_PER_IP, ip=ip, prefix="rl_")
    assert all(r.status_code in (200, 201) for r in initial), \
        f"Expected first {RATE_LIMIT_PER_IP} to succeed."

    # One more should hit the limiter
    username = unique("rlx")
    r_last = create_user(client, unique, username=username, email=f"{username}@e.com", ip=ip)
    assert r_last.status_code == 429, f"Expected 429 after threshold; got {r_last.status_code}: {r_last.text}"


def test_rate_limit_returns_retry_after_header_if_available(client, unique):
    """
    When the rate limit is exceeded, a Retry-After header SHOULD be present.
    Accept both integer seconds and HTTP-date formats.
    If your API doesn't implement it yet, mark this test xfail or update the assertion.
    """
    ip = "8.8.8.8"
    # Hit the limit
    _ = create_many_users(client, unique, RATE_LIMIT_PER_IP, ip=ip, prefix="rlh_")
    username = unique("rlh_extra")
    r = create_user(client, unique, username=username, email=f"{username}@e.com", ip=ip)
    assert r.status_code == 429, f"Expected 429; got {r.status_code}"

    # Be lenient: just ensure the header exists and is non-empty
    retry_after = r.headers.get("Retry-After")
    assert retry_after is not None and str(retry_after).strip() != "", "Retry-After header should be present on 429"


def test_rate_limit_is_per_ip_isolated(client, unique):
    """
    Exhaust IP A, then verify IP B is still allowed to create users.
    This demonstrates per-IP isolation (no global throttle).
    """
    ip_a = "7.7.7.7"
    ip_b = "7.7.7.8"

    _ = create_many_users(client, unique, RATE_LIMIT_PER_IP, ip=ip_a, prefix="rla_")
    # IP A now blocked
    blocked_username = unique("blocked_a")
    blocked = create_user(client, unique, username=blocked_username, email=f"{blocked_username}@e.com", ip=ip_a)
    assert blocked.status_code == 429

    # IP B should still be permitted
    ok_username = unique("ok_b")
    ok = create_user(client, unique, username=ok_username, email=f"{ok_username}@e.com", ip=ip_b)
    assert ok.status_code in (200, 201), ok.text


def test_subsequent_calls_after_429_remain_blocked_immediately(client, unique):
    """
    Immediately after hitting 429, another request from the same IP should also be blocked,
    unless the window has reset (we don't wait here).
    """
    ip = "6.6.6.6"
    _ = create_many_users(client, unique, RATE_LIMIT_PER_IP, ip=ip, prefix="rlc_")
    username1 = unique("rlc_extra1")
    username2 = unique("rlc_extra2")
    r1 = create_user(client, unique, username=username1, email=f"{username1}@e.com", ip=ip)
    r2 = create_user(client, unique, username=username2, email=f"{username2}@e.com", ip=ip)
    assert r1.status_code == 429 and r2.status_code == 429, (r1.status_code, r2.status_code)


@pytest.mark.xfail(strict=True, reason="Time window reset not simulated in tests.")
def test_rate_limit_window_eventually_resets(client, unique):
    """
    Optional: if you can freeze/advance time in the app, assert that the window resets
    and requests succeed again after Retry-After. Marked xfail here.
    """
    ip = "5.5.5.5"
    _ = create_many_users(client, unique, RATE_LIMIT_PER_IP, ip=ip, prefix="rlt_")
    username = unique("rlt_block")
    r_block = create_user(client, unique, username=username, email=f"{username}@e.com", ip=ip)
    assert r_block.status_code == 429
    # TODO: advance time / wait for window -> expect success afterwards.


# ----------------------- Bulk creation under rate limit -----------------------

def test_bulk_stops_around_threshold_due_to_rate_limit(client, unique):
    """
    Bulk endpoint should honor the same per-IP rate limiting.
    If called with > RATE_LIMIT_PER_IP items from the same IP, expect:
      - HTTP 200 (bulk accepted) but partial success
      - `created` count <= RATE_LIMIT_PER_IP
      - If `errors` array is present, its length >= (submitted - created)
    """
    ip = "127.0.0.1"
    total = RATE_LIMIT_PER_IP + 20  # e.g., 120
    users = [
        {
            "username": unique(f"b{i:03d}"),
            "email": f"{unique(f'b{i}')}@e.com",
            "password": "pppppp",
            "age": 20
        }
        for i in range(total)
    ]

    r = client.post("/users/bulk", json=users, headers={"x-real-ip": ip})
    assert r.status_code == 200, r.text
    data = r.json()

    # Must expose at least a created count
    assert "created" in data, f"Bulk response should contain 'created' field: {data}"
    assert data["created"] <= RATE_LIMIT_PER_IP, f"created={data['created']} exceeds rate limit"

    # If the API returns an errors collection, validate it's consistent with partial success
    remaining = total - data["created"]
    if "errors" in data and isinstance(data["errors"], list):
        assert len(data["errors"]) >= max(0, remaining), \
            f"errors length should cover blocked items; got {len(data['errors'])}, expected >= {remaining}"


@pytest.mark.xfail(strict=True, reason="Contract decision: bulk should be all-or-nothing or partial? Currently assuming partial.")
def test_bulk_atomicity_policy_is_defined(client):
    """
    Decide whether bulk is atomic (all-or-nothing) or partial.
    This test marks the decision; update once the API contract is finalized.
    """
    # Intentionally left as a contract marker.
    assert False, "Define and assert your bulk atomicity policy."
