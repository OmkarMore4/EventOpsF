from datetime import datetime

from flask import Blueprint, redirect, render_template, request, session, url_for, flash
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db, limiter
from models import User
from utils.helpers import event_status, today_str, to_object_id

auth_bp = Blueprint("auth", __name__)


def _redirect_for_role(role):
    return redirect(url_for("admin.dashboard" if role == "admin" else "volunteer.dashboard"))


@auth_bp.route("/")
def index():
    if current_user.is_authenticated:
        return _redirect_for_role(current_user.role)
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute; 50 per hour", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return _redirect_for_role(current_user.role)

    if request.method == "POST":
        identifier = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user_doc = None
        if identifier and password:
            user_doc = db.users.find_one(
                {"$or": [{"username": identifier}, {"email": identifier}]}
            )

        if user_doc and check_password_hash(user_doc["password_hash"], password):
            user = User(user_doc)
            login_user(user)
            session.permanent = True
            db.users.update_one(
                {"_id": user_doc["_id"]}, {"$set": {"last_login": datetime.now()}}
            )
            flash(f"Welcome back, {user.name.split(' ')[0]}.", "success")
            next_url = request.args.get("next")
            if next_url and next_url.startswith("/"):
                return redirect(next_url)
            return _redirect_for_role(user.role)

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    """
    Public volunteer sign-up. Submissions land as a `volunteers` document
    with status="pending" and are NOT given a working login until an admin
    approves them (see admin.volunteer_approve) — this keeps a stranger
    filling out this form from getting immediate access to anything.
    """
    if current_user.is_authenticated:
        return _redirect_for_role(current_user.role)

    open_events = [e for e in db.events.find().sort("created_at", -1) if event_status(e) != "completed"]

    if request.method == "POST":
        event_oid = to_object_id(request.form.get("event_id"))
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        domain = (request.form.get("domain") or "").strip()
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        event = db.events.find_one({"_id": event_oid}) if event_oid else None

        errors = []
        if not event:
            errors.append("Please select an event to volunteer for.")
        if not name:
            errors.append("Name is required.")
        if not email or "@" not in email:
            errors.append("A valid email is required.")
        if not domain:
            errors.append("Please tell us which domain/team you'd like to help with.")
        if not username:
            errors.append("Username is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if not errors and db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            errors.append("That username or email is already registered.")
        if not errors and db.volunteers.find_one({"email": email, "status": "pending"}):
            errors.append("A pending request already exists for that email — sit tight for the admin to review it.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", events=open_events, values=request.form)

        db.volunteers.insert_one({
            "event_id": event["_id"], "name": name, "email": email, "phone": phone, "domain": domain,
            "responsibilities": "", "status": "pending", "joined_date": today_str(),
            "pending_username": username, "pending_password_hash": generate_password_hash(password),
            "created_at": datetime.now(),
        })
        flash(
            "Thanks! Your request has been sent to the event admin for approval. "
            "You'll be able to log in with the username/password you chose once it's approved.", "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("register.html", events=open_events, values=None)
