"""
Geofencing helpers.

EventOps verifies attendance with a straightforward point-radius geofence:
the great-circle (Haversine) distance between the volunteer's reported GPS
position and the event's configured center is compared against the event's
allowed radius. Event locations are also stored as GeoJSON Points with a
2dsphere index (see seed.py / routes/admin.py) so the same data can be
queried with MongoDB's native geospatial operators if the project is
extended later — but the authoritative check on every attendance attempt is
this deterministic, dependency-free calculation, so it behaves identically
regardless of what indexes exist.
"""

import math

EARTH_RADIUS_METERS = 6_371_000


def haversine_distance_meters(lat1, lon1, lat2, lon2):
    """Great-circle distance in meters between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.asin(min(1, math.sqrt(a)))
    return EARTH_RADIUS_METERS * c


def is_within_geofence(volunteer_lat, volunteer_lon, event_lat, event_lon, radius_meters):
    """Returns (is_inside: bool, distance_meters: float)."""
    distance = haversine_distance_meters(volunteer_lat, volunteer_lon, event_lat, event_lon)
    return distance <= radius_meters, distance


def event_latlng(event):
    """
    Extract (lat, lng) floats from an event document's GeoJSON `location`
    field. GeoJSON stores coordinates as [longitude, latitude] — this
    helper exists so that ordering mistake only has to be handled in one
    place in the whole codebase.
    """
    coords = (event or {}).get("location", {}).get("coordinates", [0.0, 0.0])
    lng, lat = coords[0], coords[1]
    return lat, lng


def make_geojson_point(lat, lng):
    return {"type": "Point", "coordinates": [lng, lat]}


def valid_coordinates(lat, lon):
    """Basic sanity check for user-supplied latitude/longitude values."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180
