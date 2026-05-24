"""
CIA Retest Portal v8 — models.py
Full SQLAlchemy model definitions for all tables.
"""

from datetime import datetime, date
from flask import json
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import json 
from extensions import db


# ─────────────────────────────────────────────────────────────────────────────
# USER
# ─────────────────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(120), nullable=False)
    email            = db.Column(db.String(150), unique=True, nullable=False)
    password_hash    = db.Column(db.String(256), nullable=False)
    phone            = db.Column(db.String(20),  nullable=True)
    department       = db.Column(db.String(100), nullable=True)

    # Role: student | subject_staff | tutor | hod | coordinator | admin
    role             = db.Column(db.String(30), nullable=False, default='student')
    secondary_role   = db.Column(db.String(30), nullable=True)   # dual-role staff

    is_active        = db.Column(db.Boolean, default=True, nullable=False)

    # OTP / password reset
    otp              = db.Column(db.String(10),  nullable=True)
    otp_expiry       = db.Column(db.DateTime,    nullable=True)

    # v8 — students
    year             = db.Column(db.Integer,     nullable=True)   # 1-4
    section          = db.Column(db.String(5),   nullable=True)   # A / B / C

    # v8 — staff
    handling_year    = db.Column(db.Integer,     nullable=True)   # which year they handle
    handling_section = db.Column(db.String(5),   nullable=True)   # which section they handle

    # Student-only: register number
    register_number  = db.Column(db.String(30),  nullable=True)

    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    def display_role(self):
        if self.secondary_role:
         return f"{self.role.capitalize()} ({self.secondary_role.capitalize()})"
        return self.role.capitalize()
    # ── helpers ──────────────────────────────────────────────────────────
    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email} [{self.role}]>'
    

# ─────────────────────────────────────────────────────────────────────────────
# SUBJECT
# ─────────────────────────────────────────────────────────────────────────────
class Subject(db.Model):
    __tablename__ = 'subject'

    id            = db.Column(db.Integer, primary_key=True)
    subject_name  = db.Column(db.String(150), nullable=False)
    subject_code  = db.Column(db.String(30),  nullable=False)
    semester      = db.Column(db.Integer,     nullable=False)
    department    = db.Column(db.String(100), nullable=True)
    is_active     = db.Column(db.Boolean, default=True, nullable=False)

    # Primary staff for this subject (legacy / fallback)
    staff_id      = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'),
                               nullable=True)

    # v8 — derived from semester: sem 1-2 = Year 1, 3-4 = Year 2, 5-6 = Year 3, 7-8 = Year 4
    year          = db.Column(db.Integer, nullable=True)

    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    staff         = db.relationship('User', foreign_keys=[staff_id],
                                    backref=db.backref('subjects', lazy='dynamic'))

    def __repr__(self):
        return f'<Subject {self.subject_code} sem={self.semester}>'


