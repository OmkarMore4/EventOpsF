def test_dashboard_loads_with_seeded_event(admin_client):
    r = admin_client.get("/admin/dashboard")
    assert r.status_code == 200
    assert b"TechFusion" in r.data
    assert b"Present right now" in r.data


def test_dashboard_live_endpoint_returns_current_stats(admin_client, seeded):
    r = admin_client.get("/admin/dashboard/live")
    assert r.status_code == 200
    assert r.mimetype == "application/json"
    data = r.get_json()
    assert "present_today" in data and "total_volunteers" in data
    assert "recent_activity" in data
    assert isinstance(data["recent_activity"], list)


def test_dashboard_live_reflects_new_checkin(admin_client, volunteer_client_factory, db, seeded):
    from utils.geo import event_latlng
    event = db.events.find_one({"_id": seeded["event1_id"]})
    lat, lng = event_latlng(event)

    before = admin_client.get("/admin/dashboard/live").get_json()

    admin_client.get("/logout")
    c = volunteer_client_factory("neha.joshi")
    c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng})
    c.get("/logout")

    admin_client.post("/login", data={"username": "admin", "password": seeded["admin_password"]})
    after = admin_client.get("/admin/dashboard/live").get_json()

    assert after["present_today"] == before["present_today"] + 1
    assert any(item["volunteer_name"] == "Neha Joshi" for item in after["recent_activity"])


def test_event_create_persists_geojson_location(admin_client, db):
    r = admin_client.post("/admin/events/create", data={
        "name": "Pytest Event", "description": "A test event", "venue": "Test Ground",
        "start_date": "2026-01-01", "end_date": "2026-01-05",
        "latitude": "19.10", "longitude": "72.90", "geofence_radius": "80",
        "domains": "Registration, Logistics",
    }, follow_redirects=True)
    assert b"was created" in r.data

    ev = db.events.find_one({"name": "Pytest Event"})
    assert ev is not None
    assert ev["location"]["type"] == "Point"
    assert ev["location"]["coordinates"] == [72.90, 19.10]  # GeoJSON is [lng, lat]
    assert ev["geofence_radius"] == 80
    assert ev["domains"] == ["Registration", "Logistics"]


def test_event_create_validates_required_fields(admin_client, db):
    r = admin_client.post("/admin/events/create", data={"name": ""}, follow_redirects=True)
    assert b"required" in r.data.lower()
    assert db.events.find_one({"name": ""}) is None


def test_volunteer_create_links_a_user_account(admin_client, db):
    admin_client.post("/admin/volunteers/create", data={
        "name": "Pytest Volunteer", "email": "pytest.vol@eventops.local", "phone": "1234567890",
        "domain": "Registration", "responsibilities": "Testing",
        "username": "pytest.vol", "password": "TestPass123",
    }, follow_redirects=True)

    vol = db.volunteers.find_one({"email": "pytest.vol@eventops.local"})
    assert vol is not None
    user = db.users.find_one({"volunteer_id": vol["_id"]})
    assert user is not None
    assert user["role"] == "volunteer"
    assert user["username"] == "pytest.vol"


def test_volunteer_create_rejects_duplicate_username(admin_client, db):
    r = admin_client.post("/admin/volunteers/create", data={
        "name": "Duplicate", "email": "dup@eventops.local", "phone": "1",
        "domain": "Registration", "responsibilities": "",
        "username": "rahul.verma",  # already exists from seed data
        "password": "TestPass123",
    }, follow_redirects=True)
    assert b"already exists" in r.data


def test_task_create_assigns_to_volunteer(admin_client, db, seeded):
    vol = db.volunteers.find_one({"email": "rahul.verma@eventops.local"})
    r = admin_client.post("/admin/tasks/create", data={
        "title": "Pytest Task", "description": "desc", "assigned_to": str(vol["_id"]),
        "domain": "Registration", "priority": "high", "due_date": "2026-01-02",
    }, follow_redirects=True)
    assert b"assigned to Rahul Verma" in r.data

    task = db.tasks.find_one({"title": "Pytest Task"})
    assert task["assigned_to"] == vol["_id"]
    assert task["status"] == "pending"


def test_equipment_create_and_delete(admin_client, db):
    admin_client.post("/admin/equipment/create", data={
        "name": "Pytest Tent", "category": "Structure", "total_quantity": "5",
        "assigned_quantity": "2", "condition": "Good", "assigned_to": "", "notes": "",
    }, follow_redirects=True)
    item = db.equipment.find_one({"name": "Pytest Tent"})
    assert item is not None

    r = admin_client.post(f"/admin/equipment/{item['_id']}/delete", follow_redirects=True)
    assert b"removed from inventory" in r.data
    assert db.equipment.find_one({"name": "Pytest Tent"}) is None


def test_issue_resolution_updates_status_and_response(admin_client, db):
    issue = db.issues.find_one({"status": "open"})
    r = admin_client.post(f"/admin/issues/{issue['_id']}/update", data={
        "status": "resolved", "admin_response": "Fixed via pytest",
    }, follow_redirects=True)
    assert b"marked as resolved" in r.data

    updated = db.issues.find_one({"_id": issue["_id"]})
    assert updated["status"] == "resolved"
    assert updated["admin_response"] == "Fixed via pytest"
    assert updated["resolved_at"] is not None


def test_attendance_csv_export(admin_client):
    r = admin_client.get("/admin/reports/attendance/export")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert b"Volunteer" in r.data and b"Check-in time" in r.data


def test_event_report_pdf_export(admin_client):
    r = admin_client.get("/admin/reports/pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data[:4] == b"%PDF"  # a real PDF file, not an error page
    assert len(r.data) > 1000


def test_task_csv_export(admin_client):
    r = admin_client.get("/admin/reports/tasks/export")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert b"Title" in r.data


def test_event_delete_cascades_related_data(admin_client, db, seeded):
    event2_id = seeded["event2_id"]
    assert db.volunteers.count_documents({"event_id": event2_id}) > 0

    r = admin_client.post(f"/admin/events/{event2_id}/delete", follow_redirects=True)
    assert b"deleted" in r.data
    assert db.events.find_one({"_id": event2_id}) is None
    assert db.volunteers.count_documents({"event_id": event2_id}) == 0
    assert db.tasks.count_documents({"event_id": event2_id}) == 0


def test_nonexistent_event_edit_returns_404(admin_client):
    r = admin_client.get("/admin/events/000000000000000000000000/edit")
    assert r.status_code == 404
