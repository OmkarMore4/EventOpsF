"""
Run in a fresh subprocess by tests/test_auth.py's rate-limiting test.

Flask-Limiter's enabled/disabled state is effectively fixed by whichever
create_app() call happens first in a process. Every other test in this
suite creates a TestConfig app (RATELIMIT_ENABLED=False) before an inline
rate-limit test would get a chance to run, which would make rate limiting
look permanently disabled here too — so this specific check needs to be
the first (and only) app created in its own process instead.
"""
import os
import re
import sys

import mongomock
import pymongo

pymongo.MongoClient = mongomock.MongoClient

os.environ["SECRET_KEY"] = "isolated-ratelimit-test-secret"
os.environ["MONGO_URI"] = "mongodb://localhost:27017/eventops_ratelimit_isolated"
os.environ["DB_NAME"] = "eventops_ratelimit_isolated"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Config
from app import create_app


def main():
    app = create_app(Config)
    c = app.test_client()

    r = c.get("/login")
    token = re.search(r'name="csrf_token" value="([^"]+)"', r.data.decode()).group(1)

    statuses = []
    for _ in range(20):
        r = c.post("/login", data={"username": "admin", "password": "wrong", "csrf_token": token})
        statuses.append(r.status_code)

    assert 429 in statuses, f"expected a 429 among repeated attempts, got: {statuses}"
    print("RATE_LIMIT_TEST_OK")


if __name__ == "__main__":
    main()
