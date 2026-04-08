from datetime import datetime
from app import db   # if db is created in app.py

year             = db.Column(db.Integer, nullable=True)           # students: 1-4
section          = db.Column(db.String(5), nullable=True)         # students: A/B/C
handling_year    = db.Column(db.Integer, nullable=True)           # staff: year they handle
handling_section = db.Column(db.String(5), nullable=True)         # staff: section A/B/C


# ── 2. ADD TO Subject model ──────────────────────────────────────────
# (inside class Subject(db.Model):)

year = db.Column(db.Integer, nullable=True)   # derived: ceil(semester/2)


# ── 3. ADD TO RetestApplication model ────────────────────────────────
# (inside class RetestApplication(db.Model):)

student_section = db.Column(db.String(5), nullable=True)    # A/B/C at submission time
student_year    = db.Column(db.Integer, nullable=True)       # 1-4 at submission time


# ── 4. NEW MODEL — add to models.py ──────────────────────────────────
# (add this as a new class, after Subject or RetestApplication)

class SubjectStaffSection(db.Model):
    """Maps a subject + section + semester to a specific handling staff member."""
    __tablename__ = 'subject_staff_section'

    id           = db.Column(db.Integer, primary_key=True)
    subject_id   = db.Column(db.Integer, db.ForeignKey('subject.id', ondelete='CASCADE'), nullable=False)
    staff_id     = db.Column(db.Integer, db.ForeignKey('user.id',    ondelete='CASCADE'), nullable=False)
    semester     = db.Column(db.Integer, nullable=False)
    section      = db.Column(db.String(5), nullable=False, default='A')   # A / B / C
    academic_year = db.Column(db.String(20), nullable=True)
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    subject = db.relationship('Subject', backref=db.backref('section_mappings', lazy='dynamic'))
    staff   = db.relationship('User',    backref=db.backref('section_assignments', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('subject_id', 'section', 'semester', name='uq_subj_sec_sem'),
    )

    def __repr__(self):
        return f'<SSSMap subj={self.subject_id} sec={self.section} sem={self.semester} staff={self.staff_id}>'


# ── 5. ADD TO imports at top of models.py ────────────────────────────
# Make sure this import exists:
# from datetime import datetime
