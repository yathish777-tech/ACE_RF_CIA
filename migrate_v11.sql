ALTER TABLE seating_allotment
  ADD COLUMN exam_date DATE NULL;

ALTER TABLE exam_attendance
  ADD COLUMN exam_date DATE NULL;
