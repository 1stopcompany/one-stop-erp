"""
Master Data Models for Daily Reports

This module contains master data models for:
- Workforce Categories and Classifications
- Equipment Master List
- Bill of Quantities (BOQ) for Materials
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from projects.models import Project


class WorkforceCategory(models.Model):
    """
    Workforce Categories
    
    Examples: Project Management, Work Force, etc.
    """
    
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text=_('Category name (e.g., Project Management, Work Force)')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Description of this workforce category')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this category is available for selection')
    )

    is_staff_category = models.BooleanField(
        default=False,
        help_text=_('Counts as "staff" (موظفين) rather than "workers" (عمال) when the Daily Report splits '
                    'man-hours between the two on its KPI strip -- e.g. Project Management vs Work Force')
    )

    order = models.IntegerField(
        default=0,
        help_text=_('Display order')
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = _('Workforce Category')
        verbose_name_plural = _('Workforce Categories')
    
    def __str__(self):
        return self.name


class LaborClassification(models.Model):
    """
    Labor Classifications within a Workforce Category
    
    Examples: Project Manager, Civil Engineer, Skilled Labor, etc.
    """
    
    GENDER_CHOICES = (
        ('M', _('Male')),
        ('F', _('Female')),
        ('O', _('Other')),
    )
    
    category = models.ForeignKey(
        WorkforceCategory,
        on_delete=models.CASCADE,
        related_name='labor_classifications',
        help_text=_('Parent workforce category')
    )
    
    name = models.CharField(
        max_length=100,
        help_text=_('Labor classification name (e.g., Project Manager, Civil Engineer)')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Description of this labor classification')
    )
    
    default_gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        default='M',
        help_text=_('Default gender for this classification')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this classification is available')
    )
    
    order = models.IntegerField(
        default=0,
        help_text=_('Display order within category')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'order', 'name']
        unique_together = ['category', 'name']
        verbose_name = _('Labor Classification')
        verbose_name_plural = _('Labor Classifications')
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"


class EquipmentMaster(models.Model):
    """
    Master Equipment List
    
    Predefined equipment that can be used across all projects
    """
    
    name = models.CharField(
        max_length=150,
        help_text=_('Equipment name (e.g., Fixed Winch, Dump Truck)')
    )
    
    description = models.TextField(
        blank=True,
        help_text=_('Equipment description and specifications')
    )
    
    manufacturer = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Equipment manufacturer')
    )
    
    model = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Equipment model')
    )
    
    year_built = models.IntegerField(
        null=True,
        blank=True,
        help_text=_('Year equipment was built/manufactured')
    )
    
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Equipment category (e.g., Excavation, Concrete, Lifting)')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this equipment is available for selection')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['category', 'name']
        verbose_name = _('Equipment Master')
        verbose_name_plural = _('Equipment Masters')
    
    def __str__(self):
        if self.manufacturer and self.model:
            return f"{self.name} - {self.manufacturer} {self.model}"
        return self.name


class ReportMaterialItem(models.Model):
    """
    Project-specific material reference list used for logging DAILY
    MATERIAL USAGE on site reports (DailyReportMaterialEntry).

    This is intentionally separate from procurement.BillOfQuantities,
    which is the formal, priced Bill of Quantities tied to purchasing
    (item master, approvals, purchase orders). This list only needs to
    answer "what materials can a site engineer log against today", so it
    is simpler and does not go through a procurement approval workflow.
    """
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='report_material_items',
        help_text=_('Associated project')
    )
    
    item_code = models.CharField(
        max_length=50,
        help_text=_('Item code/reference')
    )
    
    description = models.CharField(
        max_length=255,
        help_text=_('Material/item description')
    )
    
    unit = models.CharField(
        max_length=50,
        help_text=_('Unit of measurement (e.g., kg, liters, pieces, m3)')
    )
    
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=_('Total quantity in BOQ')
    )
    
    unit_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Unit rate/price')
    )
    
    total_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_('Total amount (quantity × unit_rate)')
    )
    
    category = models.CharField(
        max_length=100,
        blank=True,
        help_text=_('Material category (e.g., Concrete, Steel, Bricks)')
    )
    
    supplier = models.CharField(
        max_length=150,
        blank=True,
        help_text=_('Supplier name')
    )
    
    is_active = models.BooleanField(
        default=True,
        help_text=_('Whether this BOQ item is available')
    )
    
    notes = models.TextField(
        blank=True,
        help_text=_('Additional notes about this material')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['project', 'category', 'item_code']
        unique_together = ['project', 'item_code']
        verbose_name = _('Report Material Item')
        verbose_name_plural = _('Report Material Items')
    
    def __str__(self):
        return f"{self.project.name} - {self.item_code}: {self.description}"
    
    def save(self, *args, **kwargs):
        """Calculate total amount when saving"""
        if self.unit_rate:
            self.total_amount = self.quantity * self.unit_rate
        super().save(*args, **kwargs)


class DailyReportWorkforceEntry(models.Model):
    """
    Structured Workforce Entry for Daily Reports
    
    Links to LaborClassification for predefined options
    """
    
    from .models import DailyReport
    
    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='workforce_entries',
        help_text=_('Associated daily report')
    )
    
    labor_classification = models.ForeignKey(
        LaborClassification,
        on_delete=models.PROTECT,
        help_text=_('Labor classification from master list')
    )
    
    number_of_employees = models.IntegerField(
        default=0,
        help_text=_('Number of employees in this classification')
    )
    
    gender = models.CharField(
        max_length=1,
        choices=LaborClassification._meta.get_field('default_gender').choices,
        default='M',
        help_text=_('Gender of employees')
    )
    
    hours_worked = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text=_('Total hours worked by this group')
    )
    
    notes = models.TextField(
        blank=True,
        help_text=_('Additional notes about this workforce entry')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['report', 'labor_classification__category', 'labor_classification']
        unique_together = ['report', 'labor_classification']
        verbose_name = _('Daily Report Workforce Entry')
        verbose_name_plural = _('Daily Report Workforce Entries')
    
    def __str__(self):
        return f"{self.report.report_number} - {self.labor_classification.name}"


class DailyReportEquipmentEntry(models.Model):
    """
    Structured Equipment Entry for Daily Reports
    
    Links to EquipmentMaster for predefined options
    """
    
    from .models import DailyReport
    
    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='equipment_entries',
        help_text=_('Associated daily report')
    )
    
    equipment = models.ForeignKey(
        EquipmentMaster,
        on_delete=models.PROTECT,
        help_text=_('Equipment from master list')
    )
    
    quantity_in_use = models.IntegerField(
        default=0,
        help_text=_('Quantity of this equipment in use')
    )
    
    hours_worked = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        help_text=_('Hours this equipment worked')
    )
    
    quantity_idle = models.IntegerField(
        default=0,
        help_text=_('Quantity of this equipment idle')
    )
    
    remarks = models.TextField(
        blank=True,
        help_text=_('Remarks about equipment status')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['report', 'equipment__category', 'equipment']
        unique_together = ['report', 'equipment']
        verbose_name = _('Daily Report Equipment Entry')
        verbose_name_plural = _('Daily Report Equipment Entries')
    
    def __str__(self):
        return f"{self.report.report_number} - {self.equipment.name}"


class DailyReportMaterialEntry(models.Model):
    """
    Structured Material Entry for Daily Reports
    
    Links to ReportMaterialItem for project-specific materials
    """
    
    from .models import DailyReport
    
    report = models.ForeignKey(
        'DailyReport',
        on_delete=models.CASCADE,
        related_name='material_entries',
        help_text=_('Associated daily report')
    )
    
    boq_item = models.ForeignKey(
        ReportMaterialItem,
        on_delete=models.PROTECT,
        help_text=_('Material from project BOQ')
    )
    
    quantity_used = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Quantity of material used today')
    )
    
    quantity_wasted = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text=_('Quantity of material wasted')
    )
    
    remarks = models.TextField(
        blank=True,
        help_text=_('Remarks about material usage')
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['report', 'boq_item__category', 'boq_item']
        unique_together = ['report', 'boq_item']
        verbose_name = _('Daily Report Material Entry')
        verbose_name_plural = _('Daily Report Material Entries')
    
    def __str__(self):
        return f"{self.report.report_number} - {self.boq_item.description}"
