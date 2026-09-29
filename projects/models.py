from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _
from accounts.models import CustomUser
from datetime import datetime

from .validators import validate_document_file


class Project(models.Model):
    """Project model for construction projects"""
    
    STATUS_CHOICES = (
        ('planning', _('Planning')),
        ('active', _('Active')),
        ('on_hold', _('On Hold')),
        ('completed', _('Completed')),
        ('archived', _('Archived')),
    )
    
    MAINTENANCE_TYPE_CHOICES = (
        ('preventive', _('Preventive Maintenance')),
        ('corrective', _('Corrective Maintenance')),
        ('predictive', _('Predictive Maintenance')),
        ('routine', _('Routine Maintenance')),
    )
    
    name = models.CharField(
        max_length=255,
        help_text=_('Project name')
    )
    
    project_symbol = models.CharField(
        max_length=50,
        unique=True,
        help_text=_('Unique project symbol/code')
    )
    
    contract_number = models.CharField(
        max_length=100,
        unique=True,
        help_text=_('Contract number')
    )

    contract_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Total contract value, used to convert phase progress percentages into monetary amounts for financial reports')
    )

    advance_payment_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Advance/mobilization payment value, recovered against progress payments over the life of the contract')
    )

    performance_retention_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('10.00'),
        help_text=_('% of each certified payment withheld as performance retention (e.g. 10.00 for 10%)')
    )

    client_name = models.CharField(
        max_length=255,
        help_text=_('Client or CMC name (e.g., One Stop)')
    )
    
    start_date = models.DateField(
        help_text=_('Project start date')
    )
    
    end_date = models.DateField(
        null=True,
        blank=True,
        help_text=_('Project end date')
    )
    
    maintenance_type = models.CharField(
        max_length=20,
        choices=MAINTENANCE_TYPE_CHOICES,
        default='preventive',
        help_text=_('Type of maintenance')
    )
    
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active',
        help_text=_('Project status')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Project description')
    )
    
    location = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Project location')
    )
    
    manager = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='managed_projects',
        limit_choices_to={'role': 'project_manager'},
        help_text=_('Project manager -- creates the Monthly (EDGE) and Owner Financial reports')
    )

    site_engineer = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='engineered_projects',
        limit_choices_to={'role': 'site_engineer'},
        help_text=_('Site engineer assigned to this project -- the only one who may create its Daily reports')
    )

    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_projects',
        help_text=_('User who created the project')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    applicable_spec_sections = models.ManyToManyField(
        'core.SpecificationSection',
        blank=True,
        related_name='projects',
        help_text=_('Which sections of the company standard (One Stop Standards and Specifications) apply '
                    'to this project, based on its own nature (e.g. no subcontractors -> that section stays off).')
    )

    class Meta:
        verbose_name = _('Project')
        verbose_name_plural = _('Projects')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project_symbol']),
            models.Index(fields=['contract_number']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.project_symbol})"
    
    def is_active(self):
        return self.status == 'active'


class ProjectFloor(models.Model):
    """Floors/Levels in a project"""
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='floors',
        help_text=_('Associated project')
    )
    
    floor_number = models.CharField(
        max_length=50,
        help_text=_('Floor name or number (e.g., G, 1, 2, B1)')
    )
    
    floor_name = models.CharField(
        max_length=255,
        blank=True,
        help_text=_('Floor name or description')
    )
    
    area_sqm = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Floor area in square meters')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Floor description')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = _('Project Floor')
        verbose_name_plural = _('Project Floors')
        ordering = ['project', 'floor_number']
        unique_together = ('project', 'floor_number')
    
    def __str__(self):
        return f"{self.project.name} - Floor {self.floor_number}"


# ==================== Project workflow (insurance -> tender documents -> drawings) ====================

def insurance_upload_path(instance, filename):
    return f"project_docs/{instance.project_id}/insurance/{filename}"


def tender_upload_path(instance, filename):
    return f"project_docs/{instance.project_id}/tender/{filename}"


