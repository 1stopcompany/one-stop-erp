# Developer Guide - Construction Reports System

## For Developers & Contributors

This guide provides technical information for developers working with the Construction Reports Management System.

---

## Development Environment Setup

### 1. Clone Repository
```bash
git clone your-repo-url
cd site_engineer_reports
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

### 3. Install Development Dependencies
```bash
pip install -r requirements.txt
pip install django-debug-toolbar  # For debugging
pip install black flake8 isort     # For code quality
```

### 4. Configure Development Settings
Create `.env` file:
```
DEBUG=True
SECRET_KEY=dev-secret-key
DATABASE_URL=sqlite:///db.sqlite3
ALLOWED_HOSTS=localhost,127.0.0.1
```

### 5. Initialize Database
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py shell < create_fixtures.py
```

### 6. Run Development Server
```bash
python manage.py runserver
```

---

## Project Architecture

### Models Layer (reports/models.py)

**Base Model Pattern**:
```python
class BaseReport(models.Model):
    # Common fields for all reports
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    site_engineer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        abstract = True
```

**Inheritance Pattern**:
- `DailyReport` extends `BaseReport`
- `MonthlyReport` extends `BaseReport`
- Each has separate database table
- Shared functionality in base class

### Views Layer (reports/views.py)

**View Pattern**:
```python
@login_required
@require_http_methods(["GET", "POST"])
def report_create(request):
    # Check permissions
    if not request.user.profile.is_site_engineer():
        messages.error(request, 'Permission denied')
        return redirect('dashboard')
    
    # Handle GET/POST
    if request.method == 'POST':
        form = ReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.site_engineer = request.user
            report.save()
            return redirect('report_detail', pk=report.pk)
    else:
        form = ReportForm()
    
    return render(request, 'template.html', {'form': form})
```

### Forms Layer (reports/forms.py)

**Form Pattern**:
```python
class DailyReportForm(forms.ModelForm):
    class Meta:
        model = DailyReport
        fields = ['project', 'report_date', 'weather', 'remarks']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-control'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        # Custom validation
        return cleaned_data
```

**Formset Pattern**:
```python
DailyWorkForceFormSet = inlineformset_factory(
    DailyReport,
    DailyWorkForce,
    form=DailyWorkForceForm,
    extra=1,
    can_delete=True
)
```

---

## Code Style Guide

### Python (PEP 8)

**Naming Conventions**:
```python
# Classes: PascalCase
class DailyReport(models.Model):
    pass

# Functions/Methods: snake_case
def get_report_status(report):
    pass

# Constants: UPPER_SNAKE_CASE
MAX_FILE_SIZE = 100 * 1024 * 1024

# Private: _leading_underscore
def _internal_helper():
    pass
```

**Line Length**: Max 88 characters (Black formatter)

**Imports**: Organize in groups
```python
# Standard library
import os
from datetime import datetime

# Third-party
from django.db import models
from rest_framework import serializers

# Local
from .models import DailyReport
from .utils import generate_pdf
```

### Format Code
```bash
# Auto-format with Black
black .

# Check style with Flake8
flake8 .

# Sort imports
isort .
```

---

## Database Migrations

### Creating Migrations

```bash
# Create migration for model changes
python manage.py makemigrations

# Create empty migration for data changes
python manage.py makemigrations --empty reports --name add_custom_field

# Show migration plan
python manage.py migrate --plan
```

### Writing Custom Migrations

```python
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('reports', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailyreport',
            name='custom_field',
            field=models.CharField(max_length=100, default=''),
        ),
    ]
```

### Applying Migrations

```bash
# Apply all pending migrations
python manage.py migrate

# Apply specific app migrations
python manage.py migrate reports

# Apply specific migration
python manage.py migrate reports 0002

# Rollback migration
python manage.py migrate reports 0001
```

---

## Testing

### Unit Tests

```python
# reports/tests.py
from django.test import TestCase
from django.contrib.auth.models import User
from .models import DailyReport, Project

class DailyReportTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        self.project = Project.objects.create(
            name='Test Project',
            location='Test Location',
            start_date='2025-01-01'
        )
    
    def test_create_daily_report(self):
        report = DailyReport.objects.create(
            project=self.project,
            site_engineer=self.user,
            report_date='2025-12-20'
        )
        self.assertEqual(report.status, 'draft')
        self.assertIsNotNone(report.report_number)
    
    def test_submit_report(self):
        report = DailyReport.objects.create(
            project=self.project,
            site_engineer=self.user
        )
        report.submit()
        self.assertEqual(report.status, 'submitted')
        self.assertIsNotNone(report.submitted_at)
```

### View Tests

```python
from django.test import Client, TestCase
from django.urls import reverse

class DailyReportViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
    
    def test_daily_report_list_requires_login(self):
        response = self.client.get(reverse('reports:daily_report_list'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_daily_report_list_authenticated(self):
        self.client.login(username='testuser', password='testpass')
        response = self.client.get(reverse('reports:daily_report_list'))
        self.assertEqual(response.status_code, 200)
```

### Running Tests

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test reports

# Run specific test class
python manage.py test reports.tests.DailyReportTestCase

# Run with verbose output
python manage.py test -v 2

# Run with coverage
pip install coverage
coverage run --source='.' manage.py test
coverage report
coverage html
```

---

## Debugging

### Django Debug Toolbar

```python
# settings.py
INSTALLED_APPS = [
    # ...
    'debug_toolbar',
]

