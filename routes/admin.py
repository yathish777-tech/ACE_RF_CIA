import os, io, uuid
from flask import (Blueprint, render_template, redirect, url_for,
                   flash, request, jsonify, current_app, send_file)
from flask_login import login_required, current_user
from models import db, User, Subject, CIADate, RetestApplication, AbsenceRecord, SubjectStaffSection, SeatingAllotment, ExamAttendance
from datetime import datetime, date, timedelta
from functools import wraps

admin_bp = Blueprint('admin', __name__)

SEMESTER_TO_YEAR = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4}
SECTIONS = ['A', 'B', 'C']

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if current_user.role != 'admin':
            flash('Access denied.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated


# ─── DASHBOARD ──────────────────────────────────────────────────────────────
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_apps     = RetestApplication.query.count()
    approved       = RetestApplication.query.filter_by(final_status='approved').count()
    rejected       = RetestApplication.query.filter_by(final_status='rejected').count()
    pending        = RetestApplication.query.filter_by(final_status='pending').count()
    pre_count      = RetestApplication.query.filter_by(submission_type='pre').count()
    late_count     = RetestApplication.query.filter_by(submission_type='late').count()
    total_students = User.query.filter_by(role='student').count()
    total_staff    = User.query.filter(
        User.role.in_(['subject_staff','tutor','hod','coordinator'])).count()

    subjects = Subject.query.filter_by(is_active=True).all()
    subject_stats = sorted([
        {'name': s.subject_name, 'code': s.subject_code,
         'count': RetestApplication.query.filter_by(subject_id=s.id).count()}
        for s in subjects], key=lambda x: x['count'], reverse=True)

    recent_apps = RetestApplication.query\
        .order_by(RetestApplication.submitted_at.desc()).limit(10).all()

    # Year-wise section-wise stats
    year_section_stats = _get_year_section_stats()

    stats = {'total': total_apps, 'approved': approved, 'rejected': rejected,
             'pending': pending, 'pre': pre_count, 'late': late_count,
             'students': total_students, 'staff': total_staff}
    return render_template('admin/dashboard.html', stats=stats,
                           subject_stats=subject_stats, recent_apps=recent_apps,
                           year_section_stats=year_section_stats, sections=SECTIONS)


def _get_year_section_stats():
    """Returns year->section->list of applications mapping."""
    apps = RetestApplication.query.all()
    stats = {}
    for year in range(1, 5):
        stats[year] = {}
        for sec in SECTIONS:
            year_apps = [a for a in apps
                         if (a.student_year == year and a.student_section == sec)]
            stats[year][sec] = {
                'total': len(year_apps),
                'approved': sum(1 for a in year_apps if a.final_status == 'approved'),
                'rejected': sum(1 for a in year_apps if a.final_status == 'rejected'),
                'pending': sum(1 for a in year_apps if a.final_status == 'pending'),
                'apps': year_apps
            }
    return stats


# ─── BULK UPLOAD PAGE (GET) ──────────────────────────────────────────────────
@admin_bp.route('/bulk-upload', methods=['GET'])
@login_required
@admin_required
def bulk_upload():
    subjects  = Subject.query.order_by(Subject.subject_name).all()
    cia_dates = CIADate.query.order_by(CIADate.exam_date.desc()).all()
    staff_list = User.query.filter(
        User.role.in_(['subject_staff','tutor','hod','coordinator'])
    ).order_by(User.name).all()
    sss_list = SubjectStaffSection.query.order_by(
        SubjectStaffSection.semester, SubjectStaffSection.section).all()
    return render_template('admin/bulk_upload.html',
                           subjects=subjects, cia_dates=cia_dates,
                           staff_list=staff_list, sss_list=sss_list)


# ─── UPLOAD 1: STAFF DETAILS FILE ───────────────────────────────────────────
@admin_bp.route('/bulk-upload/staff', methods=['POST'])
@login_required
@admin_required
def bulk_upload_staff():
    """
    Upload Staff Details Excel/CSV.
    Required columns: staff_name, staff_email, role, phone, handling_year, handling_section
    """
    f = request.files.get('staff_file')
    if not f or not f.filename:
        flash('Please select a Staff Details file.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx','xls','csv'):
        flash('Only Excel (.xlsx/.xls) or CSV files accepted.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    try:
        import pandas as pd
        df = pd.read_csv(f) if ext == 'csv' else pd.read_excel(f, dtype=str)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        added = updated = 0
        VALID_ROLES = ('subject_staff', 'tutor', 'hod', 'coordinator')

        for _, row in df.iterrows():
            row = {k: (str(v).strip() if str(v).strip().lower() not in ('nan','none','') else '')
                   for k, v in row.items()}
            name  = row.get('staff_name') or row.get('name', '')
            email = (row.get('staff_email') or row.get('email', '')).lower()
            role  = (row.get('role') or row.get('staff_role', 'subject_staff'))\
                    .strip().lower().replace(' ', '_')
            dept  = row.get('department', '')
            phone = row.get('phone', '') or row.get('phone_number', '')
            h_year = row.get('handling_year', '')
            h_sec  = (row.get('handling_section', '') or '').upper().strip()

            if not email or not name:
                continue
            if role not in VALID_ROLES:
                role = 'subject_staff'

            h_year_int = int(float(h_year)) if h_year else None
            h_sec_val = h_sec if h_sec in ('A','B','C') else None

            existing = User.query.filter(db.func.lower(User.email) == email).first()
            if existing:
                if existing.role != role and not existing.secondary_role:
                    existing.secondary_role = role
                if dept:  existing.department = dept
                if phone: existing.phone = phone
                if h_year_int: existing.handling_year = h_year_int
                if h_sec_val:  existing.handling_section = h_sec_val
                updated += 1
            else:
                u = User(name=name, email=email, role=role,
                         department=dept, phone=phone,
                         handling_year=h_year_int, handling_section=h_sec_val)
                u.set_password('staff123')
                db.session.add(u)
                added += 1

        db.session.commit()
        flash(f'Staff upload complete: {added} added, {updated} updated. '
              f'Default password for new accounts: staff123', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Staff upload error: {e}', 'danger')
    return redirect(url_for('admin.bulk_upload'))


# ─── UPLOAD 2: SUBJECT FILE ──────────────────────────────────────────────────
@admin_bp.route('/bulk-upload/subjects', methods=['POST'])
@login_required
@admin_required
def bulk_upload_subjects():
    """
    Upload Subject Details Excel/CSV.
    Columns: subject_name, subject_code, semester, section, shsn (staff email or name),
             department
    Each row = one subject+section+staff combo.
    """
    f = request.files.get('subject_file')
    if not f or not f.filename:
        flash('Please select a Subject file.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx','xls','csv'):
        flash('Only Excel (.xlsx/.xls) or CSV files accepted.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    try:
        import pandas as pd
        df = pd.read_csv(f) if ext == 'csv' else pd.read_excel(f, dtype=str)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        added_sub = added_map = updated_map = 0

        for _, row in df.iterrows():
            row = {k: (str(v).strip() if str(v).strip().lower() not in ('nan','none','') else '')
                   for k, v in row.items()}
            sub_name  = row.get('subject_name') or row.get('subject', '')
            sub_code  = row.get('subject_code') or row.get('code', '')
            semester  = row.get('semester', '')
            section   = (row.get('section', '') or '').upper().strip()
            shsn      = row.get('shsn') or row.get('staff_email') or row.get('staff_name', '')
            dept      = row.get('department', '')

            if not (sub_name and sub_code and semester):
                continue

            sem_int = int(float(semester))
            year    = SEMESTER_TO_YEAR.get(sem_int, 1)
            sec_val = section if section in ('A','B','C') else None

            # Find/create subject
            subject = Subject.query.filter_by(
                subject_code=sub_code, semester=sem_int).first()
            if not subject:
                subject = Subject(subject_name=sub_name, subject_code=sub_code,
                                  semester=sem_int, department=dept, year=year)
                db.session.add(subject)
                db.session.flush()
                added_sub += 1
            else:
                if dept: subject.department = dept

            # Resolve staff by email or name
            staff_obj = None
            if shsn:
                if '@' in shsn:
                    staff_obj = User.query.filter(
                        db.func.lower(User.email) == shsn.lower()).first()
                else:
                    staff_obj = User.query.filter(
                        db.func.lower(User.name) == shsn.lower()).first()

            # Set default staff on subject
            if staff_obj and not subject.staff_id:
                subject.staff_id = staff_obj.id

            # Create section mapping if section specified
            if sec_val and staff_obj:
                existing_sss = SubjectStaffSection.query.filter_by(
                    subject_id=subject.id, section=sec_val, semester=sem_int).first()
                if existing_sss:
                    existing_sss.staff_id = staff_obj.id
                    updated_map += 1
                else:
                    db.session.add(SubjectStaffSection(
                        subject_id=subject.id, staff_id=staff_obj.id,
                        semester=sem_int, section=sec_val))
                    added_map += 1

        db.session.commit()
        flash(f'Subject upload complete: {added_sub} subjects created, '
              f'{added_map} section mappings added, {updated_map} updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Subject upload error: {e}', 'danger')
    return redirect(url_for('admin.bulk_upload'))


# ─── UPLOAD 3: CIA SCHEDULE FILE ─────────────────────────────────────────────
@admin_bp.route('/bulk-upload/cia', methods=['POST'])
@login_required
@admin_required
def bulk_upload_cia():
    """
    Upload CIA Schedule Excel/CSV.
    Required: subject_code, semester, cia_number, cia_exam_date
    Optional: cia_deadline_date, cia_retest_date, academic_year, section
    """
    f = request.files.get('cia_file')
    if not f or not f.filename:
        flash('Please select a CIA Schedule file.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    ext = f.filename.rsplit('.', 1)[-1].lower()
    if ext not in ('xlsx','xls','csv'):
        flash('Only Excel (.xlsx/.xls) or CSV files accepted.', 'danger')
        return redirect(url_for('admin.bulk_upload'))
    try:
        import pandas as pd
        df = pd.read_csv(f) if ext == 'csv' else pd.read_excel(f, dtype=str)
        df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]

        added_cia = updated_cia = 0

        for _, row in df.iterrows():
            row = {k: (str(v).strip() if str(v).strip().lower() not in ('nan','none','') else '')
                   for k, v in row.items()}

            sub_code   = row.get('subject_code') or row.get('code', '')
            sub_name   = row.get('subject_name') or row.get('subject', '')
            semester   = row.get('semester', '')
            cia_num    = row.get('cia_number') or row.get('cia_no', '')
            exam_str   = row.get('cia_exam_date') or row.get('exam_date', '')
            retest_str = row.get('cia_retest_date') or row.get('retest_date', '')
            dead_str   = row.get('cia_deadline_date') or row.get('deadline', '') or row.get('cia_deadline', '')
            acad_year  = row.get('academic_year', '')

            if not (semester and cia_num and exam_str):
                continue

            sem_int = int(float(semester))
            cia_int = int(float(cia_num))

            # Find subject
            subject = None
            if sub_code:
                subject = Subject.query.filter_by(
                    subject_code=sub_code, semester=sem_int).first()
            if not subject and sub_name:
                subject = Subject.query.filter_by(
                    subject_name=sub_name, semester=sem_int).first()
            if not subject:
                continue

            try:
                ed = pd.to_datetime(exam_str).date()
                rd = pd.to_datetime(retest_str).date() if retest_str else None
                nd = pd.to_datetime(dead_str).date()   if dead_str   else None
            except Exception:
                continue

            existing = CIADate.query.filter_by(
                subject_id=subject.id, cia_number=cia_int).first()
            if existing:
                existing.exam_date = ed
                if rd: existing.retest_date = rd
                if nd: existing.application_end_date = nd
                if acad_year: existing.academic_year = acad_year
                updated_cia += 1
            else:
                db.session.add(CIADate(
                    subject_id=subject.id, cia_number=cia_int,
                    exam_date=ed, retest_date=rd,
                    application_end_date=nd, semester=sem_int,
                    academic_year=acad_year, created_by=current_user.id))
                added_cia += 1

        db.session.commit()
        flash(f'CIA Schedule upload complete: {added_cia} added, {updated_cia} updated.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'CIA upload error: {e}', 'danger')
    return redirect(url_for('admin.bulk_upload'))


# ─── PORTAL WINDOW CONTROLS ──────────────────────────────────────────────────
@admin_bp.route('/cia-dates/<int:cid>/toggle-window', methods=['POST'])
@login_required
def toggle_retest_window(cid):
    allowed = (current_user.role == 'admin' or
               current_user.role == 'hod' or
               current_user.secondary_role == 'hod')
    if not allowed:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    cia = CIADate.query.get_or_404(cid)
    cia.application_window_open = not cia.application_window_open
    db.session.commit()
    state = 'OPENED' if cia.application_window_open else 'CLOSED'
    flash(f'Portal window {state} for {cia.subject.subject_name} — CIA {cia.cia_number}.', 'success')
    return redirect(request.referrer or url_for('admin.manage_cia_dates'))


@admin_bp.route('/cia-dates/<int:cid>/set-window', methods=['POST'])
@login_required
def set_retest_window(cid):
    allowed = (current_user.role == 'admin' or
               current_user.role == 'hod' or
               current_user.secondary_role == 'hod')
    if not allowed:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    cia = CIADate.query.get_or_404(cid)
    open_date = request.form.get('open_until_date', '').strip()
    try:
        new_end = datetime.strptime(open_date, '%Y-%m-%d').date()
        cia.application_end_date    = new_end
        cia.application_window_open = True
        db.session.commit()
        flash(f'Portal reopened for {cia.subject.subject_name} CIA {cia.cia_number}. '
              f'New deadline: {new_end.strftime("%d %b %Y")}.', 'success')
    except ValueError:
        flash('Invalid date format.', 'danger')
    return redirect(request.referrer or url_for('admin.manage_cia_dates'))


# ─── DOWNLOAD APPLICATIONS (year/section filter) ─────────────────────────────
@admin_bp.route('/applications/download/<fmt>')
@login_required
@admin_required
def download_applications(fmt):
    year_filter    = request.args.get('year', type=int)
    section_filter = request.args.get('section', '')

    query = RetestApplication.query
    if year_filter:
        query = query.filter_by(student_year=year_filter)
    if section_filter:
        query = query.filter_by(student_section=section_filter)
    apps = query.order_by(RetestApplication.submitted_at.desc()).all()

    rows = [{'ID': a.id, 'Student': a.student_name, 'Reg No': a.register_number,
             'Email': a.student_email,
             'Year': a.student_year or '', 'Section': a.student_section or '',
             'Subject': a.subject.subject_name, 'Code': a.subject.subject_code,
             'Semester': a.semester, 'CIA No': a.cia_number, 'CIA Date': str(a.cia_date),
             'Reason': a.reason_type.replace('_', ' ').title(),
             'Type': a.submission_type.upper(),
             'Staff': a.staff_status, 'Tutor': a.tutor_status,
             'Coordinator': a.coordinator_status, 'HOD': a.hod_status,
             'Final': a.final_status,
             'Submitted': a.submitted_at.strftime('%d %b %Y %H:%M')} for a in apps]

    label = ''
    if year_filter: label += f'_Year{year_filter}'
    if section_filter: label += f'_Sec{section_filter}'

    if fmt == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'Applications'
        if rows:
            hdrs = list(rows[0].keys())
            for ci, h in enumerate(hdrs, 1):
                c = ws.cell(1, ci, h)
                c.font = Font(bold=True, color='FFFFFF', name='Arial')
                c.fill = PatternFill('solid', fgColor='1A237E')
                c.alignment = Alignment(horizontal='center')
            for ri, row in enumerate(rows, 2):
                for ci, v in enumerate(row.values(), 1):
                    ws.cell(ri, ci, v)
                bg = ('E8F5E9' if row['Final'] == 'approved' else
                      'FFEBEE' if row['Final'] == 'rejected' else 'FFFFFF')
                for ci in range(1, len(hdrs)+1):
                    ws.cell(ri, ci).fill = PatternFill('solid', fgColor=bg)
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = 16
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, as_attachment=True,
            download_name=f'applications{label}_{datetime.now().strftime("%Y%m%d")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=20, rightMargin=20, topMargin=30, bottomMargin=20)
        styles = getSampleStyleSheet()
        title_str = 'CIA Retest Applications'
        if year_filter: title_str += f' — Year {year_filter}'
        if section_filter: title_str += f', Section {section_filter}'
        els = [Paragraph(title_str, styles['Title']),
               Paragraph(f'Generated: {datetime.now().strftime("%d %b %Y %H:%M")}',
                         styles['Normal']), Spacer(1, 12)]
        if rows:
            hdrs = ['#', 'Student', 'Reg No', 'Yr', 'Sec', 'Subject', 'Sem', 'CIA',
                    'Type', 'Staff', 'Tutor', 'HOD', 'Final']
            td = [hdrs] + [[str(r['ID']), r['Student'][:16], r['Reg No'],
                             str(r['Year']), str(r['Section']),
                             r['Subject'][:16], str(r['Semester']),
                             str(r['CIA No']), r['Type'],
                             r['Staff'].upper(), r['Tutor'].upper(),
                             r['HOD'].upper(), r['Final'].upper()] for r in rows]
            t = Table(td, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A237E')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F5F7FF')]),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ]))
            els.append(t)
        doc.build(els); buf.seek(0)
        return send_file(buf, as_attachment=True,
            download_name=f'applications{label}_{datetime.now().strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf')


