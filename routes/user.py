import os, uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify, send_from_directory, abort)
from flask_login import login_required, current_user
from models import db, User, Subject, CIADate, RetestApplication, SubjectStaffSection
from datetime import datetime, date
from functools import wraps

user_bp = Blueprint('user', __name__)

SEMESTER_TO_YEAR = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}
YEAR_LABEL = {1: 'First Year (I)', 2: 'First Year (I)', 3: 'Second Year (II)', 4: 'Second Year (II)',
              5: 'Third Year (III)', 6: 'Third Year (III)', 7: 'Fourth Year (IV)', 8: 'Fourth Year (IV)'}
ALLOWED = {'pdf', 'jpg', 'jpeg', 'png'}


# =========================
# AUTH CHECK
# =========================
def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'student':
            flash('Access denied.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


# =========================
# DASHBOARD
# =========================
@user_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    applications = RetestApplication.query.filter_by(
        student_id=current_user.id
    ).order_by(RetestApplication.submitted_at.desc()).all()

    return render_template('user/dashboard.html', applications=applications)


# =========================
# GET SUBJECTS
# =========================
@user_bp.route('/get_subjects_by_semester/<int:semester>')
@login_required
def get_subjects_by_semester(semester):

    student_section = getattr(current_user, 'section', 'A')

    sss_list = SubjectStaffSection.query.filter_by(
        semester=semester,
        section=student_section
    ).all()

    subject_data = []

    # ✅ NORMAL CASE (mapping exists)
    if sss_list:
        for sss in sss_list:
            s = sss.subject
            subject_data.append({
                'id': s.id,
                'name': s.subject_name,
                'staff_id': sss.staff_id,
                'staff_name': sss.staff.name if sss.staff else None
            })

    # ✅ FALLBACK CASE (mapping missing)
    else:
        subjects = Subject.query.filter_by(semester=semester).all()
        for s in subjects:
            subject_data.append({
                'id': s.id,
                'name': s.subject_name,
                'staff_id': s.staff_id,
                'staff_name': s.staff.name if s.staff else None
            })

    return jsonify({'subjects': subject_data})


# =========================
# GET CIA INFO (FIXED)
# =========================
@user_bp.route('/get_cia_info/<int:subject_id>/<int:cia_num>')
@login_required
def get_cia_info(subject_id, cia_num):
    cia = CIADate.query.filter_by(
        subject_id=subject_id,
        cia_number=cia_num
    ).first()

    if not cia:
        return jsonify({'error': 'not found'})

    today = date.today()

    # ✅ Check if application window is open
    retest_open = False
    is_open = False
    end_date_display = None
    
    if cia.application_end_date:
        retest_open = cia.application_end_date >= today
        is_open = retest_open
        if cia.application_end_date:
            end_date_display = cia.application_end_date.strftime('%d-%b-%Y')

    return jsonify({
        'exam_date': cia.exam_date.strftime('%Y-%m-%d') if cia.exam_date else None,
        'end_date': cia.application_end_date.strftime('%Y-%m-%d') if cia.application_end_date else None,
        'retest_open': retest_open,
        'is_open': is_open,
        'end_date_display': end_date_display
    })


# =========================
# APPLY (FIXED)
# =========================
@user_bp.route('/apply', methods=['GET', 'POST'])
@login_required
@student_required
def apply():

    tutors = User.query.filter(
        (User.role == 'tutor') | (User.secondary_role == 'tutor'),
        User.is_active == True
    ).all()

    # ✅ Get student section & year
    student_section = (getattr(current_user, 'section', '') or '').upper().strip()
    _yr = getattr(current_user, 'year', None)
    student_year = YEAR_LABEL.get(_yr, '') if _yr else ''

    form = {}
    errors = {}

    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items() if isinstance(v, str)}

        # ✅ Required fields
        required_fields = [
            'register_number', 'student_name', 'student_email',
            'semester', 'subject_id', 'cia_number',
            'cia_date', 'staff_id', 'tutor_id',
            'reason_type', 'submission_type'
        ]

        for field in required_fields:
            if not form.get(field):
                errors[field] = f'{field.replace("_", " ").title()} is required.'

        # ✅ If reason is "others", require reason_detail
        if form.get('reason_type') == 'others' and not form.get('reason_detail'):
            errors['reason_detail'] = 'Please specify your reason.'

        # ✅ Prevent duplicate application
        if form.get('subject_id'):
            existing = RetestApplication.query.filter_by(
                student_id=current_user.id,
                subject_id=int(form['subject_id'])
            ).first()

            if existing:
                errors['subject_id'] = 'You already applied for this subject.'

        # ✅ CIA window check
        if form.get('subject_id') and form.get('cia_number'):
            cia = CIADate.query.filter_by(
                subject_id=int(form['subject_id']),
                cia_number=int(form['cia_number'])
            ).first()

            if cia and not cia.is_application_open():
                errors['cia_number'] = 'Application window closed.'

        # ✅ File check
        file = request.files.get('attachment')
        if not file or not file.filename:
            errors['attachment'] = 'File required'
        else:
            # ✅ Check file extension
            ext = file.filename.split('.')[-1].lower()
            if ext not in ALLOWED:
                errors['attachment'] = f'Invalid file type. Allowed: {", ".join(ALLOWED)}'

        if not errors:

            # ✅ Get academic year from submitted form (semester-based)
            semester = int(form['semester'])
            submitted_year = SEMESTER_TO_YEAR.get(semester, None)

            # ✅ Save file
            ext = file.filename.split('.')[-1]
            filename = f"{uuid.uuid4().hex}.{ext}"
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))

            # ✅ Create application
            application = RetestApplication(
                student_id=current_user.id,
                student_name=form['student_name'],
                register_number=form['register_number'],
                student_email=form['student_email'],
                subject_id=int(form['subject_id']),
                cia_number=int(form['cia_number']),
                cia_date=datetime.strptime(form['cia_date'], '%Y-%m-%d').date(),
                semester=semester,
                staff_id=int(form['staff_id']),
                tutor_id=int(form['tutor_id']),
                reason_type=form['reason_type'],
                reason_detail=form.get('reason_detail', ''),
                submission_type=form['submission_type'],
                attachment_filename=filename,
                student_section=student_section,   # ✅ From user profile
                student_year=submitted_year,       # ✅ NEW: From semester selection (not user.year)
                submitted_at=datetime.utcnow()
            )

            db.session.add(application)
            db.session.commit()

            flash('Application submitted successfully', 'success')
            return redirect(url_for('user.dashboard'))

    return render_template(
        'user/apply.html',
        tutors=tutors,
        form=form,
        errors=errors,
        student_section=student_section,   # ✅ pass to template
        student_year=student_year
    )


# =========================
# VIEW APPLICATION
# =========================
@user_bp.route('/view/<int:app_id>')
@login_required
@student_required
def view_application(app_id):
    app = RetestApplication.query.filter_by(
        id=app_id,
        student_id=current_user.id
    ).first_or_404()

    return render_template('user/view_application.html', app=app)


# =========================
# VIEW FILE
# =========================
@user_bp.route('/attachment/<int:app_id>')
@login_required
def view_attachment(app_id):

    application = RetestApplication.query.get_or_404(app_id)

    allowed = False
    if application.student_id == current_user.id:
        allowed = True
    elif current_user.role == 'admin':
        allowed = True
    elif current_user.role == 'subject_staff' or current_user.secondary_role == 'subject_staff':
        allowed = application.staff_id == current_user.id
    elif current_user.role == 'tutor' or current_user.secondary_role == 'tutor':
        allowed = application.tutor_id == current_user.id
    elif current_user.role == 'coordinator' or current_user.secondary_role == 'coordinator':
        allowed = application.submission_type == 'late'
    elif current_user.role == 'hod' or current_user.secondary_role == 'hod':
        allowed = True

    if not allowed:
        abort(403)

    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        application.attachment_filename
    )