"""
Test Suite: Pagination & Sorting (User Management API)

Goals:
- Enforce limit and offset semantics (no overfetch, no overlap between pages)
- Verify sorting by explicit fields (id, created_at) in both directions
- Check default/invalid parameter behavior (marked xfail if the contract is undecided)
"""

from uuid import uuid4
from datetime import datetime
import pytest


# ----------------------- Helpers -----------------------

def make_users(client, unique, n, start_age=20):
    """
    Create n distinct users and return their JSON rows (in creation order).
    Uses unique username/email to avoid collisions with other tests.
    """
    out = []
    for i in range(n):
        username = unique(f"u_{i}")
        r = client.post(
            "/users",
            json={
                "username": username,
                "email": f"{username}@e.com",
                "password": "pppppp",
                "age": start_age + i,
            },
        )
        assert r.status_code in (200, 201), r.text
        out.append(r.json())
    return out


def non_decreasing(seq):
    return all(a <= b for a, b in zip(seq, seq[1:]))


def non_increasing(seq):
    return all(a >= b for a, b in zip(seq, seq[1:]))


def parse_dt(s: str) -> datetime:
    """
    Parse ISO timestamps returned by the API.
    Accepts both naive and 'Z' suffixed strings.
    """
    if s.endswith("Z"):
        s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


# ----------------------- Limit & Offset -----------------------

def test_list_respects_limit_and_sort_by_id(client, unique):
    """
    The endpoint must not return more than 'limit' items and must honor sorting.
    """
    make_users(client, unique, 8)
    r = client.get("/users", params={"limit": 5, "offset": 0, "sort_by": "id", "order": "asc"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data) <= 5, f"Exceeded limit: got {len(data)}"

    # Verify non-decreasing id order (allows equality in case backend returns ties)
    ids = [u["id"] for u in data]
    assert non_decreasing(ids), f"IDs not ascending: {ids}"


def test_offset_paginates_without_overlap(client, unique):
    """
    Page 1 (offset=0, limit=5) and Page 2 (offset=5, limit=5) must not overlap.
    """
    make_users(client, unique, 12)
    r1 = client.get("/users", params={"limit": 5, "offset": 0, "sort_by": "id", "order": "asc"})
    r2 = client.get("/users", params={"limit": 5, "offset": 5, "sort_by": "id", "order": "asc"})
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)

    p1 = r1.json()
    p2 = r2.json()
    ids1 = {u["id"] for u in p1}
    ids2 = {u["id"] for u in p2}

    assert len(p1) <= 5 and len(p2) <= 5
    assert ids1.isdisjoint(ids2), f"Pages overlap: {ids1 & ids2}"


@pytest.mark.parametrize("lim", [0, 1, 5])
def test_limit_boundary_values(client, unique, lim):
    """
    limit=0 should either:
      - be rejected (400), or
      - return an empty page (200 with 0 items)
    Other limits should cap results to <= limit.
    """
    make_users(client, unique, 6)
    r = client.get("/users", params={"limit": lim, "offset": 0, "sort_by": "id", "order": "asc"})
    if lim == 0:
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            assert len(r.json()) == 0
    else:
        assert r.status_code == 200, r.text
        assert len(r.json()) <= lim


# ----------------------- Sorting -----------------------

@pytest.mark.parametrize("order", ["asc", "desc"])
def test_sort_by_created_at_is_monotonic(client, unique, order):
    """
    Sorting by created_at must be monotonic (non-decreasing for asc, non-increasing for desc).
    """
    make_users(client, unique, 4)
    r = client.get("/users", params={"limit": 50, "sort_by": "created_at", "order": order})
    assert r.status_code == 200, r.text
    data = r.json()
    assert all("created_at" in u for u in data), "created_at missing in response"

    times = [parse_dt(u["created_at"]) for u in data]
    if order == "asc":
        assert non_decreasing(times), f"created_at not ascending: {times}"
    else:
        assert non_increasing(times), f"created_at not descending: {times}"


def test_sort_by_id_desc(client, unique):
    """
    Basic smoke check for id-based descending sort.
    """
    make_users(client, unique, 5)
    r = client.get("/users", params={"limit": 50, "sort_by": "id", "order": "desc"})
    assert r.status_code == 200, r.text
    data = r.json()
    ids = [u["id"] for u in data]
    assert non_increasing(ids), f"IDs not descending: {ids}"


# ----------------------- Invalid Param Behavior (contract TBD) -----------------------

@pytest.mark.xfail(strict=True, reason="Contract: invalid 'order' should be rejected with 400.")
def test_invalid_order_is_rejected(client, unique):
    make_users(client, unique, 2)
    r = client.get("/users", params={"limit": 10, "offset": 0, "sort_by": "id", "order": "sideways"})
    assert r.status_code == 400


@pytest.mark.xfail(strict=True, reason="Contract: invalid 'sort_by' should be rejected with 400.")
def test_invalid_sort_field_is_rejected(client, unique):
    make_users(client, unique, 2)
    r = client.get("/users", params={"limit": 10, "offset": 0, "sort_by": "nonexistent", "order": "asc"})
    assert r.status_code == 400
