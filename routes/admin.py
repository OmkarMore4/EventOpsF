"""
Admin routes.

Most admin sections (volunteers, tasks, attendance, equipment, schedule,
issues, notifications, reports) are scoped to a single "current event",
tracked in the session and switchable from the top bar. This keeps each
page's queries simple (always filtered by event_id) while still letting
one admin account run multiple events over time.
"""

import csv
import io
from datetime import datetime, date, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, Response, abort, jsonify
from flask_login import current_user
from werkzeug.security import generate_password_hash

from extensions import db
from utils.decorators import admin_required
from utils.geo import make_geojson_point, valid_coordinates, event_latlng
from utils.helpers import to_object_id, today_str, parse_date_str, parse_float, parse_int, split_csv_field
from utils.qr import generate_qr_secret, qr_code_data_uri
from utils.pdf_report import build_event_report_pdf

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Event context helpers
# ---------------------------------------------------------------------------

def get_current_event():
    """Return the admin's currently-selected event, defaulting to the most recent one."""
    event = None
    event_id = session.get("current_event_id")
    if event_id:
        event = db.events.find_one({"_id": to_object_id(event_id)})
    if not event:
        event = db.events.find_one(sort=[("created_at", -1)])
        if event:
            session["current_event_id"] = str(event["_id"])
        else:
            session.pop("current_event_id", None)
    return event


