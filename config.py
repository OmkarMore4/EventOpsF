"""
Application configuration.

All secrets and environment-specific values are read from environment
variables (populated from .env via python-dotenv in app.py). Nothing
sensitive is hardcoded here.
"""

import os


class Config:
    # --- Core Flask settings -------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set. Copy .env.example to .env and set a "
            "SECRET_KEY before running the app."
        )

    # --- MongoDB ---------------------------------------------------------------
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/eventops")
    DB_NAME = os.environ.get("DB_NAME", "eventops")

    # --- Session / cookies -----------------------------------------------------
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Must stay False for local http://localhost dev (browsers drop Secure
    # cookies over plain HTTP). Set to True in Render/Vercel env vars once
    # the app is served over HTTPS — see README.md "Deploying to production".
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").strip().lower() in ("1", "true", "yes", "on")
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME_SECONDS", 60 * 60 * 8))

    # --- Misc --------------------------------------------------------------
    APP_NAME = os.environ.get("APP_NAME", "EventOps")
    DEFAULT_GEOFENCE_RADIUS_METERS = int(os.environ.get("DEFAULT_GEOFENCE_RADIUS_METERS", 100))

    # --- Flask-WTF / CSRF --------------------------------------------------
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # tokens don't expire mid-session


class TestConfig(Config):
    """Used only by the project's own smoke tests (see tests/) — never in production."""
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