# ─── ALL APPLICATIONS (with year/section filter) ──────────────────────────────
@admin_bp.route('/applications')
@login_required
@admin_required
def all_applications():
    year_filter    = request.args.get('year', type=int)
    section_filter = request.args.get('section', '')
    query = RetestApplication.query
    if year_filter:
        query = query.filter_by(student_year=year_filter)
    if section_filter:
        query = query.filter_by(student_section=section_filter)
    apps = query.order_by(RetestApplication.submitted_at.desc()).all()
    year_section_stats = _get_year_section_stats()
    return render_template('admin/all_applications.html', apps=apps,
                           year_section_stats=year_section_stats,
                           sections=SECTIONS,
                           year_filter=year_filter,
                           section_filter=section_filter)


@admin_bp.route('/applications/<int:app_id>')
@login_required
@admin_required
def view_application(app_id):
    app = RetestApplication.query.get_or_404(app_id)
    return render_template('admin/view_application.html', app=app)


# ─── STAFF MANAGEMENT ────────────────────────────────────────────────────────
@admin_bp.route('/staff')
@login_required
@admin_required
def manage_staff():
    staff_list = User.query.filter(
        User.role.in_(['subject_staff','tutor','hod','coordinator'])
    ).order_by(User.name).all()
    return render_template('admin/manage_staff.html', staff_list=staff_list)


