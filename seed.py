"""
Seed EventOps with indexes + demo data.

Run directly:   python seed.py          (asks for confirmation if data exists)
Non-interactive: python seed.py --yes    (skips the confirmation prompt)

This script is intentionally self-contained (it makes its own MongoDB
connection rather than importing app.py) so it can be run before the Flask
app has ever started, and so it stays usable as a "reset my demo data"
utility any time.

All dates are computed relative to *today* (the day this script runs), so
the seeded event is always "in progress" and attendance can be marked
immediately, no matter when you set this project up.
"""

import math
import os
import random
import sys
from datetime import datetime, date, timedelta

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from werkzeug.security import generate_password_hash

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.qr import generate_qr_secret

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/eventops")
DB_NAME = os.environ.get("DB_NAME", "eventops")
DEMO_PASSWORD = "Demo@123"
ADMIN_PASSWORD = "Admin@123"


def jitter_point(lat, lng, max_meters):
    """A random point within max_meters of (lat, lng) — for realistic-looking demo GPS data."""
    if max_meters <= 0:
        return lat, lng
    deg_lat = max_meters / 111_320
    deg_lng = max_meters / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return lat + random.uniform(-deg_lat, deg_lat), lng + random.uniform(-deg_lng, deg_lng)


def haversine_meters(lat1, lon1, lat2, lon2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1, math.sqrt(a)))


def create_indexes(db):
    db.users.create_index([("username", ASCENDING)], unique=True)
    db.users.create_index([("email", ASCENDING)], unique=True)
    db.volunteers.create_index([("event_id", ASCENDING)])
    db.events.create_index([("location", "2dsphere")])
    db.attendance.create_index([("volunteer_id", ASCENDING), ("event_id", ASCENDING), ("date", ASCENDING)], unique=True)
    db.attendance.create_index([("event_id", ASCENDING), ("date", ASCENDING)])
    db.tasks.create_index([("event_id", ASCENDING)])
    db.tasks.create_index([("assigned_to", ASCENDING)])
    db.issues.create_index([("event_id", ASCENDING), ("status", ASCENDING)])
    db.equipment.create_index([("event_id", ASCENDING)])
    db.schedules.create_index([("event_id", ASCENDING), ("date", ASCENDING)])
    db.notifications.create_index([("event_id", ASCENDING), ("is_active", ASCENDING)])


def clear_collections(db):
    for name in ["users", "events", "volunteers", "attendance", "tasks", "issues",
                 "equipment", "schedules", "notifications"]:
        db[name].delete_many({})


def d(offset_days, fmt="%Y-%m-%d"):
    return (date.today() + timedelta(days=offset_days)).strftime(fmt)


