# Email Reminder System Documentation

## Overview

The Email Reminder System is an automated notification service that sends email reminders to site engineers to fill their daily and monthly construction reports. The system is fully configurable, scalable, and includes comprehensive audit logging.

---

## Features

✅ **Automated Reminders**
- Daily report reminders
- Monthly report reminders
- Overdue report reminders
- Customizable frequency and timing

✅ **Flexible Configuration**
- Multiple reminder types
- Customizable send times
- Target specific engineers or projects
- Day-of-week scheduling for weekly/bi-weekly reminders

✅ **Email Management**
- HTML and plain text email templates
- Template variable substitution
- Email logging and audit trail
- Error tracking and retry capability

✅ **Scheduling**
- Daily, weekly, bi-weekly, and monthly schedules
- Custom time scheduling
- Automatic next-send calculation
- Prevents duplicate sends

✅ **Admin Interface**
- Full Django admin integration
- Easy reminder creation and management
- Email log viewing
- Template management

---

## Installation

### 1. Add Models to Django

The email reminder system includes the following models:

```python
# reports/email_models.py
- EmailReminder: Reminder configuration
- EmailLog: Email sending audit log
- ReminderSchedule: Schedule tracking
- ReminderTemplate: Email templates
```

### 2. Create Migrations

```bash
python manage.py makemigrations reports
python manage.py migrate
```

### 3. Load Default Templates

```bash
python manage.py shell
>>> from reports.email_templates import load_default_templates
>>> load_default_templates()
```

### 4. Configure Email Settings

In `settings.py`:

```python
# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'  # or your email provider
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'your-email@gmail.com'
EMAIL_HOST_PASSWORD = 'your-app-password'
DEFAULT_FROM_EMAIL = 'noreply@your-company.com'

# Site Configuration
SITE_URL = 'http://localhost:8000'  # or your production URL
COMPANY_NAME = 'Your Company Name'
```

---

## Usage

### Manual Reminder Sending

#### Send All Active Reminders
```bash
python manage.py send_reminders
```

#### Send Only Daily Reminders
```bash
python manage.py send_reminders --daily
```

#### Send Only Monthly Reminders
```bash
python manage.py send_reminders --monthly
```

#### Send Specific Reminder
```bash
python manage.py send_reminders --reminder-id 1
```

#### Test Mode (Preview without sending)
```bash
python manage.py send_reminders --test
```

### Programmatic Usage

```python
from reports.email_service import EmailService
from reports.email_models import EmailReminder
from accounts.models import CustomUser

# Send reminder to specific engineer
engineer = CustomUser.objects.get(username='engineer1')
EmailService.send_daily_report_reminder(engineer)

# Send batch reminders
reminder = EmailReminder.objects.get(id=1)
EmailService.send_batch_reminders(reminder)

# Send all active reminders
EmailService.send_all_active_reminders()
```

---

## Configuration

### Creating a Reminder in Admin

1. Go to Django Admin: `/admin/`
2. Navigate to **Email Reminders**
3. Click **Add Email Reminder**
4. Fill in the form:

| Field | Description |
|-------|-------------|
| **Name** | Reminder name (e.g., "Daily Report Reminder") |
| **Description** | Optional description |
| **Reminder Type** | Daily, Monthly, or Both |
| **Frequency** | Daily, Weekly, Bi-weekly, or Monthly |
| **Send Time** | Morning (8 AM), Afternoon (1 PM), Evening (5 PM), End of Day (6 PM), or Custom |
| **Custom Time** | If "Custom" selected, specify exact time |
| **Target Engineers** | Leave empty for all, or select specific engineers |
| **Target Projects** | Leave empty for all, or select specific projects |
| **Days of Week** | For weekly/bi-weekly, select which days to send |
| **Is Active** | Enable/disable the reminder |

### Example Configurations

#### Daily Report Reminder - Every Weekday at 5 PM
```
Name: Weekday Daily Reports
Reminder Type: Daily
Frequency: Weekly
Send Time: Evening (5 PM)
Days: Monday-Friday
Target Engineers: All
```

#### Monthly Report Reminder - First of Month
```
Name: Monthly Reports
Reminder Type: Monthly
Frequency: Monthly
Send Time: Morning (8 AM)
Target Projects: [Select specific projects]
```

#### Both Reports - Daily
```
Name: Daily Reminders
Reminder Type: Both
Frequency: Daily
Send Time: End of Day (6 PM)
Days: Monday-Friday
```

