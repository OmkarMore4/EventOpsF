def test_volunteer_cannot_access_admin_dashboard(volunteer_client_factory):
    c = volunteer_client_factory("rahul.verma")
    r = c.get("/admin/dashboard")
    assert r.status_code == 403


def test_volunteer_cannot_access_admin_volunteer_management(volunteer_client_factory):
    c = volunteer_client_factory("rahul.verma")
    r = c.get("/admin/volunteers")
    assert r.status_code == 403


def test_admin_cannot_access_volunteer_only_routes(admin_client):
    r = admin_client.get("/volunteer/dashboard")
    assert r.status_code == 403


def test_volunteer_cannot_update_someone_elses_task(volunteer_client_factory, db):
    other_vol = db.volunteers.find_one({"email": "rahul.verma@eventops.local"})
    someone_elses_task = db.tasks.find_one({"assigned_to": other_vol["_id"]})
    assert someone_elses_task is not None

    c = volunteer_client_factory("neha.joshi")  # a different volunteer
    r = c.post(f"/volunteer/tasks/{someone_elses_task['_id']}/status", data={"status": "completed"})
    assert r.status_code == 404

    # confirm it truly wasn't changed
    unchanged = db.tasks.find_one({"_id": someone_elses_task["_id"]})
    assert unchanged["status"] == someone_elses_task["status"]


def test_volunteer_can_update_own_task(volunteer_client_factory, db):
    c = volunteer_client_factory("rahul.verma")
    vol = db.volunteers.find_one({"email": "rahul.verma@eventops.local"})
    own_task = db.tasks.find_one({"assigned_to": vol["_id"]})

    r = c.post(f"/volunteer/tasks/{own_task['_id']}/status", data={"status": "completed"}, follow_redirects=True)
    assert b"marked as completed" in r.data
    assert db.tasks.find_one({"_id": own_task["_id"]})["status"] == "completed"


def test_volunteer_can_report_and_view_own_issue(volunteer_client_factory, db):
    c = volunteer_client_factory("neha.joshi")
    r = c.post("/volunteer/issues/report", data={
        "title": "Pytest reported issue", "description": "Something needs attention",
        "category": "Other", "priority": "low",
    }, follow_redirects=True)
    assert b"Issue reported" in r.data

    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    issue = db.issues.find_one({"title": "Pytest reported issue"})
    assert issue["reported_by"] == vol["_id"]

    r = c.get("/volunteer/issues")
    assert b"Pytest reported issue" in r.data


def test_unauthenticated_user_redirected_not_500(client):
    for url in ["/admin/dashboard", "/volunteer/dashboard", "/admin/events", "/volunteer/tasks"]:
        r = client.get(url)
        assert r.status_code == 302
