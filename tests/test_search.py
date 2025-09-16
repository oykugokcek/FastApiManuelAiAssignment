"""
Test Suite: Search Endpoint (User Management API)

Focus:
- Reachability of /users/search (no route shadowing by /users/{id})
- Username partial vs exact searches (case-sensitivity expectations)
- Email exact search should use equality (not substring)
- Field parameter validation and basic pagination behaviors

Notes:
- Tests marked with xfail(strict=True) document current known issues:
  1) Route conflict (/users/{id} shadows /users/search)
  2) Email/username equality should be case-insensitive when exact=True
"""

import pytest
from uuid import uuid4


# ----------------------- Helpers -----------------------

def mkuser(client, unique, **overrides):
    """
    Create a user with unique defaults unless overridden.
    Returns the created JSON body.
    """
    username = unique("user")
    body = {
        "username": overrides.get("username", username),
        "email": overrides.get("email", f"{username}@e.com"),
        "password": overrides.get("password", "pppppp"),
        "age": overrides.get("age", 21),
    }
    r = client.post("/users", json=body)
    assert r.status_code in (200, 201), r.text
    return r.json()


def search(client, q, field="username", exact=False, **kwargs):
    """
    Call /users/search with given params. Returns (status_code, json_or_text).
    kwargs are passed as extra params (e.g., limit/offset).
    """
    params = {"q": q, "field": field, "exact": exact, **kwargs}
    r = client.get("/users/search", params=params)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


# ----------------------- Route reachability -----------------------

@pytest.mark.xfail(strict=True, reason="Route conflict: /users/{id} is shadowing /users/search; ensure static route is registered before dynamic.")
def test_search_endpoint_is_reachable(client, unique):
    """
    Sanity check: /users/search should respond 200 for a trivial query.
    Currently expected to FAIL if the route is shadowed by /users/{id}.
    """
    mkuser(client, unique, username=unique("search_me_123"), email="s@example.com")
    status, _ = search(client, q="search", field="username", exact=False)
    assert status == 200


# ----------------------- Username: partial and exact -----------------------

@pytest.mark.xfail(strict=True, reason="Route conflict or case-sensitivity mismatch for exact username match.")
def test_username_partial_and_exact(client, unique):
    """
    partial: 'search_me' should match 'search_me_123'
    exact (case-insensitive): 'Search_Me_123' should match the stored username.
    """
    username = unique("search_me_123")
    mkuser(client, unique, username=username, email="a@a.com")

    # Partial (should include)
    status1, body1 = search(client, q="search_me", field="username", exact=False)
    assert status1 == 200, f"partial search should be 200, got {status1}"
    assert any(u["username"] == username for u in body1), body1

    # Exact (case-insensitive match expected)
    status2, body2 = search(client, q=username.title(), field="username", exact=True)
    assert status2 == 200, f"exact search should be 200, got {status2}"
    assert any(u["username"].lower() == username.lower() for u in body2), body2


# ----------------------- Email: exact should be equality -----------------------

@pytest.mark.xfail(strict=True, reason="Email exact search currently behaves like substring; should be equality and case-insensitive.")
def test_email_exact_is_equality_case_insensitive(client):
    """
    exact search for email must perform equality (not substring) and be case-insensitive.
    """
    mkuser(client, username="x", email="X@Example.com")
    status, body = search(client, q="x@example.com", field="email", exact=True)
    assert status == 200
    # Expect exactly one equality match (case-insensitive)
    assert len([u for u in body if u["email"].lower() == "x@example.com"]) == 1, body


# ----------------------- Field validation -----------------------

@pytest.mark.xfail(strict=True, reason="Contract: invalid field should return 400 with clear error.")
def test_invalid_field_is_rejected_with_400(client):
    """
    Passing an unknown 'field' must be rejected (400).
    """
    mkuser(client)  # just to ensure DB not empty
    status, _ = search(client, q="x", field="nonexistent", exact=False)
    assert status == 400


@pytest.mark.xfail(strict=True, reason="Contract: missing q should be 400, not treated as wildcard.")
def test_missing_q_returns_400(client):
    """
    Omitting 'q' should be a client error (400), not 'match everything'.
    """
    r = client.get("/users/search", params={"field": "username", "exact": False})
    assert r.status_code == 400


# ----------------------- Pagination on search -----------------------

def test_search_respects_limit_and_offset(client, unique):
    """
    Search results must respect limit/offset without overlapping pages.
    Uses a stable field to sort by (id ascending) via backend defaults or params if supported.
    """
    base = unique("needle")
    # Create 8 matching and 3 non-matching to avoid empty-set issues
    for i in range(8):
        mkuser(client, unique, username=f"{base}_{i}", email=f"{base}_{i}@e.com")
    for j in range(3):
        other = unique("other")
        mkuser(client, unique, username=other, email=f"{other}@e.com")

    # Page 1
    r1 = client.get("/users/search", params={"q": base, "field": "username", "exact": False, "limit": 5, "offset": 0})
    # Page 2
    r2 = client.get("/users/search", params={"q": base, "field": "username", "exact": False, "limit": 5, "offset": 5})

    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)
    p1, p2 = r1.json(), r2.json()

    # No overlap
    ids1 = {u["id"] for u in p1}
    ids2 = {u["id"] for u in p2}
    assert ids1.isdisjoint(ids2), f"pages overlap: {ids1 & {ids2}}"
    # Page sizes respect limit
    assert len(p1) <= 5 and len(p2) <= 5


# ----------------------- Safety: query should not error on risky input -----------------------

def test_search_handles_risky_query_input_without_error(client, unique):
    """
    The backend must remain safe for inputs often used in injections.
    Expect a 200 and a JSON array (possibly empty), not a 5xx.
    """
    username = unique('risk_target_01')
    mkuser(client, unique, username=username, email='risk01@example.com')
    status, body = search(client, q='x";--', field="username", exact=False)
    assert status == 200, f"search should not 5xx on risky input, got {status}"
    assert isinstance(body, list), f"expected list response, got: {type(body)}"
