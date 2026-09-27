def test_admin_can_view_qr_code_page(admin_client, seeded):
    r = admin_client.get(f"/admin/events/{seeded['event1_id']}/qr")
    assert r.status_code == 200
    assert b"data:image/png;base64" in r.data


def test_qr_scan_with_valid_secret_shows_confirmation(volunteer_client_factory, db, seeded):
    event = db.events.find_one({"_id": seeded["event1_id"]})
    c = volunteer_client_factory("neha.joshi")
    r = c.get(f"/volunteer/attendance/qr/{seeded['event1_id']}/{event['qr_secret']}")
    assert r.status_code == 200
    assert b"Check in now" in r.data


def test_qr_scan_with_wrong_secret_is_rejected(volunteer_client_factory, seeded):
    c = volunteer_client_factory("neha.joshi")
    r = c.get(f"/volunteer/attendance/qr/{seeded['event1_id']}/totally-wrong-secret", follow_redirects=True)
    assert b"invalid" in r.data.lower()


def test_qr_checkin_records_attendance_without_gps(volunteer_client_factory, db, seeded):
    event = db.events.find_one({"_id": seeded["event1_id"]})
    c = volunteer_client_factory("neha.joshi")
    r = c.post(f"/volunteer/attendance/qr/{seeded['event1_id']}/{event['qr_secret']}", follow_redirects=True)
    assert b"via the venue QR code" in r.data

    vol = db.volunteers.find_one({"email": "neha.joshi@eventops.local"})
    att = db.attendance.find_one({"volunteer_id": vol["_id"], "event_id": seeded["event1_id"]})
    assert att["check_in"]["method"] == "qr"
    assert att["check_in"]["lat"] is None  # no GPS involved in this path


def test_regenerating_qr_code_invalidates_the_old_one(admin_client, volunteer_client_factory, db, seeded):
    old_event = db.events.find_one({"_id": seeded["event1_id"]})
    old_secret = old_event["qr_secret"]

    admin_client.post(f"/admin/events/{seeded['event1_id']}/qr/regenerate", follow_redirects=True)
    admin_client.get("/logout")  # admin_client and volunteer_client_factory share one session

    new_event = db.events.find_one({"_id": seeded["event1_id"]})
    assert new_event["qr_secret"] != old_secret

    c = volunteer_client_factory("neha.joshi")
    r = c.get(f"/volunteer/attendance/qr/{seeded['event1_id']}/{old_secret}", follow_redirects=True)
    assert b"invalid" in r.data.lower()


def test_qr_checkin_respects_event_date_range(volunteer_client_factory, db, seeded):
    """A QR scan for an event outside its date range should still be rejected,
    same as the GPS path — the QR method skips the geofence, not the date check."""
    event2 = db.events.find_one({"_id": seeded["event2_id"]})  # a past, completed event

    c = volunteer_client_factory("rohan.desai")  # a volunteer on event2
    r = c.post(f"/volunteer/attendance/qr/{seeded['event2_id']}/{event2['qr_secret']}", follow_redirects=True)
    assert b"can only be marked during the event dates" in r.data