@admin_bp.route('/staff/add', methods=['POST'])
@login_required
@admin_required
def add_staff():
    name = request.form.get('name','').strip()
    email = request.form.get('email','').strip().lower()
    phone = request.form.get('phone','').strip()
    role = request.form.get('role','')
    secondary = request.form.get('secondary_role','').strip() or None
    department = request.form.get('department','').strip()
    password = request.form.get('password','staff123').strip() or 'staff123'
    h_year = request.form.get('handling_year','').strip()
    h_sec  = request.form.get('handling_section','').strip().upper()
    if role == 'admin':
        flash('Cannot add Admin here.','danger')
        return redirect(url_for('admin.manage_staff'))
    existing = User.query.filter_by(email=email).first()
    if existing:
        flash('Email exists. Use Edit to change roles.','danger')
        return redirect(url_for('admin.manage_staff'))
    u = User(name=name, email=email, phone=phone, role=role,
             secondary_role=secondary, department=department,
             handling_year=int(h_year) if h_year else None,
             handling_section=h_sec if h_sec in ('A','B','C') else None)
    u.set_password(password)
    db.session.add(u); db.session.commit()
    flash(f'Staff added! Default password: {password}', 'success')
    return redirect(url_for('admin.manage_staff'))


@admin_bp.route('/staff/edit/<int:uid>', methods=['POST'])
@login_required
@admin_required
def edit_staff(uid):
    u = User.query.get_or_404(uid)
    u.name = request.form.get('name', u.name).strip()
    u.phone = request.form.get('phone', u.phone or '').strip()
    u.department = request.form.get('department', u.department or '').strip()
    sec = request.form.get('secondary_role','').strip()
    u.secondary_role = sec if sec else None
    h_year = request.form.get('handling_year','').strip()
    h_sec  = request.form.get('handling_section','').strip().upper()
    u.handling_year = int(h_year) if h_year else None
    u.handling_section = h_sec if h_sec in ('A','B','C') else None
    pw = request.form.get('password','').strip()
    if pw: u.set_password(pw)
    db.session.commit(); flash('Staff updated.','success')
    return redirect(url_for('admin.manage_staff'))