# ─────────────────────────────────────────────────────────────────────────────
# SUBJECT–STAFF–SECTION  (v8 new table)
# Maps subject + section + semester → specific staff member
# ─────────────────────────────────────────────────────────────────────────────
class SubjectStaffSection(db.Model):
    __tablename__ = 'subject_staff_section'

    id            = db.Column(db.Integer, primary_key=True)
    subject_id    = db.Column(db.Integer,
                               db.ForeignKey('subject.id', ondelete='CASCADE'),
                               nullable=False)
    staff_id      = db.Column(db.Integer,
                               db.ForeignKey('user.id', ondelete='CASCADE'),
                               nullable=False)
    semester      = db.Column(db.Integer,    nullable=False)
    section       = db.Column(db.String(5),  nullable=False, default='A')   # A / B / C
    academic_year = db.Column(db.String(20), nullable=True)
    created_at    = db.Column(db.DateTime,   default=datetime.utcnow)

    # Relationships
    subject = db.relationship('Subject',
                               backref=db.backref('section_mappings', lazy='dynamic'))
    staff   = db.relationship('User',
                               backref=db.backref('section_assignments', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('subject_id', 'section', 'semester',
                            name='uq_subj_sec_sem'),
    )

    def __repr__(self):
        return (f'<SSSMap subj={self.subject_id} '
                f'sec={self.section} sem={self.semester} staff={self.staff_id}>')


# ─────────────────────────────────────────────────────────────────────────────
# CIA DATE  (exam window per subject)
# ─────────────────────────────────────────────────────────────────────────────
class CIADate(db.Model):
    __tablename__ = 'cia_date'

    id                   = db.Column(db.Integer, primary_key=True)
    subject_id           = db.Column(db.Integer,
                                      db.ForeignKey('subject.id', ondelete='CASCADE'),
                                      nullable=False)
    cia_number           = db.Column(db.Integer, nullable=False)          # 1, 2, or 3
    semester             = db.Column(db.Integer, nullable=True)
    academic_year        = db.Column(db.String(20), nullable=True)        # e.g. "2025-26"

    exam_date            = db.Column(db.Date, nullable=True)
    application_end_date = db.Column(db.Date, nullable=True)             # application deadline
    retest_date          = db.Column(db.Date, nullable=True)

    created_by           = db.Column(db.Integer,
                                      db.ForeignKey('user.id', ondelete='SET NULL'),
                                      nullable=True)
    created_at           = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subject    = db.relationship('Subject',
                                  backref=db.backref('cia_dates', lazy='dynamic'))
    creator    = db.relationship('User', foreign_keys=[created_by])

    # ── helper ───────────────────────────────────────────────────────────
    def is_application_open(self) -> bool:
        """Return True if today is within the application window."""
        today = date.today()
        if self.exam_date and self.application_end_date:
            # Applications open AFTER exam and close on the deadline
            return self.exam_date < today <= self.application_end_date
        return False

    def __repr__(self):
        return f'<CIADate subj={self.subject_id} CIA{self.cia_number}>'


# ─────────────────────────────────────────────────────────────────────────────
# RETEST APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
class RetestApplication(db.Model):
    __tablename__ = 'retest_application'

    id              = db.Column(db.Integer, primary_key=True)

    # Student info (snapshot at submission time)
    student_id      = db.Column(db.Integer,
                                 db.ForeignKey('user.id', ondelete='CASCADE'),
                                 nullable=False)
    student_name    = db.Column(db.String(120), nullable=False)
    student_email   = db.Column(db.String(150), nullable=False)
    register_number = db.Column(db.String(30),  nullable=True)

    # v8 — section & year snapshot
    student_section = db.Column(db.String(5))
    student_year = db.Column(db.Integer)  # 1-4

    # Subject / CIA details
    subject_id      = db.Column(db.Integer,
                                 db.ForeignKey('subject.id', ondelete='CASCADE'),
                                 nullable=False)
    semester        = db.Column(db.Integer, nullable=False)
    cia_number      = db.Column(db.Integer, nullable=False)     # 1, 2, or 3
    cia_date        = db.Column(db.Date,    nullable=True)      # actual exam date
    attachment_filename = db.Column(db.String(300), nullable=True)  # uploaded proof file name

    # Application type
    submission_type = db.Column(db.String(10), nullable=False, default='post')  # pre / post
    reason_type     = db.Column(db.String(50), nullable=True)
    reason_detail = db.Column(db.Text)   # ✅ ADD THIS
    # Assigned staff pipeline
    staff_id        = db.Column(db.Integer,
                                 db.ForeignKey('user.id', ondelete='SET NULL'),
                                 nullable=True)
    tutor_id        = db.Column(db.Integer,
                                 db.ForeignKey('user.id', ondelete='SET NULL'),
                                 nullable=True)

    # Approval statuses: pending | approved | rejected
    staff_status       = db.Column(db.String(20), default='pending', nullable=False)
    staff_remark       = db.Column(db.Text,       nullable=True)
    staff_action_time  = db.Column(db.DateTime,   nullable=True)

    tutor_status       = db.Column(db.String(20), default='pending', nullable=False)
    tutor_remark       = db.Column(db.Text,       nullable=True)
    tutor_action_time  = db.Column(db.DateTime,   nullable=True)

    coordinator_status       = db.Column(db.String(20), default='pending', nullable=False)
    coordinator_remark       = db.Column(db.Text,       nullable=True)
    coordinator_action_time  = db.Column(db.DateTime,   nullable=True)

    hod_status       = db.Column(db.String(20), default='pending', nullable=False)
    hod_remark       = db.Column(db.Text,       nullable=True)
    hod_action_time  = db.Column(db.DateTime,   nullable=True)

    # Final decision (set after HOD approves)
    final_status     = db.Column(db.String(20), default='pending', nullable=False)

    # v10 — retransmit tracking
    retransmit_count = db.Column(db.Integer, default=0, nullable=True)
    retransmit_by    = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    retransmit_at    = db.Column(db.DateTime, nullable=True)

    submitted_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow,
                                  onupdate=datetime.utcnow)

    # Relationships
    student = db.relationship('User', foreign_keys=[student_id],
                               backref=db.backref('applications', lazy='dynamic'))
    subject = db.relationship('Subject',
                               backref=db.backref('applications', lazy='dynamic'))
    staff   = db.relationship('User', foreign_keys=[staff_id],
                               backref=db.backref('staff_reviews', lazy='dynamic'))
    tutor   = db.relationship('User', foreign_keys=[tutor_id],
                               backref=db.backref('tutor_reviews', lazy='dynamic'))

    def __repr__(self):
        return (f'<RetestApp id={self.id} student={self.student_id} '
                f'subj={self.subject_id} CIA{self.cia_number} [{self.final_status}]>')


# ─────────────────────────────────────────────────────────────────────────────
# ABSENCE RECORD  (absentee upload by subject staff)
# ─────────────────────────────────────────────────────────────────────────────
  # ✅ MUST BE AT TOP OF FILE

