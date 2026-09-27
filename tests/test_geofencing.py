from utils.geo import event_latlng, haversine_distance_meters, is_within_geofence


def test_haversine_zero_distance_for_identical_points():
    assert haversine_distance_meters(19.076, 72.8777, 19.076, 72.8777) == 0


def test_haversine_known_distance_is_reasonable():
    # Roughly Mumbai to Pune, ~120km apart as the crow flies.
    d = haversine_distance_meters(19.0760, 72.8777, 18.5204, 73.8567)
    assert 100_000 < d < 150_000


def test_is_within_geofence_boundary_cases():
    inside, dist = is_within_geofence(19.0760, 72.8777, 19.0760, 72.8777, 100)
    assert inside is True and dist == 0

    # ~0.001 degrees latitude is roughly 111 meters -- outside a 100m radius.
    inside, dist = is_within_geofence(19.0770, 72.8777, 19.0760, 72.8777, 100)
    assert inside is False
    assert dist > 100


def test_attendance_rejected_outside_geofence(volunteer_client_factory, db, seeded):
    c = volunteer_client_factory("neha.joshi")
    event = db.events.find_one({"_id": seeded["event1_id"]})
    lat, lng = event_latlng(event)

    r = c.post("/volunteer/attendance/mark", data={"latitude": lat + 0.05, "longitude": lng + 0.05}, follow_redirects=True)
    assert b"Attendance rejected" in r.data
    assert b"outside the" in r.data

    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    att = db.attendance.find_one({"volunteer_id": vol["_id"], "event_id": seeded["event1_id"]})
    assert att is not None
    assert att["check_in"] is None
    assert len(att["rejected_attempts"]) == 1
    assert att["rejected_attempts"][0]["distance_meters"] > event["geofence_radius"]


def test_attendance_accepted_inside_geofence(volunteer_client_factory, db, seeded):
    c = volunteer_client_factory("neha.joshi")
    event = db.events.find_one({"_id": seeded["event1_id"]})
    lat, lng = event_latlng(event)

    r = c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng}, follow_redirects=True)
    assert b"Checked in successfully" in r.data

    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    att = db.attendance.find_one({"volunteer_id": vol["_id"], "event_id": seeded["event1_id"]})
    assert att["check_in"] is not None
    assert att["check_in"]["lat"] == lat
    assert att["check_in"]["lng"] == lng
    assert att["check_in"]["distance_meters"] is not None
    assert att["check_in"]["distance_meters"] <= event["geofence_radius"]


def test_second_attempt_same_day_is_checkout_not_new_checkin(volunteer_client_factory, db, seeded):
    c = volunteer_client_factory("neha.joshi")
    event = db.events.find_one({"_id": seeded["event1_id"]})
    lat, lng = event_latlng(event)

    c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng})
    r = c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng}, follow_redirects=True)
    assert b"Checked out successfully" in r.data

    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    att = db.attendance.find_one({"volunteer_id": vol["_id"], "event_id": seeded["event1_id"]})
    assert att["check_in"] is not None
    assert att["check_out"] is not None


def test_third_attempt_same_day_is_a_no_op(volunteer_client_factory, db, seeded):
    c = volunteer_client_factory("neha.joshi")
    event = db.events.find_one({"_id": seeded["event1_id"]})
    lat, lng = event_latlng(event)

    c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng})
    c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng})
    r = c.post("/volunteer/attendance/mark", data={"latitude": lat, "longitude": lng}, follow_redirects=True)
    assert b"already completed" in r.data.lower()


def test_missing_gps_coordinates_are_rejected_cleanly(volunteer_client_factory):
    c = volunteer_client_factory("neha.joshi")
    r = c.post("/volunteer/attendance/mark", data={}, follow_redirects=True)
    assert b"read your location" in r.data.lower()


def test_admin_manual_override_bypasses_geofence(admin_client, db, seeded):
    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    r = admin_client.post("/admin/attendance/manual", data={"volunteer_id": str(vol["_id"])}, follow_redirects=True)
    assert b"manual entry" in r.data

    att = db.attendance.find_one({"volunteer_id": vol["_id"], "event_id": seeded["event1_id"]})
    assert att["check_in"]["method"] == "manual"
    assert att["check_in"]["lat"] is None
