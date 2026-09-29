@echo off
setlocal

if not exist manage.py (
  echo Run this script from the ERP project root.
  exit /b 1
)

copy /Y db.sqlite3 db_before_mysql.sqlite3 >nul
if errorlevel 1 exit /b 1

py manage.py check
if errorlevel 1 exit /b 1

py manage.py database_inventory --output sqlite_inventory.json
if errorlevel 1 exit /b 1

py manage.py dumpdata ^
  --natural-foreign ^
  --natural-primary ^
  --exclude contenttypes ^
  --exclude auth.permission ^
  --exclude sessions.session ^
  --exclude admin.logentry ^
  --indent 2 ^
  --output sqlite_data.json
if errorlevel 1 exit /b 1

echo.
echo SQLite backup, inventory, and fixture created successfully.
endlocal
