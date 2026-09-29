"""
Management Command: Send Email Reminders

This command sends email reminders to engineers to fill their reports.
Can be run manually or scheduled with cron/celery.

Usage:
    python manage.py send_reminders
    python manage.py send_reminders --daily
    python manage.py send_reminders --monthly
    python manage.py send_reminders --reminder-id 1
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from reports.email_models import EmailReminder
from reports.email_service import EmailService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send email reminders to engineers to fill their reports'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--daily',
            action='store_true',
            help='Send only daily report reminders',
        )
        
        parser.add_argument(
            '--monthly',
            action='store_true',
            help='Send only monthly report reminders',
        )
        
        parser.add_argument(
            '--reminder-id',
            type=int,
            help='Send specific reminder by ID',
        )
        
        parser.add_argument(
            '--test',
            action='store_true',
            help='Test mode - show what would be sent without actually sending',
        )
        
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting reminder service...'))
        
        try:
            if options['reminder_id']:
                # Send specific reminder
                self.send_specific_reminder(options['reminder_id'], options['test'])
            elif options['daily']:
                # Send only daily reminders
                self.send_by_type('daily', options['test'])
            elif options['monthly']:
                # Send only monthly reminders
                self.send_by_type('monthly', options['test'])
            else:
                # Send all active reminders
                self.send_all_reminders(options['test'])
            
            self.stdout.write(self.style.SUCCESS('Reminder service completed successfully!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            logger.error(f'Error in send_reminders command: {str(e)}')
            raise CommandError(str(e))
    
    def send_specific_reminder(self, reminder_id, test_mode=False):
        """Send specific reminder by ID"""
        try:
            reminder = EmailReminder.objects.get(id=reminder_id)
        except EmailReminder.DoesNotExist:
            raise CommandError(f'Reminder with ID {reminder_id} not found')
        
        if not reminder.is_active:
            self.stdout.write(self.style.WARNING(f'Reminder "{reminder.name}" is not active'))
            return
        
        if test_mode:
            self.stdout.write(self.style.WARNING('TEST MODE - No emails will be sent'))
            self.show_reminder_details(reminder)
        else:
            sent = EmailService.send_batch_reminders(reminder)
            self.stdout.write(
                self.style.SUCCESS(f'Sent {sent} reminders for "{reminder.name}"')
            )
    
    def send_by_type(self, report_type, test_mode=False):
        """Send reminders by type (daily or monthly)"""
        reminders = EmailReminder.objects.filter(
            is_active=True,
            reminder_type=report_type
        )
        
        if not reminders.exists():
            self.stdout.write(
                self.style.WARNING(f'No active {report_type} reminders found')
            )
            return
        
        total_sent = 0
        
        for reminder in reminders:
            if not reminder.should_send_today():
                self.stdout.write(
                    self.style.WARNING(f'Skipping "{reminder.name}" - not scheduled for today')
                )
                continue
            
            if test_mode:
                self.stdout.write(self.style.WARNING('TEST MODE - No emails will be sent'))
                self.show_reminder_details(reminder)
            else:
                sent = EmailService.send_batch_reminders(reminder)
                total_sent += sent
                self.stdout.write(
                    self.style.SUCCESS(f'Sent {sent} reminders for "{reminder.name}"')
                )
        
        if not test_mode:
            self.stdout.write(
                self.style.SUCCESS(f'Total {report_type} reminders sent: {total_sent}')
            )
    
    def send_all_reminders(self, test_mode=False):
        """Send all active reminders"""
        reminders = EmailReminder.objects.filter(is_active=True)
        
        if not reminders.exists():
            self.stdout.write(self.style.WARNING('No active reminders found'))
            return
        
        if test_mode:
            self.stdout.write(self.style.WARNING('TEST MODE - No emails will be sent'))
            for reminder in reminders:
                if reminder.should_send_today():
                    self.show_reminder_details(reminder)
        else:
            total_sent = EmailService.send_all_active_reminders()
            self.stdout.write(
                self.style.SUCCESS(f'Total reminders sent: {total_sent}')
            )
    
    def show_reminder_details(self, reminder):
        """Show details of a reminder"""
        self.stdout.write(f'\nReminder: {reminder.name}')
        self.stdout.write(f'  Type: {reminder.get_reminder_type_display()}')
        self.stdout.write(f'  Frequency: {reminder.get_frequency_display()}')
        self.stdout.write(f'  Send Time: {reminder.get_send_time()}')
        
        if reminder.target_engineers.exists():
            engineers = reminder.target_engineers.filter(is_site_engineer=True, is_active=True)
            self.stdout.write(f'  Target Engineers: {engineers.count()}')
            for eng in engineers[:5]:
                self.stdout.write(f'    - {eng.get_full_name()} ({eng.email})')
            if engineers.count() > 5:
                self.stdout.write(f'    ... and {engineers.count() - 5} more')
        else:
            from accounts.models import CustomUser
            engineers = CustomUser.objects.filter(is_site_engineer=True, is_active=True)
            self.stdout.write(f'  Target Engineers: All ({engineers.count()})')
