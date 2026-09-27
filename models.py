"""
Thin Flask-Login wrapper around a `users` document.

EventOps stores real data as plain MongoDB documents (dicts) everywhere —
this is the one class in the project, and it exists only because
Flask-Login expects an object with these methods/attributes.
"""

from bson import ObjectId
from bson.errors import InvalidId
from flask_login import UserMixin

from extensions import db, login_manager


class User(UserMixin):
    def __init__(self, doc):
        self._doc = doc
        self.id = str(doc["_id"])
        self.username = doc["username"]
        self.email = doc.get("email")
        self.name = doc.get("name")
        self.role = doc.get("role")  # "admin" | "volunteer"
        self.volunteer_id = str(doc["volunteer_id"]) if doc.get("volunteer_id") else None

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def is_volunteer(self):
        return self.role == "volunteer"


@login_manager.user_loader
def load_user(user_id):
    try:
        oid = ObjectId(user_id)
    except (InvalidId, TypeError):
        return None
    doc = db.users.find_one({"_id": oid})
    return User(doc) if doc else None
