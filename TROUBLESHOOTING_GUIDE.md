# Troubleshooting Guide

## Common Issues & Solutions

---

## Installation Issues

### Issue: ModuleNotFoundError: No module named 'django'

**Cause**: Virtual environment not activated or dependencies not installed

**Solution**:
```bash
# Activate virtual environment
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

---

### Issue: python: command not found

**Cause**: Python not installed or not in PATH

**Solution**:
```bash
# Check Python installation
python3 --version

# Use python3 instead of python
python3 manage.py runserver
```

---

### Issue: pip: command not found

**Cause**: pip not installed or not in PATH

**Solution**:
```bash
# Install pip
python3 -m pip install --upgrade pip

# Use python -m pip
python3 -m pip install -r requirements.txt
```

---

## Database Issues

### Issue: django.db.utils.OperationalError: no such table

**Cause**: Database migrations not applied

**Solution**:
```bash
# Apply all migrations
python manage.py migrate

# Check migration status
python manage.py showmigrations
```

---

### Issue: sqlite3.OperationalError: database is locked

**Cause**: Multiple processes accessing database simultaneously

**Solution**:
```bash
# Stop all Django processes
# Kill any running servers (Ctrl+C)

# Delete database and recreate
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

---

### Issue: ProgrammingError: relation does not exist

**Cause**: Migration not applied for new model

**Solution**:
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Verify
python manage.py check
```

---

### Issue: IntegrityError: UNIQUE constraint failed

**Cause**: Duplicate data in unique field

**Solution**:
```bash
# Check for duplicates
python manage.py shell
>>> from reports.models import DailyReport
>>> DailyReport.objects.values('report_number').annotate(count=Count('id')).filter(count__gt=1)

# Delete duplicates or reset database
rm db.sqlite3
python manage.py migrate
```

---

## Server Issues

### Issue: Address already in use

**Cause**: Port 8000 already in use

**Solution**:
```bash
# Use different port
python manage.py runserver 8001

# Find and kill process using port 8000
# Linux/Mac:
lsof -ti:8000 | xargs kill -9

# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

---

### Issue: ConnectionRefusedError: [Errno 111] Connection refused

**Cause**: Database server not running (PostgreSQL)

**Solution**:
```bash
# Start PostgreSQL
sudo systemctl start postgresql

# Or use SQLite (no server needed)
# Update DATABASES in settings.py
```

---

### Issue: 500 Internal Server Error

**Cause**: Application error

**Solution**:
```bash
# Check error logs
tail -f /var/log/django/error.log

# Enable DEBUG mode (development only)
# settings.py: DEBUG = True

# Check for syntax errors
python manage.py check

# Test in shell
python manage.py shell
```

---

## Authentication Issues

### Issue: Login page shows but login fails

**Cause**: User doesn't exist or password incorrect

**Solution**:
```bash
# Create test user
python manage.py createsuperuser

# Or create via shell
python manage.py shell
>>> from django.contrib.auth.models import User
>>> User.objects.create_user('username', 'email@example.com', 'password')
```

---

### Issue: Permission Denied error

**Cause**: User doesn't have required role

**Solution**:
```bash
# Check user role
python manage.py shell
>>> from django.contrib.auth.models import User
>>> user = User.objects.get(username='engineer1')
>>> user.profile.role
'engineer'

# Update user role
>>> user.profile.role = 'manager'
>>> user.profile.save()
```

---

### Issue: Session expired or logged out unexpectedly

**Cause**: Session timeout or cookie issues

**Solution**:
```bash
# Clear browser cookies
# Browser → Settings → Clear browsing data → Cookies

# Or extend session timeout in settings.py
SESSION_COOKIE_AGE = 86400  # 24 hours

# Restart browser and login again
```

---

## Static Files Issues

### Issue: CSS/JavaScript not loading (404 errors)

**Cause**: Static files not collected

**Solution**:
```bash
# Collect static files
python manage.py collectstatic --noinput

# Check static files location
python manage.py findstatic style.css

# Verify STATIC_URL and STATIC_ROOT in settings.py
```

---

### Issue: Images not displaying

**Cause**: Media files path incorrect

**Solution**:
```bash
# Check MEDIA_URL and MEDIA_ROOT in settings.py
# Verify file exists in media directory

# In development, ensure media files are served
# urls.py should have:
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

---

## Form Issues

### Issue: Form validation errors not showing

**Cause**: Form not rendering errors properly

**Solution**:
```html
<!-- In template, ensure errors are displayed -->
{% if form.errors %}
    <div class="alert alert-danger">
        {{ form.errors }}
    </div>
{% endif %}

<!-- Or for specific field -->
{% if form.field_name.errors %}
    <span class="error">{{ form.field_name.errors }}</span>
{% endif %}
```

---

### Issue: CSRF token missing or invalid

**Cause**: CSRF token not included in form

**Solution**:
```html
<!-- Include CSRF token in all POST forms -->
<form method="POST">
    {% csrf_token %}
    <!-- form fields -->
</form>
```

---

### Issue: File upload fails

**Cause**: File size too large or format not allowed

**Solution**:
```python
# Check file size limit in settings.py
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600  # 100MB

