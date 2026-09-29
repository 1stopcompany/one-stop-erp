from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import CustomUser
from projects.validators import validate_document_file


def specification_upload_path(instance, filename):
    return f"company_specs/{filename}"


class SpecificationVolume(models.Model):
    """
    One volume of the company's own master specification book ("One Stop Standards and Specifications") --
    a company-wide reference, not tied to any single project (see SpecificationSection for the numbered
    sections inside it, used to browse/search without opening the whole document). Design-Build projects
    are built to these specifications by default; Tender-type projects come with drawings and
    specifications of their own from the client/consultant, so these don't apply to them.
    """
    label = models.CharField(max_length=50, help_text=_('e.g. "Volume I"'))
    title = models.CharField(max_length=255, blank=True)
    revision = models.CharField(max_length=100, blank=True, help_text=_('e.g. "REV03", "Final July 6, 2026"'))
    document = models.FileField(upload_to=specification_upload_path, validators=[validate_document_file])
    order = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'label']
        verbose_name = _('Specification Volume')
        verbose_name_plural = _('Specification Volumes')

    def __str__(self):
        return self.label


class SpecificationSection(models.Model):
    """
    One numbered section/article within a SpecificationVolume (e.g. "01010 - Summary of Work"), for
    browsing and search. This indexes the volume's own table of contents -- it is not a separate document;
    the full text stays in the volume's uploaded file.
    """
    volume = models.ForeignKey(SpecificationVolume, on_delete=models.CASCADE, related_name='sections')
    code = models.CharField(max_length=20, help_text=_('e.g. "01010"'))
    title = models.CharField(max_length=255)
    order = models.PositiveIntegerField(default=0)
    content = models.TextField(
        blank=True,
        help_text=_('This section\'s own text, extracted from the volume document, for the popup card and its standalone PDF'),
    )

    class Meta:
        ordering = ['order', 'code']
        verbose_name = _('Specification Section')
        verbose_name_plural = _('Specification Sections')
        # Not unique_together on (volume, code): the source document itself has at least one duplicated
        # code within a volume (Volume I lists "01500" twice, for two different sections) -- indexing what
        # the real table of contents says matters more here than enforcing a code is only used once.

    def __str__(self):
        return f"{self.code} - {self.title}"


class SystemSettings(models.Model):
    """System-wide settings"""
    
    key = models.CharField(
        max_length=100,
        unique=True,
        help_text=_('Setting key')
    )
    
    value = models.TextField(
        help_text=_('Setting value')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Description of the setting')
    )
    
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('System Setting')
        verbose_name_plural = _('System Settings')
    
    def __str__(self):
        return f"{self.key}: {self.value}"


class NotificationTemplate(models.Model):
    """Email notification templates"""
    
    TEMPLATE_TYPE_CHOICES = (
        ('report_submitted', _('Report Submitted')),
        ('report_approved', _('Report Approved')),
        ('report_rejected', _('Report Rejected')),
        ('user_created', _('User Created')),
        ('password_reset', _('Password Reset')),
    )
    
    name = models.CharField(
        max_length=100,
        help_text=_('Template name')
    )
    
    template_type = models.CharField(
        max_length=50,
        choices=TEMPLATE_TYPE_CHOICES,
        unique=True,
        help_text=_('Template type')
    )
    
    subject = models.CharField(
        max_length=255,
        help_text=_('Email subject')
    )
    
    body = models.TextField(
        help_text=_('Email body (supports HTML)')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether the template is active')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Notification Template')
        verbose_name_plural = _('Notification Templates')
    
    def __str__(self):
        return f"{self.name} ({self.get_template_type_display()})"
