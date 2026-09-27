"""Small shared helpers used across route modules."""

from datetime import datetime, date

from bson import ObjectId
from bson.errors import InvalidId

DATE_FMT = "%Y-%m-%d"


def to_object_id(id_str):
    """Safely convert a string to a bson ObjectId, returning None on failure."""
    if not id_str:
        return None
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None


def today_str():
    """Today's date as YYYY-MM-DD, using the server's local clock."""
    return date.today().strftime(DATE_FMT)


def parse_date_str(value):
    """Parse a YYYY-MM-DD string into a date object, or None if invalid/empty."""
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FMT).date()
    except ValueError:
        return None


def parse_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def event_status(event):
    """Derive 'upcoming' / 'ongoing' / 'completed' from an event's date range."""
    today = date.today().strftime(DATE_FMT)
    start = event.get("start_date")
    end = event.get("end_date")
    if start and today < start:
        return "upcoming"
    if end and today > end:
        return "completed"
    return "ongoing"


def split_csv_field(value):
    """Turn a comma-separated form field ('Registration, Logistics') into a clean list."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def clamp(value, low, high):
    return max(low, min(high, value))


_BADGE_CLASSES = {
    # positive / done states
    "present": "bg-emerald-100 text-emerald-700",
    "checked-out": "bg-emerald-100 text-emerald-700",
    "completed": "bg-emerald-100 text-emerald-700",
    "resolved": "bg-emerald-100 text-emerald-700",
    "approved": "bg-emerald-100 text-emerald-700",
    "active": "bg-emerald-100 text-emerald-700",
    "ongoing": "bg-emerald-100 text-emerald-700",
    "good": "bg-emerald-100 text-emerald-700",
    # waiting / needs-attention states
    "pending": "bg-amber-100 text-amber-700",
    "open": "bg-amber-100 text-amber-700",
    "upcoming": "bg-amber-100 text-amber-700",
    "medium": "bg-amber-100 text-amber-700",
    "important": "bg-amber-100 text-amber-700",
    "under repair": "bg-amber-100 text-amber-700",
    # in-flight states
    "in-progress": "bg-sky-100 text-sky-700",
    "info": "bg-sky-100 text-sky-700",
    # negative / blocked states
    "absent": "bg-rose-100 text-rose-700",
    "rejected": "bg-rose-100 text-rose-700",
    "high": "bg-rose-100 text-rose-700",
    "urgent": "bg-rose-100 text-rose-700",
    "damaged": "bg-rose-100 text-rose-700",
    "completed-event": "bg-slate-100 text-slate-600",
    # neutral states
    "inactive": "bg-slate-100 text-slate-600",
    "low": "bg-slate-100 text-slate-600",
    "normal": "bg-slate-100 text-slate-600",
}


def badge_class(status):
    """Map a status/priority string to a Tailwind badge color pair. Always returns something."""
    if not status:
        return "bg-slate-100 text-slate-600"
    return _BADGE_CLASSES.get(str(status).lower(), "bg-slate-100 text-slate-600")


def format_date(value, fmt="%d %b %Y"):
    """Format a YYYY-MM-DD string (or date object) for display. Returns '—' if empty/invalid."""
    if not value:
        return "—"
    if isinstance(value, str):
        parsed = parse_date_str(value)
        if not parsed:
            return value
        return parsed.strftime(fmt)
    if isinstance(value, (date, datetime)):
        return value.strftime(fmt)
    return str(value)


def format_datetime(value, fmt="%d %b %Y, %I:%M %p"):
    """Format a datetime object for display. Returns '—' if empty."""
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime(fmt)
    return str(value)


def format_time(value):
    """Format an HH:MM 24h string as e.g. '2:30 PM'. Returns the raw value if unparseable."""
    if not value:
        return "—"
    try:
        parsed = datetime.strptime(value, "%H:%M")
        return parsed.strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return value