class AbsenceRecord(db.Model):
    __tablename__ = 'absence_record'

    id = db.Column(db.Integer, primary_key=True)

    subject_id = db.Column(
        db.Integer,
        db.ForeignKey('subject.id', ondelete='CASCADE'),
        nullable=False
    )

    cia_number = db.Column(db.Integer, nullable=False)
    semester = db.Column(db.Integer, nullable=True)

    # Optional (single student fields – keep if needed)
    student_name = db.Column(db.String(120), nullable=True)
    register_number = db.Column(db.String(30), nullable=True)

    # File path
    file_path = db.Column(db.String(300), nullable=True)

    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='SET NULL'),
        nullable=True
    )

    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ NEW: store multiple students (JSON)
    students = db.Column(db.Text)

    # Relationships
    subject = db.relationship(
        'Subject',
        backref=db.backref('absence_records', lazy='dynamic')
    )

    uploader = db.relationship('User', foreign_keys=[uploaded_by])

    def set_students(self, students_list):
        self.students = json.dumps(students_list)

    def get_students(self):
        """Get students list from JSON, normalizing keys for backward compatibility"""
        if self.students:
            students = json.loads(self.students)
            # Normalize each student record to ensure all keys are present
            normalized = []
            for s in students:
                if isinstance(s, dict):
                    reg = s.get('reg_no') or s.get('register_number') or s.get('register_no') or s.get('reg') or ''
                    name = s.get('name') or s.get('student_name') or ''
                    year = s.get('year') or s.get('yr') or ''
                    section = (s.get('section') or s.get('sec') or '').upper()
                    normalized.append({
                        'reg_no': reg,
                        'register_number': reg,
                        'register_no': reg,
                        'reg': reg,
                        'name': name,
                        'student_name': name,
                        'year': year,
                        'section': section
                    })
            return normalized
        return []


# ─────────────────────────────────────────────────────────────────────────────
# SEATING ALLOTMENT  (uploaded by admin/HOD — hall-wise exam seating)
# ─────────────────────────────────────────────────────────────────────────────
class SeatingAllotment(db.Model):
    __tablename__ = 'seating_allotment'

    id           = db.Column(db.Integer, primary_key=True)
    hall_number  = db.Column(db.String(30),  nullable=False)   # e.g. CSCR107
    year         = db.Column(db.Integer,     nullable=True)    # 1-4
    section      = db.Column(db.String(5),   nullable=True)    # A / B / C
    # Register numbers stored as JSON list ["6176AC22UCS022","6176AC22UCS105",...]
    register_numbers = db.Column(db.Text,    nullable=True)
    num_students     = db.Column(db.Integer, nullable=True)    # count per row
    total_students   = db.Column(db.Integer, nullable=True)    # total in hall

    # Invigilator assigned to this hall
    invigilator_id = db.Column(db.Integer,
                                db.ForeignKey('user.id', ondelete='SET NULL'),
                                nullable=True)

    uploaded_by  = db.Column(db.Integer,
                              db.ForeignKey('user.id', ondelete='SET NULL'),
                              nullable=True)
    uploaded_at  = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    invigilator = db.relationship('User', foreign_keys=[invigilator_id],
                                   backref=db.backref('invigilator_halls', lazy='dynamic'))
    uploader    = db.relationship('User', foreign_keys=[uploaded_by],
                                   backref=db.backref('seating_uploads', lazy='dynamic'))

    def set_register_numbers(self, reg_list):
        self.register_numbers = json.dumps(reg_list)

    def get_register_numbers(self):
        if self.register_numbers:
            return json.loads(self.register_numbers)
        return []

    def __repr__(self):
        return f'<SeatingAllotment hall={self.hall_number} yr={self.year} sec={self.section}>'


# ─────────────────────────────────────────────────────────────────────────────
# EXAM ATTENDANCE  (invigilator marks absent/present per hall per student)
# ─────────────────────────────────────────────────────────────────────────────
class ExamAttendance(db.Model):
    __tablename__ = 'exam_attendance'

    id               = db.Column(db.Integer, primary_key=True)
    seating_id       = db.Column(db.Integer,
                                  db.ForeignKey('seating_allotment.id', ondelete='CASCADE'),
                                  nullable=False)
    hall_number      = db.Column(db.String(30),  nullable=False)
    register_number  = db.Column(db.String(30),  nullable=False)
    year             = db.Column(db.Integer,      nullable=True)
    section          = db.Column(db.String(5),    nullable=True)
    status           = db.Column(db.String(10),   nullable=False, default='present')  # present / absent

    marked_by        = db.Column(db.Integer,
                                  db.ForeignKey('user.id', ondelete='SET NULL'),
                                  nullable=True)
    marked_at        = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    seating  = db.relationship('SeatingAllotment',
                                backref=db.backref('attendance_records', lazy='dynamic'))
    marker   = db.relationship('User', foreign_keys=[marked_by],
                                backref=db.backref('attendance_marked', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('seating_id', 'register_number',
                            name='uq_attendance_seating_reg'),
    )

    def __repr__(self):
        return f'<ExamAttendance hall={self.hall_number} reg={self.register_number} {self.status}>'