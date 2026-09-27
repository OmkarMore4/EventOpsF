def test_registration_page_loads_with_open_events(client):
    r = client.get("/register")
    assert r.status_code == 200
    assert b"TechFusion" in r.data  # event1 is ongoing, so it's selectable
    assert b"Cultural Fiesta" not in r.data  # event2 is a past/completed event


def test_registration_creates_pending_volunteer_not_a_working_login(client, db, seeded):
    r = client.post("/register", data={
        "event_id": str(seeded["event1_id"]), "name": "Pytest Registrant", "email": "pytest.reg@eventops.local",
        "phone": "1234567890", "domain": "Registration", "username": "pytest.reg", "password": "TestPass123",
    }, follow_redirects=True)
    assert b"sent to the event admin for approval" in r.data

    vol = db.volunteers.find_one({"email": "pytest.reg@eventops.local"})
    assert vol is not None
    assert vol["status"] == "pending"
    assert db.users.find_one({"email": "pytest.reg@eventops.local"}) is None  # no login yet

    # and logging in with those credentials should fail until approved
    r = client.post("/login", data={"username": "pytest.reg", "password": "TestPass123"}, follow_redirects=True)
    assert b"Invalid username or password" in r.data


def test_registration_rejects_duplicate_username(client, seeded):
    r = client.post("/register", data={
        "event_id": str(seeded["event1_id"]), "name": "Dup", "email": "dup2@eventops.local",
        "phone": "1", "domain": "Registration", "username": "rahul.verma", "password": "TestPass123",
    }, follow_redirects=True)
    assert b"already registered" in r.data


def test_registration_rejects_short_password(client, seeded):
    r = client.post("/register", data={
        "event_id": str(seeded["event1_id"]), "name": "Short Pw", "email": "shortpw@eventops.local",
        "phone": "1", "domain": "Registration", "username": "shortpw", "password": "abc",
    }, follow_redirects=True)
    assert b"at least 6 characters" in r.data


def test_admin_sees_pending_registration_in_queue(admin_client):
    r = admin_client.get("/admin/volunteers")
    assert r.status_code == 200
    assert b"Pending registration requests" in r.data
    assert b"Meera Kulkarni" in r.data


def test_admin_approve_creates_working_login(admin_client, client, db, seeded):
    pending = db.volunteers.find_one({"email": "meera.kulkarni@eventops.local", "status": "pending"})
    assert pending is not None

    r = admin_client.post(f"/admin/volunteers/{pending['_id']}/approve", data={"domain": "Hospitality"}, follow_redirects=True)
    assert b"was approved" in r.data

    approved = db.volunteers.find_one({"_id": pending["_id"]})
    assert approved["status"] == "active"
    user = db.users.find_one({"volunteer_id": pending["_id"]})
    assert user is not None
    assert user["username"] == "meera.kulkarni"

    # the approved volunteer can now actually log in
    admin_client.get("/logout")
    r = client.post("/login", data={"username": "meera.kulkarni", "password": seeded["volunteer_password"]}, follow_redirects=True)
    assert b"Dashboard" in r.data or r.status_code == 200


def test_admin_reject_deletes_pending_request(admin_client, db):
    pending = db.volunteers.find_one({"email": "meera.kulkarni@eventops.local", "status": "pending"})
    r = admin_client.post(f"/admin/volunteers/{pending['_id']}/reject", follow_redirects=True)
    assert b"declined" in r.data
    assert db.volunteers.find_one({"_id": pending["_id"]}) is None
    assert db.users.find_one({"email": "meera.kulkarni@eventops.local"}) is None


def test_volunteer_cannot_approve_registrations(volunteer_client_factory, db):
    pending = db.volunteers.find_one({"status": "pending"})
    c = volunteer_client_factory("rahul.verma")
    r = c.post(f"/admin/volunteers/{pending['_id']}/approve", data={})
    assert r.status_code == 403