@admin_bp.route('/staff/delete/<int:uid>', methods=['POST'])
@login_required
@admin_required
def delete_staff(uid):
    u = User.query.get_or_404(uid)
    linked = RetestApplication.query.filter(
        (RetestApplication.staff_id == uid) | (RetestApplication.tutor_id == uid)).count()
    if linked:
        flash(f'Cannot delete — linked to {linked} application(s).','danger')
        return redirect(url_for('admin.manage_staff'))
    db.session.delete(u); db.session.commit()
    flash(f'"{u.name}" deleted.', 'success')
    return redirect(url_for('admin.manage_staff'))


@admin_bp.route('/staff/toggle/<int:uid>', methods=['POST'])
@login_required
@admin_required
def toggle_staff(uid):
    u = User.query.get_or_404(uid)
    u.is_active = not u.is_active; db.session.commit()
    flash(f'User {"activated" if u.is_active else "deactivated"}.','success')
    return redirect(url_for('admin.manage_staff'))


# ─── SUBJECT MANAGEMENT ──────────────────────────────────────────────────────
@admin_bp.route('/subjects')
@login_required
@admin_required
def manage_subjects():
    subjects = Subject.query.order_by(Subject.semester, Subject.subject_name).all()
    staff_list = User.query.filter(
        (User.role == 'subject_staff') | (User.secondary_role == 'subject_staff'),
        User.is_active == True).order_by(User.name).all()
    sss_list = SubjectStaffSection.query.order_by(
        SubjectStaffSection.semester, SubjectStaffSection.section).all()
    return render_template('admin/manage_subjects.html',
                           subjects=subjects, staff_list=staff_list,
                           sss_list=sss_list, sections=SECTIONS)


@admin_bp.route('/subjects/add', methods=['POST'])
@login_required
@admin_required
def add_subject():
    sem = int(request.form.get('semester', 1))
    s = Subject(
        subject_name=request.form.get('subject_name','').strip(),
        subject_code=request.form.get('subject_code','').strip(),
        semester=sem,
        year=SEMESTER_TO_YEAR.get(sem, 1),
        department=request.form.get('department','').strip(),
        staff_id=int(request.form.get('staff_id')) if request.form.get('staff_id') else None)
    db.session.add(s); db.session.commit(); flash('Subject added.','success')
    return redirect(url_for('admin.manage_subjects'))


@admin_bp.route('/subjects/edit/<int:sid>', methods=['POST'])
@login_required
@admin_required
def edit_subject(sid):
    s = Subject.query.get_or_404(sid)
    s.subject_name = request.form.get('subject_name', s.subject_name)
    s.subject_code = request.form.get('subject_code', s.subject_code)
    s.semester     = int(request.form.get('semester', s.semester))
    s.year         = SEMESTER_TO_YEAR.get(s.semester, 1)
    s.department   = request.form.get('department', s.department)
    s.staff_id     = int(request.form.get('staff_id')) if request.form.get('staff_id') else None
    s.is_active    = request.form.get('is_active') == 'on'
    db.session.commit(); flash('Subject updated.','success')
    return redirect(url_for('admin.manage_subjects'))


@admin_bp.route('/subjects/delete/<int:sid>', methods=['POST'])
@login_required
@admin_required
def delete_subject(sid):
    s = Subject.query.get_or_404(sid)
    linked = RetestApplication.query.filter_by(subject_id=sid).count()
    if linked:
        flash(f'Cannot delete — {linked} application(s) exist.','danger')
        return redirect(url_for('admin.manage_subjects'))
    SubjectStaffSection.query.filter_by(subject_id=sid).delete()
    CIADate.query.filter_by(subject_id=sid).delete()
    db.session.delete(s); db.session.commit()
    flash('Subject deleted.','success')
    return redirect(url_for('admin.manage_subjects'))


# ─── SECTION-STAFF MAPPING (SubjectStaffSection) ─────────────────────────────
@admin_bp.route('/subjects/section-map/add', methods=['POST'])
@login_required
@admin_required
def add_section_map():
    subject_id = int(request.form.get('subject_id'))
    staff_id   = int(request.form.get('staff_id'))
    semester   = int(request.form.get('semester'))
    section    = request.form.get('section','').upper().strip()
    if section not in ('A','B','C'):
        flash('Invalid section.','danger')
        return redirect(url_for('admin.manage_subjects'))
    existing = SubjectStaffSection.query.filter_by(
        subject_id=subject_id, semester=semester, section=section).first()
    if existing:
        existing.staff_id = staff_id
        flash('Section mapping updated.','success')
    else:
        db.session.add(SubjectStaffSection(
            subject_id=subject_id, staff_id=staff_id,
            semester=semester, section=section))
        flash('Section mapping added.','success')
    db.session.commit()
    return redirect(url_for('admin.manage_subjects'))


@admin_bp.route('/subjects/section-map/delete/<int:mid>', methods=['POST'])
@login_required
@admin_required
def delete_section_map(mid):
    m = SubjectStaffSection.query.get_or_404(mid)
    db.session.delete(m); db.session.commit()
    flash('Section mapping removed.','success')
    return redirect(url_for('admin.manage_subjects'))


