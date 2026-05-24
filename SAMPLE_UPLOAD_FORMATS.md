# CIA Retest Portal v10 — Sample Upload Formats

---

## 1. Staff Details (staff_details.xlsx)

| staff_name | staff_email | role | phone | handling_year | handling_section |
|---|---|---|---|---|---|
| Prof. Kavitha R. | kavitha@ace.edu | subject_staff | 9876543210 | 2 | A |
| Prof. Ravi Kumar | ravi@ace.edu | subject_staff | 9876543211 | 2 | B |
| Prof. Priya S. | priya@ace.edu | subject_staff | 9876543212 | 2 | C |
| Prof. Senthil K. | senthil@ace.edu | tutor | 9876543213 | 2 | A |
| Prof. Meena D. | meena@ace.edu | tutor | 9876543216 | 2 | B |
| Prof. Arjun P. | arjun@ace.edu | tutor | 9876543217 | 2 | C |
| Dr. Ramesh M. | hod@ace.edu | hod | 9876543214 | | |
| Ms. Anitha P. | coord@ace.edu | coordinator | 9876543215 | | |

> **Tutor Auto-mapping:** Set `handling_year` + `handling_section` for tutors. Students are auto-assigned
> the right tutor when applying — no manual selection needed.

---

## 2. Subject Details (subject_details.xlsx)

| subject_name | subject_code | semester | section | shsn | department |
|---|---|---|---|---|---|
| Data Structures | CS2201 | 4 | A | kavitha@ace.edu | Computer Science |
| Data Structures | CS2201 | 4 | B | ravi@ace.edu | Computer Science |
| DBMS | CS2202 | 4 | A | kavitha@ace.edu | Computer Science |

---

## 3. CIA Schedule (cia_schedule.xlsx)

| subject_code | subject_name | semester | cia_number | cia_exam_date | cia_deadline_date | cia_retest_date | academic_year |
|---|---|---|---|---|---|---|---|
| CS2201 | Data Structures | 4 | 1 | 2024-09-10 | 2024-09-16 | 2024-09-20 | 2024-25 |

---

## 4. Seating Allotment (seating_allotment.xlsx) — NEW v10

| hall_number | year | section | register_numbers | no_of_students | total_no_of_students | invigilator_email |
|---|---|---|---|---|---|---|
| CSCR107 | 3 | A | 6176AC22UCS022, 6176AC22UCS105, 6176AC23UCS001-6176AC23UCS028 | 30 | 60 | leena@ace.edu |
| CSCR107 | 2 | A | 2403617610421001-2403617610421018, (No Numbers: 19), 2403617610421020-2403617610422031 | 30 | 60 | leena@ace.edu |
| CSCR109 | 3 | A | 6176AC23UCS029, 6176AC23UCS030, (No Numbers: 31), 6176AC23UCS032-6176AC23UCS059 | 30 | 60 | ravi@ace.edu |

**Supported register number formats:**
- Single: `6176AC23UCS060`
- Comma list: `6176AC22UCS022, 6176AC22UCS105`
- Range: `6176AC23UCS001-6176AC23UCS028` (auto-expands)
- Skip numbers: `(No Numbers: 19)` — skips that number in a range

---

## Upload Order
1. Staff (with tutor handling_year/section)
2. Subjects
3. CIA Schedule
4. Seating Allotment (assign invigilators via column or admin panel)
