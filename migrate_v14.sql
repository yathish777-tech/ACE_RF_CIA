-- migrate_v14.sql  (MySQL syntax)
-- Many-to-Many Staff Roles Migration
-- Converts existing role + secondary_role columns into the staff_roles junction table.
-- Safe to run multiple times (INSERT IGNORE = no duplicate errors).
--
-- Run ONCE before restarting the app:
--   mysql -u root -p cia_rf_1 < migrate_v14.sql
-- ─────────────────────────────────────────────────────────────────────────────

-- Step 1: Create the junction table if it does not already exist
CREATE TABLE IF NOT EXISTS staff_roles (
    user_id   INT NOT NULL,
    role_name VARCHAR(30) NOT NULL,
    PRIMARY KEY (user_id, role_name),
    CONSTRAINT fk_staff_roles_user
        FOREIGN KEY (user_id) REFERENCES `user`(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Step 2: Migrate existing primary roles for all staff accounts
INSERT IGNORE INTO staff_roles (user_id, role_name)
SELECT id, role
FROM   `user`
WHERE  role IN ('subject_staff', 'tutor', 'hod', 'coordinator', 'admin');

-- Step 3: Migrate existing secondary roles (where populated)
INSERT IGNORE INTO staff_roles (user_id, role_name)
SELECT id, secondary_role
FROM   `user`
WHERE  secondary_role IS NOT NULL
  AND  secondary_role != ''
  AND  secondary_role IN ('subject_staff', 'tutor', 'hod', 'coordinator', 'admin');

-- Verify:
-- SELECT u.name, u.role, u.secondary_role, GROUP_CONCAT(sr.role_name) AS all_roles
-- FROM `user` u
-- LEFT JOIN staff_roles sr ON u.id = sr.user_id
-- WHERE u.role != 'student'
-- GROUP BY u.id;