def run_seed(db, verbose=True):
    def log(msg):
        if verbose:
            print(msg)

    create_indexes(db)
    clear_collections(db)
    log("✓ Indexes ensured, existing demo collections cleared.")

    # --- Admin -----------------------------------------------------------------
    db.users.insert_one({
        "username": "admin",
        "email": "admin@eventops.local",
        "password_hash": generate_password_hash(ADMIN_PASSWORD),
        "role": "admin",
        "name": "Event Admin",
        "volunteer_id": None,
        "created_at": datetime.now(),
        "last_login": None,
    })
    log("✓ Admin account created (admin / " + ADMIN_PASSWORD + ")")

    # --- Event 1: the main, currently-ongoing demo event ------------------------
    venue_lat, venue_lng = 19.0760, 72.8777
    event1_id = db.events.insert_one({
        "name": "TechFusion 2026 \u2014 Annual Technical Symposium",
        "description": (
            "A multi-day college technical symposium featuring workshops, a hackathon, "
            "a project expo and guest talks from industry speakers."
        ),
        "venue": "Central Convention Centre, Main Campus",
        "start_date": d(-1),
        "end_date": d(3),
        "location": {"type": "Point", "coordinates": [venue_lng, venue_lat]},
        "geofence_radius": 150,
        "domains": ["Registration", "Hospitality", "Technical Support", "Logistics", "Security", "Media & Documentation"],
        "created_by": "Event Admin",
        "created_at": datetime.now(),
        "qr_secret": generate_qr_secret(),
    }).inserted_id
    log("✓ Event created: TechFusion 2026 (" + d(-1) + " to " + d(3) + ")")

    # --- Event 2: a second, smaller event to demonstrate multi-event support ----
    event2_id = db.events.insert_one({
        "name": "Cultural Fiesta 2025 \u2014 Annual Cultural Fest",
        "description": "A two-day inter-college cultural festival with music, dance and drama competitions.",
        "venue": "Open Air Amphitheatre, Main Campus",
        "start_date": d(-60),
        "end_date": d(-58),
        "location": {"type": "Point", "coordinates": [72.8347, 18.9220]},
        "geofence_radius": 100,
        "domains": ["Stage Management", "Registration", "Hospitality"],
        "created_by": "Event Admin",
        "created_at": datetime.now() - timedelta(days=61),
        "qr_secret": generate_qr_secret(),
    }).inserted_id
    log("✓ Event created: Cultural Fiesta 2025 (past event, for multi-event demo)")

    # --- Volunteers for event 1 --------------------------------------------------
    volunteers_data = [
        ("Rahul Verma", "rahul.verma", "Registration", "9820011111"),
        ("Sneha Iyer", "sneha.iyer", "Hospitality", "9820022222"),
        ("Arjun Mehta", "arjun.mehta", "Technical Support", "9820033333"),
        ("Priya Nair", "priya.nair", "Logistics", "9820044444"),
        ("Karan Singh", "karan.singh", "Security", "9820055555"),
        ("Divya Rao", "divya.rao", "Media & Documentation", "9820066666"),
        ("Aditya Kulkarni", "aditya.kulkarni", "Technical Support", "9820077777"),
        ("Neha Joshi", "neha.joshi", "Registration", "9820088888"),
    ]
    responsibilities_by_domain = {
        "Registration": "Check in attendees, issue ID badges, and resolve registration desk queries.",
        "Hospitality": "Look after guest speakers and VIPs, and coordinate refreshments.",
        "Technical Support": "Set up and troubleshoot A/V equipment, Wi-Fi and demo systems.",
        "Logistics": "Handle signage, seating, transport and material movement across venues.",
        "Security": "Monitor entry points and escalate any safety concerns to the admin team.",
        "Media & Documentation": "Capture photos/videos and document sessions for the highlight reel.",
    }

    volunteers = {}
    for name, username, domain, phone in volunteers_data:
        vol_id = db.volunteers.insert_one({
            "event_id": event1_id,
            "name": name,
            "email": f"{username}@eventops.local",
            "phone": phone,
            "domain": domain,
            "responsibilities": responsibilities_by_domain[domain],
            "status": "active",
            "joined_date": d(-3),
            "created_at": datetime.now() - timedelta(days=3),
        }).inserted_id
        db.users.insert_one({
            "username": username,
            "email": f"{username}@eventops.local",
            "password_hash": generate_password_hash(DEMO_PASSWORD),
            "role": "volunteer",
            "name": name,
            "volunteer_id": vol_id,
            "created_at": datetime.now() - timedelta(days=3),
            "last_login": None,
        })
        volunteers[username] = vol_id
    log(f"✓ {len(volunteers_data)} volunteers created for TechFusion 2026 (all passwords: {DEMO_PASSWORD})")

    # --- Volunteers for event 2 (kept minimal) -----------------------------------
    for name, username, domain, phone in [
        ("Rohan Desai", "rohan.desai", "Stage Management", "9820099999"),
        ("Ananya Pillai", "ananya.pillai", "Registration", "9820000000"),
    ]:
        vol_id = db.volunteers.insert_one({
            "event_id": event2_id, "name": name, "email": f"{username}@eventops.local", "phone": phone,
            "domain": domain, "responsibilities": "", "status": "inactive", "joined_date": d(-62),
            "created_at": datetime.now() - timedelta(days=62),
        }).inserted_id
        db.users.insert_one({
            "username": username, "email": f"{username}@eventops.local",
            "password_hash": generate_password_hash(DEMO_PASSWORD), "role": "volunteer", "name": name,
            "volunteer_id": vol_id, "created_at": datetime.now() - timedelta(days=62), "last_login": None,
        })
    log("✓ 2 volunteers created for Cultural Fiesta 2025")

    # --- Tasks for event 1 --------------------------------------------------------
    tasks_data = [
        ("Set up registration desk", "rahul.verma", "Registration", "high", "completed"),
        ("Print participant ID badges", "rahul.verma", "Registration", "medium", "completed"),
        ("Verify visitor badges at hall entrance", "neha.joshi", "Registration", "medium", "completed"),
        ("Arrange welcome kits for guest speakers", "sneha.iyer", "Hospitality", "medium", "in-progress"),
        ("Coordinate guest speaker airport pickup", "sneha.iyer", "Hospitality", "high", "pending"),
        ("Test projectors in all seminar halls", "arjun.mehta", "Technical Support", "high", "completed"),
        ("Set up live-stream for keynote session", "aditya.kulkarni", "Technical Support", "high", "in-progress"),
        ("Arrange directional signage across campus", "priya.nair", "Logistics", "medium", "completed"),
        ("Coordinate transport for outstation guests", "priya.nair", "Logistics", "medium", "pending"),
        ("Monitor entry gate security checks", "karan.singh", "Security", "high", "in-progress"),
        ("Capture event photos for social media", "divya.rao", "Media & Documentation", "low", "pending"),
        ("Compile Day 1 highlight reel", "divya.rao", "Media & Documentation", "medium", "pending"),
    ]
    for title, username, domain, priority, status in tasks_data:
        history = [{"status": "pending", "time": datetime.now() - timedelta(days=2)}]
        if status != "pending":
            history.append({"status": status, "time": datetime.now() - timedelta(hours=random.randint(1, 20))})
        db.tasks.insert_one({
            "event_id": event1_id, "title": title, "description": f"{title}. Coordinate with the {domain} lead for any blockers.",
            "domain": domain, "priority": priority, "due_date": d(random.choice([0, 1, 2])),
            "assigned_to": volunteers[username], "assigned_to_name": dict((u, n) for n, u, *_ in volunteers_data)[username],
            "status": status, "status_history": history,
            "created_at": datetime.now() - timedelta(days=2), "updated_at": datetime.now() - timedelta(hours=2),
        })
    log(f"✓ {len(tasks_data)} tasks created and assigned")

    for title, username, domain, priority, status in [
        ("Coordinate stage lighting rehearsal", "rohan.desai", "Stage Management", "high", "completed"),
        ("Manage participant registration desk", "ananya.pillai", "Registration", "medium", "completed"),
    ]:
        vol_doc = db.volunteers.find_one({"event_id": event2_id, "email": f"{username}@eventops.local"})
        db.tasks.insert_one({
            "event_id": event2_id, "title": title, "description": title, "domain": domain, "priority": priority,
            "due_date": d(-59), "assigned_to": vol_doc["_id"], "assigned_to_name": vol_doc["name"],
            "status": status, "status_history": [{"status": "completed", "time": datetime.now() - timedelta(days=59)}],
            "created_at": datetime.now() - timedelta(days=60), "updated_at": datetime.now() - timedelta(days=59),
        })

    # --- Equipment for event 1 ----------------------------------------------------
    equipment_data = [
        ("Wireless Microphones", "Electronics", 10, 6, "Good"),
        ("Projectors", "Electronics", 5, 5, "Good"),
        ("Folding Tables", "Furniture", 20, 14, "Good"),
        ("Plastic Chairs", "Furniture", 150, 120, "Good"),
        ("Walkie-Talkies", "Electronics", 12, 10, "Good"),
        ("First Aid Kits", "Safety", 6, 4, "Good"),
        ("Extension Cords", "Electronics", 25, 20, "Under Repair"),
        ("Banner Stands", "Signage", 8, 8, "Damaged"),
    ]
    for name, category, total, assigned, condition in equipment_data:
        db.equipment.insert_one({
            "event_id": event1_id, "name": name, "category": category, "total_quantity": total,
            "assigned_quantity": assigned, "condition": condition,
            "assigned_to": random.choice(["Technical Support", "Logistics", "Registration", ""]),
            "notes": "", "created_at": datetime.now() - timedelta(days=3), "updated_at": datetime.now() - timedelta(hours=5),
        })
    log(f"✓ {len(equipment_data)} equipment items added to inventory")

    # --- Schedule for event 1 ------------------------------------------------------
    schedule_data = [
        (-1, "Opening Ceremony", "09:00", "10:00", "Main Auditorium", "Session"),
        (-1, "Keynote: The Future of AI", "10:15", "11:15", "Main Auditorium", "Session"),
        (-1, "Lunch Break", "13:00", "14:00", "Cafeteria", "Break"),
        (0, "Hackathon Kickoff Briefing", "09:00", "09:30", "Innovation Lab", "Briefing"),
        (0, "Hackathon Coding Round", "09:30", "18:00", "Innovation Lab", "Session"),
        (1, "Project Expo", "10:00", "13:00", "Exhibition Hall", "Session"),
        (2, "Closing Ceremony & Prizes", "16:00", "17:00", "Main Auditorium", "Session"),
    ]
    for offset, title, start_time, end_time, venue, item_type in schedule_data:
        db.schedules.insert_one({
            "event_id": event1_id, "title": title, "description": "", "date": d(offset),
            "start_time": start_time, "end_time": end_time, "venue": venue, "type": item_type,
            "created_at": datetime.now() - timedelta(days=3),
        })
    log(f"✓ {len(schedule_data)} schedule items added")

    # --- Issues for event 1 ---------------------------------------------------------
    issues_data = [
        ("Projector not working in Hall B", "The main projector in Hall B lost signal midway through a session.",
         "arjun.mehta", "Equipment", "high", "resolved", "Replaced with a spare projector from AV storage."),
        ("Shortage of extension cords at Stall 12", "Exhibitors at Stall 12 need two more extension cords.",
         "priya.nair", "Logistics", "medium", "in-progress", "Procurement notified, more cords arriving by 3 PM."),
        ("Water cooler empty near registration desk", "The water cooler near the main registration desk is empty.",
         "sneha.iyer", "Facilities", "low", "open", ""),
        ("Unrecognised person near speaker green room", "Someone without a badge tried to enter the speaker green room.",
         "karan.singh", "Security", "high", "open", ""),
    ]
    for title, description, username, category, priority, status, response in issues_data:
        vol_doc = db.volunteers.find_one({"_id": volunteers[username]})
        doc = {
            "event_id": event1_id, "reported_by": vol_doc["_id"], "reported_by_name": vol_doc["name"],
            "title": title, "description": description, "category": category, "priority": priority,
            "status": status, "admin_response": response, "resolved_by": None, "resolved_at": None,
            "created_at": datetime.now() - timedelta(hours=random.randint(2, 30)),
        }
        if status == "resolved":
            doc["resolved_by"] = "Event Admin"
            doc["resolved_at"] = datetime.now() - timedelta(hours=1)
        db.issues.insert_one(doc)
    log(f"✓ {len(issues_data)} issues logged")

    # --- Notifications for event 1 ---------------------------------------------------
    notifications_data = [
        ("Welcome to TechFusion 2026!",
         "Please collect your ID badge and volunteer t-shirt from the registration desk before your shift begins. Thank you for volunteering!",
         "normal"),
        ("Lunch break timing updated",
         "Lunch break has been shifted to 1:00 PM \u2013 2:00 PM for Technical Support and Logistics volunteers.",
         "important"),
        ("Security briefing at Gate 2",
         "All Security volunteers must attend a short briefing at Gate 2, 30 minutes before gates open each day.",
         "urgent"),
        ("Great work, Day 1!",
         "Attendance and task completion numbers look excellent so far \u2014 keep up the great work, everyone!",
         "normal"),
    ]
    for title, message, priority in notifications_data:
        db.notifications.insert_one({
            "event_id": event1_id, "title": title, "message": message, "priority": priority,
            "is_active": True, "created_by": "Event Admin", "created_at": datetime.now() - timedelta(hours=random.randint(1, 20)),
        })
    log(f"✓ {len(notifications_data)} announcements posted")

    # --- Attendance: yesterday (full day) + today (partial, in progress) ------------
    present_yesterday = ["rahul.verma", "sneha.iyer", "arjun.mehta", "priya.nair", "karan.singh", "divya.rao"]
    for username in present_yesterday:
        in_pt = jitter_point(venue_lat, venue_lng, 60)
        out_pt = jitter_point(venue_lat, venue_lng, 60)
        in_dist = haversine_meters(*in_pt, venue_lat, venue_lng)
        out_dist = haversine_meters(*out_pt, venue_lat, venue_lng)
        yesterday_dt = datetime.now() - timedelta(days=1)
        db.attendance.insert_one({
            "volunteer_id": volunteers[username],
            "volunteer_name": dict((u, n) for n, u, *_ in volunteers_data)[username],
            "event_id": event1_id, "date": d(-1),
            "check_in": {
                "time": yesterday_dt.replace(hour=8, minute=random.randint(45, 59)),
                "lat": in_pt[0], "lng": in_pt[1], "distance_meters": round(in_dist, 1), "method": "gps",
            },
            "check_out": {
                "time": yesterday_dt.replace(hour=18, minute=random.randint(0, 30)),
                "lat": out_pt[0], "lng": out_pt[1], "distance_meters": round(out_dist, 1), "method": "gps",
            },
            "rejected_attempts": [], "created_at": yesterday_dt, "updated_at": yesterday_dt,
        })

    present_today = ["rahul.verma", "sneha.iyer", "arjun.mehta"]
    for username in present_today:
        in_pt = jitter_point(venue_lat, venue_lng, 60)
        in_dist = haversine_meters(*in_pt, venue_lat, venue_lng)
        today_dt = datetime.now()
        db.attendance.insert_one({
            "volunteer_id": volunteers[username],
            "volunteer_name": dict((u, n) for n, u, *_ in volunteers_data)[username],
            "event_id": event1_id, "date": d(0),
            "check_in": {
                "time": today_dt.replace(hour=min(today_dt.hour, 9) if today_dt.hour >= 9 else today_dt.hour,
                                          minute=today_dt.minute if today_dt.hour >= 9 else today_dt.minute),
                "lat": in_pt[0], "lng": in_pt[1], "distance_meters": round(in_dist, 1), "method": "gps",
            },
            "check_out": None, "rejected_attempts": [], "created_at": today_dt, "updated_at": today_dt,
        })
    log(f"✓ Attendance seeded for yesterday (6 present, 2 absent) and today ({len(present_today)} checked in so far)")

    # --- One pending self-registration, so the admin approval queue has something to show ----
    db.volunteers.insert_one({
        "event_id": event1_id, "name": "Meera Kulkarni", "email": "meera.kulkarni@eventops.local",
        "phone": "9820012345", "domain": "Hospitality", "responsibilities": "", "status": "pending",
        "joined_date": d(0), "pending_username": "meera.kulkarni",
        "pending_password_hash": generate_password_hash(DEMO_PASSWORD),
        "created_at": datetime.now() - timedelta(hours=3),
    })
    log("✓ 1 pending volunteer registration seeded (visible in the admin approval queue)")

    return {
        "admin_username": "admin",
        "admin_password": ADMIN_PASSWORD,
        "volunteer_password": DEMO_PASSWORD,
        "event1_id": event1_id,
        "event2_id": event2_id,
    }


def main():
    non_interactive = "--yes" in sys.argv or "-y" in sys.argv

    print(f"Connecting to MongoDB at {MONGO_URI} (database: {DB_NAME}) ...")
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"✗ Could not connect to MongoDB: {exc}")
        print("  Make sure MongoDB is running and MONGO_URI in .env is correct, then try again.")
        sys.exit(1)

    db = client[DB_NAME]

    if db.users.count_documents({}) > 0 and not non_interactive:
        answer = input(
            "This database already has data. Seeding will ERASE existing users, events, "
            "volunteers, tasks, attendance, issues, equipment, schedules and notifications "
            "and replace them with fresh demo data. Continue? [y/N]: "
        )
        if answer.strip().lower() != "y":
            print("Cancelled. No changes were made.")
            sys.exit(0)

    print("\nSeeding demo data...\n")
    result = run_seed(db)

    print("\n" + "=" * 60)
    print("EventOps demo data is ready!")
    print("=" * 60)
    print(f"  Admin login:      admin / {result['admin_password']}")
    print(f"  Volunteer login:  e.g. rahul.verma / {result['volunteer_password']}")
    print("  (see README.md for the full list of demo volunteer usernames)")
    print("=" * 60)


if __name__ == "__main__":
    main()
