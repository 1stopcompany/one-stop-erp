"""
Default Email Templates for Reminders

This module contains default email templates that can be loaded into the database.
"""

DEFAULT_TEMPLATES = [
    {
        'name': 'Daily Report Reminder',
        'template_type': 'daily',
        'subject': 'Reminder: Please Fill Your Daily Construction Report',
        'body_html': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #2c3e50; color: white; padding: 20px; text-align: center; border-radius: 5px; }
        .content { padding: 20px; background-color: #f9f9f9; border: 1px solid #ddd; margin: 20px 0; border-radius: 5px; }
        .button { display: inline-block; background-color: #3498db; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Daily Construction Report Reminder</h1>
        </div>
        
        <div class="content">
            <p>Hi {{ engineer_name }},</p>
            
            <p>This is a friendly reminder to fill your <strong>Daily Construction Report (DCR)</strong> for today.</p>
            
            <p>Please take a few minutes to document:</p>
            <ul>
                <li>Weather conditions</li>
                <li>Workforce details</li>
                <li>Equipment status</li>
                <li>Daily activities and progress</li>
                <li>Materials used</li>
                <li>Any visitors or incidents</li>
            </ul>
            
            <p>
                <a href="{{ create_report_url }}" class="button">Fill Daily Report Now</a>
            </p>
            
            <p>Or visit your dashboard: <a href="{{ dashboard_url }}">{{ dashboard_url }}</a></p>
            
            <p>Thank you for keeping our records up to date!</p>
            
            <p>Best regards,<br>{{ company_name }} System</p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>&copy; {{ company_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        ''',
        'body_text': '''
Daily Construction Report Reminder

Hi {{ engineer_name }},

This is a friendly reminder to fill your Daily Construction Report (DCR) for today.

Please take a few minutes to document:
- Weather conditions
- Workforce details
- Equipment status
- Daily activities and progress
- Materials used
- Any visitors or incidents

Fill Daily Report: {{ create_report_url }}

Or visit your dashboard: {{ dashboard_url }}

Thank you for keeping our records up to date!

Best regards,
{{ company_name }} System

---
This is an automated message. Please do not reply to this email.
© {{ company_name }}. All rights reserved.
        '''
    },
    {
        'name': 'Monthly Report Reminder',
        'template_type': 'monthly',
        'subject': 'Reminder: Please Fill Your Monthly Maintenance Report',
        'body_html': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #27ae60; color: white; padding: 20px; text-align: center; border-radius: 5px; }
        .content { padding: 20px; background-color: #f9f9f9; border: 1px solid #ddd; margin: 20px 0; border-radius: 5px; }
        .button { display: inline-block; background-color: #27ae60; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Monthly Maintenance Report Reminder</h1>
        </div>
        
        <div class="content">
            <p>Hi {{ engineer_name }},</p>
            
            <p>This is a friendly reminder to fill your <strong>Monthly Maintenance Report (MMR)</strong>.</p>
            
            <p>Please provide details on:</p>
            <ul>
                <li>Floor-by-floor activities and progress</li>
                <li>External works completed</li>
                <li>Materials supplied and used</li>
                <li>Upcoming works planned</li>
                <li>Any issues or concerns</li>
            </ul>
            
            <p>
                <a href="{{ create_report_url }}" class="button">Fill Monthly Report Now</a>
            </p>
            
            <p>Or visit your dashboard: <a href="{{ dashboard_url }}">{{ dashboard_url }}</a></p>
            
            <p>Thank you for your detailed reporting!</p>
            
            <p>Best regards,<br>{{ company_name }} System</p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>&copy; {{ company_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        ''',
        'body_text': '''
Monthly Maintenance Report Reminder

Hi {{ engineer_name }},

This is a friendly reminder to fill your Monthly Maintenance Report (MMR).

Please provide details on:
- Floor-by-floor activities and progress
- External works completed
- Materials supplied and used
- Upcoming works planned
- Any issues or concerns

Fill Monthly Report: {{ create_report_url }}

Or visit your dashboard: {{ dashboard_url }}

Thank you for your detailed reporting!

Best regards,
{{ company_name }} System

---
This is an automated message. Please do not reply to this email.
© {{ company_name }}. All rights reserved.
        '''
    },
    {
        'name': 'Overdue Report Reminder',
        'template_type': 'overdue',
        'subject': 'URGENT: Your {{ report_type }} is Overdue',
        'body_html': '''
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #e74c3c; color: white; padding: 20px; text-align: center; border-radius: 5px; }
        .content { padding: 20px; background-color: #fff5f5; border: 2px solid #e74c3c; margin: 20px 0; border-radius: 5px; }
        .button { display: inline-block; background-color: #e74c3c; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; margin: 10px 0; }
        .footer { text-align: center; color: #666; font-size: 12px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>URGENT: Report Overdue</h1>
        </div>
        
        <div class="content">
            <p>Hi {{ engineer_name }},</p>
            
            <p><strong style="color: #e74c3c;">Your {{ report_type }} is now overdue!</strong></p>
            
            <p>We have not received your {{ report_type }} submission. This report is important for project management and compliance.</p>
            
            <p>Please submit your report immediately:</p>
            
            <p>
                <a href="{{ create_report_url }}" class="button">Submit Report Now</a>
            </p>
            
            <p>If you have already submitted this report, please disregard this message.</p>
            
            <p>If you need assistance, please contact your project manager.</p>
            
            <p>Thank you,<br>{{ company_name }} System</p>
        </div>
        
        <div class="footer">
            <p>This is an automated message. Please do not reply to this email.</p>
            <p>&copy; {{ company_name }}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        ''',
        'body_text': '''
URGENT: Report Overdue

Hi {{ engineer_name }},

Your {{ report_type }} is now overdue!

We have not received your {{ report_type }} submission. This report is important for project management and compliance.

Please submit your report immediately:
{{ create_report_url }}

If you have already submitted this report, please disregard this message.

If you need assistance, please contact your project manager.

Thank you,
{{ company_name }} System

---
This is an automated message. Please do not reply to this email.
© {{ company_name }}. All rights reserved.
        '''
    }
]


def load_default_templates():
    """Load default templates into database"""
    from .email_models import ReminderTemplate
    
    created_count = 0
    
    for template_data in DEFAULT_TEMPLATES:
        template, created = ReminderTemplate.objects.get_or_create(
            template_type=template_data['template_type'],
            defaults={
                'name': template_data['name'],
                'subject': template_data['subject'],
                'body_html': template_data['body_html'],
                'body_text': template_data['body_text'],
                'is_active': True,
            }
        )
        
        if created:
            created_count += 1
    
    return created_count
