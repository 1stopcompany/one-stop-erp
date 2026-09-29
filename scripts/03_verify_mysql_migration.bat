@echo off
setlocal

if not exist manage.py (
  echo Run this script from the ERP project root.
  exit /b 1
)

if not exist sqlite_inventory.json (
  echo sqlite_inventory.json was not found.
  exit /b 1
)

py manage.py check --database default
if errorlevel 1 exit /b 1

py manage.py database_inventory --output mysql_inventory.json --compare sqlite_inventory.json
if errorlevel 1 exit /b 1

py manage.py test
if errorlevel 1 exit /b 1

echo.
echo MySQL data verification and tests completed successfully.
endlocal
