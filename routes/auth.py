"""
routes/auth.py — Authentication blueprint
Handles: login, logout, register, forgot_password, verify_otp,
         reset_password, change_password
"""

import random
import re
import string
from datetime import datetime, timedelta
from models import User

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, session)
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message

from extensions import db   

auth_bp = Blueprint('auth', __name__)


# ── helpers ───────────────────────────────────────────────────────────────────
def _generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


def _send_otp_email(mail, to_email: str, otp: str, subject: str = "Your OTP Code"):
    """Send OTP via Flask-Mail. Import mail inside function to avoid circular import."""
    try:
        msg = Message(subject, recipients=[to_email])
        msg.body = (
            f"Your OTP for CIA Retest Portal is: {otp}\n\n"
            f"This code expires in 10 minutes.\n"
            f"If you did not request this, please ignore this email."
        )
        msg.html = f"""
        <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                    border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
          <div style="background:linear-gradient(135deg,#1a237e,#e53935);padding:24px;text-align:center;">
            <h2 style="color:#fff;margin:0;">CIA Retest Portal</h2>
            <p style="color:rgba(255,255,255,.8);margin:4px 0 0;">Adhiyamaan College of Engineering</p>
          </div>
          <div style="padding:32px;text-align:center;">
            <p style="color:#555;font-size:15px;">{subject}</p>
            <div style="font-size:42px;font-weight:700;letter-spacing:10px;
                        color:#1a237e;margin:20px 0;">{otp}</div>
            <p style="color:#999;font-size:13px;">Expires in 10 minutes.</p>
          </div>
        </div>
        """
        mail.send(msg)
        return True
    except Exception as e:
        print(f"[Email error] {e}")
        return False


# ── LOGIN ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter(
            db.func.lower(User.email) == email
        ).first()

        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Contact the admin.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('auth/login.html')


# ── LOGOUT ────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ── REGISTER (students only) ──────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        name            = request.form.get('name', '').strip()
        register_number = re.sub(r'\s+', '', request.form.get('register_number', '').strip()).upper()
        email           = request.form.get('email', '').strip().lower()
        phone           = request.form.get('phone', '').strip()
        department      = request.form.get('department', '').strip()
        year            = request.form.get('year', type=int)
        section         = request.form.get('section', '').strip().upper()
        password        = request.form.get('password', '')
        confirm         = request.form.get('confirm_password', '')

        # Validation
        if not all([name, email, password, register_number]):
            flash('Name, register number, email and password are required.', 'danger')
            return redirect(url_for('auth.register'))

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth.register'))

        existing_email = User.query.filter(db.func.lower(User.email) == email).first()
        existing_register = User.query.filter(
            User.role == 'student',
            db.func.upper(User.register_number) == register_number
        ).first()

        if existing_email and (not existing_register or existing_email.id != existing_register.id):
            flash('An account with this email already exists.', 'danger')
            return redirect(url_for('auth.register'))

        if existing_register:
            if not existing_register.email.endswith('@student.local') and existing_register.email.lower() != email:
                flash('An account with this register number already exists.', 'danger')
                return redirect(url_for('auth.register'))
            user = existing_register
            user.name = name
            user.email = email
            user.phone = phone
            user.department = department
            user.year = year
            user.section = section if section else None
            user.is_active = True
        else:
            user = User(
                name=name,
                email=email,
                phone=phone,
                department=department,
                role='student',
                register_number=register_number,
                year=year,
                section=section if section else None,
                is_active=True,
            )
            db.session.add(user)
        user.set_password(password)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


# ── FORGOT PASSWORD ───────────────────────────────────────────────────────────
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user  = User.query.filter(db.func.lower(User.email) == email).first()

        if user:
            otp            = _generate_otp()
            user.otp       = otp
            user.otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()

            # Send email
            from app import mail
            sent = _send_otp_email(mail, user.email, otp, "Password Reset OTP")
            if sent:
                flash('OTP sent to your email address.', 'success')
            else:
                flash('Could not send email. Please check mail configuration.', 'warning')
        else:
            # Don't reveal whether email exists
            flash('If that email is registered, an OTP has been sent.', 'info')

        session['reset_email'] = email
        return redirect(url_for('auth.verify_otp'))

    return render_template('auth/forgot_password.html')


# ── VERIFY OTP ────────────────────────────────────────────────────────────────
@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('reset_email', '')
    if not email:
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        entered_otp = request.form.get('otp', '').strip()
        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()

        if not user or not user.otp:
            flash('OTP expired or invalid. Please try again.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if user.otp_expiry and datetime.utcnow() > user.otp_expiry:
            flash('OTP has expired. Please request a new one.', 'danger')
            user.otp = None
            user.otp_expiry = None
            db.session.commit()
            return redirect(url_for('auth.forgot_password'))

        if user.otp != entered_otp:
            flash('Incorrect OTP. Please try again.', 'danger')
            return render_template('auth/verify_otp.html', email=email)

        # OTP correct — clear it and allow password reset
        user.otp = None
        user.otp_expiry = None
        db.session.commit()
        session['reset_verified'] = True
        return redirect(url_for('auth.reset_password'))

    return render_template('auth/verify_otp.html', email=email)


# ── RESET PASSWORD ────────────────────────────────────────────────────────────
@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if not session.get('reset_verified'):
        flash('Please verify your OTP first.', 'warning')
        return redirect(url_for('auth.forgot_password'))

    email = session.get('reset_email', '')

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth.reset_password'))

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.reset_password'))

        user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
        if not user:
            flash('User not found. Please try again.', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user.set_password(password)
        db.session.commit()

        session.pop('reset_email', None)
        session.pop('reset_verified', None)

        flash('Password reset successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')


# ── CHANGE PASSWORD (logged-in users) ────────────────────────────────────────
@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw     = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('auth.change_password'))

        if len(new_pw) < 6:
            flash('New password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth.change_password'))

        if new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
            return redirect(url_for('auth.change_password'))

        current_user.set_password(new_pw)
        db.session.commit()
        flash('Password changed successfully.', 'success')
        return redirect(url_for('main.index'))

    return render_template('auth/change_password.html')
