import os, uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, current_app, jsonify, send_file)
from flask_login import login_required, current_user
from models import db, RetestApplication, AbsenceRecord, Subject
from datetime import datetime
from functools import wraps
import io
import re

staff_bp = Blueprint('staff', __name__)
ALLOWED = {'pdf','jpg','jpeg','png','xlsx','xls','csv'}


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

    if not subject_id or not cia_number:
        flash('Subject and CIA number are required.', 'danger')
        return redirect(url_for('staff.dashboard'))

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
                    for col_name, value in row.items():
                        normalized_col = normalize_column_name(col_name)
                        if not reg and normalized_col in reg_keys:
                            reg = normalize_value(value)
                        if not name and normalized_col in name_keys:
                            name = normalize_value(value)
                    if not reg:
                        reg = normalize_value(
                            row.get('reg_no') or row.get('register_number') or
                            row.get('register_no') or row.get('reg') or ''
                        )
                    if not name:
                        name = normalize_value(
                            row.get('name') or row.get('student_name') or ''
                        )
                    if reg or name:
                        students.append({
                            'reg_no': reg,
                            'register_number': reg,
                            'register_no': reg,
                            'reg': reg,
                            'name': name,
                            'student_name': name
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
                'student_name': n
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