from datetime import datetime
from app import db   # if db is created in app.py

year             = db.Column(db.Integer, nullable=True)       # students: 1-4
section          = db.Column(db.String(5), nullable=True)     # students: A/B/C
handling_year    = db.Column(db.Integer, nullable=True)       # staff: which year
handling_section = db.Column(db.String(5), nullable=True)     # staff: A/B/C


# ─────────────────────────────────────────────────────────────
# 2. ADD to Subject model (inside class Subject):
# ─────────────────────────────────────────────────────────────

    # v8 additions
year = db.Column(db.Integer, nullable=True)  # 1-4, derived from semester


# ─────────────────────────────────────────────────────────────
# 3. ADD to RetestApplication model (inside class RetestApplication):
# ─────────────────────────────────────────────────────────────

    # v8 additions
student_section = db.Column(db.String(5), nullable=True)  # A/B/C
student_year    = db.Column(db.Integer, nullable=True)     # 1-4


# ─────────────────────────────────────────────────────────────
# 4. NEW MODEL — add as a new class in models.py
# ─────
class SubjectStaffSection(db.Model):
    __tablename__ = 'subject_staff_section'

    id            = db.Column(db.Integer, primary_key=True)
    subject_id    = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='CASCADE'), nullable=False)
    staff_id      = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    semester      = db.Column(db.Integer, nullable=False)
    section       = db.Column(db.String(5), nullable=False, default='A')
    academic_year = db.Column(db.String(20), nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    subject = db.relationship('Subject', backref=db.backref('section_mappings', lazy='dynamic'))
    staff   = db.relationship('User',    backref=db.backref('section_assignments', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('subject_id', 'section', 'semester', name='uq_subj_sec_sem'),
    )


# ─────────────────────────────────────────────────────────────
# 5. ADD to imports in models.py (if not already present):
#    from datetime import datetime
# ─────────────────────────────────────────────────────────────
