import pytest

# This test file simulates the README/seed_data.py users by creating them
# via the API within the test, then exercising login and protected endpoints.

from uuid import uuid4


def create_seed_users(client):
    users = [
        {"username": "john_doe", "email": "john@example.com", "password": "password123", "age": 30, "phone": "+15551234567"},
        {"username": "jane_smith", "email": "jane@example.com", "password": "securepass456", "age": 25, "phone": "+14155551234"},
    ]
    for u in users:
        r = client.post("/users", json=u)
        # If the session-level seeding already populated these users, accept a 400 'Username already exists'
        if r.status_code not in (200, 201):
            assert r.status_code == 400 and "Username already exists" in r.text, f"Failed to create seed user {u['username']}: {r.text}"
    return users


def test_seeded_users_login_and_update(client):
    # Ensure seed users exist in the app for this test (created in-test)
    create_seed_users(client)

    # Login as john_doe
    r = client.post("/login", json={"username": "john_doe", "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json().get("token")
    assert token, "No token returned"

    headers = {"Authorization": f"Bearer {token}"}

    # Fetch john_doe by listing users and filtering by username (avoid /users/search route collision)
    rl = client.get("/users", params={"limit": 50, "offset": 0, "sort_by": "id", "order": "asc"})
    assert rl.status_code == 200, rl.text
    users = rl.json()
    matches = [u for u in users if u.get("username") == "john_doe"]
    assert len(matches) == 1, f"expected john_doe to be present in listing, got: {matches}"
    user = matches[0]

    # Update john_doe's phone
    new_phone = "+15559998877"
    r_up = client.put(f"/users/{user['id']}", json={"phone": new_phone}, headers=headers)
    assert r_up.status_code == 200, r_up.text
    updated = r_up.json()
    assert updated['phone'] == new_phone

