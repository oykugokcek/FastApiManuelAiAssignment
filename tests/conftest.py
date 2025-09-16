import pytest, importlib, sys, os, pathlib, importlib.util
from datetime import datetime
from datetime import datetime

# Detected module path is written by setup script
DETECTED_PATH_FILE = pathlib.Path(__file__).with_name("_detected_module_path.txt")
assert DETECTED_PATH_FILE.exists(), "Detected module path file missing"
TARGET_FILE = pathlib.Path(DETECTED_PATH_FILE.read_text(encoding="utf-8").strip())

# Try to import by module name if it's under repo root; else load by file path
REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

appmod = None
if TARGET_FILE.exists():
    # If target file is under a package, add its parent to sys.path
    sys.path.insert(0, str(TARGET_FILE.parent))
    modname = TARGET_FILE.stem
    try:
        appmod = importlib.import_module(modname)
    except Exception:
        # Load by absolute path
        spec = importlib.util.spec_from_file_location("appmod_loaded", str(TARGET_FILE))
        appmod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(appmod)

assert hasattr(appmod, "app"), "FastAPI 'app' nesnesi bulunamadı"

from fastapi.testclient import TestClient
import uuid

@pytest.fixture(autouse=True)
def clean_state():
    # If session seeding is active, preserve `users_db`; always clear transient state.
    seeded = os.environ.get("TESTS_USE_SEED_DATA", "0") == "1"
    if not seeded:
        for name in ["users_db", "sessions", "request_counts", "last_request_time"]:
            if hasattr(appmod, name):
                getattr(appmod, name).clear()
    else:
        for name in ["sessions", "request_counts", "last_request_time"]:
            if hasattr(appmod, name):
                getattr(appmod, name).clear()
    yield
    if not seeded:
        for name in ["users_db", "sessions", "request_counts", "last_request_time"]:
            if hasattr(appmod, name):
                getattr(appmod, name).clear()
    else:
        for name in ["sessions", "request_counts", "last_request_time"]:
            if hasattr(appmod, name):
                getattr(appmod, name).clear()


# Optional session-scoped seeding fixture controlled by environment variable
@pytest.fixture(scope="session", autouse=True)
def maybe_seed_session():
    """If `TESTS_USE_SEED_DATA=1` is set, populate `users_db` from `seed_data.sample_users` once.
    This keeps tests deterministic for seed-data-focused runs while leaving default test isolation intact.
    """
    use_seed = os.environ.get("TESTS_USE_SEED_DATA", "0") == "1"
    if not use_seed:
        yield
        return

    try:
        from seed_data import sample_users as SAMPLE_USERS
    except Exception:
        SAMPLE_USERS = []

    if SAMPLE_USERS and hasattr(appmod, "users_db"):
        with getattr(appmod, "db_lock"):
            users_db = getattr(appmod, "users_db")
            next_id = max([u.get("id", 0) for u in users_db.values()], default=0) + 1
            for u in SAMPLE_USERS:
                uname = u["username"].lower()
                if uname in users_db:
                    continue
                users_db[uname] = {
                    "id": next_id,
                    "username": uname,
                    "email": u["email"],
                    "password": appmod.hash_password(u["password"]),
                    "age": u.get("age"),
                    "phone": u.get("phone"),
                    "created_at": datetime.now(),
                    "is_active": True,
                    "last_login": None,
                }
                next_id += 1

    yield

@pytest.fixture
def client():
    return TestClient(appmod.app)

def mk_user_payload(prefix="u"):
    uname = make_unique_username(prefix)
    return {
        "username": uname,
        "email": f"{uname}@ex.com",
        "password": "secret123",
        "age": 25,
        "phone": "+905551112233",
    }

@pytest.fixture
def created_user(client):
    # If running with seed data, return an existing seeded user (prefer john_doe)
    use_seed = os.environ.get("TESTS_USE_SEED_DATA", "0") == "1"
    if use_seed and hasattr(appmod, "users_db") and "john_doe" in getattr(appmod, "users_db"):
        # Find plaintext password from seed_data.sample_users
        try:
            from seed_data import sample_users as SAMPLE_USERS
        except Exception:
            SAMPLE_USERS = []
        sample_pw = None
        for su in SAMPLE_USERS:
            if su.get("username", "").lower() == "john_doe":
                sample_pw = su.get("password")
                break
        # Return the stored user record but include plaintext password for tests
        user_rec = getattr(appmod, "users_db")["john_doe"].copy()
        if sample_pw:
            user_rec["password"] = sample_pw
        return user_rec

    payload = mk_user_payload()
    r = client.post("/users", json=payload, headers={"x-real-ip":"1.2.3.4"})
    assert r.status_code in (200, 201), r.text
    return r.json()

def basic_auth(username, password):
    import base64
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def bearer(token):
    return {"Authorization": f"Bearer {token}"}

def make_unique_username(base: str) -> str:
    """Generate unique username for tests, handles seed data mode"""
    if os.environ.get("TESTS_USE_SEED_DATA", "0") == "1":
        return f"{base}_{uuid.uuid4().hex[:6]}"
    return base

@pytest.fixture
def unique():
    """Fixture to generate unique usernames"""
    return make_unique_username
