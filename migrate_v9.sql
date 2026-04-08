-- ============================================================
-- CIA Retest Portal v9 — Bug-fix Migration
-- Run ONLY if upgrading from v8
-- ============================================================
USE cia_rf_1;

-- No schema changes in v9 — all fixes are in Python/HTML code:
-- 1. apply.html: form no longer auto-refreshes on file select
-- 2. apply.html: CIA exam date auto-fills correctly via AJAX
-- 3. manage_cia_dates.html: edit CIA URL fixed (/edit/${id})
-- 4. user.py: view_attachment route added (was missing)
-- 5. apply.html: submit button no longer stays disabled

SELECT 'v9 bug-fix migration: no schema changes needed.' AS status;
