"""
Shared pytest fixtures for the EventOps test suite.

These tests run against mongomock (an in-memory MongoDB stand-in), not a
real database, so they work with zero setup: no MongoDB installation
needed. That's why this suite is optional and separate from the app
itself — see requirements-dev.txt and README.md > "Running the tests".
"""
import os
import sys

import mongomock
import pymongo

# Must happen before app/extensions/routes are imported anywhere, including
# by pytest's own collection step, since MongoClient is resolved once at
# each module's first import.
pymongo.MongoClient = mongomock.MongoClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-automated-tests-only")
os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017/eventops_test")
os.environ.setdefault("DB_NAME", "eventops_test")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from config import TestConfig
from app import create_app
import seed as seed_module


@pytest.fixture()
def app():
    """A fresh Flask app wired to a freshly-seeded mongomock database."""
    flask_app = create_app(TestConfig)
    yield flask_app


@pytest.fixture()
def db(app):
    from extensions import db as _db
    return _db


@pytest.fixture()
def seeded(app, db):
    """Seeds demo data and returns the dict run_seed() returns (ids, demo passwords)."""
    return seed_module.run_seed(db, verbose=False)


@pytest.fixture()
def client(app, seeded):
    return app.test_client()


@pytest.fixture()
def admin_client(client, seeded):
    client.post("/login", data={"username": "admin", "password": seeded["admin_password"]})
    return client


@pytest.fixture()
def volunteer_client_factory(client, seeded):
    """volunteer_client_factory('rahul.verma') -> a logged-in test client for that volunteer."""
    def _make(username):
        client.post("/login", data={"username": username, "password": seeded["volunteer_password"]})
        return client
    return _make
