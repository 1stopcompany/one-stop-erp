#!/bin/bash

# One Stop ERP System - Linux/macOS Startup Script

echo "======================================"
echo "One Stop ERP System"
echo "======================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements-sqlite.txt

# Run migrations
echo "Checking Django configuration..."
python manage.py check

echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start development server
echo ""
echo "======================================"
echo "Starting Django Development Server"
echo "======================================"
echo ""
echo "Access the application at:"
echo "http://localhost:8000"
echo ""
echo "Admin Panel:"
echo "http://localhost:8000/admin"
echo ""
echo "Press Ctrl+C to stop the server"
echo "======================================"
echo ""

python manage.py runserver