def require_current_event():
    event = get_current_event()
    if not event:
        flash("Create an event first to unlock this section.", "info")
    return event


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    event = get_current_event()
    events_count = db.events.count_documents({})
    if not event:
        return render_template("admin/dashboard.html", event=None, events_count=events_count)

    event_id = event["_id"]
    today = today_str()

    total_volunteers = db.volunteers.count_documents({"event_id": event_id})
    present_today = db.attendance.count_documents(
        {"event_id": event_id, "date": today, "check_in": {"$ne": None}}
    )
    pending_tasks = db.tasks.count_documents({"event_id": event_id, "status": {"$in": ["pending", "in-progress"]}})
    completed_tasks = db.tasks.count_documents({"event_id": event_id, "status": "completed"})
    total_tasks = pending_tasks + completed_tasks
    open_issues = db.issues.count_documents({"event_id": event_id, "status": {"$ne": "resolved"}})
    total_equipment = db.equipment.count_documents({"event_id": event_id})

    start_range = (date.today() - timedelta(days=6)).strftime("%Y-%m-%d")
    trend_pipeline = [
        {"$match": {"event_id": event_id, "date": {"$gte": start_range, "$lte": today}, "check_in": {"$ne": None}}},
        {"$group": {"_id": "$date", "count": {"$sum": 1}}},
    ]
    counts_by_date = {row["_id"]: row["count"] for row in db.attendance.aggregate(trend_pipeline)}
    trend_labels, trend_values = [], []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
        trend_labels.append(d[5:])
        trend_values.append(counts_by_date.get(d, 0))

    task_pipeline = [
        {"$match": {"event_id": event_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    task_counts = {row["_id"]: row["count"] for row in db.tasks.aggregate(task_pipeline)}
    task_labels = ["Pending", "In progress", "Completed"]
    task_values = [task_counts.get("pending", 0), task_counts.get("in-progress", 0), task_counts.get("completed", 0)]

    domain_pipeline = [
        {"$match": {"event_id": event_id}},
        {"$group": {"_id": "$domain", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    domain_rows = list(db.volunteers.aggregate(domain_pipeline))
    domain_labels = [row["_id"] or "Unassigned" for row in domain_rows]
    domain_values = [row["count"] for row in domain_rows]

    recent_issues = list(
        db.issues.find({"event_id": event_id, "status": {"$ne": "resolved"}}).sort("created_at", -1).limit(5)
    )

    return render_template(
        "admin/dashboard.html",
        event=event,
        events_count=events_count,
        total_volunteers=total_volunteers,
        present_today=present_today,
        pending_tasks=pending_tasks,
        completed_tasks=completed_tasks,
        total_tasks=total_tasks,
        open_issues=open_issues,
        total_equipment=total_equipment,
        trend_labels=trend_labels,
        trend_values=trend_values,
        task_labels=task_labels,
        task_values=task_values,
        domain_labels=domain_labels,
        domain_values=domain_values,
        recent_issues=recent_issues,
    )


@admin_bp.route("/dashboard/live")
@admin_required
def dashboard_live():
    """
    Polled by static/js/live_dashboard.js every few seconds so the dashboard
    reflects new check-ins without a manual page reload. Deliberately plain
    HTTP polling rather than WebSockets: it behaves identically whether the
    app is deployed on Render (long-running server) or Vercel (serverless
    functions, no persistent connections) — see README.md.
    """
    event = get_current_event()
    if not event:
        return jsonify({"error": "no_event"}), 404

    event_id = event["_id"]
    today = today_str()

    present_today = db.attendance.count_documents({"event_id": event_id, "date": today, "check_in": {"$ne": None}})
    total_volunteers = db.volunteers.count_documents({"event_id": event_id})
    pending_tasks = db.tasks.count_documents({"event_id": event_id, "status": {"$in": ["pending", "in-progress"]}})
    open_issues = db.issues.count_documents({"event_id": event_id, "status": {"$ne": "resolved"}})

    recent_docs = list(db.attendance.find({"event_id": event_id, "date": today}).sort("updated_at", -1).limit(10))
    activity = []
    for a_doc in recent_docs:
        for kind, label in (("check_out", "Checked out"), ("check_in", "Checked in")):
            entry = a_doc.get(kind)
            if entry and entry.get("time"):
                activity.append({
                    "volunteer_name": a_doc.get("volunteer_name", ""),
                    "action": label,
                    "method": entry.get("method", "gps"),
                    "time_label": entry["time"].strftime("%I:%M %p"),
                    "sort_key": entry["time"].isoformat(),
                })
    activity.sort(key=lambda item: item["sort_key"], reverse=True)

    return jsonify({
        "present_today": present_today,
        "total_volunteers": total_volunteers,
        "pending_tasks": pending_tasks,
        "open_issues": open_issues,
        "recent_activity": activity[:6],
        "updated_at": datetime.now().strftime("%I:%M:%S %p"),
    })


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@admin_bp.route("/events")
@admin_required
def events_list():
    events = list(db.events.find().sort("created_at", -1))
    current_event = get_current_event()
    current_id = str(current_event["_id"]) if current_event else None
    return render_template("admin/events.html", events=events, current_id=current_id)


def _build_event_doc_from_form(form):
    errors = []
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    venue = (form.get("venue") or "").strip()
    start_date = (form.get("start_date") or "").strip()
    end_date = (form.get("end_date") or "").strip()
    lat = parse_float(form.get("latitude"))
    lng = parse_float(form.get("longitude"))
    radius = parse_int(form.get("geofence_radius"))
    domains = split_csv_field(form.get("domains"))

    if not name:
        errors.append("Event name is required.")
    if not venue:
        errors.append("Venue is required.")
    start_parsed = parse_date_str(start_date)
    end_parsed = parse_date_str(end_date)
    if not start_parsed:
        errors.append("A valid start date is required.")
    if not end_parsed:
        errors.append("A valid end date is required.")
    if start_parsed and end_parsed and start_parsed > end_parsed:
        errors.append("Start date must be on or before the end date.")
    if lat is None or lng is None or not valid_coordinates(lat, lng):
        errors.append("A valid venue location is required — click the map or use \u201cUse my location\u201d.")
    if not radius or radius <= 0:
        errors.append("Geofence radius must be a positive number of meters.")
    if not domains:
        errors.append("Add at least one volunteer domain (comma-separated).")

    doc = {
        "name": name,
        "description": description,
        "venue": venue,
        "start_date": start_date,
        "end_date": end_date,
        "geofence_radius": radius if radius and radius > 0 else 100,
        "domains": domains,
    }
    if lat is not None and lng is not None and valid_coordinates(lat, lng):
        doc["location"] = make_geojson_point(lat, lng)

    return doc, errors


@admin_bp.route("/events/create", methods=["GET", "POST"])
@admin_required
def event_create():
    if request.method == "POST":
        doc, errors = _build_event_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/event_form.html", event=None, values=request.form,
                lat=request.form.get("latitude", ""), lng=request.form.get("longitude", ""),
                radius=request.form.get("geofence_radius", 100),
            )

        doc["created_by"] = current_user.name
        doc["created_at"] = datetime.now()
        doc["qr_secret"] = generate_qr_secret()
        result = db.events.insert_one(doc)
        session["current_event_id"] = str(result.inserted_id)
        flash(f"\u201c{doc['name']}\u201d was created and is now your active event.", "success")
        return redirect(url_for("admin.events_list"))

    return render_template("admin/event_form.html", event=None, values=None, lat="", lng="", radius=100)


@admin_bp.route("/events/<event_id>/edit", methods=["GET", "POST"])
@admin_required
def event_edit(event_id):
    oid = to_object_id(event_id)
    event = db.events.find_one({"_id": oid}) if oid else None
    if not event:
        abort(404)

    if request.method == "POST":
        doc, errors = _build_event_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "admin/event_form.html", event=event, values=request.form,
                lat=request.form.get("latitude", ""), lng=request.form.get("longitude", ""),
                radius=request.form.get("geofence_radius", 100),
            )
        db.events.update_one({"_id": oid}, {"$set": doc})
        flash(f"\u201c{doc['name']}\u201d was updated.", "success")
        return redirect(url_for("admin.events_list"))

    lat, lng = event_latlng(event)
    return render_template("admin/event_form.html", event=event, values=event, lat=lat, lng=lng, radius=event.get("geofence_radius", 100))


@admin_bp.route("/events/<event_id>/delete", methods=["POST"])
@admin_required
def event_delete(event_id):
    oid = to_object_id(event_id)
    event = db.events.find_one({"_id": oid}) if oid else None
    if not event:
        abort(404)

    volunteer_ids = [v["_id"] for v in db.volunteers.find({"event_id": oid}, {"_id": 1})]
    db.users.delete_many({"volunteer_id": {"$in": volunteer_ids}})
    db.volunteers.delete_many({"event_id": oid})
    db.tasks.delete_many({"event_id": oid})
    db.attendance.delete_many({"event_id": oid})
    db.issues.delete_many({"event_id": oid})
    db.equipment.delete_many({"event_id": oid})
    db.schedules.delete_many({"event_id": oid})
    db.notifications.delete_many({"event_id": oid})
    db.events.delete_one({"_id": oid})

    if session.get("current_event_id") == event_id:
        session.pop("current_event_id", None)

    flash(f"\u201c{event['name']}\u201d and all related data were deleted.", "success")
    return redirect(url_for("admin.events_list"))


@admin_bp.route("/events/switch", methods=["POST"])
@admin_required
def event_switch():
    event_id = request.form.get("event_id")
    if event_id and db.events.find_one({"_id": to_object_id(event_id)}):
        session["current_event_id"] = event_id
    return redirect(request.referrer or url_for("admin.dashboard"))


@admin_bp.route("/events/<event_id>/qr")
@admin_required
def event_qr(event_id):
    oid = to_object_id(event_id)
    event = db.events.find_one({"_id": oid}) if oid else None
    if not event:
        abort(404)

    if not event.get("qr_secret"):
        # Defensive backfill for any event created before this feature existed.
        qr_secret = generate_qr_secret()
        db.events.update_one({"_id": oid}, {"$set": {"qr_secret": qr_secret}})
        event["qr_secret"] = qr_secret

    checkin_url = url_for("volunteer.qr_checkin_confirm", event_id=event_id, secret=event["qr_secret"], _external=True)
    qr_image = qr_code_data_uri(checkin_url)
    return render_template("admin/event_qr.html", event=event, checkin_url=checkin_url, qr_image=qr_image)


@admin_bp.route("/events/<event_id>/qr/regenerate", methods=["POST"])
@admin_required
def event_qr_regenerate(event_id):
    oid = to_object_id(event_id)
    event = db.events.find_one({"_id": oid}) if oid else None
    if not event:
        abort(404)
    db.events.update_one({"_id": oid}, {"$set": {"qr_secret": generate_qr_secret()}})
    flash("New QR code generated — any previously printed copies will no longer work.", "success")
    return redirect(url_for("admin.event_qr", event_id=event_id))


# ---------------------------------------------------------------------------
# Volunteers
# ---------------------------------------------------------------------------

@admin_bp.route("/volunteers")
@admin_required
def volunteers_list():
    event = get_current_event()
    if not event:
        return render_template("admin/volunteers.html", event=None, volunteers=[], pending=[])

    pending = list(db.volunteers.find({"event_id": event["_id"], "status": "pending"}).sort("created_at", 1))
    volunteers = list(db.volunteers.find({"event_id": event["_id"], "status": {"$ne": "pending"}}).sort("name", 1))

    stats_pipeline = [
        {"$match": {"event_id": event["_id"]}},
        {"$group": {
            "_id": "$assigned_to",
            "total": {"$sum": 1},
            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
        }},
    ]
    stats_by_volunteer = {row["_id"]: row for row in db.tasks.aggregate(stats_pipeline)}
    for v in volunteers:
        stats = stats_by_volunteer.get(v["_id"], {"total": 0, "completed": 0})
        v["task_count"] = stats["total"]
        v["completed_task_count"] = stats["completed"]

    return render_template("admin/volunteers.html", event=event, volunteers=volunteers, pending=pending)


@admin_bp.route("/volunteers/<volunteer_id>/approve", methods=["POST"])
@admin_required
def volunteer_approve(volunteer_id):
    oid = to_object_id(volunteer_id)
    pending_vol = db.volunteers.find_one({"_id": oid, "status": "pending"}) if oid else None
    if not pending_vol:
        abort(404)

    domain = (request.form.get("domain") or pending_vol.get("domain") or "").strip()

    try:
        db.users.insert_one({
            "username": pending_vol["pending_username"],
            "email": pending_vol["email"],
            "password_hash": pending_vol["pending_password_hash"],
            "role": "volunteer",
            "name": pending_vol["name"],
            "volunteer_id": oid,
            "created_at": datetime.now(),
            "last_login": None,
        })
    except Exception:
        flash("Could not create the login account — that username or email may already be taken.", "error")
        return redirect(url_for("admin.volunteers_list"))

    db.volunteers.update_one(
        {"_id": oid},
        {"$set": {"status": "active", "domain": domain}, "$unset": {"pending_username": "", "pending_password_hash": ""}},
    )
    flash(f"{pending_vol['name']} was approved and can now log in.", "success")
    return redirect(url_for("admin.volunteers_list"))


@admin_bp.route("/volunteers/<volunteer_id>/reject", methods=["POST"])
@admin_required
def volunteer_reject(volunteer_id):
    oid = to_object_id(volunteer_id)
    pending_vol = db.volunteers.find_one({"_id": oid, "status": "pending"}) if oid else None
    if not pending_vol:
        abort(404)
    db.volunteers.delete_one({"_id": oid})
    flash(f"{pending_vol['name']}'s registration request was declined.", "success")
    return redirect(url_for("admin.volunteers_list"))


@admin_bp.route("/volunteers/create", methods=["GET", "POST"])
@admin_required
def volunteer_create():
    event = require_current_event()
    if not event:
        return redirect(url_for("admin.events_list"))

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        domain = (request.form.get("domain") or "").strip()
        responsibilities = (request.form.get("responsibilities") or "").strip()
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        errors = []
        if not name:
            errors.append("Name is required.")
        if not email or "@" not in email:
            errors.append("A valid email is required.")
        if not username:
            errors.append("Username is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if domain not in event.get("domains", []):
            errors.append("Please select a valid domain for this event.")
        if not errors and db.users.find_one({"$or": [{"username": username}, {"email": email}]}):
            errors.append("A user with that username or email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/volunteer_form.html", event=event, volunteer=None, values=request.form)

        volunteer_doc = {
            "event_id": event["_id"],
            "name": name,
            "email": email,
            "phone": phone,
            "domain": domain,
            "responsibilities": responsibilities,
            "status": "active",
            "joined_date": today_str(),
            "created_at": datetime.now(),
        }
        volunteer_id = db.volunteers.insert_one(volunteer_doc).inserted_id

        try:
            db.users.insert_one({
                "username": username,
                "email": email,
                "password_hash": generate_password_hash(password),
                "role": "volunteer",
                "name": name,
                "volunteer_id": volunteer_id,
                "created_at": datetime.now(),
                "last_login": None,
            })
        except Exception:
            db.volunteers.delete_one({"_id": volunteer_id})
            flash("Could not create the login account. Please try again.", "error")
            return render_template("admin/volunteer_form.html", event=event, volunteer=None, values=request.form)

        flash(f"{name} was added to {event['name']}. Share their username/password to let them log in.", "success")
        return redirect(url_for("admin.volunteers_list"))

    return render_template("admin/volunteer_form.html", event=event, volunteer=None, values=None)


@admin_bp.route("/volunteers/<volunteer_id>/edit", methods=["GET", "POST"])
@admin_required
def volunteer_edit(volunteer_id):
    oid = to_object_id(volunteer_id)
    volunteer = db.volunteers.find_one({"_id": oid}) if oid else None
    if not volunteer:
        abort(404)
    event = db.events.find_one({"_id": volunteer["event_id"]})
    user_doc = db.users.find_one({"volunteer_id": oid})

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        domain = (request.form.get("domain") or "").strip()
        responsibilities = (request.form.get("responsibilities") or "").strip()
        status = (request.form.get("status") or "active").strip()
        username = (request.form.get("username") or "").strip().lower()
        new_password = request.form.get("password") or ""

        errors = []
        if not name:
            errors.append("Name is required.")
        if not email or "@" not in email:
            errors.append("A valid email is required.")
        if not username:
            errors.append("Username is required.")
        if new_password and len(new_password) < 6:
            errors.append("New password must be at least 6 characters.")

        if not errors:
            conflict_query = {"$or": [{"username": username}, {"email": email}]}
            if user_doc:
                conflict_query["_id"] = {"$ne": user_doc["_id"]}
            if db.users.find_one(conflict_query):
                errors.append("Another account already uses that username or email.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/volunteer_form.html", event=event, volunteer=volunteer, values=request.form)

        db.volunteers.update_one({"_id": oid}, {"$set": {
            "name": name, "email": email, "phone": phone, "domain": domain,
            "responsibilities": responsibilities,
            "status": status if status in ("active", "inactive") else "active",
        }})

        if user_doc:
            user_update = {"username": username, "email": email, "name": name}
            if new_password:
                user_update["password_hash"] = generate_password_hash(new_password)
            db.users.update_one({"_id": user_doc["_id"]}, {"$set": user_update})

        db.tasks.update_many({"assigned_to": oid}, {"$set": {"assigned_to_name": name}})
        db.attendance.update_many({"volunteer_id": oid}, {"$set": {"volunteer_name": name}})
        db.issues.update_many({"reported_by": oid}, {"$set": {"reported_by_name": name}})

        flash(f"{name}'s profile was updated.", "success")
        return redirect(url_for("admin.volunteers_list"))

    values = dict(volunteer)
    values["username"] = user_doc.get("username", "") if user_doc else ""
    return render_template("admin/volunteer_form.html", event=event, volunteer=volunteer, values=values)


@admin_bp.route("/volunteers/<volunteer_id>/delete", methods=["POST"])
@admin_required
def volunteer_delete(volunteer_id):
    oid = to_object_id(volunteer_id)
    volunteer = db.volunteers.find_one({"_id": oid}) if oid else None
    if not volunteer:
        abort(404)
    db.users.delete_one({"volunteer_id": oid})
    db.volunteers.delete_one({"_id": oid})
    flash(f"{volunteer['name']} was removed. Their task and attendance history has been kept for your records.", "success")
    return redirect(url_for("admin.volunteers_list"))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@admin_bp.route("/tasks")
@admin_required
def tasks_list():
    event = get_current_event()
    if not event:
        return render_template("admin/tasks.html", event=None, tasks=[], volunteers=[])

    query = {"event_id": event["_id"]}
    status_filter = request.args.get("status", "")
    if status_filter:
        query["status"] = status_filter
    domain_filter = request.args.get("domain", "")
    if domain_filter:
        query["domain"] = domain_filter

    tasks = list(db.tasks.find(query).sort("created_at", -1))
    volunteers = list(db.volunteers.find({"event_id": event["_id"]}).sort("name", 1))
    return render_template(
        "admin/tasks.html", event=event, tasks=tasks, volunteers=volunteers,
        status_filter=status_filter, domain_filter=domain_filter,
    )


def _build_task_doc_from_form(form, event_id):
    errors = []
    title = (form.get("title") or "").strip()
    description = (form.get("description") or "").strip()
    domain = (form.get("domain") or "").strip()
    priority = (form.get("priority") or "medium").strip()
    due_date = (form.get("due_date") or "").strip()
    volunteer_oid = to_object_id(form.get("assigned_to"))

    if not title:
        errors.append("Task title is required.")

    volunteer = None
    if not volunteer_oid:
        errors.append("Please assign this task to a volunteer.")
    else:
        volunteer = db.volunteers.find_one({"_id": volunteer_oid, "event_id": event_id})
        if not volunteer:
            errors.append("Selected volunteer was not found in this event.")

    doc = {
        "title": title,
        "description": description,
        "domain": domain,
        "priority": priority if priority in ("low", "medium", "high") else "medium",
        "due_date": due_date or None,
        "assigned_to": volunteer["_id"] if volunteer else None,
        "assigned_to_name": volunteer["name"] if volunteer else None,
    }
    return doc, errors


@admin_bp.route("/tasks/create", methods=["GET", "POST"])
@admin_required
def task_create():
    event = require_current_event()
    if not event:
        return redirect(url_for("admin.events_list"))
    volunteers = list(db.volunteers.find({"event_id": event["_id"]}).sort("name", 1))

    if request.method == "POST":
        doc, errors = _build_task_doc_from_form(request.form, event["_id"])
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/task_form.html", event=event, task=None, volunteers=volunteers, values=request.form)

        doc.update({
            "event_id": event["_id"],
            "status": "pending",
            "status_history": [{"status": "pending", "time": datetime.now()}],
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        })
        db.tasks.insert_one(doc)
        flash(f"Task \u201c{doc['title']}\u201d assigned to {doc['assigned_to_name']}.", "success")
        return redirect(url_for("admin.tasks_list"))

    return render_template("admin/task_form.html", event=event, task=None, volunteers=volunteers, values=None)


@admin_bp.route("/tasks/<task_id>/edit", methods=["GET", "POST"])
@admin_required
def task_edit(task_id):
    oid = to_object_id(task_id)
    task = db.tasks.find_one({"_id": oid}) if oid else None
    if not task:
        abort(404)
    event = db.events.find_one({"_id": task["event_id"]})
    volunteers = list(db.volunteers.find({"event_id": task["event_id"]}).sort("name", 1))

    if request.method == "POST":
        doc, errors = _build_task_doc_from_form(request.form, task["event_id"])
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/task_form.html", event=event, task=task, volunteers=volunteers, values=request.form)

        doc["updated_at"] = datetime.now()
        db.tasks.update_one({"_id": oid}, {"$set": doc})
        flash(f"Task \u201c{doc['title']}\u201d was updated.", "success")
        return redirect(url_for("admin.tasks_list"))

    return render_template("admin/task_form.html", event=event, task=task, volunteers=volunteers, values=task)


@admin_bp.route("/tasks/<task_id>/delete", methods=["POST"])
@admin_required
def task_delete(task_id):
    oid = to_object_id(task_id)
    task = db.tasks.find_one({"_id": oid}) if oid else None
    if not task:
        abort(404)
    db.tasks.delete_one({"_id": oid})
    flash(f"Task \u201c{task['title']}\u201d was deleted.", "success")
    return redirect(url_for("admin.tasks_list"))


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@admin_bp.route("/attendance")
@admin_required
def attendance_view():
    event = get_current_event()
    if not event:
        return render_template("admin/attendance.html", event=None, rows=[], selected_date=today_str())

    selected_date = request.args.get("date") or today_str()
    volunteers = list(db.volunteers.find({"event_id": event["_id"]}).sort("name", 1))
    attendance_docs = list(db.attendance.find({"event_id": event["_id"], "date": selected_date}))
    attendance_by_vol = {str(doc["volunteer_id"]): doc for doc in attendance_docs}

    rows, present_count = [], 0
    for v in volunteers:
        att = attendance_by_vol.get(str(v["_id"]))
        if att and att.get("check_in"):
            present_count += 1
            status = "checked-out" if att.get("check_out") else "present"
        else:
            status = "absent"
        rows.append({"volunteer": v, "attendance": att, "status": status})

    return render_template(
        "admin/attendance.html", event=event, rows=rows, selected_date=selected_date,
        present_count=present_count, total_count=len(volunteers), today=today_str(),
    )


@admin_bp.route("/attendance/manual", methods=["POST"])
@admin_required
def attendance_manual():
    event = get_current_event()
    if not event:
        return redirect(url_for("admin.attendance_view"))

    volunteer_oid = to_object_id(request.form.get("volunteer_id"))
    note = (request.form.get("note") or "Marked manually by admin (GPS unavailable).").strip()
    volunteer = db.volunteers.find_one({"_id": volunteer_oid, "event_id": event["_id"]}) if volunteer_oid else None

    if not volunteer:
        flash("Volunteer not found.", "error")
        return redirect(url_for("admin.attendance_view"))

    today = today_str()
    existing = db.attendance.find_one({"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today})
    entry = {"time": datetime.now(), "lat": None, "lng": None, "distance_meters": None, "method": "manual", "note": note}

    if not existing:
        db.attendance.insert_one({
            "volunteer_id": volunteer["_id"], "volunteer_name": volunteer["name"], "event_id": event["_id"],
            "date": today, "check_in": entry, "check_out": None, "rejected_attempts": [],
            "created_at": datetime.now(), "updated_at": datetime.now(),
        })
        flash(f"Marked {volunteer['name']} present for today (manual entry).", "success")
    elif not existing.get("check_in"):
        db.attendance.update_one({"_id": existing["_id"]}, {"$set": {"check_in": entry, "updated_at": datetime.now()}})
        flash(f"Marked {volunteer['name']} present for today (manual entry).", "success")
    elif not existing.get("check_out"):
        db.attendance.update_one({"_id": existing["_id"]}, {"$set": {"check_out": entry, "updated_at": datetime.now()}})
        flash(f"Marked {volunteer['name']} checked out for today (manual entry).", "success")
    else:
        flash(f"{volunteer['name']} already has a complete attendance record for today.", "info")

    return redirect(url_for("admin.attendance_view", date=today))


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------

@admin_bp.route("/equipment")
@admin_required
def equipment_list():
    event = get_current_event()
    if not event:
        return render_template("admin/equipment.html", event=None, items=[])
    items = list(db.equipment.find({"event_id": event["_id"]}).sort("name", 1))
    return render_template("admin/equipment.html", event=event, items=items)


def _build_equipment_doc_from_form(form):
    errors = []
    name = (form.get("name") or "").strip()
    category = (form.get("category") or "").strip()
    total_quantity = parse_int(form.get("total_quantity"))
    assigned_quantity = parse_int(form.get("assigned_quantity"), 0)
    condition = (form.get("condition") or "Good").strip()
    assigned_to = (form.get("assigned_to") or "").strip()
    notes = (form.get("notes") or "").strip()

    if not name:
        errors.append("Equipment name is required.")
    if total_quantity is None or total_quantity < 0:
        errors.append("Total quantity must be a non-negative number.")
    if assigned_quantity is None or assigned_quantity < 0:
        errors.append("Assigned quantity must be a non-negative number.")
    if not errors and assigned_quantity > total_quantity:
        errors.append("Assigned quantity can't exceed total quantity.")

    doc = {
        "name": name, "category": category or "General", "total_quantity": total_quantity or 0,
        "assigned_quantity": assigned_quantity or 0, "condition": condition or "Good",
        "assigned_to": assigned_to, "notes": notes,
    }
    return doc, errors


@admin_bp.route("/equipment/create", methods=["GET", "POST"])
@admin_required
def equipment_create():
    event = require_current_event()
    if not event:
        return redirect(url_for("admin.events_list"))

    if request.method == "POST":
        doc, errors = _build_equipment_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/equipment_form.html", event=event, item=None, values=request.form)
        doc.update({"event_id": event["_id"], "created_at": datetime.now(), "updated_at": datetime.now()})
        db.equipment.insert_one(doc)
        flash(f"{doc['name']} was added to inventory.", "success")
        return redirect(url_for("admin.equipment_list"))

    return render_template("admin/equipment_form.html", event=event, item=None, values=None)


@admin_bp.route("/equipment/<item_id>/edit", methods=["GET", "POST"])
@admin_required
def equipment_edit(item_id):
    oid = to_object_id(item_id)
    item = db.equipment.find_one({"_id": oid}) if oid else None
    if not item:
        abort(404)
    event = db.events.find_one({"_id": item["event_id"]})

    if request.method == "POST":
        doc, errors = _build_equipment_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/equipment_form.html", event=event, item=item, values=request.form)
        doc["updated_at"] = datetime.now()
        db.equipment.update_one({"_id": oid}, {"$set": doc})
        flash(f"{doc['name']} was updated.", "success")
        return redirect(url_for("admin.equipment_list"))

    return render_template("admin/equipment_form.html", event=event, item=item, values=item)


@admin_bp.route("/equipment/<item_id>/delete", methods=["POST"])
@admin_required
def equipment_delete(item_id):
    oid = to_object_id(item_id)
    item = db.equipment.find_one({"_id": oid}) if oid else None
    if not item:
        abort(404)
    db.equipment.delete_one({"_id": oid})
    flash(f"{item['name']} was removed from inventory.", "success")
    return redirect(url_for("admin.equipment_list"))


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@admin_bp.route("/schedule")
@admin_required
def schedule_list():
    event = get_current_event()
    if not event:
        return render_template("admin/schedule.html", event=None, items=[])
    items = list(db.schedules.find({"event_id": event["_id"]}).sort([("date", 1), ("start_time", 1)]))
    return render_template("admin/schedule.html", event=event, items=items)


def _build_schedule_doc_from_form(form):
    errors = []
    title = (form.get("title") or "").strip()
    description = (form.get("description") or "").strip()
    item_date = (form.get("date") or "").strip()
    start_time = (form.get("start_time") or "").strip()
    end_time = (form.get("end_time") or "").strip()
    venue = (form.get("venue") or "").strip()
    item_type = (form.get("type") or "Session").strip()

    if not title:
        errors.append("Title is required.")
    if not parse_date_str(item_date):
        errors.append("A valid date is required.")
    if not start_time:
        errors.append("Start time is required.")

    doc = {
        "title": title, "description": description, "date": item_date,
        "start_time": start_time, "end_time": end_time, "venue": venue, "type": item_type,
    }
    return doc, errors


@admin_bp.route("/schedule/create", methods=["GET", "POST"])
@admin_required
def schedule_create():
    event = require_current_event()
    if not event:
        return redirect(url_for("admin.events_list"))

    if request.method == "POST":
        doc, errors = _build_schedule_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/schedule_form.html", event=event, item=None, values=request.form)
        doc.update({"event_id": event["_id"], "created_at": datetime.now()})
        db.schedules.insert_one(doc)
        flash(f"\u201c{doc['title']}\u201d was added to the schedule.", "success")
        return redirect(url_for("admin.schedule_list"))

    return render_template("admin/schedule_form.html", event=event, item=None, values=None)


@admin_bp.route("/schedule/<item_id>/edit", methods=["GET", "POST"])
@admin_required
def schedule_edit(item_id):
    oid = to_object_id(item_id)
    item = db.schedules.find_one({"_id": oid}) if oid else None
    if not item:
        abort(404)
    event = db.events.find_one({"_id": item["event_id"]})

    if request.method == "POST":
        doc, errors = _build_schedule_doc_from_form(request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/schedule_form.html", event=event, item=item, values=request.form)
        db.schedules.update_one({"_id": oid}, {"$set": doc})
        flash(f"\u201c{doc['title']}\u201d was updated.", "success")
        return redirect(url_for("admin.schedule_list"))

    return render_template("admin/schedule_form.html", event=event, item=item, values=item)


@admin_bp.route("/schedule/<item_id>/delete", methods=["POST"])
@admin_required
def schedule_delete(item_id):
    oid = to_object_id(item_id)
    item = db.schedules.find_one({"_id": oid}) if oid else None
    if not item:
        abort(404)
    db.schedules.delete_one({"_id": oid})
    flash(f"\u201c{item['title']}\u201d was removed from the schedule.", "success")
    return redirect(url_for("admin.schedule_list"))


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@admin_bp.route("/issues")
@admin_required
def issues_list():
    event = get_current_event()
    if not event:
        return render_template("admin/issues.html", event=None, issues=[], status_filter="")
    status_filter = request.args.get("status", "")
    query = {"event_id": event["_id"]}
    if status_filter:
        query["status"] = status_filter
    issues = list(db.issues.find(query).sort("created_at", -1))
    return render_template("admin/issues.html", event=event, issues=issues, status_filter=status_filter)


@admin_bp.route("/issues/<issue_id>/update", methods=["POST"])
@admin_required
def issue_update(issue_id):
    oid = to_object_id(issue_id)
    issue = db.issues.find_one({"_id": oid}) if oid else None
    if not issue:
        abort(404)

    status = (request.form.get("status") or "").strip()
    response_text = (request.form.get("admin_response") or "").strip()
    if status not in ("open", "in-progress", "resolved"):
        flash("Invalid status.", "error")
        return redirect(url_for("admin.issues_list"))

    update = {"status": status, "admin_response": response_text}
    if status == "resolved":
        update["resolved_at"] = datetime.now()
        update["resolved_by"] = current_user.name
    db.issues.update_one({"_id": oid}, {"$set": update})
    flash(f"Issue \u201c{issue['title']}\u201d marked as {status}.", "success")
    return redirect(url_for("admin.issues_list"))


# ---------------------------------------------------------------------------
# Notifications / announcements
# ---------------------------------------------------------------------------

@admin_bp.route("/notifications")
@admin_required
def notifications_list():
    event = get_current_event()
    if not event:
        return render_template("admin/notifications.html", event=None, notifications=[])
    notifications = list(db.notifications.find({"event_id": event["_id"]}).sort("created_at", -1))
    return render_template("admin/notifications.html", event=event, notifications=notifications)


@admin_bp.route("/notifications/create", methods=["GET", "POST"])
@admin_required
def notification_create():
    event = require_current_event()
    if not event:
        return redirect(url_for("admin.events_list"))

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        message = (request.form.get("message") or "").strip()
        priority = (request.form.get("priority") or "normal").strip()

        if not title or not message:
            flash("Title and message are both required.", "error")
            return render_template("admin/notification_form.html", event=event, notification=None, values=request.form)

        db.notifications.insert_one({
            "event_id": event["_id"], "title": title, "message": message,
            "priority": priority if priority in ("normal", "important", "urgent") else "normal",
            "is_active": True, "created_by": current_user.name, "created_at": datetime.now(),
        })
        flash("Announcement posted to all volunteers on this event.", "success")
        return redirect(url_for("admin.notifications_list"))

    return render_template("admin/notification_form.html", event=event, notification=None, values=None)


@admin_bp.route("/notifications/<notif_id>/edit", methods=["GET", "POST"])
@admin_required
def notification_edit(notif_id):
    oid = to_object_id(notif_id)
    notification = db.notifications.find_one({"_id": oid}) if oid else None
    if not notification:
        abort(404)
    event = db.events.find_one({"_id": notification["event_id"]})

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        message = (request.form.get("message") or "").strip()
        priority = (request.form.get("priority") or "normal").strip()
        is_active = request.form.get("is_active") == "on"

        if not title or not message:
            flash("Title and message are both required.", "error")
            return render_template("admin/notification_form.html", event=event, notification=notification, values=request.form)

        db.notifications.update_one({"_id": oid}, {"$set": {
            "title": title, "message": message,
            "priority": priority if priority in ("normal", "important", "urgent") else "normal",
            "is_active": is_active,
        }})
        flash("Announcement updated.", "success")
        return redirect(url_for("admin.notifications_list"))

    return render_template("admin/notification_form.html", event=event, notification=notification, values=notification)


@admin_bp.route("/notifications/<notif_id>/delete", methods=["POST"])
@admin_required
def notification_delete(notif_id):
    oid = to_object_id(notif_id)
    notification = db.notifications.find_one({"_id": oid}) if oid else None
    if not notification:
        abort(404)
    db.notifications.delete_one({"_id": oid})
    flash("Announcement deleted.", "success")
    return redirect(url_for("admin.notifications_list"))


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

@admin_bp.route("/reports")
@admin_required
def reports():
    event = get_current_event()
    if not event:
        return render_template("admin/reports.html", event=None)

    total_attendance_records = db.attendance.count_documents({"event_id": event["_id"], "check_in": {"$ne": None}})
    total_tasks = db.tasks.count_documents({"event_id": event["_id"]})
    completed_tasks = db.tasks.count_documents({"event_id": event["_id"], "status": "completed"})
    total_volunteers = db.volunteers.count_documents({"event_id": event["_id"]})
    total_issues = db.issues.count_documents({"event_id": event["_id"]})
    resolved_issues = db.issues.count_documents({"event_id": event["_id"], "status": "resolved"})

    return render_template(
        "admin/reports.html", event=event,
        total_attendance_records=total_attendance_records, total_tasks=total_tasks,
        completed_tasks=completed_tasks, total_volunteers=total_volunteers,
        total_issues=total_issues, resolved_issues=resolved_issues,
    )


@admin_bp.route("/reports/attendance/export")
@admin_required
def export_attendance_csv():
    event = get_current_event()
    if not event:
        flash("Create an event first.", "info")
        return redirect(url_for("admin.reports"))

    docs = list(db.attendance.find({"event_id": event["_id"]}).sort("date", -1))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Volunteer", "Date", "Check-in time", "Check-in lat", "Check-in lng", "Check-in distance (m)", "Check-in method",
        "Check-out time", "Check-out lat", "Check-out lng", "Check-out distance (m)", "Check-out method", "Status",
    ])
    method_labels = {"gps": "GPS", "manual": "Manual (admin)", "qr": "QR code"}
    for doc in docs:
        ci = doc.get("check_in") or {}
        co = doc.get("check_out") or {}
        status = "Checked out" if co else ("Present" if ci else "Incomplete")
        writer.writerow([
            doc.get("volunteer_name", ""), doc.get("date", ""),
            ci.get("time").strftime("%H:%M:%S") if ci.get("time") else "",
            ci.get("lat", ""), ci.get("lng", ""),
            round(ci["distance_meters"], 1) if ci.get("distance_meters") is not None else "",
            method_labels.get(ci.get("method"), ""),
            co.get("time").strftime("%H:%M:%S") if co.get("time") else "",
            co.get("lat", ""), co.get("lng", ""),
            round(co["distance_meters"], 1) if co.get("distance_meters") is not None else "",
            method_labels.get(co.get("method"), ""),
            status,
        ])

    filename = f"attendance_{event['name'].replace(' ', '_')}_{today_str()}.csv"
    return Response(buffer.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@admin_bp.route("/reports/tasks/export")
@admin_required
def export_tasks_csv():
    event = get_current_event()
    if not event:
        flash("Create an event first.", "info")
        return redirect(url_for("admin.reports"))

    docs = list(db.tasks.find({"event_id": event["_id"]}).sort("created_at", -1))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Title", "Domain", "Assigned to", "Priority", "Status", "Due date", "Created"])
    for doc in docs:
        writer.writerow([
            doc.get("title", ""), doc.get("domain", ""), doc.get("assigned_to_name", ""),
            doc.get("priority", ""), doc.get("status", ""), doc.get("due_date", ""),
            doc.get("created_at").strftime("%Y-%m-%d") if doc.get("created_at") else "",
        ])

    filename = f"tasks_{event['name'].replace(' ', '_')}_{today_str()}.csv"
    return Response(buffer.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename={filename}"})


@admin_bp.route("/reports/pdf")
@admin_required
def export_event_report_pdf():
    event = get_current_event()
    if not event:
        flash("Create an event first.", "info")
        return redirect(url_for("admin.reports"))

    stats = {
        "total_volunteers": db.volunteers.count_documents({"event_id": event["_id"]}),
        "total_attendance_records": db.attendance.count_documents({"event_id": event["_id"], "check_in": {"$ne": None}}),
        "total_tasks": db.tasks.count_documents({"event_id": event["_id"]}),
        "completed_tasks": db.tasks.count_documents({"event_id": event["_id"], "status": "completed"}),
        "total_issues": db.issues.count_documents({"event_id": event["_id"]}),
        "resolved_issues": db.issues.count_documents({"event_id": event["_id"], "status": "resolved"}),
    }
    attendance_docs = list(db.attendance.find({"event_id": event["_id"]}).sort("date", -1))
    task_docs = list(db.tasks.find({"event_id": event["_id"]}).sort("created_at", -1))

    pdf_buffer = build_event_report_pdf(event, stats, attendance_docs, task_docs)
    filename = f"report_{event['name'].replace(' ', '_')}_{today_str()}.pdf"
    return Response(
        pdf_buffer.read(), mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
