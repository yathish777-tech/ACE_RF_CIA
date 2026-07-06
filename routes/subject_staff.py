import os, uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify, send_file)
from flask_login import login_required, current_user
from models import db, RetestApplication, AbsenceRecord, Subject, User, Hall, SeatingAllocation, HallAttendance
from datetime import datetime
from functools import wraps
import io
import re

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


# ─── ROLE CHECK ───────────────────────────────────────────────
def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (current_user.role == 'subject_staff' or
                current_user.secondary_role == 'subject_staff'):
            flash('Access denied.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


def any_staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        roles = ('subject_staff', 'tutor', 'hod', 'coordinator', 'admin')
        if not (current_user.role in roles or current_user.secondary_role in roles):
            flash('Access denied.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


# ─── DASHBOARD ───────────────────────────────────────────────
@staff_bp.route('/dashboard')
@login_required
@staff_required
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
    exam_date = _parse_exam_date(request.args.get('exam_date', ''))
    if not cia_id or not exam_date:
        return jsonify({'halls': []})
    rows = db.session.query(Hall).join(SeatingAllocation).filter(
        SeatingAllocation.cia_id == cia_id,
        SeatingAllocation.exam_date == exam_date,
        SeatingAllocation.student_reg_no != None
    ).group_by(Hall.id).order_by(Hall.id).all()
    payload = []
    for hall in rows:
        total = SeatingAllocation.query.filter_by(cia_id=cia_id, exam_date=exam_date, hall_id=hall.id).filter(SeatingAllocation.student_reg_no != None).count()
        marked = HallAttendance.query.filter_by(cia_id=cia_id, exam_date=exam_date, hall_id=hall.id).count()
        payload.append({'id': hall.id, 'hall_name': hall.hall_name, 'block': hall.block, 'floor': hall.floor,
                        'total': total, 'status': 'Marked' if marked else 'Pending'})
    return jsonify({'halls': payload})


@staff_bp.route('/hall-attendance/students')
@login_required
@any_staff_required
def hall_attendance_students():
    cia_id = request.args.get('cia_id', type=int)
    hall_id = request.args.get('hall_id', type=int)
    exam_date = _parse_exam_date(request.args.get('exam_date', ''))
    if not cia_id or not hall_id or not exam_date:
        return jsonify({'students': [], 'submitted': False, 'last_by': '', 'last_at': ''})
    rows = SeatingAllocation.query.filter_by(cia_id=cia_id, hall_id=hall_id, exam_date=exam_date).order_by(
        SeatingAllocation.bench_position, SeatingAllocation.seat_side).all()
    existing = HallAttendance.query.filter_by(cia_id=cia_id, hall_id=hall_id, exam_date=exam_date).all()
    att_map = {a.student_reg_no: a for a in existing}
    last = max(existing, key=lambda a: a.marked_at) if existing else None
    students = []
    for row in rows:
        att = att_map.get(row.student_reg_no)
        students.append({'id': row.id, 'bench_position': row.bench_position, 'seat_label': row.seat_label,
                         'student_reg_no': row.student_reg_no, 'student_name': row.student_name,
                         'year': row.year, 'department': row.department, 'status': att.status if att else 'Present'})
    return jsonify({'students': students, 'submitted': bool(existing),
                    'last_by': last.invigilator.name if last and last.invigilator else '',
                    'last_at': last.marked_at.strftime('%d %b %Y %H:%M') if last else ''})


@staff_bp.route('/hall-attendance/save', methods=['POST'])
@login_required
@any_staff_required
def save_hall_attendance():
    data = request.get_json(force=True)
    try:
        cia_id = int(data.get('cia_id'))
        hall_id = int(data.get('hall_id'))
        staff_id = int(data.get('staff_id') or current_user.id)
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'message': 'CIA, hall, and staff are required.'}), 400
    exam_date = _parse_exam_date(data.get('exam_date'))
    if not exam_date:
        return jsonify({'ok': False, 'message': 'Valid exam date is required.'}), 400
    saved = 0
    for item in data.get('attendance', []):
        reg = item.get('student_reg_no')
        if not reg:
            continue
        att = HallAttendance.query.filter_by(cia_id=cia_id, hall_id=hall_id, student_reg_no=reg, exam_date=exam_date).first()
        if not att:
            att = HallAttendance(cia_id=cia_id, hall_id=hall_id, student_reg_no=reg, exam_date=exam_date)
            db.session.add(att)
        att.invigilator_staff_id = staff_id
        att.status = item.get('status') or 'Present'
        att.marked_at = datetime.utcnow()
        saved += 1
    db.session.commit()
    return jsonify({'ok': True, 'message': f'Attendance saved for {saved} students.'})


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