# ─── CIA DATES ────────────────────────────────────────────────────────────────
@admin_bp.route('/cia-dates')
@login_required
@admin_required
def manage_cia_dates():
    subjects  = Subject.query.filter_by(is_active=True).order_by(Subject.subject_name).all()
    cia_dates = CIADate.query.order_by(CIADate.exam_date.desc()).all()
    return render_template('admin/manage_cia_dates.html',
                           subjects=subjects, cia_dates=cia_dates, today=date.today())


@admin_bp.route('/cia-dates/add', methods=['POST'])
@login_required
@admin_required
def add_cia_date():
    try:
        ed = datetime.strptime(request.form.get('exam_date'), '%Y-%m-%d').date()
        rs = request.form.get('retest_date','').strip()
        es = request.form.get('application_end_date','').strip()
        rd = datetime.strptime(rs, '%Y-%m-%d').date() if rs else None
        nd = datetime.strptime(es, '%Y-%m-%d').date() if es else None
        db.session.add(CIADate(
            subject_id=int(request.form.get('subject_id')),
            cia_number=int(request.form.get('cia_number')),
            exam_date=ed, retest_date=rd, application_end_date=nd,
            semester=int(request.form.get('semester')),
            academic_year=request.form.get('academic_year','').strip(),
            created_by=current_user.id))
        db.session.commit(); flash('CIA date added.','success')
    except Exception as e:
        flash(f'Error: {e}','danger')
    return redirect(url_for('admin.manage_cia_dates'))


@admin_bp.route('/cia-dates/edit/<int:cid>', methods=['POST'])
@login_required
@admin_required
def edit_cia_date(cid):
    c = CIADate.query.get_or_404(cid)
    try:
        c.exam_date = datetime.strptime(request.form.get('exam_date'), '%Y-%m-%d').date()
        rs = request.form.get('retest_date','').strip()
        es = request.form.get('application_end_date','').strip()
        c.retest_date          = datetime.strptime(rs,'%Y-%m-%d').date() if rs else None
        c.application_end_date = datetime.strptime(es,'%Y-%m-%d').date() if es else None
        c.academic_year        = request.form.get('academic_year', c.academic_year)
        db.session.commit(); flash('CIA date updated.','success')
    except Exception as e:
        flash(f'Error: {e}','danger')
    return redirect(url_for('admin.manage_cia_dates'))


@admin_bp.route('/cia-dates/delete/<int:cid>', methods=['POST'])
@login_required
@admin_required
def delete_cia_date(cid):
    c = CIADate.query.get_or_404(cid)
    db.session.delete(c); db.session.commit()
    flash('CIA date deleted.','success')
    return redirect(url_for('admin.manage_cia_dates'))


# ─── ABSENTEES ───────────────────────────────────────────────────────────────
@admin_bp.route('/absentees')
@login_required
@admin_required
def view_absentees():
    records_cia1 = AbsenceRecord.query.filter_by(cia_number=1)\
        .order_by(AbsenceRecord.uploaded_at.desc()).all()
    records_cia2 = AbsenceRecord.query.filter_by(cia_number=2)\
        .order_by(AbsenceRecord.uploaded_at.desc()).all()
    records_cia3 = AbsenceRecord.query.filter_by(cia_number=3)\
        .order_by(AbsenceRecord.uploaded_at.desc()).all()
    return render_template('admin/absentees.html',
                           records_cia1=records_cia1,
                           records_cia2=records_cia2,
                           records_cia3=records_cia3)


@admin_bp.route('/absentees/download/cia<int:cia_num>/<fmt>')
@login_required
@admin_required
def download_absentees_cia(cia_num, fmt):
    records = AbsenceRecord.query.filter_by(cia_number=cia_num)\
              .order_by(AbsenceRecord.uploaded_at.desc()).all()
    rows = []
    for rec in records:
        students = rec.get_students()
        if students:
            for s in students:
                rows.append({'Subject': rec.subject.subject_name,
                             'Code': rec.subject.subject_code, 'CIA': cia_num,
                             'Semester': rec.semester or '',
                             'Reg No': s.get('reg_no',''),
                             'Student Name': s.get('name',''),
                             'Uploaded By': rec.uploader.name,
                             'Date': rec.uploaded_at.strftime('%d %b %Y')})
        else:
            rows.append({'Subject': rec.subject.subject_name,
                         'Code': rec.subject.subject_code, 'CIA': cia_num,
                         'Semester': rec.semester or '',
                         'Reg No': '—', 'Student Name': '(file only)',
                         'Uploaded By': rec.uploader.name,
                         'Date': rec.uploaded_at.strftime('%d %b %Y')})
    if fmt == 'excel':
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        wb = openpyxl.Workbook(); ws = wb.active
        ws.title = f'CIA {cia_num} Absentees'
        hdrs = ['Subject','Code','CIA','Semester','Reg No','Student Name',
                'Uploaded By','Date']
        for ci, h in enumerate(hdrs, 1):
            c = ws.cell(1, ci, h)
            c.font = Font(bold=True, color='FFFFFF', name='Arial', size=10)
            c.fill = PatternFill('solid', fgColor='1A237E')
            c.alignment = Alignment(horizontal='center')
        for ri, row in enumerate(rows, 2):
            for ci, v in enumerate([row[h] for h in hdrs], 1):
                ws.cell(ri, ci, v).fill = PatternFill(
                    'solid', fgColor='F5F7FF' if ri % 2 == 0 else 'FFFFFF')
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = 18
        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
        return send_file(buf, as_attachment=True,
            download_name=f'absentees_CIA{cia_num}_{datetime.now().strftime("%Y%m%d")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import (SimpleDocTemplate, Table,
                                        TableStyle, Paragraph, Spacer)
        from reportlab.lib.styles import getSampleStyleSheet
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=30, rightMargin=30,
                                topMargin=40, bottomMargin=30)
        styles = getSampleStyleSheet()
        els = [Paragraph(f'Absentee List — CIA {cia_num}', styles['Title']),
               Paragraph(f'Generated: {datetime.now().strftime("%d %b %Y %H:%M")}',
                         styles['Normal']), Spacer(1, 12)]
        if rows:
            hdrs = ['Subject', 'CIA', 'Sem', 'Reg No', 'Student Name', 'Uploaded By']
            td = [hdrs] + [[r['Subject'][:18], str(r['CIA']),
                             str(r['Semester']), r['Reg No'],
                             r['Student Name'], r['Uploaded By']] for r in rows]
            t = Table(td, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0),(-1,0), colors.HexColor('#1A237E')),
                ('TEXTCOLOR',  (0,0),(-1,0), colors.white),
                ('FONTNAME',   (0,0),(-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0),(-1,-1), 9),
                ('GRID',       (0,0),(-1,-1), 0.5, colors.grey),
                ('ROWBACKGROUNDS', (0,1),(-1,-1),
                 [colors.white, colors.HexColor('#EEF2FF')]),
                ('ALIGN',      (0,0),(-1,-1), 'CENTER'),
            ]))
            els.append(t)
        doc.build(els); buf.seek(0)
        return send_file(buf, as_attachment=True,
            download_name=f'absentees_CIA{cia_num}_{datetime.now().strftime("%Y%m%d")}.pdf',
            mimetype='application/pdf')