---

## Email Templates

### Default Templates

The system includes three default templates:

1. **Daily Report Reminder**
   - Reminds engineers to fill daily reports
   - Lists items to document
   - Provides direct link to create report

2. **Monthly Report Reminder**
   - Reminds engineers to fill monthly reports
   - Lists sections to complete
   - Provides direct link to create report

3. **Overdue Report Reminder**
   - Urgent reminder for overdue reports
   - Emphasizes importance
   - Provides direct link to submit

### Template Variables

Available variables for use in templates:

```
{{ engineer_name }}      - Engineer's full name
{{ engineer_email }}     - Engineer's email address
{{ report_type }}        - Type of report (Daily/Monthly)
{{ dashboard_url }}      - Link to dashboard
{{ create_report_url }}  - Link to create report
{{ company_name }}       - Company name
```

### Creating Custom Templates

1. Go to Django Admin: `/admin/`
2. Navigate to **Reminder Templates**
3. Click **Add Reminder Template**
4. Fill in:
   - **Name**: Template name
   - **Template Type**: daily, monthly, overdue, or welcome
   - **Subject**: Email subject line
   - **Body HTML**: HTML email body with {{variables}}
   - **Body Text**: Plain text version (optional)
   - **Is Active**: Enable/disable

### Template Example

```html
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; }
        .button { background-color: #3498db; color: white; padding: 10px 20px; }
    </style>
</head>
<body>
    <h1>Report Reminder</h1>
    <p>Hi {{ engineer_name }},</p>
    <p>Please fill your {{ report_type }} report.</p>
    <a href="{{ create_report_url }}" class="button">Create Report</a>
</body>
</html>
```

---

## Scheduling with Cron

### Setup Cron Job

Edit crontab:
```bash
crontab -e
```

Add entries:

```bash
# Send reminders every day at 5 PM
0 17 * * * cd /path/to/project && python manage.py send_reminders

# Send reminders every weekday at 5 PM
0 17 * * 1-5 cd /path/to/project && python manage.py send_reminders

# Send reminders every morning at 8 AM
0 8 * * * cd /path/to/project && python manage.py send_reminders --daily

# Send reminders at end of day (6 PM)
0 18 * * * cd /path/to/project && python manage.py send_reminders --monthly
```

### Setup with Celery (Optional)

```python
# celery.py or tasks.py
from celery import shared_task
from reports.email_service import EmailService

@shared_task
def send_email_reminders():
    """Send email reminders"""
    return EmailService.send_all_active_reminders()
```

In `settings.py`:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'send-email-reminders': {
        'task': 'reports.tasks.send_email_reminders',
        'schedule': crontab(hour=17, minute=0),  # 5 PM daily
    },
}
```

---

## Email Logging

### Viewing Email Logs

1. Go to Django Admin: `/admin/`
2. Navigate to **Email Logs**
3. View all sent emails with status

### Email Log Fields

| Field | Description |
|-------|-------------|
| **Subject** | Email subject line |
| **Recipient** | Engineer who received email |
| **Status** | Sent, Failed, Bounced, Opened, Clicked |
| **Sent At** | When email was sent |
| **Opened At** | When email was opened (if tracked) |
| **Clicked At** | When email link was clicked (if tracked) |
| **Error Message** | If failed, reason for failure |

### Filtering Logs

```python
# Get all failed emails
from reports.email_models import EmailLog
failed = EmailLog.objects.filter(status='failed')

# Get emails sent to specific engineer
engineer_emails = EmailLog.objects.filter(recipient__username='engineer1')

# Get emails from specific reminder
reminder_emails = EmailLog.objects.filter(reminder__id=1)

# Get emails from last 7 days
from django.utils import timezone
from datetime import timedelta
recent = EmailLog.objects.filter(
    sent_at__gte=timezone.now() - timedelta(days=7)
)
```

---

## Reminder Schedules

### Tracking Schedules

The system automatically creates and updates reminder schedules for each engineer.

```python
from reports.email_models import ReminderSchedule

# Get schedule for engineer
schedule = ReminderSchedule.objects.get(
    reminder__id=1,
    engineer__username='engineer1'
)

# View last sent and next send times
print(f"Last sent: {schedule.last_sent}")
print(f"Next send: {schedule.next_send}")
print(f"Times sent: {schedule.send_count}")
```

### Manual Schedule Updates

```python
# Update next send time
schedule.update_next_send()

