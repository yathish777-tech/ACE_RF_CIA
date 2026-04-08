# CIA Retest Portal v8 — Sample Upload Formats

## 1. Staff Details (staff_details.xlsx)

| staff_name | staff_email | role | phone | handling_year | handling_section |
|---|---|---|---|---|---|
| Prof. Kavitha R. | kavitha@ace.edu | subject_staff | 9876543210 | 2 | A |
| Prof. Ravi Kumar | ravi@ace.edu | subject_staff | 9876543211 | 2 | B |
| Prof. Priya S. | priya@ace.edu | subject_staff | 9876543212 | 2 | C |
| Prof. Senthil K. | senthil@ace.edu | tutor | 9876543213 | 2 | A |
| Dr. Ramesh M. | hod@ace.edu | hod | 9876543214 | | |
| Ms. Anitha P. | coord@ace.edu | coordinator | 9876543215 | | |

**Valid roles:** `subject_staff` | `tutor` | `hod` | `coordinator`

---

## 2. Subject Details (subject_details.xlsx)

| subject_name | subject_code | semester | section | shsn | department |
|---|---|---|---|---|---|
| Data Structures | CS2201 | 4 | A | kavitha@ace.edu | Computer Science |
| Data Structures | CS2201 | 4 | B | ravi@ace.edu | Computer Science |
| Data Structures | CS2201 | 4 | C | priya@ace.edu | Computer Science |
| DBMS | CS2202 | 4 | A | kavitha@ace.edu | Computer Science |
| DBMS | CS2202 | 4 | B | ravi@ace.edu | Computer Science |
| DBMS | CS2202 | 4 | C | priya@ace.edu | Computer Science |
| OOP | CS2203 | 4 | A | senthil@ace.edu | Computer Science |

**Note:**
- `shsn` = Subject Handling Staff Name — use email (preferred) or staff name
- One row per subject + section combo
- Same subject across 3 sections = 3 rows
- One staff can handle multiple subjects or sections

---

## 3. CIA Schedule (cia_schedule.xlsx)

| subject_code | subject_name | semester | cia_number | cia_exam_date | cia_deadline_date | cia_retest_date | academic_year |
|---|---|---|---|---|---|---|---|
| CS2201 | Data Structures | 4 | 1 | 2024-09-10 | 2024-09-16 | 2024-09-20 | 2024-25 |
| CS2201 | Data Structures | 4 | 2 | 2024-11-05 | 2024-11-11 | 2024-11-15 | 2024-25 |
| CS2201 | Data Structures | 4 | 3 | 2025-01-10 | 2025-01-16 | 2025-01-20 | 2024-25 |
| CS2202 | DBMS | 4 | 1 | 2024-09-12 | 2024-09-18 | 2024-09-22 | 2024-25 |

**Date format:** YYYY-MM-DD  
**cia_number:** 1, 2, or 3

---

## Semester → Year Mapping (automatic)

| Semester | Academic Year |
|---|---|
| 1, 2 | First Year |
| 3, 4 | Second Year |
| 5, 6 | Third Year |
| 7, 8 | Fourth Year |

## Upload Order

1. **Staff** first (so emails/names can be resolved in step 2)
2. **Subjects** second (creates section-staff mappings)
3. **CIA Schedule** last (links dates to subjects)