# Check allowed file types
ALLOWED_FILE_EXTENSIONS = ['pdf', 'jpg', 'png', 'doc', 'docx']

# Verify media directory exists and is writable
mkdir -p media/reports
chmod 755 media
```

---

## Report Issues

### Issue: Report number not generating

**Cause**: Save method not called or error in save()

**Solution**:
```python
# Check DailyReport.save() method
# Ensure report_number is generated:
def save(self, *args, **kwargs):
    if not self.report_number:
        date_str = self.report_date.strftime('%Y%m%d')
        count = DailyReport.objects.filter(report_date=self.report_date).count()
        self.report_number = f"DCR-{self.project.id}-{date_str}-{count+1:03d}"
    super().save(*args, **kwargs)
```

---

### Issue: Can't submit report

**Cause**: Report status not 'draft' or validation error

**Solution**:
```bash
# Check report status
python manage.py shell
>>> from reports.models import DailyReport
>>> report = DailyReport.objects.get(id=1)
>>> report.status
'submitted'  # Can't submit if already submitted

# Reset to draft (if needed)
>>> report.status = 'draft'
>>> report.save()
```

---

### Issue: PDF export fails

**Cause**: ReportLab not installed or file permission issue

**Solution**:
```bash
# Install ReportLab
pip install reportlab

# Check file permissions
chmod 755 media/
chmod 755 media/reports/

# Test PDF generation
python manage.py shell
>>> from reports.utils import generate_daily_report_pdf
>>> from reports.models import DailyReport
>>> report = DailyReport.objects.first()
>>> pdf = generate_daily_report_pdf(report)
```

---

## API Issues

### Issue: API returns 401 Unauthorized

**Cause**: Not authenticated

**Solution**:
```bash
# Include authentication header
curl -H "Authorization: Bearer your-token" http://localhost:8000/api/reports/

# Or use session authentication
curl -b "sessionid=your-session-id" http://localhost:8000/api/reports/
```

---

### Issue: API returns 403 Forbidden

**Cause**: User doesn't have permission

**Solution**:
```bash
# Check user role and permissions
python manage.py shell
>>> from django.contrib.auth.models import User
>>> user = User.objects.get(username='engineer1')
>>> user.profile.role
'engineer'

# Ensure user has required role for endpoint
```

---

### Issue: API returns 404 Not Found

**Cause**: Endpoint doesn't exist or wrong URL

**Solution**:
```bash
# Check API URLs
python manage.py show_urls | grep api

# Verify endpoint exists
curl -v http://localhost:8000/api/reports/daily/
```

---

## Performance Issues

### Issue: Application running slowly

**Cause**: N+1 queries, missing indexes, or heavy computation

**Solution**:
```python
# Use select_related for foreign keys
reports = DailyReport.objects.select_related('project', 'site_engineer')

# Use prefetch_related for reverse relations
reports = DailyReport.objects.prefetch_related('workforce', 'equipment')

# Add database indexes
class DailyReport(models.Model):
    report_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, db_index=True)
```

---

### Issue: High memory usage

**Cause**: Loading too much data at once

**Solution**:
```python
# Use pagination
from django.core.paginator import Paginator

reports = DailyReport.objects.all()
paginator = Paginator(reports, 20)  # 20 per page
page = paginator.get_page(1)

# Use only() to limit fields
reports = DailyReport.objects.only('id', 'report_number', 'status')

# Use values() for dictionaries
reports = DailyReport.objects.values('id', 'report_number')
```

---

## Deployment Issues

### Issue: Static files not serving in production

**Cause**: STATIC_ROOT not configured or files not collected

**Solution**:
```bash
# Collect static files
python manage.py collectstatic --noinput

# Verify STATIC_ROOT in settings.py
STATIC_ROOT = '/var/www/static/'

# Configure Nginx to serve static files
location /static/ {
    alias /var/www/static/;
}
```

---

### Issue: Database connection fails in production

**Cause**: Incorrect database credentials or server not running

**Solution**:
```bash
# Test database connection
python manage.py dbshell

# Check database credentials in settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'reports_db',
        'USER': 'reports_user',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Verify database server is running
sudo systemctl status postgresql
```

---

### Issue: Email notifications not sending

**Cause**: Email configuration incorrect or SMTP server down

**Solution**:
```python
# Check email settings
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'

# Test email
python manage.py shell
>>> from django.core.mail import send_mail
>>> send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])
```

---

## Getting Help

### Debug Information to Collect

When reporting issues, include:
1. **Error message** (full traceback)
2. **Steps to reproduce** (exact steps that cause the issue)
3. **Environment** (Python version, Django version, OS)
4. **Logs** (error logs, server logs)
5. **Code** (relevant code snippets)

### Resources

- Django Documentation: https://docs.djangoproject.com/
- Stack Overflow: https://stackoverflow.com/questions/tagged/django
- GitHub Issues: Check project repository
- Community Forums: Django forum at discuss.djangoproject.com

### Getting Support

1. Check this troubleshooting guide
2. Search existing issues/documentation
3. Create detailed bug report with all information
4. Contact development team with reproducible example

---

**Last Updated**: December 20, 2025  
**Version**: 1.0.0
