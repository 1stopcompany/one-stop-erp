from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import EmailValidator
from django.utils.translation import gettext_lazy as _


class CustomUser(AbstractUser):
    """Extended user model with additional fields for site engineers and managers"""
    
    USER_ROLES = (
        ('admin', _('Administrator')),
        ('general_manager', _('General Manager')),
        ('engineering_manager', _('Engineering Manager')),
        ('project_manager', _('Project Manager')),
        ('site_engineer', _('Site Engineer')),
        ('procurement_officer', _('Procurement Officer')),
    )
    
    role = models.CharField(
        max_length=20,
        choices=USER_ROLES,
        default='site_engineer',
        help_text=_('User role in the system')
    )
    
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text=_('Contact phone number')
    )
    
    designation = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_('Job designation or title')
    )
    
    department = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text=_('Department or team')
    )

    daily_report_section_order = models.JSONField(
        null=True,
        blank=True,
        help_text=_("This user's own preferred order for the Daily Report page's section list "
                    "(saved via its move-up/move-down controls on each section); unset falls back "
                    "to the page's default order")
    )

    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether the user account is active')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_full_name()} ({self.get_role_display()})"
    
    def is_admin(self):
        # A Django superuser should always have full access, even if
        # their `role` field happens to be set to something else (e.g.
        # a superuser account created for testing that was never given
        # role='admin').
        return self.role == 'admin' or self.is_superuser
    
    def is_project_manager(self):
        return self.role == 'project_manager'
    
    def is_site_engineer(self):
        return self.role == 'site_engineer'

    def is_engineering_manager(self):
        return self.role == 'engineering_manager'

    def is_general_manager(self):
        return self.role == 'general_manager'

    def is_procurement_officer(self):
        return self.role == 'procurement_officer'


class UserAuditLog(models.Model):
    """Audit trail for user actions"""
    
    ACTION_CHOICES = (
        ('login', _('Login')),
        ('logout', _('Logout')),
        ('create', _('Create')),
        ('update', _('Update')),
        ('delete', _('Delete')),
        ('approve', _('Approve')),
        ('reject', _('Reject')),
        ('export', _('Export')),
    )
    
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='audit_logs'
    )
    
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        help_text=_('Action performed')
    )
    
    content_type = models.CharField(
        max_length=100,
        help_text=_('Type of object affected')
    )
    
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_('ID of the affected object')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Description of the action')
    )
    
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_('IP address of the user')
    )
    
    user_agent = models.TextField(
        blank=True,
        help_text=_('User agent information')
    )
    
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = _('Audit Log')
        verbose_name_plural = _('Audit Logs')
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.user} - {self.get_action_display()} - {self.timestamp}"
