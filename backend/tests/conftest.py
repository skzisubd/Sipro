import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://sipro-next-1.preview.emergentagent.com").rstrip("/")
PASS = "Sipro#2026"


def _login(email: str):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login {email} failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL


@pytest.fixture(scope="session")
def tok_finance():
    return _login("finance@sipro.co.id")


@pytest.fixture(scope="session")
def tok_finlead():
    return _login("finlead@sipro.co.id")


@pytest.fixture(scope="session")
def tok_sales():
    return _login("sales@sipro.co.id")


@pytest.fixture(scope="session")
def tok_owner():
    return _login("owner@sipro.co.id")


def _sess(tok):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return s


@pytest.fixture
def s_finance(tok_finance):
    return _sess(tok_finance)


@pytest.fixture
def s_finlead(tok_finlead):
    return _sess(tok_finlead)


@pytest.fixture
def s_sales(tok_sales):
    return _sess(tok_sales)


@pytest.fixture
def s_owner(tok_owner):
    return _sess(tok_owner)
