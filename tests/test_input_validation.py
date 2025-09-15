"""
Test Suite: Input Validation (User Management API)

Scope:
- Required fields: username, email, password
- Email/phone format validations
- Type/boundary errors for age
- Behavior for unknown/extra fields
- Validation on update (with Bearer token)
- Items marked with xfail(strict=True) are design decisions not enforced yet
"""

import pytest
from uuid import uuid4

BASE_PASS = "secret123"


# ----------------------- Helpers -----------------------

def make_user_payload(unique, **overrides):
    """Return a fresh, unique user payload; fields can be overridden via kwargs."""
    username = unique("user")
    payload = {
        "username": username,
        "email": f"{username}@e.com",
        "password": BASE_PASS,
        "age": 25,
    }
    payload.update(overrides)
    return payload


def login_token(client, username, password=BASE_PASS):
    """Login and return the Bearer token; fail fast if login does not work."""
    r = client.post("/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return r.json()["token"]


def bearer(token):
    """Convenience helper for Authorization header."""
    return {"Authorization": f"Bearer {token}"}


# ----------------------- Phone & Username -----------------------

@pytest.mark.parametrize("bad_phone", [
    "12345",            # too short
    "abcde",            # contains letters
    "+90 532 123 45",   # spaces + missing digits
    "005321234567",     # leading 00 variant
    "+-905321234567",   # invalid symbol sequence
])
def test_phone_validation_rejects_bad_formats(client, unique, bad_phone):
    """
    Creating a user with an invalid phone number must be rejected.
    Expected: 422 Unprocessable Entity.
    """
    payload = make_user_payload(unique, phone=bad_phone)
    r = client.post("/users", json=payload)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


def test_username_allows_risky_but_legal_chars(client, unique):
    """
    The username regex should accept characters that are legal but often used in
    injection attempts; the server must still be safe.
    Expected: 200/201 Created.
    """
    payload = make_user_payload(unique, username=unique("x\";--"))
    r = client.post("/users", json=payload)
    assert r.status_code in (200, 201), r.text


@pytest.mark.xfail(strict=True, reason="Design decision: trim username or reject? Prefer explicit 422.")
def test_username_leading_trailing_spaces(client, unique):
    """
    If username has leading/trailing spaces, either trim (and create) or reject with 422.
    We prefer explicit rejection to avoid ambiguous identity.
    """
    payload = make_user_payload(unique, username=unique("  spaced  "))
    r = client.post("/users", json=payload)
    assert r.status_code == 422


# ----------------------- Required Fields -----------------------

@pytest.mark.parametrize("missing_key", ["username", "email", "password"])
def test_missing_required_fields_return_422(client, unique, missing_key):
    """
    Omitting a required field must return 422 with a clear validation error message.
    """
    payload = make_user_payload(unique)
    payload.pop(missing_key)
    r = client.post("/users", json=payload)
    assert r.status_code == 422, f"missing {missing_key} should be 422"


# ----------------------- Email Validation -----------------------

@pytest.mark.parametrize("bad_email", [
    "a", "a@", "a@b", "a@b.", "a@.com", "a@b..com", "a..b@example.com", "a b@example.com"
])
def test_email_validation_common_bad_formats(client, unique, bad_email):
    """
    Common invalid email formats should be rejected with 422.
    """
    payload = make_user_payload(unique, email=bad_email)
    r = client.post("/users", json=payload)
    assert r.status_code == 422, f"bad email should be 422, got {r.status_code}: {r.text}"


def test_email_uppercase_is_allowed(client, unique):
    """
    Email case should not matter for creation; uppercase is acceptable.
    """
    base = make_user_payload(unique)
    base["email"] = base["email"].upper()
    r = client.post("/users", json=base)
    assert r.status_code in (200, 201), r.text


@pytest.mark.xfail(strict=True, reason="Design decision: email uniqueness should be case-insensitive.")
def test_email_uniqueness_is_case_insensitive(client, unique):
    """
    Creating the same email in a different case should be considered duplicate.
    Expected: 409/422/400 depending on API contract.
    """
    one = make_user_payload(unique)
    one["email"] = "UPPER@CASE.COM"
    r1 = client.post("/users", json=one)
    assert r1.status_code in (200, 201)
    r2 = client.post("/users", json=make_user_payload(
        unique,
        username=unique("another"),
        email="upper@case.com"
    ))
    assert r2.status_code in (409, 422, 400)


# ----------------------- Age Validation -----------------------

@pytest.mark.parametrize("bad_age", [-1, -100, 3.14, "thirty", None])
def test_age_rejects_invalid_values(client, unique, bad_age):
    """
    Age must be a non-negative integer within a reasonable range.
    Invalid values should return 400/422.
    """
    payload = make_user_payload(unique, age=bad_age)
    r = client.post("/users", json=payload)
    assert r.status_code in (400, 422)


def test_age_large_boundary(client, unique):
    """
    Extremely large ages should be rejected (400/422), unless business rules say otherwise.
    """
    payload = make_user_payload(unique, age=999)
    r = client.post("/users", json=payload)
    assert r.status_code in (400, 422)


# ----------------------- Extra Fields -----------------------

def test_extra_fields_are_ignored_or_rejected_consistently(client, unique):
    """
    If the schema uses `extra='ignore'`, unknown fields must be dropped from the response.
    If it uses `extra='forbid'`, expect 422 instead. This test accepts both by branching.
    """
    payload = make_user_payload(unique)
    payload["unknown_field"] = "1"
    r = client.post("/users", json=payload)
    if r.status_code in (200, 201):
        body = r.json()
        assert "unknown_field" not in body, "unknown field should not be echoed back"
    else:
        assert r.status_code == 422, f"unexpected status: {r.status_code}"


# ----------------------- Update-time Validation (Bearer) -----------------------

def test_update_rejects_non_int_age(client, unique):
    """
    Updating with a non-integer age must be rejected with 400/422.
    """
    u = client.post("/users", json=make_user_payload(unique)).json()
    t = login_token(client, u["username"])
    r = client.put(f"/users/{u['id']}", json={"age": "31"}, headers=bearer(t))
    assert r.status_code in (400, 422), r.text


@pytest.mark.xfail(strict=True, reason="Design decision: username should be immutable after creation.")
def test_update_username_is_immutable(client, unique):
    """
    Changing username via update should be forbidden for identity stability.
    """
    u = client.post("/users", json=make_user_payload(unique)).json()
    t = login_token(client, u["username"])
    r = client.put(f"/users/{u['id']}", json={"username": "newname"}, headers=bearer(t))
    assert r.status_code in (400, 403, 422)


@pytest.mark.parametrize("bad_email", ["no-at.com", "a@b", "a@b..com"])
def test_update_rejects_bad_email_format_if_editable(client, unique, bad_email):
    """
    If the API allows updating email, invalid formats must be rejected (422).
    If email is immutable, the endpoint should respond with a 4xx accordingly.
    """
    u = client.post("/users", json=make_user_payload(unique)).json()
    t = login_token(client, u["username"])
    r = client.put(f"/users/{u['id']}", json={"email": bad_email}, headers=bearer(t))
    assert r.status_code in (400, 403, 422)


# ----------------------- Password Validation -----------------------

@pytest.mark.xfail(strict=True, reason="Password policy (min length/complexity) not enforced yet.")
@pytest.mark.parametrize("pwd", ["", "123", "abcde", "short"])
def test_password_min_length_policy(client, unique, pwd):
    """
    Weak or too-short passwords should be rejected according to the password policy.
    """
    payload = make_user_payload(unique, password=pwd)
    r = client.post("/users", json=payload)
    assert r.status_code in (400, 422)