class ProjectStage(models.Model):
    """
    One step of the project's start-up flow. The steps are strictly ordered and each
    is locked until the one before it is complete (see projects.workflow):

      1. insurance -- valid insurance policies are on file
      2. tender    -- the tender documents have been uploaded
      3. drawings  -- an engineering drawing is approved for construction, its BOQ is fully priced, and the
                      drawing has government, municipality and civil defense approval on file
      4. schedule  -- a project schedule has been imported (see reports.ScheduleTask)
      5. plans     -- every required project-management plan document is uploaded (ESHS, quality, risk,
                      technical approach, project team, code of conduct, site management & logistics --
                      the last one also needs its own 6-point checklist fully checked); completing this
                      step is what starts the work (project becomes Active)
    """
    INSURANCE, TENDER, DRAWINGS, SCHEDULE, PLANS = "insurance", "tender", "drawings", "schedule", "plans"
    KEYS = [
        (INSURANCE, "Insurance"),
        (TENDER, "Tender documents"),
        (DRAWINGS, "Drawings approved for construction"),
        (SCHEDULE, "Project schedule"),
        (PLANS, "Project management plans"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="stages")
    key = models.CharField(max_length=20, choices=KEYS)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="completed_project_stages",
        help_text=_("Blank for stages marked complete automatically on projects that were already running"),
    )

    class Meta:
        unique_together = ("project", "key")

    @property
    def is_complete(self):
        return self.completed_at is not None

    def __str__(self):
        return f"{self.project} - {self.get_key_display()}"


class ProjectInsurance(models.Model):
    """An insurance policy / guarantee for a project, with the dates the expiry alert runs on."""
    TYPES = [
        ("car", "Contractor's All Risks (CAR)"),
        ("third_party", "Third-party liability"),
        ("workers", "Workers' compensation / employer's liability"),
        ("performance_bond", "Performance bond"),
        ("advance_payment", "Advance payment guarantee"),
        ("other", "Other"),
    ]
    EXPIRY_WARNING_DAYS = 30

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="insurances")
    policy_type = models.CharField(max_length=30, choices=TYPES)
    insurer = models.CharField(max_length=200, help_text=_("Insurance company / issuing bank"))
    policy_number = models.CharField(max_length=100)
    insured_amount = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    document = models.FileField(upload_to=insurance_upload_path, validators=[validate_document_file])
    notes = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["end_date"]

    def days_left(self, today=None):
        from django.utils import timezone
        return (self.end_date - (today or timezone.localdate())).days

    @property
    def state(self):
        """'expired', 'expiring' (within the warning window) or 'valid'."""
        left = self.days_left()
        if left < 0:
            return "expired"
        if left <= self.EXPIRY_WARNING_DAYS:
            return "expiring"
        return "valid"

    def __str__(self):
        return f"{self.project} - {self.get_policy_type_display()} {self.policy_number}"


