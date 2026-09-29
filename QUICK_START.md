# Quick Start Guide - Site Engineer Reports System

Get up and running in 5 minutes!

## Prerequisites

- **Python 3.11+** installed
- **Git** (optional, for cloning)
- **Windows**, **Linux**, or **macOS**

## Option 1: Fastest Way (Recommended)

### Windows
```bash
# 1. Extract the project folder
# 2. Double-click: run_windows.bat
# 3. Wait for the server to start
# 4. Open browser: http://localhost:8000
```

### Linux/macOS
```bash
# 1. Extract the project folder
# 2. Open terminal in project directory
# 3. Run: chmod +x run_linux.sh && ./run_linux.sh
# 4. Open browser: http://localhost:8000
```

## Option 2: Manual Setup (5 minutes)

### Step 1: Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/macOS
python3.11 -m venv venv
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Setup Database
```bash
python manage.py migrate
```

### Step 4: Create Sample Data (Optional)
```bash
python manage.py shell < create_fixtures.py
```

### Step 5: Run Server
```bash
python manage.py runserver
```

## Access the Application

**URL**: http://localhost:8000

## Demo Credentials

| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Manager | manager | manager123 |
| Engineer | engineer | engineer123 |

## First Steps

### As Administrator
1. Login with admin credentials
2. Go to Admin Panel (http://localhost:8000/admin)
3. Create new users or projects
4. Manage system settings

### As Project Manager
1. Login with manager credentials
2. View and approve reports
3. Manage projects
4. Review engineer submissions

### As Site Engineer
1. Login with engineer credentials
2. Create new monthly report
3. Add floor activities
4. Submit for approval
5. Export as PDF

## Common Issues & Solutions

### Issue: "Python not found"
**Solution**: 
- Windows: Install Python from https://www.python.org/
- Linux: Run `sudo apt install python3.11`
- macOS: Run `brew install python@3.11`

### Issue: "No module named 'django'"
**Solution**: Ensure virtual environment is activated and run `pip install -r requirements.txt`

### Issue: "Database locked"
**Solution**: Delete `db.sqlite3` and run `python manage.py migrate` again

### Issue: Port 8000 already in use
**Solution**: Run `python manage.py runserver 8001` to use a different port

## Next Steps

1. **Read Documentation**
   - README.md - Full feature documentation
   - DEPLOYMENT.md - Production deployment guide

2. **Explore Features**
   - Create a project
   - Create a monthly report
   - Add activities and materials
   - Export to PDF

3. **Customize**
   - Edit settings in `config/settings.py`
   - Customize templates in `templates/`
   - Add your company logo

4. **Deploy to Production**
   - Follow DEPLOYMENT.md guide
   - Configure PostgreSQL
   - Set up SSL/HTTPS
   - Deploy to cloud or on-premises

## Useful Commands

```bash
# Create superuser for admin
python manage.py createsuperuser

# Create sample data
python manage.py shell < create_fixtures.py

# Backup database
python manage.py dumpdata > backup.json

# Restore database
python manage.py loaddata backup.json

# Run tests
python manage.py test

# Check for issues
python manage.py check

# Collect static files (production)
python manage.py collectstatic --noinput
```

## Getting Help

- Check README.md for detailed documentation
- Review DEPLOYMENT.md for deployment issues
- Check Django documentation: https://docs.djangoproject.com/

---

**Ready to start?** Run the startup script or follow Option 2 above!
