from functools import wraps

from flask import current_app, flash, redirect, url_for
from flask_login import current_user


def user_roles(user=None):
    user = user or current_user
    roles = []
    primary = getattr(user, 'role', None)
    secondary = getattr(user, 'secondary_role', None)
    if primary:
        roles.append(primary)
    if secondary and secondary not in roles:
        roles.append(secondary)
    return roles


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
        '[permissions:%s] current_user.id=%s role=%s secondary_role=%s',
        context,
        current_user.id,
        getattr(current_user, 'role', None),
        getattr(current_user, 'secondary_role', None)
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
