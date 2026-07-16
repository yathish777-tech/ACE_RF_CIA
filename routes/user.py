import uuid, re
import cloudinary.uploader
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify)
from flask_login import login_required, current_user
from models import db, User, Subject, CIADate, RetestApplication, SubjectStaffSection, AbsenceRecord, HallAttendance
from datetime import datetime, date
from functools import wraps
from utils.permissions import has_role, role_required

user_bp = Blueprint('user', __name__)

SEMESTER_TO_YEAR = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}
YEAR_LABEL = {1: 'First Year (I)', 2: 'First Year (I)', 3: 'Second Year (II)', 4: 'Second Year (II)',
              5: 'Third Year (III)', 6: 'Third Year (III)', 7: 'Fourth Year (IV)', 8: 'Fourth Year (IV)'}
ALLOWED = {'pdf', 'jpg', 'jpeg', 'png'}


# =========================
# AUTH CHECK
# =========================
def student_required(f):
    return role_required('student')(f)


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

    student_section = (request.args.get('section') or getattr(current_user, 'section', 'A') or 'A').upper().strip()

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


@user_bp.route('/get_staff/<int:subject_id>')
@login_required
def get_staff(subject_id):
    section = (request.args.get('section') or getattr(current_user, 'section', '') or '').upper().strip()
    sss = SubjectStaffSection.query.filter_by(subject_id=subject_id, section=section).first()
    if sss and sss.staff:
        return jsonify({'staff_id': sss.staff_id, 'staff_name': sss.staff.name})
    subject = Subject.query.get(subject_id)
    if subject and subject.staff:
        return jsonify({'staff_id': subject.staff_id, 'staff_name': subject.staff.name})
    return jsonify({})


