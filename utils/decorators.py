"""Role-based access decorators layered on top of Flask-Login's @login_required."""

from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(role):
    """Restrict a view to a single role ('admin' or 'volunteer'). Implies login_required."""

    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role != role:
                abort(403)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


admin_required = role_required("admin")
volunteer_required = role_required("volunteer")
