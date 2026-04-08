-- ============================================================
-- CIA Retest Portal - MySQL Database Setup Script
-- Run this in MySQL Workbench or CLI before starting Flask
-- ============================================================

-- Create the database
CREATE DATABASE IF NOT EXISTS cia_rf_1 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Use it
USE cia_rf;

-- Verify connection works (Flask will auto-create all tables via SQLAlchemy)
SELECT 'Database cia_rf created successfully!' AS status;

-- ============================================================
-- After running this script, start Flask:
--   python app.py
-- Flask will auto-create all tables on first run.
-- Default admin credentials:
--   Email   : admin@dept.edu
--   Password: admin123
-- ============================================================
