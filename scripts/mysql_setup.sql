-- Run this script in MySQL Workbench while connected as an administrative user.
-- Replace CHANGE_THIS_PASSWORD before execution.

CREATE DATABASE IF NOT EXISTS `one_stop_erp`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'one_stop_user'@'127.0.0.1'
  IDENTIFIED BY 'CHANGE_THIS_PASSWORD';

ALTER USER 'one_stop_user'@'127.0.0.1'
  IDENTIFIED BY 'CHANGE_THIS_PASSWORD';

GRANT ALL PRIVILEGES ON `one_stop_erp`.*
  TO 'one_stop_user'@'127.0.0.1';

-- Django creates and drops this database while running the automated tests.
GRANT ALL PRIVILEGES ON `test_one_stop_erp`.*
  TO 'one_stop_user'@'127.0.0.1';

FLUSH PRIVILEGES;
