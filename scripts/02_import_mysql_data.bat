@echo off
setlocal

if not exist manage.py (
  echo Run this script from the ERP project root.
  exit /b 1
)

if not exist sqlite_data.json (
  echo sqlite_data.json was not found. Run scripts\01_export_sqlite_data.bat first.
  exit /b 1
)

py manage.py check --database default
if errorlevel 1 exit /b 1

py manage.py migrate
if errorlevel 1 exit /b 1

py manage.py loaddata sqlite_data.json
if errorlevel 1 exit /b 1

py manage.py database_inventory --output mysql_inventory.json --compare sqlite_inventory.json
if errorlevel 1 exit /b 1

py manage.py test
if errorlevel 1 exit /b 1

echo.
echo MySQL migration and verification completed successfully.
endlocal