# ─── RETRANSMIT ───────────────────────────────────────────────────────────────
@admin_bp.route('/applications/<int:app_id>/retransmit', methods=['POST'])
@login_required
def retransmit(app_id):
    # Allow the approval roles to restart a rejected application from the failed stage.
    allowed = (current_user.role in ('admin', 'hod', 'tutor', 'subject_staff') or
               current_user.secondary_role in ('hod', 'tutor', 'subject_staff'))
    if not allowed:
        flash('Access denied. Only approval staff can retransmit.', 'danger')
        return redirect(url_for('main.index'))

    app = RetestApplication.query.get_or_404(app_id)
    if (current_user.role == 'subject_staff' or current_user.secondary_role == 'subject_staff') and app.staff_id != current_user.id:
        flash('You can retransmit only applications assigned to you.', 'danger')
        return redirect(url_for('staff.dashboard'))

    if app.final_status != 'rejected':
        flash('Only rejected applications can be retransmitted.', 'warning')
        if current_user.role == 'subject_staff' or current_user.secondary_role == 'subject_staff':
            return redirect(url_for('staff.dashboard'))
        if current_user.role == 'tutor' or current_user.secondary_role == 'tutor':
            return redirect(url_for('tutor.dashboard'))
        return redirect(url_for('admin.view_application', app_id=app_id))

    # Reset only the rejected stage
    if app.hod_status == 'rejected':
        app.hod_status = 'pending'; app.hod_remark = None; app.hod_action_time = None
    elif app.coordinator_status == 'rejected':
        app.coordinator_status = 'pending'; app.coordinator_remark = None; app.coordinator_action_time = None
    elif app.tutor_status == 'rejected':
        app.tutor_status = 'pending'; app.tutor_remark = None; app.tutor_action_time = None
    elif app.staff_status == 'rejected':
        app.staff_status = 'pending'; app.staff_remark = None; app.staff_action_time = None

    app.final_status     = 'pending'
    app.retransmit_count = (app.retransmit_count or 0) + 1
    app.retransmit_by    = current_user.id
    app.retransmit_at    = datetime.utcnow()
    db.session.commit()
    flash(f'Application #{app_id} retransmitted successfully.', 'success')

    if current_user.role == 'subject_staff' or current_user.secondary_role == 'subject_staff':
        return redirect(url_for('staff.dashboard'))
    if current_user.role == 'tutor' or current_user.secondary_role == 'tutor':
        return redirect(url_for('tutor.dashboard'))
    return redirect(url_for('admin.view_application', app_id=app_id))


# ─── HELPER ───────────────────────────────────────────────────────────────────
def _expand_register_numbers(raw: str) -> list:
    """
    Expand register-number ranges and comma-separated lists.
    E.g. '6176AC23UCS001-6176AC23UCS028' expands to individual reg nos.
    Supports (No Numbers: 19) exclusion annotations.
    """
    import re
    if not raw:
        return []
    excluded = set()
    for match in re.finditer(r'\(No Numbers?:\s*(\d+)\)', raw, re.IGNORECASE):
        excluded.add(int(match.group(1)))
    raw = re.sub(r'\(No Numbers?:\s*\d+\)', '', raw, flags=re.IGNORECASE)
    result = []
    parts = re.split(r'[,\n]+', raw)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        range_match = re.match(r'^([A-Za-z0-9]+?)(\d+)\s*-\s*([A-Za-z0-9]+?)(\d+)$', part)
        if range_match:
            prefix1, start_str, prefix2, end_str = range_match.groups()
            if prefix1 == prefix2:
                width = len(start_str)
                for n in range(int(start_str), int(end_str) + 1):
                    if n not in excluded:
                        result.append(f"{prefix1}{str(n).zfill(width)}")
            else:
                result.append(part)
        else:
            result.append(part)
    return result


# ─── SEATING ALLOTMENT ────────────────────────────────────────────────────────
@admin_bp.route('/seating')
@login_required
def seating_allotment():
    if not (current_user.role in ('admin', 'hod', 'coordinator') or
            current_user.secondary_role in ('hod', 'coordinator')):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    allotments = SeatingAllotment.query.order_by(SeatingAllotment.hall_number).all()
    all_staff  = User.query.filter(
        User.role.in_(['subject_staff', 'tutor', 'hod', 'coordinator']),
        User.is_active == True
    ).order_by(User.name).all()
    hall_map = {}
    for a in allotments:
        hall_map.setdefault(a.hall_number, []).append(a)
    return render_template('admin/seating_allotment.html',
                           allotments=allotments, hall_map=hall_map, all_staff=all_staff)