MIDDLEWARE = [
    # ...
    'debug_toolbar.middleware.DebugToolbarMiddleware',
]

INTERNAL_IPS = ['127.0.0.1']
```

### Print Debugging

```python
from django.db import connection
from django.test.utils import CaptureQueriesContext

# Check queries
with CaptureQueriesContext(connection) as ctx:
    reports = DailyReport.objects.all()
    for report in reports:
        print(report.project.name)  # N+1 query problem

print(f"Total queries: {len(ctx)}")
for query in ctx:
    print(query['sql'])
```

### Shell Debugging

```bash
python manage.py shell

>>> from reports.models import DailyReport
>>> reports = DailyReport.objects.all()
>>> reports.count()
>>> reports.first()
>>> reports.filter(status='approved')
>>> reports.values('status').annotate(count=Count('id'))
```

---

## Performance Optimization

### Database Query Optimization

```python
# Bad: N+1 queries
reports = DailyReport.objects.all()
for report in reports:
    print(report.project.name)  # Extra query per report

# Good: Use select_related
reports = DailyReport.objects.select_related('project', 'site_engineer')
for report in reports:
    print(report.project.name)  # No extra queries

# Good: Use prefetch_related for reverse relations
reports = DailyReport.objects.prefetch_related('workforce', 'equipment')
for report in reports:
    for wf in report.workforce.all():
        print(wf.category)  # No extra queries
```

### Caching

```python
from django.views.decorators.cache import cache_page
from django.core.cache import cache

# Cache view for 15 minutes
@cache_page(60 * 15)
def expensive_view(request):
    pass

# Cache specific data
def get_report_stats():
    stats = cache.get('report_stats')
    if stats is None:
        stats = {
            'total': DailyReport.objects.count(),
            'approved': DailyReport.objects.filter(status='approved').count(),
        }
        cache.set('report_stats', stats, 60 * 5)  # 5 minutes
    return stats
```

### Database Indexing

```python
class DailyReport(models.Model):
    report_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True  # Create index
    )
    report_date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        db_index=True
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['project', 'report_date']),
            models.Index(fields=['status', '-created_at']),
        ]
```

---

## API Development

### Creating API Endpoints

```python
# reports/api.py
from rest_framework import viewsets, serializers
from .models import DailyReport

class DailyReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReport
        fields = ['id', 'report_number', 'project', 'status', 'report_date']

class DailyReportViewSet(viewsets.ModelViewSet):
    queryset = DailyReport.objects.all()
    serializer_class = DailyReportSerializer
    
    def get_queryset(self):
        # Filter by user
        if self.request.user.profile.is_site_engineer():
            return DailyReport.objects.filter(site_engineer=self.request.user)
        return DailyReport.objects.all()
```

### URL Configuration

```python
# reports/urls.py
from rest_framework.routers import DefaultRouter
from .api import DailyReportViewSet

router = DefaultRouter()
router.register(r'daily-reports', DailyReportViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
]
```

---

## Security Best Practices

### Authentication & Authorization

```python
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

@login_required
def sensitive_view(request):
    # Check permission
    if not request.user.profile.is_project_manager():
        raise PermissionDenied
    
    # Process request
    pass
```

### CSRF Protection

```html
<!-- In forms -->
<form method="POST">
    {% csrf_token %}
    <!-- form fields -->
</form>
```

### SQL Injection Prevention

```python
# Good: Use ORM
reports = DailyReport.objects.filter(status='approved')

# Bad: Raw SQL (avoid)
reports = DailyReport.objects.raw(
    'SELECT * FROM reports WHERE status = %s',
    [status]
)
```

### XSS Prevention

```html
<!-- Good: Auto-escaped -->
<p>{{ user.name }}</p>

<!-- Bad: Unsafe (avoid) -->
<p>{{ user.bio|safe }}</p>

<!-- Use mark_safe only when necessary -->
{% autoescape off %}
{{ trusted_html }}
{% endautoescape %}
```

---

## Logging

### Configure Logging

```python
# settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': 'logs/error.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}
```

### Use Logging

```python
import logging

logger = logging.getLogger(__name__)

def create_report(request):
    try:
        report = DailyReport.objects.create(...)
        logger.info(f'Report created: {report.report_number}')
    except Exception as e:
        logger.error(f'Error creating report: {str(e)}')
        raise
```

---

## Deployment Checklist for Developers

- [ ] Code follows PEP 8 style guide
- [ ] All tests pass
- [ ] No debug statements left in code
- [ ] No hardcoded secrets
- [ ] Database migrations created and tested
- [ ] Static files collected
- [ ] Documentation updated
- [ ] Code reviewed by team
- [ ] Performance tested
- [ ] Security audit completed

---

## Useful Commands

```bash
# Check code style
flake8 .

# Format code
black .

# Sort imports
isort .

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Run tests
python manage.py test

# Open shell
python manage.py shell

# Collect static files
python manage.py collectstatic

# Check for issues
python manage.py check

# Show installed apps
python manage.py show_apps
```

---

## Resources

- Django Documentation: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- Python Style Guide: https://pep8.org/
- Django Best Practices: https://django-best-practices.readthedocs.io/

---

**Last Updated**: December 20, 2025  
**Version**: 1.0.0
