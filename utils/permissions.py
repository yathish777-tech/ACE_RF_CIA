from functools import wraps

from flask import current_app, flash, redirect, url_for
from flask_login import current_user


def user_roles(user=None):
    """Return a list of all role-name strings for the given user.

    Reads from the many-to-many staff_roles table via user.roles_list.
    Falls back gracefully to [user.role] for unauthenticated / anonymous proxies.
    """
    user = user or current_user
    # Use the new many-to-many roles_list property when available
    if hasattr(user, 'roles_list'):
        return list(user.roles_list)
    # Fallback for unauthenticated / anonymous proxies
    primary = getattr(user, 'role', None)
    return [primary] if primary else []


def has_role(*required_roles, user=None):
    roles = set(user_roles(user))
    return any(role in roles for role in required_roles)


def has_any_role(required_roles, user=None):
    return has_role(*tuple(required_roles), user=user)


def log_current_user_permissions(context):
    if not getattr(current_user, 'is_authenticated', False):
        current_app.logger.info('[permissions:%s] anonymous-user', context)
        return
    current_app.logger.info(
        '[permissions:%s] current_user.id=%s roles=%s',
        context,
        current_user.id,
        getattr(current_user, 'roles_list', [getattr(current_user, 'role', None)])
    )


def role_required(*required_roles, allow_admin=False):
    roles = tuple(required_roles) + (('admin',) if allow_admin else ())

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            log_current_user_permissions(f.__name__)
            if not has_role(*roles):
                flash('Access denied.', 'danger')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated
    return decorator