@admin_bp.route('/seating/upload', methods=['POST'])
@login_required
def seating_upload():
    if not (current_user.role in ('admin', 'hod', 'coordinator') or
            current_user.secondary_role in ('hod', 'coordinator')):
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.seating_allotment'))

    added = updated = 0
    f = request.files.get('seating_file')
    if f and f.filename:
        ext = f.filename.rsplit('.', 1)[-1].lower()
        if ext not in ('xlsx', 'xls', 'csv'):
            flash('Only Excel/CSV files accepted.', 'danger')
            return redirect(url_for('admin.seating_allotment'))
        try:
            import pandas as pd
            df = pd.read_csv(f) if ext == 'csv' else pd.read_excel(f, dtype=str)
            df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]
            for _, row in df.iterrows():
                def v(*keys):
                    for k in keys:
                        val = row.get(k, '')
                        if str(val).strip().lower() not in ('nan', 'none', ''):
                            return str(val).strip()
                    return ''
                hall    = v('hall_number', 'hall_no', 'hall')
                yr_str  = v('year', 'yr')
                sec     = v('section', 'sec').upper()
                reg_raw = v('register_numbers', 'register_number', 'reg_numbers', 'reg_nos')
                num_s   = v('no_of_students', 'num_students', 'count')
                tot_s   = v('total_no_of_students', 'total_students', 'total')
                inv_em  = v('invigilator_email', 'invigilator', 'staff_email')
                if not hall:
                    continue
                yr_int  = int(float(yr_str)) if yr_str else None
                sec_val = sec if sec in ('A', 'B', 'C') else None
                num_int = int(float(num_s)) if num_s else None
                tot_int = int(float(tot_s)) if tot_s else None
                reg_list = _expand_register_numbers(reg_raw)
                inv_user = None
                if inv_em:
                    inv_user = User.query.filter(db.func.lower(User.email) == inv_em.lower()).first()
                existing = SeatingAllotment.query.filter_by(
                    hall_number=hall, year=yr_int, section=sec_val).first()
                if existing:
                    existing.set_register_numbers(reg_list)
                    existing.num_students   = num_int or len(reg_list) or existing.num_students
                    existing.total_students = tot_int or existing.total_students
                    if inv_user:
                        existing.invigilator_id = inv_user.id
                    existing.uploaded_by = current_user.id
                    existing.uploaded_at = datetime.utcnow()
                    updated += 1
                else:
                    sa = SeatingAllotment(
                        hall_number=hall, year=yr_int, section=sec_val,
                        num_students=num_int or len(reg_list), total_students=tot_int,
                        invigilator_id=inv_user.id if inv_user else None,
                        uploaded_by=current_user.id)
                    sa.set_register_numbers(reg_list)
                    db.session.add(sa)
                    added += 1
            db.session.commit()
            flash(f'Seating allotment uploaded: {added} new, {updated} updated.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Upload failed: {e}', 'danger')
    elif request.form.get('hall_number'):
        record_id = request.form.get('record_id')
        hall = (request.form.get('hall_number') or '').strip()
        student_count = request.form.get('student_count') or request.form.get('num_students')

        if not hall:
            flash('Hall number is required for manual entry.', 'danger')
            return redirect(url_for('admin.seating_allotment'))

        try:
            student_count_int = int(student_count)
        except (TypeError, ValueError):
            flash('Number of students must be a valid number.', 'danger')
            return redirect(url_for('admin.seating_allotment'))

        if student_count_int < 1:
            flash('Number of students must be at least 1.', 'danger')
            return redirect(url_for('admin.seating_allotment'))

        if record_id:
            existing = SeatingAllotment.query.get(int(record_id)) if record_id.isdigit() else None
            if not existing:
                flash('Hall record not found.', 'danger')
                return redirect(url_for('admin.seating_allotment'))
            existing.hall_number = hall
            existing.year = None
            existing.section = None
            existing.set_register_numbers([])
            existing.num_students = student_count_int
            existing.total_students = student_count_int
            existing.uploaded_by = current_user.id
            existing.uploaded_at = datetime.utcnow()
            updated += 1
        else:
            existing = SeatingAllotment.query.filter_by(hall_number=hall).first()
            if existing:
                existing.year = None
                existing.section = None
                existing.set_register_numbers([])
                existing.num_students = student_count_int
                existing.total_students = student_count_int
                existing.uploaded_by = current_user.id
                existing.uploaded_at = datetime.utcnow()
                updated += 1
            else:
                sa = SeatingAllotment(
                    hall_number=hall,
                    year=None,
                    section=None,
                    num_students=student_count_int,
                    total_students=student_count_int,
                    uploaded_by=current_user.id
                )
                sa.set_register_numbers([])
                db.session.add(sa)
                added += 1
        db.session.commit()
        flash(f'Hall entry saved: {added} new, {updated} updated.', 'success')
    else:
        flash('Please upload a seating file or submit manual hall details.', 'danger')
    return redirect(url_for('admin.seating_allotment'))


@admin_bp.route('/seating/<int:sa_id>/get')
@login_required
def get_seating_entry(sa_id):
    if not (current_user.role in ('admin', 'hod', 'coordinator') or
            current_user.secondary_role in ('hod', 'coordinator')):
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.seating_allotment'))
    sa = SeatingAllotment.query.get_or_404(sa_id)
    return jsonify({
        'id': sa.id,
        'hall_number': sa.hall_number,
        'year': sa.year,
        'section': sa.section,
        'register_numbers': sa.get_register_numbers(),
        'num_students': sa.num_students,
        'total_students': sa.total_students
    })


@admin_bp.route('/seating/<int:sa_id>/assign', methods=['POST'])
@login_required
def assign_invigilator(sa_id):
    if not (current_user.role in ('admin', 'hod') or current_user.secondary_role == 'hod'):
        flash('Access denied.', 'danger')
        return redirect(url_for('admin.seating_allotment'))
    sa = SeatingAllotment.query.get_or_404(sa_id)
    sa.invigilator_id = request.form.get('invigilator_id', type=int) or None
    db.session.commit()
    flash('Invigilator assigned.', 'success')
    return redirect(url_for('admin.seating_allotment'))


