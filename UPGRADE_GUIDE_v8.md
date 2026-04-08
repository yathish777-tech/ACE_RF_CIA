# CIA Retest Portal — v7 → v8 Upgrade Guide

## Overview of Changes

### New Features
1. **Semester → Year auto-selection** in student application form
2. **Section-aware staff auto-mapping** (student's section A/B/C → correct staff)
3. **HOD & Admin dashboards**: Year-wise × Section-wise application views with filters
4. **Admin uploads split into 3 separate files**: Staff, Subjects (with section mapping), CIA Schedule
5. **Download button** added to all dashboards except student (Excel + PDF)

---

## Step 1: Database Migration

Run `migrate_v8.sql` on your MySQL database:

```bash
mysql -u root -p ace_cia_rf < migrate_v8.sql
```

This adds:
- `user.year`, `user.section`, `user.handling_year`, `user.handling_section`
- `subject.year`
- `retest_application.student_section`, `retest_application.student_year`
- New table: `subject_staff_section`

---

## Step 2: Update models.py

Open your `models.py` and apply changes from `models_v8_additions.py`:

### In `User` class, add:
```python
year             = db.Column(db.Integer, nullable=True)
section          = db.Column(db.String(5), nullable=True)
handling_year    = db.Column(db.Integer, nullable=True)
handling_section = db.Column(db.String(5), nullable=True)
```

### In `Subject` class, add:
```python
year = db.Column(db.Integer, nullable=True)
```

### In `RetestApplication` class, add:
```python
student_section = db.Column(db.String(5), nullable=True)
student_year    = db.Column(db.Integer, nullable=True)
```

### Add new `SubjectStaffSection` model class (full code in `models_v8_additions.py`)

### Update imports in models.py:
```python
from models import db, User, Subject, CIADate, RetestApplication, AbsenceRecord, SubjectStaffSection
```

---

## Step 3: Replace Route Files

Copy updated route files from this package:

| File | Replace |
|------|---------|
| `routes/admin.py` | Full replacement |
| `routes/hod.py` | Full replacement |
| `routes/tutor.py` | Full replacement |
| `routes/coordinator.py` | Full replacement |
| `routes/user.py` | Full replacement (was empty) |
| `routes/subject_staff.py` | Append download section only |

---

## Step 4: Replace Templates

| Template | Change |
|----------|--------|
| `templates/user/apply.html` | Full replacement — semester→year auto-fill, section-aware staff |
| `templates/admin/bulk_upload.html` | Full replacement — 3 separate upload cards |
| `templates/admin/all_applications.html` | Full replacement — year×section grid + download |
| `templates/hod/dashboard.html` | Full replacement — year×section tabs + download |

---

## Step 5: Register Blueprint (if user_bp was not registered)

In your `app.py`, ensure `user_bp` is registered:

```python
from routes.user import user_bp
app.register_blueprint(user_bp, url_prefix='/user')
```

---

## Upload File Formats

### ① Staff Upload File
Columns: `staff_name`, `staff_email`, `role`, `phone`, `handling_year`, `handling_section`

| staff_name | staff_email | role | phone | handling_year | handling_section |
|------------|-------------|------|-------|---------------|-----------------|
| Prof. Kavitha R. | kavitha@ace.edu | subject_staff | 9876543210 | 2 | A |
| Prof. Rajan | rajan@ace.edu | subject_staff | 9876543211 | 2 | B |
| Dr. Senthil | senthil@ace.edu | tutor | 9876543212 | 2 | A |

**Notes:**
- Default password for all new accounts: `staff123`
- One staff can handle multiple subjects — repeat their email across rows
- One staff can have multiple roles: upload them twice with different roles (second becomes `secondary_role`)

### ② Subject Upload File
Columns: `subject_name`, `subject_code`, `semester`, `section`, `shsn`, `department`

| subject_name | subject_code | semester | section | shsn | department |
|-------------|-------------|---------|---------|------|-----------|
| Data Structures | CS2201 | 4 | A | kavitha@ace.edu | CSE |
| Data Structures | CS2201 | 4 | B | rajan@ace.edu | CSE |
| Data Structures | CS2201 | 4 | C | meena@ace.edu | CSE |
| DBMS | CS2202 | 4 | A | kavitha@ace.edu | CSE |
| DBMS | CS2202 | 4 | B | kavitha@ace.edu | CSE |

**Notes:**
- `shsn` = Subject Handling Staff Name (accepts email OR full name)
- Same subject, same semester but different section → different row
- Same staff can handle multiple subjects
- Year is derived automatically: sem 1-2 = Year 1, 3-4 = Year 2, 5-6 = Year 3, 7-8 = Year 4

### ③ CIA Schedule Upload File
Columns: `subject_code`, `semester`, `cia_number`, `cia_exam_date`, `cia_deadline_date`, `cia_retest_date`, `academic_year`

| subject_code | semester | cia_number | cia_exam_date | cia_deadline_date | cia_retest_date | academic_year |
|-------------|---------|-----------|--------------|------------------|----------------|--------------|
| CS2201 | 4 | 1 | 2025-09-10 | 2025-09-16 | 2025-09-20 | 2025-26 |
| CS2201 | 4 | 2 | 2025-11-05 | 2025-11-11 | 2025-11-15 | 2025-26 |
| CS2201 | 4 | 3 | 2026-01-10 | 2026-01-16 | 2026-01-20 | 2025-26 |

**Notes:**
- Dates must be `YYYY-MM-DD` format
- `subject_code` + `semester` must match existing subjects (upload subjects first)
- If a CIA date already exists for that subject+CIA number, it will be updated

---

## Backend Mapping Logic

```
Student selects Semester 4
    → Year auto-fills as "Year 2 (2nd Year)"
    → Subjects load from SubjectStaffSection WHERE semester=4 AND section=student.section
    → Student selects "Data Structures"
    → Staff auto-fills from SubjectStaffSection WHERE subject_id=X AND section=student.section
    → Application stores student_year=2, student_section="A"
```

---

## Student Profile Setup

For the auto-mapping to work, students must have `section` set on their `User` record.
Set this during student registration or via admin:

```python
student.section = 'A'  # or 'B' or 'C'
student.year = 2        # optional, auto-derived from semester during apply
```

---

## Download URLs

| Dashboard | Excel | PDF |
|-----------|-------|-----|
| Admin — All | `/admin/applications/download/excel` | `/admin/applications/download/pdf` |
| Admin — Filtered | `/admin/applications/download/excel?year=2&section=A` | same with `/pdf` |
| HOD | `/hod/applications/download/excel` | `/hod/applications/download/pdf` |
| Tutor | `/tutor/applications/download/excel` | `/tutor/applications/download/pdf` |
| Staff | `/staff/applications/download/excel` | `/staff/applications/download/pdf` |
| Coordinator | `/coordinator/applications/download/excel` | `/coordinator/applications/download/pdf` |

