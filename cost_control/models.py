from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum


Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    if x is None:
        x = Decimal("0")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Q2, rounding=ROUND_HALF_UP)


class Budget(models.Model):
    STATUS_CHOICES = [
        ("on_budget", "On Budget"),
        ("over_budget", "Over Budget"),
        ("under_budget", "Under Budget"),
    ]

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="cost_budgets")
    item = models.ForeignKey("procurement.ItemMaster", on_delete=models.PROTECT, related_name="cost_budgets")

    budgeted_quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    budgeted_unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    budgeted_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    actual_quantity = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    actual_unit_price = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    actual_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    quantity_variance = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    price_variance = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    total_variance = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    variance_percentage = models.DecimalField(max_digits=7, decimal_places=2, editable=False, default=0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, editable=False, default="on_budget")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cost_budgets_created")
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("project", "item")]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["item"]),
        ]
        ordering = ["item__full_code"]

    def __str__(self):
        return f"{self.project} | {self.item.full_code}"

    def recompute(self):
        bq = q2(self.budgeted_quantity)
        bup = q2(self.budgeted_unit_price)
        aq = q2(self.actual_quantity)
        aup = q2(self.actual_unit_price)

        self.budgeted_total = q2(bq * bup)
        self.actual_total = q2(aq * aup)

        self.quantity_variance = q2(aq - bq)
        self.price_variance = q2(aup - bup)
        self.total_variance = q2(self.actual_total - self.budgeted_total)

        if self.budgeted_total > 0:
            self.variance_percentage = q2((self.total_variance / self.budgeted_total) * Decimal("100"))
        else:
            self.variance_percentage = Decimal("0.00")

        if self.total_variance > 0:
            self.status = "over_budget"
        elif self.total_variance < 0:
            self.status = "under_budget"
        else:
            self.status = "on_budget"

    def save(self, *args, **kwargs):
        self.recompute()
        super().save(*args, **kwargs)


class CostForecast(models.Model):
    CONF_CHOICES = [
        ("low", "Low (50–70%)"),
        ("medium", "Medium (70–85%)"),
        ("high", "High (85–95%)"),
    ]

    budget = models.ForeignKey("cost_control.Budget", on_delete=models.CASCADE, related_name="forecasts")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="cost_forecasts", editable=False)
    item = models.ForeignKey("procurement.ItemMaster", on_delete=models.PROTECT, related_name="cost_forecasts", editable=False)

    forecast_date = models.DateField(auto_now_add=True)
    forecast_quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    forecast_unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    forecast_total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    quantity_variance = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    price_variance = models.DecimalField(max_digits=12, decimal_places=2, editable=False, default=0)
    total_variance = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    confidence_level = models.CharField(max_length=20, choices=CONF_CHOICES, default="medium")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cost_forecasts_created")
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-forecast_date"]

    def save(self, *args, **kwargs):
        self.project = self.budget.project
        self.item = self.budget.item

        fq = q2(self.forecast_quantity)
        fup = q2(self.forecast_unit_price)
        self.forecast_total = q2(fq * fup)

        b = self.budget
        self.quantity_variance = q2(fq - q2(b.budgeted_quantity))
        self.price_variance = q2(fup - q2(b.budgeted_unit_price))
        self.total_variance = q2(self.forecast_total - q2(b.budgeted_total))

        super().save(*args, **kwargs)


class CostReport(models.Model):
    TYPE_CHOICES = [
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
    ]

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="cost_reports")
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    report_date = models.DateField(auto_now_add=True)
    period_start = models.DateField()
    period_end = models.DateField()

    total_budgeted = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    total_actual = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    total_variance = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)
    variance_percentage = models.DecimalField(max_digits=7, decimal_places=2, editable=False, default=0)

    on_budget_count = models.IntegerField(editable=False, default=0)
    over_budget_count = models.IntegerField(editable=False, default=0)
    under_budget_count = models.IntegerField(editable=False, default=0)

    recommendations = models.TextField(blank=True)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cost_reports_created")
    created_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "report_type", "period_start")]
        ordering = ["-report_date"]

    def refresh_from_budgets(self):
        """
        Snapshot the project's cost position. "Variance" here is actual minus EARNED value
        (positive = over cost) -- not actual minus the whole budget, which would read as
        "under budget" for the entire first half of every project.
        """
        from .services import project_cost_summary  # local import: services imports this module

        summary = project_cost_summary(self.project)
        totals = summary["totals"]

        self.total_budgeted = q2(totals["budget"])
        self.total_actual = q2(totals["actual"])
        self.total_variance = q2(totals["actual"] - totals["earned"])

        if totals["earned"] > 0:
            self.variance_percentage = q2((self.total_variance / totals["earned"]) * Decimal("100"))
        else:
            self.variance_percentage = Decimal("0.00")

        self.on_budget_count = summary["counts"]["on_budget"]
        self.over_budget_count = summary["counts"]["over_budget"]
        self.under_budget_count = summary["counts"]["under_budget"]

    def save(self, *args, **kwargs):
        self.refresh_from_budgets()
        super().save(*args, **kwargs)


class BudgetAlert(models.Model):
    ALERT_CHOICES = [
        ("overrun", "Budget Overrun"),
        ("threshold", "Threshold Exceeded"),
        ("variance", "High Variance"),
        ("forecast", "Forecast Alert"),
    ]
    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="budget_alerts")
    budget = models.ForeignKey("cost_control.Budget", on_delete=models.CASCADE, related_name="alerts", null=True, blank=True)
    sub_item = models.ForeignKey(
        "reports.ProjectPhaseSubItem", on_delete=models.CASCADE, null=True, blank=True, related_name="cost_alerts",
        help_text="The project BOQ item this alert is about",
    )

    alert_type = models.CharField(max_length=20, choices=ALERT_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="medium")
    message = models.TextField()

    threshold_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    actual_value = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    is_active = models.BooleanField(default=True)
    is_resolved = models.BooleanField(default=False)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="budget_alerts_created")
    created_date = models.DateTimeField(auto_now_add=True)
    resolved_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_date"]
        indexes = [
            models.Index(fields=["project", "severity"]),
            models.Index(fields=["is_active", "is_resolved"]),
        ]
