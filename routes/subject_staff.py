import os, uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify, send_file)
from flask_login import login_required, current_user
from models import db, RetestApplication, AbsenceRecord, Subject, User, Hall, SeatingAllocation, HallAttendance, SeatingAllotment, ExamAttendance, CIADate
from datetime import datetime
from functools import wraps
import io
import re
from utils.permissions import has_role, log_current_user_permissions, role_required

staff_bp = Blueprint('staff', __name__)
ALLOWED = {'pdf','jpg','jpeg','png','xlsx','xls','csv'}


def _parse_exam_date(value):
    value = (value or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return None


def normalize_column_name(col):
    if not isinstance(col, str):
        return ''
    col = col.strip().lower()
    col = re.sub(r'[^a-z0-9]+', '_', col)
    col = re.sub(r'_+', '_', col)
    return col.strip('_')


def normalize_value(val):
    if val is None:
        return ''
    text = str(val).strip()
    if text.lower() in ('nan', 'none', 'na', ''):
        return ''
    return text


def _normalize_register_number(value) -> str:
    return re.sub(r'[^A-Z0-9]', '', normalize_value(value).upper())


def _allotment_student_count(allotment):
    regs = allotment.get_register_numbers()
    return len(regs) if regs else (allotment.total_students or allotment.num_students or 0)


def _registered_student_map():
    return {
        _normalize_register_number(student.register_number): student
        for student in User.query.filter_by(role='student').all()
        if _normalize_register_number(student.register_number)
    }


def _display_attendance_status(status):
    return 'Absent' if str(status or '').lower() == 'absent' else 'Present'


def _student_payload(register_number):
    reg = _normalize_register_number(register_number)
    student = next(
        (
            candidate for candidate in User.query.filter_by(role='student').all()
            if _normalize_register_number(candidate.register_number) == reg
        ),
        None
    )
    return {
        'reg_no': reg,
        'register_number': reg,
        'register_no': reg,
        'reg': reg,
        'name': student.name if student else '',
        'student_name': student.name if student else '',
        'year': student.year if student and student.year else '',
        'section': (student.section if student and student.section else '').upper()
    }


def _sync_absence_records_for_cia(cia_number, exam_date, staff_id):
    """Mirror saved hall attendance absentees into AbsenceRecord for retest validation."""
    cia_dates = CIADate.query.filter_by(cia_number=cia_number, exam_date=exam_date).all()
    current_app.logger.info(
        '[hall-attendance:absence-sync] cia_number=%s exam_date=%s matched_cia_dates=%s',
        cia_number, exam_date, [(cia.id, cia.subject_id) for cia in cia_dates]
    )
    if not cia_dates:
        return 0

    hall_absence_rows = HallAttendance.query.filter(
        HallAttendance.cia_id == cia_number,
        HallAttendance.exam_date == exam_date,
        db.func.lower(HallAttendance.status).in_(('absent', 'a'))
    ).all()
    hall_absent_regs = [_normalize_register_number(row.student_reg_no) for row in hall_absence_rows]
    absent_regs = sorted({reg for reg in hall_absent_regs if reg})
    students = [_student_payload(reg) for reg in absent_regs]
    current_app.logger.info(
        '[hall-attendance:absence-sync] absent_rows=%s absent_count=%s absent_registers=%s objects=%s',
        len(hall_absence_rows), len(students), absent_regs, [repr(row) for row in hall_absence_rows]
    )

    synced = 0
    for cia in cia_dates:
        record = AbsenceRecord.query.filter_by(
            subject_id=cia.subject_id,
            cia_number=cia.cia_number
        ).first()
        if not record:
            record = AbsenceRecord(
                subject_id=cia.subject_id,
                cia_number=cia.cia_number,
                semester=cia.semester,
                uploaded_by=staff_id
            )
            db.session.add(record)
            current_app.logger.info(
                '[hall-attendance:absence-sync] creating AbsenceRecord subject_id=%s cia_number=%s',
                cia.subject_id, cia.cia_number
            )
        else:
            current_app.logger.info(
                '[hall-attendance:absence-sync] updating AbsenceRecord id=%s subject_id=%s cia_number=%s',
                record.id, record.subject_id, record.cia_number
            )
        record.semester = cia.semester or record.semester
        record.uploaded_by = staff_id
        record.uploaded_at = datetime.utcnow()
        record.set_students(students)
        synced += 1
    return synced


# ─── ROLE CHECK ───────────────────────────────────────────────
def staff_required(f):
    return role_required('subject_staff')(f)


def staff_dashboard_required(f):
    return role_required('subject_staff', 'hod')(f)


def any_staff_required(f):
    return role_required('subject_staff', 'tutor', 'hod', 'coordinator', 'admin')(f)


# ─── DASHBOARD ───────────────────────────────────────────────
@staff_bp.route('/dashboard')
@login_required
@staff_dashboard_required
def dashboard():
    pending = RetestApplication.query.filter_by(
        staff_id=current_user.id, staff_status='pending'
    ).all()

    reviewed = RetestApplication.query.filter(
        RetestApplication.staff_id == current_user.id,
        RetestApplication.staff_status.in_(['approved','rejected'])
    ).all()

    my_subjects = Subject.query.filter_by(
        staff_id=current_user.id, is_active=True
    ).all()

    absence_records = AbsenceRecord.query.filter_by(
        uploaded_by=current_user.id
    ).all()

    stats = {
        'pending': len(pending),
        'approved': sum(1 for r in reviewed if r.staff_status == 'approved'),
        'rejected': sum(1 for r in reviewed if r.staff_status == 'rejected'),
        'total': len(pending) + len(reviewed),
    }

    return render_template('subject_staff/dashboard.html',
                           pending=pending, reviewed=reviewed,
                           stats=stats,
                           my_subjects=my_subjects,
                           absence_records=absence_records)


@staff_bp.route('/hall-attendance')
@login_required
@any_staff_required
def hall_attendance():
    staff_list = User.query.filter(User.role != 'student', User.is_active == True).order_by(User.name).all()
    return render_template('staff/hall_attendance.html', staff_list=staff_list)


@staff_bp.route('/hall-attendance/halls')
@login_required
@any_staff_required
def hall_attendance_halls():
    cia_id = request.args.get('cia_id', type=int)
    staff_id = request.args.get('staff_id', type=int)
    exam_date = _parse_exam_date(request.args.get('exam_date', ''))
    current_app.logger.info(
        '[hall-attendance:halls] params cia_id=%s staff_id=%s exam_date_raw=%s parsed=%s',
        cia_id, staff_id, request.args.get('exam_date', ''), exam_date
    )
    if not cia_id or not exam_date:
        response_payload = {'halls': []}
        current_app.logger.info('[hall-attendance:halls] response=%s', response_payload)
        return jsonify(response_payload)

    rows = db.session.query(Hall).join(SeatingAllocation).filter(
        SeatingAllocation.cia_id == cia_id,
        SeatingAllocation.exam_date == exam_date,
        SeatingAllocation.student_reg_no != None
    ).group_by(Hall.id).order_by(Hall.id).all()
    current_app.logger.info(
        '[hall-attendance:halls] SeatingAllocation hall ids=%s',
        [hall.id for hall in rows]
    )
    payload = []
    if rows:
        for hall in rows:
            total = SeatingAllocation.query.filter_by(cia_id=cia_id, exam_date=exam_date, hall_id=hall.id).filter(SeatingAllocation.student_reg_no != None).count()
            marked = HallAttendance.query.filter_by(cia_id=cia_id, exam_date=exam_date, hall_id=hall.id).count()
            payload.append({
                'source': 'allocation',
                'key': str(hall.id),
                'id': hall.id,
                'hall_name': hall.hall_name or hall.hall_number or f'Hall {hall.id}',
                'hall_number': hall.hall_number,
                'block': hall.block,
                'floor': hall.floor,
                'total': total,
                'status': 'Marked' if marked else 'Pending'
            })
    else:
        allotments = SeatingAllotment.query.filter_by(exam_date=exam_date).order_by(
            SeatingAllotment.hall_number, SeatingAllotment.year, SeatingAllotment.section
        ).all()
        current_app.logger.info(
            '[hall-attendance:halls] SeatingAllotment rows=%s details=%s',
            len(allotments),
            [(a.id, a.hall_number, a.exam_date.isoformat() if a.exam_date else None, _allotment_student_count(a)) for a in allotments]
        )
        grouped = {}
        for allotment in allotments:
            grouped.setdefault(allotment.hall_number, []).append(allotment)
        for hall_number, hall_allotments in grouped.items():
            seating_ids = [a.id for a in hall_allotments]
            total = sum(_allotment_student_count(a) for a in hall_allotments)
            marked = ExamAttendance.query.filter(ExamAttendance.seating_id.in_(seating_ids)).count() if seating_ids else 0
            payload.append({
                'source': 'allotment',
                'key': hall_number,
                'id': hall_number,
                'hall_name': hall_number,
                'hall_number': hall_number,
                'block': '',
                'floor': '',
                'total': total,
                'status': 'Marked' if marked else 'Pending'
            })

    response_payload = {'halls': payload}
    current_app.logger.info('[hall-attendance:halls] response=%s', response_payload)
    return jsonify(response_payload)


@staff_bp.route('/hall-attendance/students')
@login_required
@any_staff_required
def hall_attendance_students():
    cia_id = request.args.get('cia_id', type=int)
    hall_id = request.args.get('hall_id', type=int)
    hall_key = request.args.get('hall_key', '')
    source = request.args.get('source', 'allocation')
    exam_date = _parse_exam_date(request.args.get('exam_date', ''))
    current_app.logger.info(
        '[hall-attendance:students] params cia_id=%s hall_id=%s hall_key=%s source=%s exam_date_raw=%s parsed=%s',
        cia_id, hall_id, hall_key, source, request.args.get('exam_date', ''), exam_date
    )
    if not cia_id or not exam_date:
        response_payload = {'students': [], 'submitted': False, 'last_by': '', 'last_at': ''}
        current_app.logger.info('[hall-attendance:students] response=%s', response_payload)
        return jsonify(response_payload)

    if source == 'allotment':
        allotments = SeatingAllotment.query.filter_by(hall_number=hall_key, exam_date=exam_date).order_by(
            SeatingAllotment.year, SeatingAllotment.section
        ).all()
        seating_ids = [a.id for a in allotments]
        existing = ExamAttendance.query.filter(ExamAttendance.seating_id.in_(seating_ids)).all() if seating_ids else []
        attendance_map = {
            (att.seating_id, _normalize_register_number(att.register_number)): att
            for att in existing
        }
        student_map = _registered_student_map()
        students = []
        row_no = 1
        for allotment in allotments:
            for reg in allotment.get_register_numbers():
                reg = _normalize_register_number(reg)
                student = student_map.get(reg)
                att = attendance_map.get((allotment.id, reg))
                students.append({
                    'source': 'allotment',
                    'seating_id': allotment.id,
                    'bench_position': row_no,
                    'seat_label': f"Year {allotment.year or '-'} / Section {allotment.section or '-'}",
                    'student_reg_no': reg,
                    'student_name': student.name if student else '',
                    'year': student.year if student and student.year else allotment.year,
                    'department': student.department if student else '',
                    'status': _display_attendance_status(att.status if att else 'present')
                })
                row_no += 1
        last = max(existing, key=lambda a: a.marked_at) if existing else None
        response_payload = {
            'students': students,
            'submitted': bool(existing),
            'last_by': last.marker.name if last and last.marker else '',
            'last_at': last.marked_at.strftime('%d %b %Y %H:%M') if last else ''
        }
        current_app.logger.info(
            '[hall-attendance:students] SeatingAllotment ids=%s student_count=%s response=%s',
            seating_ids, len(students), response_payload
        )
        return jsonify(response_payload)

    if not hall_id:
        response_payload = {'students': [], 'submitted': False, 'last_by': '', 'last_at': ''}
        current_app.logger.info('[hall-attendance:students] response=%s', response_payload)
        return jsonify(response_payload)
    rows = SeatingAllocation.query.filter_by(cia_id=cia_id, hall_id=hall_id, exam_date=exam_date).order_by(
        SeatingAllocation.bench_position, SeatingAllocation.seat_side).all()
    existing = HallAttendance.query.filter_by(cia_id=cia_id, hall_id=hall_id, exam_date=exam_date).all()
    att_map = {_normalize_register_number(a.student_reg_no): a for a in existing}
    last = max(existing, key=lambda a: a.marked_at) if existing else None
    students = []
    for row in rows:
        reg = _normalize_register_number(row.student_reg_no)
        att = att_map.get(reg)
        current_app.logger.info(
            '[hall-attendance:students] row allocation_id=%s cia_id=%s exam_date=%s hall_id=%s register_raw=%s register=%s attendance_found=%s attendance_object=%s',
            row.id, cia_id, exam_date, hall_id, row.student_reg_no, reg, bool(att), repr(att) if att else None
        )
        students.append({'id': row.id, 'bench_position': row.bench_position, 'seat_label': row.seat_label,
                         'source': 'allocation', 'seating_id': row.id,
                         'student_reg_no': reg, 'student_name': row.student_name,
                         'year': row.year, 'department': row.department, 'status': att.status if att else 'Present'})
    response_payload = {'students': students, 'submitted': bool(existing),
                        'last_by': last.invigilator.name if last and last.invigilator else '',
                        'last_at': last.marked_at.strftime('%d %b %Y %H:%M') if last else ''}
    current_app.logger.info(
        '[hall-attendance:students] SeatingAllocation rows=%s response=%s',
        len(rows), response_payload
    )
    return jsonify(response_payload)


@staff_bp.route('/hall-attendance/save', methods=['POST'])
@login_required
@any_staff_required
def save_hall_attendance():
    data = request.get_json(force=True)
    source = data.get('source', 'allocation')
    attendance_items = data.get('attendance', [])
    current_app.logger.info(
        '[hall-attendance:save] source=%s cia_id=%s hall_id=%s hall_key=%s exam_date_raw=%s students_received=%s payload=%s',
        source, data.get('cia_id'), data.get('hall_id'), data.get('hall_key'),
        data.get('exam_date'), len(attendance_items), data
    )
    try:
        cia_id = int(data.get('cia_id'))
        staff_id = int(data.get('staff_id') or current_user.id)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'CIA and staff are required.'}), 400
    exam_date = _parse_exam_date(data.get('exam_date'))
    if not exam_date:
        return jsonify({'ok': False, 'message': 'Valid exam date is required.'}), 400

    try:
        if source == 'allotment':
            saved = inserted = updated = 0
            for idx, item in enumerate(attendance_items, 1):
                reg = _normalize_register_number(item.get('student_reg_no'))
                seating_id = item.get('seating_id')
                current_app.logger.info(
                    '[hall-attendance:save] item=%s source=allotment seating_id=%s register=%s status=%s',
                    idx, seating_id, reg, item.get('status')
                )
                if not reg or not seating_id:
                    continue
                seating = SeatingAllotment.query.get(seating_id)
                if not seating:
                    current_app.logger.warning(
                        '[hall-attendance:save] missing SeatingAllotment seating_id=%s register=%s',
                        seating_id, reg
                    )
                    continue
                status = 'absent' if item.get('status') == 'Absent' else 'present'
                att = ExamAttendance.query.filter_by(seating_id=seating.id, register_number=reg).first()
                if not att:
                    att = ExamAttendance(seating_id=seating.id, hall_number=seating.hall_number, register_number=reg)
                    db.session.add(att)
                    inserted += 1
                    current_app.logger.info('[hall-attendance:save] inserting ExamAttendance=%s', att)
                else:
                    updated += 1
                    current_app.logger.info('[hall-attendance:save] updating ExamAttendance id=%s', att.id)
                att.exam_date = seating.exam_date or exam_date
                att.year = seating.year
                att.section = seating.section
                att.status = status
                att.marked_by = staff_id
                att.marked_at = datetime.utcnow()
                saved += 1
            synced_absence_records = _sync_absence_records_for_cia(cia_id, exam_date, staff_id)
            db.session.commit()
            current_app.logger.info(
                '[hall-attendance:save] commit success table=exam_attendance saved=%s inserted=%s updated=%s absence_records_synced=%s',
                saved, inserted, updated, synced_absence_records
            )
            response_payload = {'ok': True, 'message': f'Attendance saved for {saved} students.'}
            current_app.logger.info('[hall-attendance:save] response=%s', response_payload)
            return jsonify(response_payload)

        try:
            hall_id = int(data.get('hall_id'))
        except (TypeError, ValueError):
            return jsonify({'ok': False, 'message': 'Hall is required.'}), 400
        saved = inserted = updated = 0
        for idx, item in enumerate(attendance_items, 1):
            reg = _normalize_register_number(item.get('student_reg_no'))
            current_app.logger.info(
                '[hall-attendance:save] item=%s source=allocation subject_lookup=cia_date cia_id=%s hall_id=%s exam_date=%s register=%s status=%s',
                idx, cia_id, hall_id, exam_date, reg, item.get('status')
            )
            if not reg:
                continue
            allocation_row = SeatingAllocation.query.filter_by(
                cia_id=cia_id,
                hall_id=hall_id,
                exam_date=exam_date,
                student_reg_no=item.get('student_reg_no')
            ).first()
            if not allocation_row:
                allocation_candidates = SeatingAllocation.query.filter_by(
                    cia_id=cia_id,
                    hall_id=hall_id,
                    exam_date=exam_date
                ).all()
                allocation_row = next(
                    (row for row in allocation_candidates if _normalize_register_number(row.student_reg_no) == reg),
                    None
                )
            current_app.logger.info(
                '[hall-attendance:save] allocation_lookup register=%s cia_id=%s exam_date=%s hall_id=%s found=%s object=%s',
                reg, cia_id, exam_date, hall_id, bool(allocation_row), repr(allocation_row) if allocation_row else None
            )
            att = HallAttendance.query.filter_by(
                cia_id=cia_id,
                hall_id=hall_id,
                student_reg_no=reg,
                exam_date=exam_date
            ).first()
            if not att:
                att = HallAttendance(cia_id=cia_id, hall_id=hall_id, student_reg_no=reg, exam_date=exam_date)
                db.session.add(att)
                inserted += 1
                current_app.logger.info(
                    '[hall-attendance:save] inserting HallAttendance cia_id=%s hall_id=%s register=%s exam_date=%s',
                    cia_id, hall_id, reg, exam_date
                )
            else:
                updated += 1
                current_app.logger.info('[hall-attendance:save] updating HallAttendance id=%s', att.id)
            att.invigilator_staff_id = staff_id
            att.status = item.get('status') or 'Present'
            att.marked_at = datetime.utcnow()
            current_app.logger.info(
                '[hall-attendance:save] prepared HallAttendance object=%s status=%s',
                repr(att), att.status
            )
            saved += 1
        synced_absence_records = _sync_absence_records_for_cia(cia_id, exam_date, staff_id)
        db.session.commit()
        committed_rows = HallAttendance.query.filter_by(cia_id=cia_id, hall_id=hall_id, exam_date=exam_date).all()
        current_app.logger.info(
            '[hall-attendance:save] commit success table=hall_attendance saved=%s inserted=%s updated=%s absence_records_synced=%s committed_rows=%s objects=%s',
            saved, inserted, updated, synced_absence_records, len(committed_rows), [repr(row) for row in committed_rows]
        )
        response_payload = {'ok': True, 'message': f'Attendance saved for {saved} students.'}
        current_app.logger.info('[hall-attendance:save] response=%s', response_payload)
        return jsonify(response_payload)
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception('[hall-attendance:save] rollback after exception: %s', exc)
        return jsonify({'ok': False, 'message': 'Attendance save failed. Check Flask logs.'}), 500


