# Manuel AI – Hands‑on QA Assignment Response

Author: Öykü Gökçek  
Date: 15 Sep 2025  
Deadline: 16 Sep 2025 – 21:00 (CET)  
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

## Deliverables Included (per assignment)

- `qa_deliverables/bugs_report.md` — Full bug list with descriptions and priorities
- `qa_deliverables/QA_Assignment_Response.md` — This report (bugs + observations + recommendations)
- `qa_deliverables/test_report.md` — Test execution summary and metrics
- `qa_deliverables/README_TESTS.md` — How to run tests and documentation pointers
- `qa_deliverables/requirements_test.txt` — Test dependencies

All critical bugs include reproduction steps (curl) in this document; screenshots can be added on request.

## 4) Prioritized Bug List (with steps)

Severity definitions: Critical (service/security), High (core functionality), Medium (validation/UX), Low (polish).

### BUG‑10 (SEC‑001): Missing object‑level authorization
Severity: Critical | Area: `PUT/DELETE /users/{id}`

Steps
```bash
# Create A and B
curl -s -X POST http://localhost:8000/users -H 'Content-Type: application/json' \
  -d '{"username":"user_a","email":"a@ex.com","password":"p","age":25}' | jq .id > /tmp/aid
curl -s -X POST http://localhost:8000/users -H 'Content-Type: application/json' \
  -d '{"username":"user_b","email":"b@ex.com","password":"p","age":30}'
TOKEN=$(curl -s -X POST http://localhost:8000/login -H 'Content-Type: application/json' \
  -d '{"username":"user_b","password":"p"}' | jq -r .token)
ID=$(cat /tmp/aid)

# B updates A
curl -i -X PUT http://localhost:8000/users/$ID -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"age":99}'
```
Expected: `403 Forbidden` (only owner can modify)  
Actual: `200 OK` (modification allowed)

Impact: Unauthorized data modification; high security risk.

### BUG‑11 (SEC‑002): Token expiration not enforced
Severity: Critical | Area: Auth/session

Steps
```bash
# Login and obtain token
TOKEN=$(curl -s -X POST http://localhost:8000/login -H 'Content-Type: application/json' \
  -d '{"username":"user_b","password":"p"}' | jq -r .token)
# Wait beyond intended expiry (or mutate server-side expiry in session store) and call an authenticated endpoint
curl -i -X PUT http://localhost:8000/users/1 -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"age":31}'
```
Expected: `401 Unauthorized` after expiry  
Actual: Token continues to work

Impact: Sessions never expire; increases hijacking risk.

### BUG‑12 (API‑001): Authentication method inconsistency
Severity: High | Area: Mutating endpoints

Steps
```bash
# Create user u and login to get Bearer token
curl -s -X POST http://localhost:8000/users -H 'Content-Type: application/json' \
  -d '{"username":"u_del","email":"u_del@ex.com","password":"p","age":22}' | jq .id > /tmp/uid
TOKEN=$(curl -s -X POST http://localhost:8000/login -H 'Content-Type: application/json' -d '{"username":"u_del","password":"p"}' | jq -r .token)
ID=$(cat /tmp/uid)

# Try DELETE with Bearer (rejected) vs Basic (accepted)
curl -i -X DELETE http://localhost:8000/users/$ID -H "Authorization: Bearer $TOKEN"
curl -i -X DELETE http://localhost:8000/users/$ID -H "Authorization: Basic $(printf 'u_del:p' | base64)"
```
Expected: Consistent auth scheme across mutations (prefer Bearer), or clearly documented differences  
Actual: `PUT` uses Bearer, `DELETE` requires Basic

Impact: Client complexity and security confusion.

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

### BUG‑07: `/stats?include_details=true` exposes sensitive data
Severity: Critical | Area: `GET /stats`

Steps
```bash
curl -s "http://localhost:8000/stats?include_details=true" | jq
```
Expected: Denied to anonymous (401/403) OR sanitized aggregates without secrets  
Actual: Detailed payload may include sensitive fields (e.g., emails, tokens)

Impact: Privacy breach; high risk of data leakage.

### BUG‑08: `limit=0` handling is inconsistent
Severity: Low | Area: `GET /users`

Steps
```bash
curl -s "http://localhost:8000/users?limit=0&offset=0&sort_by=id&order=asc" | jq 'length'
```
Expected: Either `200` with `0` items OR `400 Bad Request` by contract  
Actual: Returns non‑zero items (observed `1`), violating the contract expectation

Impact: Client paging logic becomes ambiguous; hard to rely on boundary semantics.

### BUG‑09: Email search (exact) behaves like substring and is case‑sensitive
Severity: Medium | Area: `GET /users/search`