# Deactivate schedule
schedule.is_active = False
schedule.save()
```

---

## API Integration

### Send Reminder via API

```python
from django.http import JsonResponse
from reports.email_service import EmailService
from reports.email_models import EmailReminder
from accounts.models import CustomUser

def send_reminder_api(request, reminder_id):
    """API endpoint to send reminder"""
    try:
        reminder = EmailReminder.objects.get(id=reminder_id)
        sent = EmailService.send_batch_reminders(reminder)
        
        return JsonResponse({
            'success': True,
            'message': f'Sent {sent} reminders',
            'count': sent
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)
```

---

## Troubleshooting

### Emails Not Sending

**Problem**: Reminders not being sent

**Solutions**:
1. Check email configuration in `settings.py`
2. Verify SMTP credentials
3. Check email logs for errors: `/admin/reports/emaillog/`
4. Test email manually:
   ```python
   python manage.py shell
   >>> from django.core.mail import send_mail
   >>> send_mail('Test', 'Test message', 'from@example.com', ['to@example.com'])
   ```

### Duplicate Emails

**Problem**: Engineers receiving duplicate reminders

**Solutions**:
1. Check reminder frequency and days of week
2. Verify cron job isn't running multiple times
3. Check ReminderSchedule for correct next_send times
4. Review email logs to see send history

### Template Not Rendering

**Problem**: Email variables not being replaced

**Solutions**:
1. Check template syntax: `{{ variable_name }}`
2. Verify variable names match available variables
3. Test template rendering:
   ```python
   from reports.email_models import ReminderTemplate
   template = ReminderTemplate.objects.first()
   context = {'engineer_name': 'John', ...}
   html = template.render(context)
   ```

### Emails Going to Spam

**Problem**: Reminders ending up in spam folder

**Solutions**:
1. Add SPF record for email domain
2. Add DKIM signature
3. Add DMARC policy
4. Use professional email address (not Gmail)
5. Include unsubscribe link in template

---

## Best Practices

1. **Test Before Production**
   - Use `--test` flag to preview emails
   - Send test emails to small group first

2. **Monitor Email Logs**
   - Regularly check email logs for failures
   - Address delivery issues promptly

3. **Optimize Timing**
   - Send reminders when engineers are likely to read them
   - Avoid too frequent reminders (causes fatigue)

4. **Personalize Templates**
   - Use engineer names in greeting
   - Include relevant project information
   - Make call-to-action clear

5. **Track Engagement**
   - Monitor email open rates
   - Track link clicks
   - Adjust timing based on engagement

6. **Maintain Templates**
   - Keep templates updated with current URLs
   - Test templates regularly
   - Archive old templates

---

## Security Considerations

1. **Email Credentials**
   - Store in environment variables
   - Never commit to version control
   - Use app-specific passwords

2. **Template Injection**
   - Validate template variables
   - Use Django's template system
   - Avoid raw string substitution

3. **Email Logs**
   - Contains sensitive information
   - Limit admin access
   - Archive old logs

4. **Rate Limiting**
   - Prevent email bombing
   - Implement cooldown periods
   - Monitor for abuse

---

## Performance Optimization

1. **Batch Sending**
   - Send multiple emails in single operation
   - Reduces database queries

2. **Caching**
   - Cache active reminders
   - Cache template content

3. **Database Indexes**
   - Indexes on recipient, status, sent_at
   - Improves query performance

4. **Async Processing**
   - Use Celery for background tasks
   - Prevents blocking web requests

---

## Migration from Old System

If migrating from existing reminder system:

```python
# Create reminders from old configuration
from reports.email_models import EmailReminder
from accounts.models import CustomUser

# Example: Create daily reminder for all engineers
reminder = EmailReminder.objects.create(
    name='Daily Report Reminder',
    reminder_type='daily',
    frequency='daily',
    send_time='evening',
    is_active=True,
    created_by=CustomUser.objects.filter(is_admin=True).first()
)

# Add all engineers
reminder.target_engineers.set(
    CustomUser.objects.filter(is_site_engineer=True)
)
```

---

## Support & Troubleshooting

For issues or questions:

1. Check Django admin interface
2. Review email logs
3. Check server logs
4. Test manually with management command
5. Review this documentation

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | Dec 21, 2025 | Initial release |

---

**Status**: Production Ready  
**Last Updated**: December 21, 2025
