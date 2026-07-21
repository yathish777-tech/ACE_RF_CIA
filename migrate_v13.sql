-- v13: Align existing staff_assignments table with StaffAssignment model.
-- Preserves existing assignment rows from the partial implementation.

ALTER TABLE staff_assignments ADD INDEX idx_staff_assignments_staff (staff_id);
ALTER TABLE staff_assignments DROP INDEX uq_staff_assignment;

ALTER TABLE staff_assignments
    CHANGE academic_year academic_year_id VARCHAR(20) NOT NULL DEFAULT '',
    CHANGE department department_id VARCHAR(100) NULL,
    CHANGE semester semester_id INTEGER NOT NULL,
    CHANGE section section_id VARCHAR(5) NOT NULL;

UPDATE staff_assignments
SET academic_year_id = COALESCE(academic_year_id, ''),
    department_id = COALESCE(department_id, '');

ALTER TABLE staff_assignments
    MODIFY department_id VARCHAR(100) NOT NULL DEFAULT '',
    MODIFY created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    MODIFY updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

ALTER TABLE staff_assignments
    ADD CONSTRAINT uq_staff_assignment
    UNIQUE (staff_id, academic_year_id, department_id, semester_id, section_id, subject_id);
