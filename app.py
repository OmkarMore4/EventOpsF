"""
EventOps — Real-Time Event Operations and Volunteer Management System.

Application factory. For local development, run:  python app.py
For production-style serving, use any WSGI server pointed at app:app
(see README.md).
"""

import os
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()  # populate os.environ from .env before Config reads anything

from flask import Flask, render_template, session
from flask_login import current_user

from config import Config
from extensions import login_manager, csrf, limiter, init_db, db
from utils.helpers import event_status, badge_class, format_date, format_datetime, format_time, to_object_id


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Connect to MongoDB before anything else touches `extensions.db`.
    init_db(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to continue."
    login_manager.login_message_category = "info"

    csrf.init_app(app)
    limiter.init_app(app)

    # --- Jinja filters -----------------------------------------------------
    app.jinja_env.filters["event_status"] = event_status
    app.jinja_env.filters["badge_class"] = badge_class
    app.jinja_env.filters["format_date"] = format_date
    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["format_time"] = format_time
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    @app.context_processor
    def inject_globals():
        current_event = None
        open_issues_count = 0
        pending_volunteers_count = 0
        all_events = []
        if current_user.is_authenticated and getattr(current_user, "is_admin", False):
            event_id = session.get("current_event_id")
            if event_id:
                current_event = db.events.find_one({"_id": to_object_id(event_id)})
            if not current_event:
                current_event = db.events.find_one(sort=[("created_at", -1)])
            if current_event:
                open_issues_count = db.issues.count_documents(
                    {"event_id": current_event["_id"], "status": {"$ne": "resolved"}}
                )
                pending_volunteers_count = db.volunteers.count_documents(
                    {"event_id": current_event["_id"], "status": "pending"}
                )
            all_events = list(db.events.find().sort("created_at", -1))

        return {
            "app_name": app.config.get("APP_NAME", "EventOps"),
            "current_year": datetime.now().year,
            "nav_current_event": current_event,
            "nav_open_issues_count": open_issues_count,
            "nav_pending_volunteers_count": pending_volunteers_count,
            "nav_all_events": all_events,
        }

    # --- Blueprints ----------------------------------------------------------
    # Imported here, after init_db(), so each route module's top-level
    # `from extensions import db` binds to the real database connection.
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.volunteer import volunteer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(volunteer_bp)

    # --- Error handlers ------------------------------------------------------
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def rate_limited(_e):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("errors/500.html"), 500

    return app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "True").strip().lower() in ("1", "true", "yes", "on")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
