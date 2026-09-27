"""
Shared extension instances.

Kept in their own module (rather than inside app.py) so route modules can
import `db` / `login_manager` without triggering circular imports.
"""

from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from pymongo import MongoClient
from werkzeug.local import LocalProxy

login_manager = LoginManager()
csrf = CSRFProtect()

# In-memory storage is fine for a single-process student/demo deployment.
# For a multi-worker production setup you'd point storage_uri at Redis
# instead — noted here rather than built in, to keep the moving parts this
# project depends on to a minimum.
limiter = Limiter(key_func=get_remote_address, default_limits=[])

_state = {"client": None, "db": None}


def _get_db():
    return _state["db"]


# `db` is a proxy, not a plain variable: every `db.<collection>.<op>(...)`
# call anywhere in the app resolves through _get_db() at the moment it's
# used, not at import time. This matters because Python only runs a
# module's top-level code the *first* time it's imported — if `db` were a
# plain name bound via `from extensions import db`, any module imported
# before a later init_db() call (or a second create_app() call, which
# pytest-style test setups do routinely) would be left holding a stale
# reference to the old connection forever. Flask uses this exact same
# LocalProxy pattern for current_app/request/g/session, for the same
# reason.
db = LocalProxy(_get_db)


def init_db(app):
    """Create the MongoClient/Database using the app's config and verify connectivity."""
    client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000)
    _state["client"] = client
    _state["db"] = client[app.config["DB_NAME"]]

    try:
        client.admin.command("ping")
        app.logger.info(
            "Connected to MongoDB database '%s' at %s",
            app.config["DB_NAME"],
            app.config["MONGO_URI"].split("@")[-1],  # hide credentials if present
        )
    except Exception as exc:  # pragma: no cover - depends on local Mongo state
        app.logger.warning(
            "Could not reach MongoDB (%s). The app will still start, but any "
            "page that touches the database will fail until MongoDB is "
            "running and MONGO_URI in .env is correct.",
            exc,
        )

    return _state["db"]
