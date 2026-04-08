from flask import Blueprint, redirect, url_for
from flask_login import current_user

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        role = current_user.role
        # Dual-role: if primary is subject_staff but secondary is tutor (or vice versa),
        # show staff dashboard first (staff dashboard is the primary role)
        if role == 'student':
            return redirect(url_for('user.dashboard'))
        elif role == 'subject_staff':
            return redirect(url_for('staff.dashboard'))
        elif role == 'tutor':
            return redirect(url_for('tutor.dashboard'))
        elif role == 'hod':
            return redirect(url_for('hod.dashboard'))
        elif role == 'coordinator':
            return redirect(url_for('coordinator.dashboard'))
        elif role == 'admin':
            return redirect(url_for('admin.dashboard'))
    return redirect(url_for('auth.login'))