# ─── APPROVE / REJECT ─────────────────────────────────────────
@staff_bp.route('/action/<int:app_id>', methods=['POST'])
@login_required
@staff_required
def action(app_id):
    application = RetestApplication.query.get_or_404(app_id)

    act = request.form.get('action')
    remark = request.form.get('remark','')

    application.staff_status = 'approved' if act == 'approve' else 'rejected'
    application.staff_remark = remark
    application.staff_action_time = datetime.utcnow()
    if act == 'reject':
        application.final_status = 'rejected'

    db.session.commit()
    flash('Action updated successfully', 'success')

    return redirect(url_for('staff.dashboard'))

@staff_bp.route('/absentees/upload', methods=['POST'])
@login_required
@staff_required
def upload_absentees():
    """
    Accept a file OR manual table rows.
    If file is Excel/CSV — parse and store student rows.
    If form has manual rows — store them directly.
    """
    subject_id = request.form.get('subject_id','')
    cia_number = request.form.get('cia_number','')
    semester   = request.form.get('semester','')
    year       = request.form.get('year','')
    section    = (request.form.get('section','') or '').upper()

    if not subject_id or not cia_number:
        flash('Subject and CIA number are required.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if year and not year.isdigit():
        flash('Year must be a valid number.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if section and section not in ('A','B','C','D','E'):
        flash('Section must be one of A, B, C, D, E.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if section and section == '':
        section = ''

    # Check for existing record
    existing = AbsenceRecord.query.filter_by(
        subject_id=int(subject_id), cia_number=int(cia_number)).first()

    students = []

    # ── Parse file upload ────────────────────────────────────────────────────
    f = request.files.get('absentee_file')
    filename_saved = None
    original_name  = None
    if f and f.filename:
        ext = f.filename.rsplit('.',1)[-1].lower()
        if ext not in ALLOWED:
            flash('Only PDF/Excel/Image accepted.', 'danger')
            return redirect(url_for('staff.dashboard'))
        # Save raw file backup
        upload_dir = os.path.join(current_app.root_path, 'static', 'absentees')
        os.makedirs(upload_dir, exist_ok=True)
        safe = f"{uuid.uuid4().hex}.{ext}"
        filepath = os.path.join(upload_dir, safe)
        f.save(filepath)
        filename_saved = safe
        original_name  = f.filename

        # Parse Excel/CSV into student rows
        if ext in ('xlsx','xls','csv'):
            try:
                import pandas as pd
                df = pd.read_excel(filepath) if ext in ('xlsx','xls') else pd.read_csv(filepath)
                df.columns = [normalize_column_name(c) for c in df.columns]
                reg_keys = {
                    'reg_no', 'register_number', 'register_no', 'reg',
                    'regno', 'registernumber', 'registration_number', 'registrar_number'
                }
                name_keys = {
                    'name', 'student_name', 'studentname', 'student name',
                    'studentname'
                }
                for _, row in df.iterrows():
                    reg = ''
                    name = ''
                    row_year = ''
                    row_section = ''
                    for col_name, value in row.items():
                        normalized_col = normalize_column_name(col_name)
                        if not reg and normalized_col in reg_keys:
                            reg = normalize_value(value)
                        if not name and normalized_col in name_keys:
                            name = normalize_value(value)
                        if not row_year and normalized_col in ('year', 'yr'):
                            row_year = normalize_value(value)
                        if not row_section and normalized_col in ('section', 'sec'):
                            row_section = normalize_value(value).upper()
                    if not reg:
                        reg = normalize_value(
                            row.get('reg_no') or row.get('register_number') or
                            row.get('register_no') or row.get('reg') or ''
                        )
                    if not name:
                        name = normalize_value(
                            row.get('name') or row.get('student_name') or ''
                        )
                    if not row_year:
                        row_year = year
                    if not row_section:
                        row_section = section
                    if reg or name:
                        students.append({
                            'reg_no': reg,
                            'register_number': reg,
                            'register_no': reg,
                            'reg': reg,
                            'name': name,
                            'student_name': name,
                            'year': row_year,
                            'section': row_section
                        })
            except Exception as e:
                flash(f'Could not parse file: {e}. Students saved as file only.', 'warning')

    # ── Manual table rows from form ──────────────────────────────────────────
    reg_nos = request.form.getlist('reg_no[]')
    names   = request.form.getlist('name[]')
    for r, n in zip(reg_nos, names):
        r, n = r.strip(), n.strip()
        if r or n:
            students.append({
                'reg_no': r,
                'register_number': r,
                'register_no': r,
                'reg': r,
                'name': n,
                'student_name': n,
                'year': year,
                'section': section
            })

    if existing:
        # Update existing record (edit mode)
        if students:
            existing.set_students(students)
        existing.uploaded_by = current_user.id
        existing.uploaded_at = datetime.utcnow()
        db.session.commit()
        flash(f'Absentee list updated for CIA {cia_number} ({len(students)} students).', 'success')
    else:
        rec = AbsenceRecord(
            subject_id=int(subject_id),
            cia_number=int(cia_number),
            semester=int(semester) if semester else None,
            uploaded_by=current_user.id,
        )
        rec.set_students(students)
        db.session.add(rec)
        db.session.commit()
        flash(f'Absentee list saved for CIA {cia_number} ({len(students)} students).', 'success')

    return redirect(url_for('staff.dashboard'))


@staff_bp.route('/absentees/<int:record_id>/delete', methods=['POST'])
@login_required
@staff_required
def delete_absentee_record(record_id):
    rec = AbsenceRecord.query.get_or_404(record_id)
    db.session.delete(rec)
    db.session.commit()
    flash('Absentee record deleted.', 'success')
    return redirect(url_for('staff.dashboard'))


@staff_bp.route('/absentees/<int:record_id>/get_students')
@login_required
def get_absentee_students(record_id):
    rec = AbsenceRecord.query.get_or_404(record_id)
    return jsonify({'students': rec.get_students(),
                    'subject': rec.subject.subject_name,
                    'cia': rec.cia_number})


# ─── DOWNLOAD APPLICATIONS (FINAL FIXED) ─────────────────────
@staff_bp.route('/applications/download/<fmt>')
@login_required
@staff_required
def download_applications(fmt):

    apps = RetestApplication.query.filter_by(
        staff_id=current_user.id
    ).all()

    rows = [[
        a.id,
        a.student_name,
        a.register_number,
        a.subject.subject_name,
        a.cia_number,
        a.final_status
    ] for a in apps]

    # ─── EXCEL ─────────────────────
    if fmt == 'excel':
        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active

        ws.append(['ID','Name','Reg No','Subject','CIA','Status'])

        for r in rows:
            ws.append(r)

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return send_file(buf,
                         as_attachment=True,
                         download_name='applications.xlsx')

    # ─── PDF ─────────────────────
    else:
        from reportlab.platypus import SimpleDocTemplate, Table

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf)

        data = [['ID','Name','Reg No','Subject','CIA','Status']] + rows

        table = Table(data)
        doc.build([table])

        buf.seek(0)

        return send_file(buf,
                         as_attachment=True,
                         download_name='applications.pdf')