def _normalize_register_number(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def _find_tutor_for_class(year, section):
    section = (section or '').upper().strip()
    if not year or not section:
        return None
    return User.query.filter(
        (User.role == 'tutor') | (User.secondary_role == 'tutor'),
        User.handling_year == year,
        db.func.upper(User.handling_section) == section,
        User.is_active == True
    ).order_by(User.name).first()


@user_bp.route('/get_tutor_for_class/<int:year>/<string:section>')
@login_required
@student_required
def get_tutor_for_class(year, section):
    tutor = _find_tutor_for_class(year, section)
    if not tutor:
        return jsonify({'error': 'No tutor mapped for this class'}), 404
    return jsonify({
        'tutor_id': tutor.id,
        'tutor_name': tutor.name,
        'tutor_email': tutor.email
    })


def _student_has_absentee_record(subject_id, cia_number, register_number, year=None, section=None):
    current_app.logger.info(
        '[retest-absence:absence-record] params subject_id=%s cia_number=%s register=%s year=%s section=%s',
        subject_id, cia_number, register_number, year, section
    )
    if not subject_id or not cia_number or not register_number:
        current_app.logger.info('[retest-absence:absence-record] result=False reason=missing-required-param')
        return False
    register_number = _normalize_register_number(register_number)
    if not register_number:
        current_app.logger.info('[retest-absence:absence-record] result=False reason=blank-register')
        return False
    section = (section or '').upper().strip()

    absence_records = AbsenceRecord.query.filter_by(
        subject_id=subject_id,
        cia_number=cia_number
    ).all()
    current_app.logger.info(
        '[retest-absence:absence-record] records_found=%s record_ids=%s',
        len(absence_records), [record.id for record in absence_records]
    )
    for record in absence_records:
        for student in record.get_students():
            student_reg = _normalize_register_number(
                student.get('register_number') or student.get('reg_no') or
                student.get('register_no') or student.get('reg')
            )
            if student_reg != register_number:
                continue

            student_year = student.get('year') or student.get('yr')
            student_section = (student.get('section') or student.get('sec') or '').upper().strip()
            try:
                student_year = int(float(student_year)) if student_year else None
            except (TypeError, ValueError):
                student_year = None

            if year and student_year and student_year != year:
                current_app.logger.info(
                    '[retest-absence:absence-record] register_match record_id=%s result=False reason=year-mismatch student_year=%s selected_year=%s',
                    record.id, student_year, year
                )
                continue
            if section and student_section and student_section != section:
                current_app.logger.info(
                    '[retest-absence:absence-record] register_match record_id=%s result=False reason=section-mismatch student_section=%s selected_section=%s',
                    record.id, student_section, section
                )
                continue
            current_app.logger.info(
                '[retest-absence:absence-record] result=True record_id=%s status=listed-absent',
                record.id
            )
            return True
    current_app.logger.info('[retest-absence:absence-record] result=False reason=no-matching-register')
    return False


def _student_hall_attendance_absence_status(register_number, cia_number, exam_date):
    register_number = _normalize_register_number(register_number)
    current_app.logger.info(
        '[retest-absence:hall-attendance] params cia_number=%s exam_date=%s register=%s',
        cia_number, exam_date, register_number
    )
    if not register_number or not cia_number or not exam_date:
        current_app.logger.info('[retest-absence:hall-attendance] result=None reason=missing-required-param')
        return None

    candidate_records = HallAttendance.query.filter(
        HallAttendance.cia_id == cia_number,
        HallAttendance.exam_date == exam_date
    ).all()
    records = [
        record for record in candidate_records
        if _normalize_register_number(record.student_reg_no) == register_number
    ]
    current_app.logger.info(
        '[retest-absence:hall-attendance] candidates_found=%s records_found=%s details=%s objects=%s',
        len(candidate_records),
        len(records),
        [
            {
                'id': record.id,
                'hall_id': record.hall_id,
                'register_raw': record.student_reg_no,
                'register': _normalize_register_number(record.student_reg_no),
                'cia_id': record.cia_id,
                'exam_date': record.exam_date.isoformat() if record.exam_date else None,
                'status': record.status
            }
            for record in records
        ],
        [repr(record) for record in records]
    )
    if not records:
        current_app.logger.info(
            '[retest-absence:hall-attendance] result=None reason=no-attendance-row candidate_details=%s',
            [
                {
                    'id': record.id,
                    'hall_id': record.hall_id,
                    'register_raw': record.student_reg_no,
                    'register': _normalize_register_number(record.student_reg_no),
                    'status': record.status
                }
                for record in candidate_records
            ]
        )
        return None

    absent_values = {'absent', 'a'}
    is_absent = any(str(record.status or '').strip().lower() in absent_values for record in records)
    current_app.logger.info(
        '[retest-absence:hall-attendance] result=%s statuses=%s objects=%s',
        is_absent, [record.status for record in records], [repr(record) for record in records]
    )
    return is_absent


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
        'retest_date': cia.retest_date.strftime('%Y-%m-%d') if cia.retest_date else None,
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

    student_section = (getattr(current_user, 'section', '') or '').upper().strip()
    student_year_num = getattr(current_user, 'year', None)
    student_year = YEAR_LABEL.get(student_year_num, '') if student_year_num else ''
    auto_tutor = _find_tutor_for_class(student_year_num, student_section)

    form   = {}
    errors = {}

    if request.method == 'POST':
        form = {k: v.strip() for k, v in request.form.items() if isinstance(v, str)}

        selected_section = (form.get('student_section') or student_section).upper().strip()
        if selected_section:
            form['student_section'] = selected_section

        required_fields = [
            'register_number', 'student_name', 'student_email',
            'semester', 'subject_id', 'cia_number',
            'cia_date', 'staff_id', 'tutor_id',
            'reason_type', 'submission_type', 'student_section'
        ]
        for field in required_fields:
            if not form.get(field):
                errors[field] = f'{field.replace("_", " ").title()} is required.'

        if form.get('register_number') and _normalize_register_number(form.get('register_number')) != _normalize_register_number(current_user.register_number):
            errors['register_number'] = 'Use your own registered register number.'

        selected_semester = None
        if form.get('semester') and form['semester'].isdigit():
            selected_semester = int(form['semester'])
        selected_year = SEMESTER_TO_YEAR.get(selected_semester)
        mapped_tutor = _find_tutor_for_class(selected_year, selected_section)
        if mapped_tutor:
            form['tutor_id'] = str(mapped_tutor.id)
            errors.pop('tutor_id', None)
        else:
            errors['tutor_id'] = 'No active tutor is mapped for the selected year and section. Contact Admin.'

        if form.get('reason_type') == 'others' and not form.get('reason_detail'):
            errors['reason_detail'] = 'Please specify your reason.'

        # Normalize absentee acknowledgement checkbox (backend source-of-truth)
        form['absentee_acknowledged'] = '1' if request.form.get('absentee_acknowledged') == '1' else '0'
        if form.get('submission_type') == 'late' and form.get('absentee_acknowledged') != '1':
            errors['absentee_acknowledged'] = 'Please acknowledge the absentee declaration before submitting a late submission request.'

        if form.get('subject_id'):
            existing = RetestApplication.query.filter_by(
                student_id=current_user.id,
                subject_id=int(form['subject_id'])
            ).first()
            if existing:
                errors['subject_id'] = 'You already applied for this subject. One student can apply only once per subject, so another CIA retest for the same subject is not allowed.'

        if form.get('subject_id') and form.get('cia_number'):
            try:
                subject_id = int(form['subject_id'])
                cia_number = int(form['cia_number'])
            except ValueError:
                subject_id = cia_number = None

            cia = CIADate.query.filter_by(
                subject_id=subject_id,
                cia_number=cia_number
            ).first() if subject_id and cia_number else None
            if not cia:
                errors['cia_number'] = 'CIA date is not configured for the selected subject.'
            else:
                # Determine application-window semantics:
                # - Pre-submission: allow while application_end_date >= today (frontend 'retest_open')
                # - Late submission: allow only after exam_date and before/at application_end_date
                submission_type = form.get('submission_type', 'pre')
                today = date.today()
                retest_open = bool(cia.application_end_date and cia.application_end_date >= today)

                if submission_type == 'pre':
                    if not retest_open:
                        errors['cia_number'] = 'Application window closed.'
                else:  # late
                    if not cia.is_application_open():
                        errors['cia_number'] = 'Application window closed.'

                # Only perform absentee-record checks for LATE submissions when CIA window is open
                if not errors.get('cia_number') and submission_type == 'late':
                    current_app.logger.info(
                        '[retest-absence:validation] student_id=%s register_raw=%s register=%s subject_id=%s cia_number=%s exam_date=%s selected_year=%s selected_section=%s cia_object=%s',
                        current_user.id, form.get('register_number', ''),
                        _normalize_register_number(form.get('register_number', '')),
                        subject_id, cia_number, cia.exam_date, selected_year,
                        selected_section, repr(cia)
                    )
                    hall_absence_status = _student_hall_attendance_absence_status(
                        form.get('register_number', ''), cia_number, cia.exam_date
                    )
                    if hall_absence_status is None:
                        absence_valid = _student_has_absentee_record(
                            subject_id, cia_number, form.get('register_number', ''),
                            selected_year, selected_section
                        )
                        validation_source = 'absence_record'
                    else:
                        absence_valid = hall_absence_status
                        validation_source = 'hall_attendance'

                    current_app.logger.info(
                        '[retest-absence:validation] source=%s final_result=%s',
                        validation_source, absence_valid
                    )
                    if not absence_valid:
                        errors['subject_id'] = 'Only students marked absent for this CIA exam date can apply for this retest.'

        file = request.files.get('attachment')
        if not file or not file.filename:
            errors['attachment'] = 'File required'
        else:
            ext = file.filename.split('.')[-1].lower()
            if ext not in ALLOWED:
                errors['attachment'] = f'Invalid file type. Allowed: {", ".join(ALLOWED)}'

        if not errors:
            semester = int(form['semester'])
            submitted_year = SEMESTER_TO_YEAR.get(semester, None)

# Upload file to Cloudinary
            result = cloudinary.uploader.upload(
            file,
            folder="ace_rf_cia_documents",
            resource_type="auto"  # supports pdf, jpg, png, etc.
            )

# Get the secure URL returned by Cloudinary
            file_url = result["secure_url"]
 
# Optional: keep the original filename
            filename = file.filename

            application = RetestApplication(
                student_id          = current_user.id,
                student_name        = form['student_name'],
                register_number     = form['register_number'],
                student_email       = form['student_email'],
                subject_id          = int(form['subject_id']),
                cia_number          = int(form['cia_number']),
                cia_date            = datetime.strptime(form['cia_date'], '%Y-%m-%d').date(),
                semester            = semester,
                staff_id            = int(form['staff_id']),
                tutor_id            = int(form['tutor_id']),
                reason_type         = form['reason_type'],
                reason_detail       = form.get('reason_detail', ''),
                submission_type     = form['submission_type'],
                attachment_filename = file_url,
                student_section     = form.get('student_section') or student_section,
                student_year        = submitted_year,
                submitted_at        = datetime.utcnow()
            )
            db.session.add(application)
            db.session.commit()
            flash('Application submitted successfully', 'success')
            return redirect(url_for('user.dashboard'))

    return render_template(
        'user/apply.html',
        auto_tutor=auto_tutor,
        form=form,
        errors=errors,
        student_section=student_section,
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