@admin_bp.route('/seating/<int:sa_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_seating(sa_id):
    sa = SeatingAllotment.query.get_or_404(sa_id)
    db.session.delete(sa)
    db.session.commit()
    flash('Seating row deleted.', 'success')
    return redirect(url_for('admin.seating_allotment'))


# ─── ATTENDANCE ENTRY (invigilator / staff) ───────────────────────────────────
@admin_bp.route('/attendance/mark/<string:hall_number>')
@login_required
def mark_attendance_page(hall_number):
    allotments = SeatingAllotment.query.filter_by(hall_number=hall_number).order_by(
        SeatingAllotment.year, SeatingAllotment.section).all()
    if not allotments:
        flash('No seating data found for this hall.', 'warning')
        return redirect(url_for('main.index'))
    can_access = (
        current_user.role in ('admin', 'hod', 'coordinator', 'tutor', 'subject_staff') or
        current_user.secondary_role in ('hod', 'coordinator', 'tutor', 'subject_staff')
    )
    if not can_access:
        flash('You do not have access to mark halls.', 'danger')
        return redirect(url_for('main.index'))
    seating = allotments[0]
    student_rows = []
    attendance_rows = ExamAttendance.query.filter_by(hall_number=hall_number).order_by(
        ExamAttendance.year, ExamAttendance.section, ExamAttendance.register_number).all()
    for att in attendance_rows:
        student_rows.append({
            'seating_id': att.seating_id,
            'register_number': att.register_number,
            'year': att.year,
            'section': att.section,
            'status': att.status,
            'marked': True,
        })
    return render_template('admin/mark_attendance.html',
                           hall_number=hall_number,
                           allotments=allotments,
                           seating=seating,
                           student_rows=student_rows)


@admin_bp.route('/attendance/mark/<string:hall_number>/submit', methods=['POST'])
@login_required
def submit_attendance(hall_number):
    allotments = SeatingAllotment.query.filter_by(hall_number=hall_number).all()
    can_access = (
        current_user.role in ('admin', 'hod', 'coordinator', 'tutor', 'subject_staff') or
        current_user.secondary_role in ('hod', 'coordinator', 'tutor', 'subject_staff')
    )
    if not can_access:
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    if not allotments:
        flash('No seating data found for this hall.', 'warning')
        return redirect(url_for('main.index'))

    seating = allotments[0]
    saved = 0
    submitted_regs = set()
    reg_numbers = request.form.getlist('register_number[]')
    years = request.form.getlist('year[]')
    sections = request.form.getlist('section[]')
    statuses = request.form.getlist('status[]')

    for idx, reg in enumerate(reg_numbers):
        reg = (reg or '').strip().upper()
        if not reg:
            continue
        year_raw = years[idx] if idx < len(years) else ''
        section = (sections[idx] if idx < len(sections) else '').strip().upper()
        status_raw = statuses[idx] if idx < len(statuses) else 'present'
        try:
            year = int(year_raw) if year_raw else None
        except ValueError:
            year = None
        if section not in ('A', 'B', 'C', 'D', 'E'):
            section = None
        status = 'absent' if status_raw == 'absent' else 'present'
        submitted_regs.add(reg)
        att = ExamAttendance.query.filter_by(seating_id=seating.id, register_number=reg).first()
        if att:
            att.year = year
            att.section = section
            att.status = status
            att.marked_by = current_user.id
            att.marked_at = datetime.utcnow()
        else:
            att = ExamAttendance(
                seating_id=seating.id, hall_number=seating.hall_number,
                register_number=reg, year=year, section=section,
                status=status, marked_by=current_user.id)
            db.session.add(att)
        saved += 1

    existing_records = ExamAttendance.query.filter_by(seating_id=seating.id).all()
    for record in existing_records:
        if record.register_number not in submitted_regs:
            db.session.delete(record)

    db.session.commit()
    flash(f'Attendance saved for hall {hall_number} ({saved} students).', 'success')
    is_adm_hod = (current_user.role in ('admin', 'hod') or current_user.secondary_role == 'hod')
    if is_adm_hod:
        return redirect(url_for('admin.view_attendance'))
    return redirect(url_for('admin.mark_attendance_page', hall_number=hall_number))


# ─── ATTENDANCE OVERVIEW (admin/HOD) ─────────────────────────────────────────
@admin_bp.route('/attendance')
@login_required
def view_attendance():
    if not (current_user.role in ('admin', 'hod') or current_user.secondary_role == 'hod'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    hall_filter    = request.args.get('hall', '')
    section_filter = request.args.get('section', '')
    year_filter    = request.args.get('year', type=int)
    query = ExamAttendance.query
    if hall_filter:    query = query.filter_by(hall_number=hall_filter)
    if section_filter: query = query.filter_by(section=section_filter)
    if year_filter:    query = query.filter_by(year=year_filter)
    records   = query.order_by(ExamAttendance.hall_number, ExamAttendance.register_number).all()
    all_halls = [h[0] for h in db.session.query(ExamAttendance.hall_number).distinct().all()]
    hall_summary = {}
    for h in all_halls:
        hrs = ExamAttendance.query.filter_by(hall_number=h)
        hall_summary[h] = {
            'total':   hrs.count(),
            'present': hrs.filter_by(status='present').count(),
            'absent':  hrs.filter_by(status='absent').count(),
        }
    ys_summary = {}
    for yr in range(1, 5):
        ys_summary[yr] = {}
        for sec in SECTIONS:
            recs = ExamAttendance.query.filter_by(year=yr, section=sec)
            ys_summary[yr][sec] = {
                'total':   recs.count(),
                'present': recs.filter_by(status='present').count(),
                'absent':  recs.filter_by(status='absent').count(),
            }
    return render_template('admin/attendance.html',
                           records=records, hall_summary=hall_summary,
                           ys_summary=ys_summary, all_halls=all_halls,
                           hall_filter=hall_filter, section_filter=section_filter,
                           year_filter=year_filter, sections=SECTIONS)


# ─── MY HALLS (invigilator) ──────────────────────────────────────────────────
@admin_bp.route('/my-halls')
@login_required
def my_halls():
    can_view_all = (
        current_user.role in ('admin', 'hod', 'coordinator', 'tutor', 'subject_staff') or
        current_user.secondary_role in ('hod', 'coordinator', 'tutor', 'subject_staff')
    )
    if can_view_all:
        halls = SeatingAllotment.query.order_by(SeatingAllotment.hall_number).all()
    else:
        halls = SeatingAllotment.query.filter_by(
            invigilator_id=current_user.id).order_by(SeatingAllotment.hall_number).all()
    hall_numbers = list({h.hall_number for h in halls})
    hall_status = {}
    for hn in hall_numbers:
        rows = SeatingAllotment.query.filter_by(hall_number=hn).all()
        total = sum((r.total_students or r.num_students or len(r.get_register_numbers())) for r in rows)
        marked = ExamAttendance.query.filter_by(hall_number=hn).count()
        hall_status[hn] = {'total': total, 'marked': marked}
    return render_template('admin/my_halls.html',
                           halls=halls, hall_numbers=hall_numbers, hall_status=hall_status)


# ─── SUBJECT-WISE ABSENTEES (admin view) ─────────────────────────────────────
@admin_bp.route('/absentees/subject-wise')
@login_required
def view_absentees_subject():
    if not (current_user.role in ('admin', 'hod') or current_user.secondary_role == 'hod'):
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))
    cia_filter     = request.args.get('cia', type=int)
    section_filter = request.args.get('section', '')
    query = AbsenceRecord.query
    if cia_filter:
        query = query.filter_by(cia_number=cia_filter)
    records = query.order_by(AbsenceRecord.cia_number, AbsenceRecord.subject_id).all()
    tree = {}
    for rec in records:
        uploader = rec.uploader
        section  = uploader.handling_section if uploader else '?'
        if section_filter and section != section_filter:
            continue
        key = (rec.subject.subject_name, rec.subject.subject_code)
        tree.setdefault(key, {}).setdefault(rec.cia_number, []).append({
            'rec': rec, 'section': section, 'count': len(rec.get_students())
        })
    return render_template('admin/absentees_subject.html',
                           tree=tree, cia_filter=cia_filter,
                           section_filter=section_filter, sections=SECTIONS)
