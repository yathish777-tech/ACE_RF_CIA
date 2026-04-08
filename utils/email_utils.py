"""
utils/email_utils.py
All transactional email notifications for the CIA Retest Portal.

Functions called from routes:
  notify_staff_new_application(app, staff_email, staff_name)
  notify_tutor_after_staff(application)
  notify_coordinator_after_tutor_late(application)
  notify_hod_after_tutor_pre(application)
  notify_hod_after_coordinator_late(application)
  notify_student_final(application)
"""

from flask_mail import Message


def _get_mail():
    """Lazy import to avoid circular imports."""
    from app import mail
    return mail


def _send(to: str, subject: str, body: str, html: str = None):
    """Low-level helper — swallows errors so a mail failure never breaks a route."""
    try:
        mail = _get_mail()
        msg = Message(subject, recipients=[to])
        msg.body = body
        if html:
            msg.html = html
        mail.send(msg)
        print(f"[email_utils] ✓ Email sent to {to} | Subject: {subject}")
    except Exception as e:
        print(f"[email_utils] ✗ Failed to send to {to}: {e}")


def _card(title: str, rows: list[tuple[str, str]], action_label: str = None,
          action_url: str = None, color: str = "#1a237e") -> str:
    """Reusable HTML email card."""
    rows_html = "".join(
        f"<tr><td style='padding:6px 0;color:#777;font-size:13px;'>{k}</td>"
        f"<td style='padding:6px 0;font-size:13px;font-weight:600;color:#333;'>{v}</td></tr>"
        for k, v in rows
    )
    btn = (
        f"<div style='text-align:center;margin-top:24px;'>"
        f"<a href='{action_url}' style='background:{color};color:#fff;"
        f"padding:12px 28px;border-radius:8px;text-decoration:none;font-size:14px;'>"
        f"{action_label}</a></div>"
        if action_label else ""
    )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;
                border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
      <div style="background:linear-gradient(135deg,{color},#e53935);
                  padding:20px 24px;">
        <h2 style="color:#fff;margin:0;font-size:18px;">{title}</h2>
        <p style="color:rgba(255,255,255,.8);margin:4px 0 0;font-size:13px;">
          CIA Retest Portal — Adhiyamaan College of Engineering
        </p>
      </div>
      <div style="padding:24px;">
        <table style="width:100%;border-collapse:collapse;">{rows_html}</table>
        {btn}
      </div>
      <div style="background:#f5f5f5;padding:12px 24px;text-align:center;
                  font-size:11px;color:#aaa;">
        This is an automated notification. Please do not reply.
      </div>
    </div>
    """


# ─────────────────────────────────────────────────────────────────────────────
# 1. New application → Subject Staff
# ─────────────────────────────────────────────────────────────────────────────
def notify_staff_new_application(application, staff_email: str, staff_name: str):
    subj = application.subject
    html = _card(
        title="New Retest Application Assigned",
        rows=[
            ("Student",   application.student_name),
            ("Reg No",    application.register_number or "—"),
            ("Subject",   subj.subject_name if subj else "—"),
            ("CIA No",    str(application.cia_number)),
            ("Type",      application.submission_type.upper()),
            ("Reason",    (application.reason_type or "—").replace("_", " ").title()),
            ("Submitted", application.submitted_at.strftime("%d %b %Y %H:%M")),
        ],
        color="#1a237e",
    )
    _send(
        to=staff_email,
        subject=f"[CIA Retest] New Application — {application.student_name}",
        body=(
            f"Dear {staff_name},\n\n"
            f"A new retest application has been submitted and assigned to you.\n"
            f"Student: {application.student_name} | Subject: {subj.subject_name if subj else '—'} "
            f"| CIA {application.cia_number}\n\n"
            f"Please log in to review it.\n\nCIA Retest Portal"
        ),
        html=html,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Staff approved → Tutor notified
# ─────────────────────────────────────────────────────────────────────────────
def notify_tutor_after_staff(application):
    tutor = application.tutor
    if not tutor:
        return
    subj = application.subject
    html = _card(
        title="Retest Application Awaiting Your Review",
        rows=[
            ("Student",        application.student_name),
            ("Reg No",         application.register_number or "—"),
            ("Subject",        subj.subject_name if subj else "—"),
            ("CIA No",         str(application.cia_number)),
            ("Staff Decision", application.staff_status.title()),
            ("Staff Remark",   application.staff_remark or "—"),
        ],
        color="#1565c0",
    )
    _send(
        to=tutor.email,
        subject=f"[CIA Retest] Action Required — {application.student_name}",
        body=(
            f"Dear {tutor.name},\n\n"
            f"A retest application approved by subject staff is awaiting your review.\n"
            f"Student: {application.student_name} | Subject: {subj.subject_name if subj else '—'}\n\n"
            f"Please log in to review it.\n\nCIA Retest Portal"
        ),
        html=html,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Tutor late (post-submission) → Coordinator notified
# ─────────────────────────────────────────────────────────────────────────────
def notify_coordinator_after_tutor_late(application):
    from models import User
    coordinators = User.query.filter(
        (User.role == 'coordinator') | (User.secondary_role == 'coordinator'),
        User.is_active == True
    ).all()
    subj = application.subject
    for coord in coordinators:
        html = _card(
            title="Escalation: Tutor Delay — Retest Application",
            rows=[
                ("Student", application.student_name),
                ("Reg No",  application.register_number or "—"),
                ("Subject", subj.subject_name if subj else "—"),
                ("CIA No",  str(application.cia_number)),
                ("Tutor",   application.tutor.name if application.tutor else "—"),
                ("Status",  "Pending tutor action (escalated to coordinator)"),
            ],
            color="#e65100",
        )
        _send(
            to=coord.email,
            subject=f"[CIA Retest] Escalation — Tutor Delay for {application.student_name}",
            body=(
                f"Dear {coord.name},\n\n"
                f"A retest application has been escalated to you due to tutor delay.\n"
                f"Student: {application.student_name} | Subject: {subj.subject_name if subj else '—'}\n\n"
                f"Please log in to review.\n\nCIA Retest Portal"
            ),
            html=html,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Tutor pre-approval → HOD notified directly
# ─────────────────────────────────────────────────────────────────────────────
def notify_hod_after_tutor_pre(application):
    from models import User
    hods = User.query.filter(
        (User.role == 'hod') | (User.secondary_role == 'hod'),
        User.is_active == True
    ).all()
    subj = application.subject
    for hod in hods:
        html = _card(
            title="Pre-Submission Retest — HOD Approval Required",
            rows=[
                ("Student",       application.student_name),
                ("Reg No",        application.register_number or "—"),
                ("Subject",       subj.subject_name if subj else "—"),
                ("CIA No",        str(application.cia_number)),
                ("Tutor Decision", application.tutor_status.title()),
                ("Tutor Remark",  application.tutor_remark or "—"),
            ],
            color="#4a148c",
        )
        _send(
            to=hod.email,
            subject=f"[CIA Retest] HOD Action Required — {application.student_name}",
            body=(
                f"Dear {hod.name},\n\n"
                f"A pre-submission retest application requires your approval.\n"
                f"Student: {application.student_name} | Subject: {subj.subject_name if subj else '—'}\n\n"
                f"Please log in to review.\n\nCIA Retest Portal"
            ),
            html=html,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 5. Coordinator approved late → HOD notified
# ─────────────────────────────────────────────────────────────────────────────
def notify_hod_after_coordinator_late(application):
    from models import User
    hods = User.query.filter(
        (User.role == 'hod') | (User.secondary_role == 'hod'),
        User.is_active == True
    ).all()
    subj = application.subject
    for hod in hods:
        html = _card(
            title="Coordinator Approved — HOD Final Decision Required",
            rows=[
                ("Student",              application.student_name),
                ("Reg No",               application.register_number or "—"),
                ("Subject",              subj.subject_name if subj else "—"),
                ("CIA No",               str(application.cia_number)),
                ("Coordinator Decision", application.coordinator_status.title()),
                ("Coordinator Remark",   application.coordinator_remark or "—"),
            ],
            color="#880e4f",
        )
        _send(
            to=hod.email,
            subject=f"[CIA Retest] Final Approval Required — {application.student_name}",
            body=(
                f"Dear {hod.name},\n\n"
                f"A retest application approved by the coordinator awaits your final decision.\n"
                f"Student: {application.student_name} | Subject: {subj.subject_name if subj else '—'}\n\n"
                f"Please log in to review.\n\nCIA Retest Portal"
            ),
            html=html,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. HOD final decision → Student notified
# ─────────────────────────────────────────────────────────────────────────────
def notify_student_final(application):
    subj    = application.subject
    status  = application.final_status
    color   = "#2e7d32" if status == "approved" else "#b71c1c"
    icon    = "✅ Approved" if status == "approved" else "❌ Rejected"
    message = (
        "Congratulations! Your retest application has been approved. "
        "Please attend the retest on the scheduled date."
        if status == "approved" else
        "We regret to inform you that your retest application has been rejected. "
        "Please contact your tutor or HOD for further information."
    )
    html = _card(
        title=f"Retest Application {icon}",
        rows=[
            ("Subject",       subj.subject_name if subj else "—"),
            ("CIA No",        str(application.cia_number)),
            ("Final Status",  status.title()),
            ("HOD Remark",    application.hod_remark or "—"),
        ],
        color=color,
    )
    _send(
        to=application.student_email,
        subject=f"[CIA Retest] Application {status.title()} — {subj.subject_name if subj else ''}",
        body=(
            f"Dear {application.student_name},\n\n"
            f"{message}\n\n"
            f"Subject: {subj.subject_name if subj else '—'} | CIA {application.cia_number}\n"
            f"Decision: {status.title()}\n"
            f"HOD Remark: {application.hod_remark or '—'}\n\n"
            f"CIA Retest Portal — Adhiyamaan College of Engineering"
        ),
        html=html,
    )