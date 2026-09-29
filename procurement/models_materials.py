"""
Material Tracking Models for Project Material Management
Supports multiple material categories with monthly cumulative tracking
"""

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from decimal import Decimal


class MaterialCategory(models.Model):
    """Material categories for organizing materials"""
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50, help_text="Unit of measurement (e.g., m³, Ton, Hour, No., Tank)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Material Categories"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.unit})"


class MaterialType(models.Model):
    """Specific material types within categories"""
    
    category = models.ForeignKey(MaterialCategory, on_delete=models.CASCADE, related_name='material_types')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=50)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    supplier = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Material Types"
        unique_together = ['category', 'name']
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.category.name} - {self.name}"


class Project(models.Model):
    """Project for material tracking"""
    
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class MaterialEntry(models.Model):
    """Daily material entry from site engineer or supplier invoices"""
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='material_entries')
    material_type = models.ForeignKey(MaterialType, on_delete=models.CASCADE, related_name='entries')
    entry_date = models.DateField()
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    
    # Source information
    source = models.CharField(
        max_length=20,
        choices=[
            ('supplier_invoice', 'Supplier Invoice'),
            ('site_engineer', 'Site Engineer Data'),
            ('manual_entry', 'Manual Entry'),
        ],
        default='manual_entry'
    )
    invoice_number = models.CharField(max_length=100, blank=True)
    supplier_name = models.CharField(max_length=200, blank=True)
    
    # Notes and tracking
    notes = models.TextField(blank=True)
    recorded_by = models.CharField(max_length=100, blank=True)
    recorded_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-entry_date', '-recorded_date']
        indexes = [
            models.Index(fields=['project', 'entry_date']),
            models.Index(fields=['material_type', 'entry_date']),
        ]
    
    def save(self, *args, **kwargs):
        """Calculate total cost before saving"""
        self.total_cost = self.quantity * self.unit_cost
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.material_type.name} - {self.quantity} {self.material_type.unit} on {self.entry_date}"


class MonthlyMaterialReport(models.Model):
    """Monthly cumulative material report"""
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='monthly_reports')
    report_month = models.DateField(help_text="First day of the month")
    report_date = models.DateTimeField(auto_now_add=True)
    
    # Totals
    total_entries = models.IntegerField(default=0)
    total_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    total_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    
    # Status
    is_approved = models.BooleanField(default=False)
    approved_by = models.CharField(max_length=100, blank=True)
    approved_date = models.DateTimeField(null=True, blank=True)
    
    # Notes
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['project', 'report_month']
        ordering = ['-report_month']
    
    def __str__(self):
        return f"{self.project.code} - {self.report_month.strftime('%B %Y')}"
    
    def generate_report(self):
        """Generate monthly report from entries"""
        from datetime import timedelta
        
        # Get first and last day of month
        first_day = self.report_month
        last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        # Get all entries for the month
        entries = MaterialEntry.objects.filter(
            project=self.project,
            entry_date__gte=first_day,
            entry_date__lte=last_day
        )
        
        # Calculate totals
        self.total_entries = entries.count()
        self.total_quantity = sum(e.quantity for e in entries) or 0
        self.total_cost = sum(e.total_cost for e in entries) or 0
        
        self.save()
        return entries


class MonthlyMaterialReportItem(models.Model):
    """Individual material items in monthly report"""
    
    report = models.ForeignKey(MonthlyMaterialReport, on_delete=models.CASCADE, related_name='items')
    material_type = models.ForeignKey(MaterialType, on_delete=models.CASCADE)
    
    # Monthly totals
    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Cumulative totals
    cumulative_quantity = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    cumulative_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Entry count
    entry_count = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ['report', 'material_type']
        ordering = ['material_type__category', 'material_type']
    
    def __str__(self):
        return f"{self.report} - {self.material_type.name}"


