def test_root_redirects_to_login_when_anonymous(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_protected_route_redirects_to_login_when_anonymous(client):
    r = client.get("/admin/dashboard")
    assert r.status_code == 302


def test_bad_password_is_rejected(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong-password"}, follow_redirects=True)
    assert b"Invalid username or password" in r.data


def test_unknown_username_is_rejected(client):
    r = client.post("/login", data={"username": "nobody", "password": "whatever"}, follow_redirects=True)
    assert b"Invalid username or password" in r.data


def test_admin_login_succeeds(admin_client):
    r = admin_client.get("/admin/dashboard")
    assert r.status_code == 200
    assert b"Dashboard" in r.data


def test_volunteer_login_succeeds(volunteer_client_factory):
    c = volunteer_client_factory("rahul.verma")
    r = c.get("/volunteer/dashboard")
    assert r.status_code == 200


def test_logout_clears_session(admin_client):
    admin_client.get("/logout")
    r = admin_client.get("/admin/dashboard")
    assert r.status_code == 302


def test_csrf_protection_rejects_request_without_token():
    """Uses the real (non-test) config, since CSRF is disabled under TestConfig
    for the rest of this suite's convenience."""
    from config import Config
    from app import create_app

    real_app = create_app(Config)
    c = real_app.test_client()
    r = c.post("/login", data={"username": "admin", "password": "whatever"})
    assert r.status_code == 400


def test_login_rate_limiting_blocks_repeated_attempts():
    """
    Runs in a fresh subprocess rather than inline — see
    tests/_isolated_ratelimit_check.py for why.
    """
    import subprocess
    import sys
    import os

    script = os.path.join(os.path.dirname(__file__), "_isolated_ratelimit_check.py")
    result = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=30)
    assert "RATE_LIMIT_TEST_OK" in result.stdout, f"stdout: {result.stdout}\nstderr: {result.stderr}"
