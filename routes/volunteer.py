"""
Volunteer routes.

The most important flow here is mark_attendance(): the browser sends the
GPS coordinates it captured via navigator.geolocation, the server computes
the Haversine distance to the event's configured center, and only accepts
the check-in/out if that distance is within the event's geofence_radius.
The client also does a quick distance pre-check for instant feedback
(see static/js/attendance.js), but this server-side check is the one that
actually decides whether attendance is recorded — never trust the client.
"""

from datetime import datetime

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user

from extensions import db
from utils.decorators import volunteer_required
from utils.geo import event_latlng, is_within_geofence, valid_coordinates
from utils.helpers import to_object_id, today_str, parse_float

volunteer_bp = Blueprint("volunteer", __name__, url_prefix="/volunteer")


def get_current_volunteer():
    if not current_user.volunteer_id:
        return None
    return db.volunteers.find_one({"_id": to_object_id(current_user.volunteer_id)})


# ---------------------------------------------------------------------------
# Dashboard & profile
# ---------------------------------------------------------------------------

@volunteer_bp.route("/dashboard")
@volunteer_required
def dashboard():
    volunteer = get_current_volunteer()
    if not volunteer:
        return render_template("volunteer/dashboard.html", volunteer=None, event=None)

    event = db.events.find_one({"_id": volunteer["event_id"]})
    today = today_str()
    today_attendance = None
    upcoming_schedule = None
    recent_notifications = []

    if event:
        today_attendance = db.attendance.find_one(
            {"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today}
        )
        upcoming_schedule = db.schedules.find_one(
            {"event_id": event["_id"], "date": {"$gte": today}}, sort=[("date", 1), ("start_time", 1)]
        )
        recent_notifications = list(
            db.notifications.find({"event_id": event["_id"], "is_active": True}).sort("created_at", -1).limit(3)
        )

    task_total = db.tasks.count_documents({"assigned_to": volunteer["_id"]})
    task_completed = db.tasks.count_documents({"assigned_to": volunteer["_id"], "status": "completed"})

    return render_template(
        "volunteer/dashboard.html", volunteer=volunteer, event=event, today_attendance=today_attendance,
        task_total=task_total, task_completed=task_completed, task_pending=task_total - task_completed,
        upcoming_schedule=upcoming_schedule, recent_notifications=recent_notifications,
    )


@volunteer_bp.route("/profile")
@volunteer_required
def profile():
    volunteer = get_current_volunteer()
    if not volunteer:
        return render_template("volunteer/profile.html", volunteer=None, event=None)
    event = db.events.find_one({"_id": volunteer["event_id"]})

    task_total = db.tasks.count_documents({"assigned_to": volunteer["_id"]})
    task_completed = db.tasks.count_documents({"assigned_to": volunteer["_id"], "status": "completed"})
    attendance_days = db.attendance.count_documents({"volunteer_id": volunteer["_id"], "check_in": {"$ne": None}})

    return render_template(
        "volunteer/profile.html", volunteer=volunteer, event=event,
        task_total=task_total, task_completed=task_completed, attendance_days=attendance_days,
    )


# ---------------------------------------------------------------------------
# Attendance (geofenced)
# ---------------------------------------------------------------------------

@volunteer_bp.route("/attendance")
@volunteer_required
def attendance_page():
    volunteer = get_current_volunteer()
    if not volunteer:
        flash("Your account isn't linked to a volunteer profile yet. Contact your event admin.", "error")
        return render_template("volunteer/attendance.html", volunteer=None, event=None, history=[])

    event = db.events.find_one({"_id": volunteer["event_id"]})
    today = today_str()
    today_attendance = None
    within_event_dates = False
    lat, lng = None, None

    if event:
        today_attendance = db.attendance.find_one(
            {"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today}
        )
        within_event_dates = event.get("start_date", "") <= today <= event.get("end_date", "9999-12-31")
        lat, lng = event_latlng(event)

    history = list(db.attendance.find({"volunteer_id": volunteer["_id"]}).sort("date", -1).limit(30))

    return render_template(
        "volunteer/attendance.html", volunteer=volunteer, event=event, today_attendance=today_attendance,
        history=history, event_lat=lat, event_lng=lng, within_event_dates=within_event_dates,
    )


@volunteer_bp.route("/attendance/mark", methods=["POST"])
@volunteer_required
def mark_attendance():
    volunteer = get_current_volunteer()
    if not volunteer:
        flash("Your account isn't linked to a volunteer profile yet. Contact your event admin.", "error")
        return redirect(url_for("volunteer.attendance_page"))

    event = db.events.find_one({"_id": volunteer["event_id"]})
    if not event:
        flash("No event is associated with your profile yet.", "error")
        return redirect(url_for("volunteer.attendance_page"))

    today = today_str()
    if not (event.get("start_date", "") <= today <= event.get("end_date", "9999-12-31")):
        flash(
            f"Attendance can only be marked during the event dates "
            f"({event.get('start_date')} to {event.get('end_date')}).", "error",
        )
        return redirect(url_for("volunteer.attendance_page"))

    lat = parse_float(request.form.get("latitude"))
    lng = parse_float(request.form.get("longitude"))

    if lat is None or lng is None or not valid_coordinates(lat, lng):
        flash("We couldn't read your location. Please allow location access in your browser and try again.", "error")
        return redirect(url_for("volunteer.attendance_page"))

    event_lat, event_lng = event_latlng(event)
    radius = event.get("geofence_radius", 100)
    inside, distance = is_within_geofence(lat, lng, event_lat, event_lng, radius)

    existing = db.attendance.find_one({"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today})

    if existing and existing.get("check_in") and existing.get("check_out"):
        flash("You've already completed attendance for today.", "info")
        return redirect(url_for("volunteer.attendance_page"))

    action = "check_in" if not (existing and existing.get("check_in")) else "check_out"

    if not inside:
        rejected_entry = {
            "type": "check-in" if action == "check_in" else "check-out",
            "time": datetime.now(), "lat": lat, "lng": lng, "distance_meters": round(distance, 1),
        }
        if existing:
            db.attendance.update_one(
                {"_id": existing["_id"]},
                {"$push": {"rejected_attempts": rejected_entry}, "$set": {"updated_at": datetime.now()}},
            )
        else:
            db.attendance.insert_one({
                "volunteer_id": volunteer["_id"], "volunteer_name": volunteer["name"], "event_id": event["_id"],
                "date": today, "check_in": None, "check_out": None, "rejected_attempts": [rejected_entry],
                "created_at": datetime.now(), "updated_at": datetime.now(),
            })
        flash(
            f"Attendance rejected — you're about {round(distance)}m from the venue, which is outside the "
            f"{radius}m allowed radius. Move closer and try again.", "error",
        )
        return redirect(url_for("volunteer.attendance_page"))

    entry = {"time": datetime.now(), "lat": lat, "lng": lng, "distance_meters": round(distance, 1), "method": "gps"}

    if existing:
        db.attendance.update_one({"_id": existing["_id"]}, {"$set": {action: entry, "updated_at": datetime.now()}})
    else:
        db.attendance.insert_one({
            "volunteer_id": volunteer["_id"], "volunteer_name": volunteer["name"], "event_id": event["_id"],
            "date": today, "check_in": entry if action == "check_in" else None,
            "check_out": entry if action == "check_out" else None, "rejected_attempts": [],
            "created_at": datetime.now(), "updated_at": datetime.now(),
        })

    verb = "Checked in" if action == "check_in" else "Checked out"
    flash(f"{verb} successfully — you're about {round(distance)}m from the venue, within the {radius}m geofence.", "success")
    return redirect(url_for("volunteer.attendance_page"))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@volunteer_bp.route("/tasks")
@volunteer_required
def tasks_page():
    volunteer = get_current_volunteer()
    if not volunteer:
        return render_template("volunteer/tasks.html", volunteer=None, tasks=[])
    tasks = list(db.tasks.find({"assigned_to": volunteer["_id"]}).sort("created_at", -1))
    return render_template("volunteer/tasks.html", volunteer=volunteer, tasks=tasks)


@volunteer_bp.route("/tasks/<task_id>/status", methods=["POST"])
@volunteer_required
def update_task_status(task_id):
    volunteer = get_current_volunteer()
    oid = to_object_id(task_id)
    task = db.tasks.find_one({"_id": oid}) if oid else None

    if not task or not volunteer or task.get("assigned_to") != volunteer["_id"]:
        abort(404)

    new_status = (request.form.get("status") or "").strip()
    if new_status not in ("pending", "in-progress", "completed"):
        flash("Invalid status.", "error")
        return redirect(url_for("volunteer.tasks_page"))

    db.tasks.update_one(
        {"_id": oid},
        {
            "$set": {"status": new_status, "updated_at": datetime.now()},
            "$push": {"status_history": {"status": new_status, "time": datetime.now()}},
        },
    )
    flash(f"Task \u201c{task['title']}\u201d marked as {new_status.replace('-', ' ')}.", "success")
    return redirect(url_for("volunteer.tasks_page"))


# ---------------------------------------------------------------------------
# Issues
# ---------------------------------------------------------------------------

@volunteer_bp.route("/issues")
@volunteer_required
def issues_page():
    volunteer = get_current_volunteer()
    if not volunteer:
        return render_template("volunteer/issues.html", volunteer=None, issues=[])
    issues = list(db.issues.find({"reported_by": volunteer["_id"]}).sort("created_at", -1))
    return render_template("volunteer/issues.html", volunteer=volunteer, issues=issues)


@volunteer_bp.route("/issues/report", methods=["POST"])
@volunteer_required
def report_issue():
    volunteer = get_current_volunteer()
    if not volunteer:
        flash("Your account isn't linked to a volunteer profile.", "error")
        return redirect(url_for("volunteer.issues_page"))

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "Other").strip()
    priority = (request.form.get("priority") or "medium").strip()

    if not title or not description:
        flash("Please provide both a title and a description.", "error")
        return redirect(url_for("volunteer.issues_page"))

    db.issues.insert_one({
        "event_id": volunteer["event_id"], "reported_by": volunteer["_id"], "reported_by_name": volunteer["name"],
        "title": title, "description": description, "category": category or "Other",
        "priority": priority if priority in ("low", "medium", "high") else "medium",
        "status": "open", "admin_response": "", "resolved_by": None, "resolved_at": None,
        "created_at": datetime.now(),
    })
    flash("Issue reported — the event admin has been notified.", "success")
    return redirect(url_for("volunteer.issues_page"))


# ---------------------------------------------------------------------------
# Schedule & announcements
# ---------------------------------------------------------------------------

@volunteer_bp.route("/schedule")
@volunteer_required
def schedule_page():
    volunteer = get_current_volunteer()
    if not volunteer:
        return render_template("volunteer/schedule.html", volunteer=None, event=None, items=[], notifications=[])

    event = db.events.find_one({"_id": volunteer["event_id"]})
    items, notifications = [], []
    if event:
        items = list(db.schedules.find({"event_id": event["_id"]}).sort([("date", 1), ("start_time", 1)]))
        notifications = list(
            db.notifications.find({"event_id": event["_id"], "is_active": True}).sort("created_at", -1)
        )

    return render_template(
        "volunteer/schedule.html", volunteer=volunteer, event=event, items=items, notifications=notifications
    )


# ---------------------------------------------------------------------------
# QR backup check-in
#
# A venue-printed QR code (generated on the admin side, see routes/admin.py)
# encodes a URL containing the event's id and a random per-event secret.
# Scanning it with a phone's normal camera app opens that URL in the
# browser — reaching it at all is treated as proof of physical presence, so
# this path skips the GPS geofence check entirely. It's meant as a fallback
# for when a volunteer's GPS isn't cooperating (common indoors), not a
# replacement for the primary flow.
# ---------------------------------------------------------------------------

def _validate_qr_scan(event_id, secret):
    """Returns (volunteer, event) if the scanned link is valid, else (None, None) with a flash message set."""
    volunteer = get_current_volunteer()
    if not volunteer:
        flash("Your account isn't linked to a volunteer profile.", "error")
        return None, None

    oid = to_object_id(event_id)
    event = db.events.find_one({"_id": oid}) if oid else None
    if not event or not secret or event.get("qr_secret") != secret:
        flash(
            "This check-in code is invalid, or the admin has since replaced it with a new one. "
            "Ask your event admin for the current code.", "error",
        )
        return None, None

    if volunteer["event_id"] != event["_id"]:
        flash("This check-in code belongs to a different event than the one you're assigned to.", "error")
        return None, None

    return volunteer, event


@volunteer_bp.route("/attendance/qr/<event_id>/<secret>", methods=["GET"])
@volunteer_required
def qr_checkin_confirm(event_id, secret):
    volunteer, event = _validate_qr_scan(event_id, secret)
    if not volunteer:
        return redirect(url_for("volunteer.attendance_page"))

    today = today_str()
    existing = db.attendance.find_one({"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today})
    if existing and existing.get("check_in") and existing.get("check_out"):
        flash("You've already completed attendance for today.", "info")
        return redirect(url_for("volunteer.attendance_page"))

    action_label = "Check in" if not (existing and existing.get("check_in")) else "Check out"
    return render_template(
        "volunteer/qr_checkin.html", event=event, action_label=action_label, event_id=event_id, secret=secret
    )


@volunteer_bp.route("/attendance/qr/<event_id>/<secret>", methods=["POST"])
@volunteer_required
def qr_checkin_submit(event_id, secret):
    volunteer, event = _validate_qr_scan(event_id, secret)
    if not volunteer:
        return redirect(url_for("volunteer.attendance_page"))

    today = today_str()
    if not (event.get("start_date", "") <= today <= event.get("end_date", "9999-12-31")):
        flash(
            f"Attendance can only be marked during the event dates "
            f"({event.get('start_date')} to {event.get('end_date')}).", "error",
        )
        return redirect(url_for("volunteer.attendance_page"))

    existing = db.attendance.find_one({"volunteer_id": volunteer["_id"], "event_id": event["_id"], "date": today})
    if existing and existing.get("check_in") and existing.get("check_out"):
        flash("You've already completed attendance for today.", "info")
        return redirect(url_for("volunteer.attendance_page"))

    action = "check_in" if not (existing and existing.get("check_in")) else "check_out"
    entry = {"time": datetime.now(), "lat": None, "lng": None, "distance_meters": None, "method": "qr"}

    if existing:
        db.attendance.update_one({"_id": existing["_id"]}, {"$set": {action: entry, "updated_at": datetime.now()}})
    else:
        db.attendance.insert_one({
            "volunteer_id": volunteer["_id"], "volunteer_name": volunteer["name"], "event_id": event["_id"],
            "date": today, "check_in": entry if action == "check_in" else None,
            "check_out": entry if action == "check_out" else None, "rejected_attempts": [],
            "created_at": datetime.now(), "updated_at": datetime.now(),
        })

    verb = "Checked in" if action == "check_in" else "Checked out"
    flash(f"{verb} successfully via the venue QR code.", "success")
    return redirect(url_for("volunteer.attendance_page"))