class ProjectTenderDocument(models.Model):
    """A tender/contract document uploaded for the project."""
    CATEGORIES = [
        ("contract", "Contract / agreement"),
        ("conditions", "Conditions of contract"),
        ("specifications", "Specifications"),
        ("boq", "Bill of quantities"),
        ("addendum", "Addendum / clarification"),
        ("other", "Other"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tender_documents")
    category = models.CharField(max_length=20, choices=CATEGORIES)
    title = models.CharField(max_length=200)
    document = models.FileField(upload_to=tender_upload_path, validators=[validate_document_file])
    notes = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["category", "title"]

    def __str__(self):
        return f"{self.project} - {self.title}"


def regulatory_upload_path(instance, filename):
    return f"project_docs/{instance.project_id}/regulatory/{filename}"


def management_plan_upload_path(instance, filename):
    return f"project_docs/{instance.project_id}/plans/{filename}"


class ProjectRegulatoryApproval(models.Model):
    """
    A drawing-approval document from an outside regulatory body, required (alongside the approved
    engineering drawing itself and the priced BOQ) before the 'drawings' stage of the start-up flow can
    complete: one uploaded document per body is enough, there is no separate review/approval workflow here
    -- the document itself already carries the outside body's approval.
    """
    GOVERNMENT, MUNICIPALITY, CIVIL_DEFENSE = "government", "municipality", "civil_defense"
    BODIES = [
        (GOVERNMENT, "Government"),
        (MUNICIPALITY, "Municipality"),
        (CIVIL_DEFENSE, "Civil Defense"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="regulatory_approvals")
    body = models.CharField(max_length=20, choices=BODIES)
    title = models.CharField(max_length=200, blank=True)
    document = models.FileField(upload_to=regulatory_upload_path, validators=[validate_document_file])
    approval_number = models.CharField(max_length=100, blank=True)
    approved_date = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["body", "-uploaded_at"]

    def __str__(self):
        return f"{self.project} - {self.get_body_display()} approval"


class ProjectManagementPlan(models.Model):
    """
    One of the project-management plan documents required before the 'plans' stage of the start-up flow can
    complete -- upload only, like ProjectTenderDocument, with no separate review/approval workflow. The
    'site_management' category additionally needs its own 6-point site logistics checklist (below) fully
    checked before it counts as done; the other six categories need only the document itself.
    """
    ESHS, QUALITY, RISK, TECHNICAL_APPROACH, PROJECT_TEAM, CODE_OF_CONDUCT, SITE_MANAGEMENT = (
        "eshs", "quality", "risk", "technical_approach", "project_team", "code_of_conduct", "site_management",
    )
    CATEGORIES = [
        (ESHS, "Environmental, Social, Health & Safety (ESHS) Management Plan"),
        (QUALITY, "Quality Management Plan"),
        (RISK, "Risk Management Plan"),
        (TECHNICAL_APPROACH, "Technical Approach and Methodology"),
        (PROJECT_TEAM, "Project Team: Organization, Staffing"),
        (CODE_OF_CONDUCT, "Code of Conduct"),
        (SITE_MANAGEMENT, "Site Management and Logistics"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="management_plans")
    category = models.CharField(max_length=20, choices=CATEGORIES)
    title = models.CharField(max_length=200, blank=True)
    document = models.FileField(upload_to=management_plan_upload_path, validators=[validate_document_file])
    notes = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # Site Management and Logistics' own checklist, straight off the real submittal list this stage is
    # based on (kept exactly as given, including the overlap between items 1/5 and 2/4 -- a formal
    # checklist item in its own right, not a duplicate to merge away). Unused/ignored for every other category.
    checklist_mobilization_demobilization = models.BooleanField(default=False, verbose_name=_("1. Mobilization and Demobilization"))
    checklist_access_control = models.BooleanField(default=False, verbose_name=_("2. Access Control"))
    checklist_sign_boards = models.BooleanField(default=False, verbose_name=_("3. Sign Boards"))
    checklist_security_provisions = models.BooleanField(default=False, verbose_name=_("4. Security Provisions and Access Control"))
    checklist_demobilization = models.BooleanField(default=False, verbose_name=_("5. Demobilization"))
    checklist_traffic_public_safety = models.BooleanField(default=False, verbose_name=_("6. Maintenance of Traffic and Public Safety"))

    CHECKLIST_FIELDS = [
        "checklist_mobilization_demobilization", "checklist_access_control", "checklist_sign_boards",
        "checklist_security_provisions", "checklist_demobilization", "checklist_traffic_public_safety",
    ]

    class Meta:
        ordering = ["category", "-uploaded_at"]

    def __str__(self):
        return f"{self.project} - {self.get_category_display()}"

    @property
    def checklist_complete(self):
        """Always True for every category except site_management, which needs all 6 points checked."""
        if self.category != self.SITE_MANAGEMENT:
            return True
        return all(getattr(self, field) for field in self.CHECKLIST_FIELDS)
