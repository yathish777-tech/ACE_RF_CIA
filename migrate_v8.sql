-- ============================================================
-- CIA Retest Portal v8 Migration
-- Run this ONLY if upgrading from v7
-- ============================================================
USE cia_rf_1;

-- 1. Add year and section fields to users table (for students)
ALTER TABLE user
  ADD COLUMN IF NOT EXISTS year INT DEFAULT NULL COMMENT '1=First Year, 2=Second Year, etc.',
  ADD COLUMN IF NOT EXISTS section VARCHAR(5) DEFAULT NULL COMMENT 'A, B, C',
  ADD COLUMN IF NOT EXISTS handling_year INT DEFAULT NULL COMMENT 'For staff: which year they handle',
  ADD COLUMN IF NOT EXISTS handling_section VARCHAR(5) DEFAULT NULL COMMENT 'For staff: which section they handle';

-- 2. Add year and section to subjects table
ALTER TABLE subject
  ADD COLUMN IF NOT EXISTS year INT DEFAULT NULL COMMENT 'Derived from semester (sem 1-2=Y1, 3-4=Y2, 5-6=Y3, 7-8=Y4)',
  ADD COLUMN IF NOT EXISTS section VARCHAR(5) DEFAULT NULL COMMENT 'Section A, B, C - NULL means all sections';

-- 3. Add subject_staff_section mapping table (staff-subject-section-semester link)
CREATE TABLE IF NOT EXISTS subject_staff_section (
  id INT AUTO_INCREMENT PRIMARY KEY,
  subject_id INT NOT NULL,
  staff_id INT NOT NULL,
  semester INT NOT NULL,
  section VARCHAR(5) NOT NULL DEFAULT 'A',
  academic_year VARCHAR(20) DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (subject_id) REFERENCES subject(id) ON DELETE CASCADE,
  FOREIGN KEY (staff_id) REFERENCES user(id) ON DELETE CASCADE,
  UNIQUE KEY uq_subj_staff_sec (subject_id, section, semester)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. Add section to retest_application
ALTER TABLE retest_application
  ADD COLUMN IF NOT EXISTS student_section VARCHAR(5) DEFAULT NULL COMMENT 'Student section A/B/C',
  ADD COLUMN IF NOT EXISTS student_year INT DEFAULT NULL COMMENT 'Academic year 1-4';

-- 5. Update year column in subject derived from semester
UPDATE subject SET year = CEIL(semester / 2) WHERE year IS NULL;

SELECT 'v8 migration complete.' AS status;
