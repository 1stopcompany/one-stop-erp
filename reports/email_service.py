"""
Email Service for Sending Reminders

This module handles sending email reminders to engineers.
"""

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings
from .email_models import EmailReminder, EmailLog, ReminderSchedule, ReminderTemplate
from accounts.models import CustomUser
import logging

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email reminders"""
    
    @staticmethod
    def send_daily_report_reminder(engineer, reminder=None):
        """
        Send daily report reminder to engineer
        
        Args:
            engineer: CustomUser instance (site engineer)
            reminder: EmailReminder instance (optional)
        """
        try:
            # Get template
            template = ReminderTemplate.objects.filter(
                template_type='daily',
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f'No active daily report template found')
                return False
            
            # Prepare context
            context = {
                'engineer_name': engineer.get_full_name() or engineer.username,
                'engineer_email': engineer.email,
                'report_type': 'Daily Construction Report',
                'dashboard_url': f'{settings.SITE_URL}/dashboard/',
                'create_report_url': f'{settings.SITE_URL}/reports/daily/create/',
                'company_name': getattr(settings, 'COMPANY_NAME', 'Construction Reports System'),
            }
            
            # Render template
            subject = template.subject.format(**context)
            html_message = template.render(context)
            text_message = strip_tags(html_message)
            
            # Send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[engineer.email]
            )
            email.attach_alternative(html_message, 'text/html')
            
            result = email.send()
            
            # Log email
            if result:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='sent'
                )
                logger.info(f'Daily report reminder sent to {engineer.email}')
                return True
            else:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='failed',
                    error_message='Email send returned 0'
                )
                logger.error(f'Failed to send daily report reminder to {engineer.email}')
                return False
                
        except Exception as e:
            logger.error(f'Error sending daily report reminder to {engineer.email}: {str(e)}')
            if reminder:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject='Daily Report Reminder',
                    body='',
                    status='failed',
                    error_message=str(e)
                )
            return False
    
    @staticmethod
    def send_monthly_report_reminder(engineer, reminder=None):
        """
        Send monthly report reminder to engineer
        
        Args:
            engineer: CustomUser instance (site engineer)
            reminder: EmailReminder instance (optional)
        """
        try:
            # Get template
            template = ReminderTemplate.objects.filter(
                template_type='monthly',
                is_active=True
            ).first()
            
            if not template:
                logger.warning(f'No active monthly report template found')
                return False
            
            # Prepare context
            context = {
                'engineer_name': engineer.get_full_name() or engineer.username,
                'engineer_email': engineer.email,
                'report_type': 'Monthly Maintenance Report',
                'dashboard_url': f'{settings.SITE_URL}/dashboard/',
                'create_report_url': f'{settings.SITE_URL}/reports/monthly/create/',
                'company_name': getattr(settings, 'COMPANY_NAME', 'Construction Reports System'),
            }
            
            # Render template
            subject = template.subject.format(**context)
            html_message = template.render(context)
            text_message = strip_tags(html_message)
            
            # Send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[engineer.email]
            )
            email.attach_alternative(html_message, 'text/html')
            
            result = email.send()
            
            # Log email
            if result:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='sent'
                )
                logger.info(f'Monthly report reminder sent to {engineer.email}')
                return True
            else:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='failed',
                    error_message='Email send returned 0'
                )
                logger.error(f'Failed to send monthly report reminder to {engineer.email}')
                return False
                
        except Exception as e:
            logger.error(f'Error sending monthly report reminder to {engineer.email}: {str(e)}')
            if reminder:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject='Monthly Report Reminder',
                    body='',
                    status='failed',
                    error_message=str(e)
                )
            return False
    
    @staticmethod
    def send_overdue_report_reminder(engineer, report_type='daily', reminder=None, extra_context=None):
        """
        Send overdue report reminder to engineer

        Args:
            engineer: CustomUser instance
            report_type: 'daily' or 'monthly'
            reminder: EmailReminder instance (optional)
            extra_context: optional dict merged into the template context (e.g. project_name,
                days_overdue, last_report_date from check_overdue_daily_reports) -- only used by
                a template that references those placeholders; harmless if the active template
                doesn't mention them.
        """
        try:
            # Get template
            template = ReminderTemplate.objects.filter(
                template_type='overdue',
                is_active=True
            ).first()

            if not template:
                logger.warning(f'No active overdue report template found')
                return False

            # Prepare context
            context = {
                'engineer_name': engineer.get_full_name() or engineer.username,
                'engineer_email': engineer.email,
                'report_type': f'{report_type.capitalize()} Report',
                'dashboard_url': f'{settings.SITE_URL}/dashboard/',
                'create_report_url': f'{settings.SITE_URL}/reports/{report_type}/create/',
                'company_name': getattr(settings, 'COMPANY_NAME', 'Construction Reports System'),
            }
            if extra_context:
                context.update(extra_context)
            
            # Render template
            subject = template.subject.format(**context)
            html_message = template.render(context)
            text_message = strip_tags(html_message)
            
            # Send email
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[engineer.email]
            )
            email.attach_alternative(html_message, 'text/html')
            
            result = email.send()
            
            # Log email
            if result:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='sent'
                )
                logger.info(f'Overdue report reminder sent to {engineer.email}')
                return True
            else:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject=subject,
                    body=html_message,
                    status='failed',
                    error_message='Email send returned 0'
                )
                logger.error(f'Failed to send overdue report reminder to {engineer.email}')
                return False
                
        except Exception as e:
            logger.error(f'Error sending overdue report reminder to {engineer.email}: {str(e)}')
            if reminder:
                EmailLog.objects.create(
                    reminder=reminder,
                    recipient=engineer,
                    subject='Overdue Report Reminder',
                    body='',
                    status='failed',
                    error_message=str(e)
                )
            return False
    
    @staticmethod
    def send_batch_reminders(reminder):
        """
        Send reminders to all target engineers for a reminder configuration
        
        Args:
            reminder: EmailReminder instance
        """
        if not reminder.is_active:
            logger.info(f'Reminder {reminder.name} is not active')
            return 0
        
        # Get target engineers
        if reminder.target_engineers.exists():
            engineers = reminder.target_engineers.filter(
                is_site_engineer=True,
                is_active=True
            )
        else:
            engineers = CustomUser.objects.filter(
                is_site_engineer=True,
                is_active=True
            )
        
        # Filter by projects if specified
        if reminder.target_projects.exists():
            engineers = engineers.filter(
                projects__in=reminder.target_projects
            ).distinct()
        
        sent_count = 0
        
        for engineer in engineers:
            # Check if should send
            schedule, created = ReminderSchedule.objects.get_or_create(
                reminder=reminder,
                engineer=engineer
            )
            
            if not schedule.is_active:
                continue
            
            if schedule.next_send > timezone.now():
                continue
            
            # Send reminder
            if reminder.reminder_type == 'daily':
                success = EmailService.send_daily_report_reminder(engineer, reminder)
            elif reminder.reminder_type == 'monthly':
                success = EmailService.send_monthly_report_reminder(engineer, reminder)
            else:  # both
                success1 = EmailService.send_daily_report_reminder(engineer, reminder)
                success2 = EmailService.send_monthly_report_reminder(engineer, reminder)
                success = success1 or success2
            
            if success:
                schedule.last_sent = timezone.now()
                schedule.send_count += 1
                schedule.update_next_send()
                sent_count += 1
        
        logger.info(f'Sent {sent_count} reminders for {reminder.name}')
        return sent_count
    
    @staticmethod
    def send_all_active_reminders():
        """Send all active reminders that are due"""
        reminders = EmailReminder.objects.filter(is_active=True)
        total_sent = 0
        
        for reminder in reminders:
            if reminder.should_send_today():
                sent = EmailService.send_batch_reminders(reminder)
                total_sent += sent
        
        logger.info(f'Total reminders sent: {total_sent}')
        return total_sent
