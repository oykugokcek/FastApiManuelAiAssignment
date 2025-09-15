# Manuel AI – Hands‑on QA Assignment Response

Author: Öykü Gökçek  
Date: 15 Sep 2025  
Project: User Management API (FastAPI)

---

## 1) Executive Summary

I reviewed and tested the provided FastAPI project both manually and via an automated pytest suite. I identified several functional and security defects, plus a few contract/design inconsistencies. The report below provides: test setup, a prioritized bug list with clear reproduction steps, expected vs actual outcomes, and improvement suggestions.

Key headlines:
- Pagination does not respect the requested limit (over‑fetches)
- Search endpoint is shadowed by the dynamic `/users/{id}` route
- Phone validation is too permissive; accepts clearly invalid formats
- Update accepts string type for numeric fields (type coercion)
- Rate limit responses miss `Retry-After` header
- Known security gaps: object‑level authorization and token expiry (documented as design gaps)

---

## 2) Environment & How to Run

Environment
- macOS, Python 3.9.6 (virtualenv), pytest 8.4.2

Install test dependencies:
```bash
pip install -r qa_deliverables/requirements_test.txt
```

Run tests (normal mode):
```bash
pytest -v
```

Run tests with seed data (recommended for stable flows):
```bash
TESTS_USE_SEED_DATA=1 pytest -v
```

---

## 3) Results Overview (from my execution)

Normal mode
- Passed: 46  | Failed: 19  | XFail: 16  | Errors: 3  | Warnings: 5

Seed‑data mode
- Passed: 50  | Failed: 18  | XFail: 16  | Warnings: 6

Notes
- A few “errors” in normal mode stem from a test‑fixture username shortness (min length 3). This is not an app defect and disappears in seed‑data mode.

---

## 4) Prioritized Bug List (with steps)

Severity definitions: Critical (service/security), High (core functionality), Medium (validation/UX), Low (polish).

### BUG‑01: Pagination limit is not enforced (over‑fetch)
Severity: High | Area: `GET /users`

Steps to Reproduce
```bash
curl -s "http://localhost:8000/users?limit=5&offset=0&sort_by=id&order=asc" | jq 'length'
```
Expected: `<= 5` items  
Actual: `6` items returned (tests show consistent over‑fetch)

Impact: Breaks paging clients, causes duplicate/overlapping items.

### BUG‑02: `/users/search` is shadowed by dynamic route
Severity: High | Area: Routing

Steps
```bash
curl -i "http://localhost:8000/users/search?q=x&field=username&exact=false"
```
Expected: `200 OK` with JSON array results  
Actual: `400 Bad Request` with message like `Invalid user ID format: search` (the dynamic `/users/{id}` route matches first)

Impact: Search feature is effectively unreachable.

### BUG‑03: Phone validation accepts invalid formats
Severity: Medium | Area: `POST /users`

Steps
```bash
curl -s -X POST http://localhost:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"u_phone","email":"u_phone@ex.com","password":"x","age":25,"phone":"005321234567"}'
```
Expected: `422 Unprocessable Entity` (invalid phone)  
Actual: `201 Created`

Impact: Data quality; possible downstream failures and user confusion.

### BUG‑04: Update allows string type for numeric field (age)
Severity: Medium | Area: `PUT /users/{id}`

Steps
```bash
# Assume you have a valid token in $TOKEN and a user id in $ID
curl -s -X PUT http://localhost:8000/users/$ID \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"age":"31"}'
```
Expected: `400/422` validation error (type mismatch)  
Actual: `200 OK` and `age` becomes `31`

Impact: Silent type coercion; weak validation guarantees.

### BUG‑05: Rate‑limit responses miss `Retry-After` header
Severity: Medium | Area: Rate limiting

Steps
1) Send `POST /users` from the same IP until `429 Too Many Requests` is returned.  
2) Inspect headers.

Expected: `Retry-After` header present with seconds or HTTP‑date  
Actual: Header is missing

Impact: Clients cannot automatically back off correctly.

### BUG‑06: Deleting non‑existent user returns 401
Severity: Medium | Area: `DELETE /users/{id}`

Steps
```bash
# Use valid Basic auth for an existing user
curl -i -X DELETE "http://localhost:8000/users/999999" -H "Authorization: Basic <base64>"
```
Expected: `404 Not Found` (or `400`)  
Actual: `401 Unauthorized`

Impact: Misleading status; complicates client error handling.

---

## 5) Known Security/Contract Gaps (Design Issues)

These are already highlighted by tests as expected failures and should be treated as product requirements rather than test breakages:

- Object‑level authorization missing (users can act on others).  
  Recommendation: enforce ownership checks on `PUT/DELETE /users/{id}`.

- Token expiration not enforced.  
  Recommendation: reject expired tokens; include `exp` or store server‑side expiry.

- Authentication method inconsistency (DELETE uses Basic, UPDATE uses Bearer).  
  Recommendation: standardize on Bearer for all protected mutations.

- `missing q` on search should be `400` (explicit contract).  
  Recommendation: require `q` and `field` with clear validation errors.

---

## 6) Additional Observations

- Test Harness Note: in normal mode, a fixture sometimes generates a 1‑char username (`"u"`) which violates the API’s `min_length=3` rule; this yields a few setup errors. Using seed‑data mode avoids this and is closer to real usage.
- Deprecations: pydantic v2 migration is advised (`@validator` → `@field_validator`, `regex` → `pattern`).
- SSL warning from urllib3 on macOS due to LibreSSL vs OpenSSL; not a product bug but can clutter logs.

---

## 7) Recommendations & Next Steps

P0 (Immediate)
- Fix pagination limit enforcement and route ordering for `/users/search`

P1 (High)
- Harden input validation: phone format; type strictness on updates
- Add `Retry-After` to 429 responses

P2 (Medium)
- Standardize authentication to Bearer for mutating endpoints
- Implement object‑level authorization and token expiry (if in scope)
- Address pydantic deprecations

---

## 8) Appendix – Commands I Used

Run with seed data (my primary validation run):
```bash
TESTS_USE_SEED_DATA=1 pytest -v
```

Quick API probes (examples):
```bash
# Pagination
curl -s "http://localhost:8000/users?limit=5&offset=0&sort_by=id&order=asc" | jq

# Search (currently shadowed)
curl -i "http://localhost:8000/users/search?q=alice&field=username&exact=false"

# Invalid phone
curl -s -X POST http://localhost:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"u_phone","email":"u_phone@ex.com","password":"x","age":25,"phone":"005321234567"}'
```

---

Thank you for the opportunity. I’m happy to walk through any finding live and validate fixes quickly.