-- ============================================================
-- CIA Retest Portal v10 — Migration Script
-- Run ONLY if upgrading from v9
-- ============================================================
USE cia_rf_1;

-- ── 1. RetestApplication — retransmit tracking columns ──────
ALTER TABLE retest_application
  ADD COLUMN IF NOT EXISTS retransmit_count INT DEFAULT 0,
  ADD COLUMN IF NOT EXISTS retransmit_by    INT NULL,
  ADD COLUMN IF NOT EXISTS retransmit_at    DATETIME NULL;

ALTER TABLE retest_application
  ADD CONSTRAINT fk_retransmit_by
    FOREIGN KEY (retransmit_by) REFERENCES user(id) ON DELETE SET NULL;

-- ── 2. SeatingAllotment — hall-wise exam seating ─────────────
CREATE TABLE IF NOT EXISTS seating_allotment (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  hall_number      VARCHAR(30)  NOT NULL,
  year             INT          NULL,          -- 1-4
  section          VARCHAR(5)   NULL,          -- A / B / C
  register_numbers TEXT         NULL,          -- JSON list
  num_students     INT          NULL,
  total_students   INT          NULL,
  invigilator_id   INT          NULL,
  uploaded_by      INT          NULL,
  uploaded_at      DATETIME     DEFAULT NOW(),
  CONSTRAINT fk_seat_invig   FOREIGN KEY (invigilator_id) REFERENCES user(id) ON DELETE SET NULL,
  CONSTRAINT fk_seat_uploader FOREIGN KEY (uploaded_by)   REFERENCES user(id) ON DELETE SET NULL
);

-- ── 3. ExamAttendance — invigilator marks present/absent ─────
CREATE TABLE IF NOT EXISTS exam_attendance (
  id               INT AUTO_INCREMENT PRIMARY KEY,
  seating_id       INT          NOT NULL,
  hall_number      VARCHAR(30)  NOT NULL,
  register_number  VARCHAR(30)  NOT NULL,
  year             INT          NULL,
  section          VARCHAR(5)   NULL,
  status           VARCHAR(10)  NOT NULL DEFAULT 'present',  -- present / absent
  marked_by        INT          NULL,
  marked_at        DATETIME     DEFAULT NOW(),
  CONSTRAINT fk_att_seating  FOREIGN KEY (seating_id) REFERENCES seating_allotment(id) ON DELETE CASCADE,
  CONSTRAINT fk_att_marker   FOREIGN KEY (marked_by)  REFERENCES user(id) ON DELETE SET NULL,
  CONSTRAINT uq_attendance_seating_reg UNIQUE (seating_id, register_number)
);

SELECT 'v10 migration complete.' AS status;
