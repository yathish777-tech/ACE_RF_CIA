-- ============================================================
-- CIA Retest Portal v7 Migration
-- Run this ONLY if upgrading from v6
-- ============================================================
USE cia_rf_1;

-- No new columns in v7 (all window logic uses existing fields).
-- The auto-close behaviour is handled in Python (is_application_open()).
-- If upgrading from v5 or earlier, run migrate_v5.sql and migrate_v6.sql first.

SELECT 'v7 migration: No schema changes — just run the new code.' AS status;