class MaterialBudget(models.Model):
    """Material budget for project"""
    
    project = models.OneToOneField(Project, on_delete=models.CASCADE, related_name='material_budget')
    total_budget = models.DecimalField(max_digits=16, decimal_places=2, validators=[MinValueValidator(0)])
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Material Budgets"
    
    def __str__(self):
        return f"{self.project.code} - Budget: {self.total_budget}"
    
    def get_spent_amount(self):
        """Calculate total spent on materials"""
        return MaterialEntry.objects.filter(
            project=self.project
        ).aggregate(total=models.Sum('total_cost'))['total'] or 0
    
    def get_remaining_budget(self):
        """Calculate remaining budget"""
        return self.total_budget - self.get_spent_amount()
    
    def get_budget_percentage(self):
        """Calculate percentage of budget spent"""
        if self.total_budget == 0:
            return 0
        return (self.get_spent_amount() / self.total_budget) * 100


class MaterialBudgetItem(models.Model):
    """Budget allocation for specific material types"""
    
    budget = models.ForeignKey(MaterialBudget, on_delete=models.CASCADE, related_name='items')
    material_type = models.ForeignKey(MaterialType, on_delete=models.CASCADE)
    allocated_budget = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    
    class Meta:
        unique_together = ['budget', 'material_type']
    
    def __str__(self):
        return f"{self.budget.project.code} - {self.material_type.name}: {self.allocated_budget}"
    
    def get_spent_amount(self):
        """Calculate spent amount for this material type"""
        return MaterialEntry.objects.filter(
            project=self.budget.project,
            material_type=self.material_type
        ).aggregate(total=models.Sum('total_cost'))['total'] or 0
    
    def get_remaining_budget(self):
        """Calculate remaining budget for this material type"""
        return self.allocated_budget - self.get_spent_amount()
    
    def get_budget_percentage(self):
        """Calculate percentage of budget spent for this material type"""
        if self.allocated_budget == 0:
            return 0
        return (self.get_spent_amount() / self.allocated_budget) * 100


class MaterialSupplier(models.Model):
    """Supplier information for materials"""
    
    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    
    # Business details
    tax_id = models.CharField(max_length=50, blank=True)
    payment_terms = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name


class MaterialInvoice(models.Model):
    """Supplier invoice for materials"""
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='material_invoices')
    supplier = models.ForeignKey(MaterialSupplier, on_delete=models.SET_NULL, null=True, blank=True)
    
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    
    # Amounts
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    
    # Status
    status = models.CharField(
        max_length=20,
        choices=[
            ('draft', 'Draft'),
            ('received', 'Received'),
            ('verified', 'Verified'),
            ('paid', 'Paid'),
            ('cancelled', 'Cancelled'),
        ],
        default='draft'
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['project', 'invoice_number']
        ordering = ['-invoice_date']
    
    def __str__(self):
        return f"{self.invoice_number} - {self.supplier.name if self.supplier else 'Unknown'}"
    
    def calculate_totals(self):
        """Calculate invoice totals"""
        items = self.items.all()
        self.subtotal = sum(item.total_amount for item in items) or 0
        self.tax_amount = self.subtotal * (self.tax_percentage / 100)
        self.total_amount = self.subtotal + self.tax_amount
        self.save()


class MaterialInvoiceItem(models.Model):
    """Individual items in supplier invoice"""
    
    invoice = models.ForeignKey(MaterialInvoice, on_delete=models.CASCADE, related_name='items')
    material_type = models.ForeignKey(MaterialType, on_delete=models.CASCADE)
    
    quantity = models.DecimalField(max_digits=12, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    
    description = models.TextField(blank=True)
    
    class Meta:
        ordering = ['material_type']
    
    def __str__(self):
        return f"{self.invoice.invoice_number} - {self.material_type.name}"
    
    def save(self, *args, **kwargs):
        """Calculate total before saving"""
        self.total_amount = self.quantity * self.unit_price
        super().save(*args, **kwargs)