Steps
```bash
# Create a user with mixed‑case email
curl -s -X POST http://localhost:8000/users \
  -H 'Content-Type: application/json' \
  -d '{"username":"mail_case","email":"X@Example.com","password":"p","age":21}'

# Exact email search with lower‑case query
curl -s "http://localhost:8000/users/search?q=x@example.com&field=email&exact=true" | jq
```
Expected: Case‑insensitive equality match (exactly one hit)  
Actual: No match or substring‑like behavior; not an equality check

Impact: Users cannot reliably find accounts by email; confusing UX and support overhead.

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

## 6) Additional Observations & Suggestions

- Test Harness Note: in normal mode, a fixture sometimes generates a 1‑char username (`"u"`) which violates the API’s `min_length=3` rule; this yields a few setup errors. Using seed‑data mode avoids this and is closer to real usage.
- Deprecations: pydantic v2 migration is advised (`@validator` → `@field_validator`, `regex` → `pattern`).
- SSL warning from urllib3 on macOS due to LibreSSL vs OpenSSL; not a product bug but can clutter logs.
- API docs: Add example request/response pairs to `/docs` for search, pagination and auth flows.
- CI/CD: Add a simple pipeline to run `pytest -v` on PRs and publish HTML reports.
- Observability: Log rate‑limit decisions and include correlation IDs for easier troubleshooting.

---

## 7) Recommendations & Next Steps

Traceability: Each recommendation references the corresponding ID in `qa_deliverables/bugs_report.md`.

P0 (Immediate)
- SEC-001 — Object-level authorization: Enforce ownership on `PUT/DELETE /users/{id}`.
  - Acceptance: Acting on a different user returns 403; tests `test_user_cannot_update_other_user` and `test_user_cannot_delete_another_user` pass without xfail.
- SEC-002 — Token expiration: Store and check expiry (JWT `exp` or server-side session TTL).
  - Acceptance: Expired token returns 401 on update; `test_expired_session_still_works_on_update` converted to a passing test.
- SEC-003 — Sensitive data exposure: Restrict `/stats?include_details=true` to authorized roles or return sanitized aggregates only.
  - Acceptance: Anonymous access is 401/403 OR payload contains no sensitive keys; `test_stats_include_details_must_not_leak_sensitive_fields` passes.

P1 (High)
- API-002 — Route shadowing: Register `/users/search` before `/users/{id}` or use more specific path handling.
  - Acceptance: `/users/search` returns 200; search pagination test passes; `test_search_endpoint_is_reachable` moves to pass.
- PAG-001 — Enforce `limit/offset`: Apply slicing at query layer and response.
  - Acceptance: `len(data) <= limit`; pages don’t overlap; `test_list_respects_limit_and_sort_by_id` and `test_offset_paginates_without_overlap` pass.
- API-001 — Auth method consistency: Standardize on Bearer for all protected mutations (or document Basic consistently and update tests).
  - Acceptance: Contract defined and implemented; delete/update auth behavior consistent and tested.

P2 (Medium)
- VAL-001 — Phone validation: Enforce E.164 (e.g., `+905321234567`) with strict pattern.
  - Acceptance: Invalid samples return 422; `test_phone_validation_rejects_bad_formats` fully passes.
- VAL-002 — Type strictness on updates: Reject string age; no implicit coercion.
  - Acceptance: `PUT {"age":"31"}` returns 400/422; `test_update_rejects_non_int_age` passes.
- RATE-001 — Include `Retry-After` on 429: Return seconds or HTTP-date.
  - Acceptance: Header present and non-empty; `test_rate_limit_returns_retry_after_header_if_available` passes.
- SEARCH-001 — Email exact equality (case-insensitive): Use normalized comparison when `exact=true`.
  - Acceptance: Mixed-case email matches; `test_email_exact_is_equality_case_insensitive` passes.

P3 (Low)
- PAG-002 — `limit=0` contract: Decide (200 with empty list vs 400) and enforce.
  - Acceptance: `test_limit_boundary_values[0]` aligned with the chosen behavior and passes.
- TECH-001 — Framework updates: Migrate to Pydantic v2; replace `regex` with `pattern` in FastAPI Query; remove deprecation warnings.
  - Acceptance: No deprecation warnings in test run; normal and seed-data modes remain green.

Implementation Notes
- Sequence: Address P0 first (security), then P1 (core behavior), P2 (validation/UX), P3 (tech debt).
- Testing: Convert related `xfail(strict=True)` markers to passing assertions as fixes land.
- Documentation: Update API docs to reflect auth scheme and search/pagination contracts.

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

---

## Submission & Next Steps

- This package contains all requested deliverables in `qa_deliverables/` and can be shared as a public repo link or zipped archive.
- I am available for a follow‑up interview to demo repro steps and discuss fixes.