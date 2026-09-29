@echo off
REM One Stop ERP System - Windows Startup Script

echo ======================================
echo One Stop ERP System
echo ======================================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install/update dependencies
echo Installing dependencies...
pip install -q -r requirements-sqlite.txt

REM Run migrations
echo Checking Django configuration...
python manage.py check

echo Running database migrations...
python manage.py migrate --noinput

REM Collect static files
echo Collecting static files...
python manage.py collectstatic --noinput

REM Start development server
echo.
echo ======================================
echo Starting Django Development Server
echo ======================================
echo.
echo Access the application at:
echo http://localhost:8000
echo.
echo Admin Panel:
echo http://localhost:8000/admin
echo.
echo Press Ctrl+C to stop the server
echo ======================================
echo.

python manage.py runserver
