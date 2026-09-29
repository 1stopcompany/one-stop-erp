"""
The company's second procurement track alongside the ordinary Purchase Order sequence
(procurement app): "Musana'a" subcontract agreements -- a signed contract with a vendor who
executes a defined scope of work against its own priced lines of the project's BOQ, rather than
just supplying material. Paid against over time (SubcontractorAgreementPayment) instead of
received in one shot like a PO. Vendors are shared with procurement (same company-wide list).
"""
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from projects.validators import validate_document_file


def d2(x) -> Decimal:
    return Decimal(x or 0).quantize(Decimal("0.01"))


def agreement_document_path(instance, filename):
    return f"subcontractor_agreements/{instance.project_id}/{filename}"


class SubcontractorGeneralTerms(models.Model):
    """
    The company's standard General Terms & Conditions that apply to EVERY Musana'a agreement --
    company-wide, not per-agreement or per-project (same relationship as core.SpecificationVolume
    to a project). A singleton row (pk=1, see load()); admin/engineering manager edit it from
    subcontractors:general_terms, and every agreement's detail page links to it rather than
    repeating the same clauses on each contract.
    """
    general_terms = models.TextField(
        blank=True, help_text="General contract terms and conditions applicable to all subcontract (Musana'a) works",
    )
    penalty_clauses = models.TextField(
        blank=True, help_text="Liquidated damages / penalty clauses for delay, defects and rework",
    )
    code_of_conduct = models.TextField(
        blank=True, help_text="Ethical / code-of-conduct commitments required of the subcontractor",
    )
    safety_commitment = models.TextField(
        blank=True, help_text="General (HSE) safety commitment required of the subcontractor",
    )
    updated_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subcontractor General Terms & Conditions"
        verbose_name_plural = "Subcontractor General Terms & Conditions"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Subcontractor General Terms & Conditions"


class SubcontractorAgreement(models.Model):
    STATUS = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("completed", "Completed"),
        ("terminated", "Terminated"),
    ]

    LANGUAGE = [
        ("ar", "Arabic / عربي"),
        ("en", "English"),
    ]

    agreement_number = models.CharField(max_length=50, unique=True, db_index=True, blank=True)

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="subcontractor_agreements")
    vendor = models.ForeignKey("procurement.Vendor", on_delete=models.PROTECT, related_name="subcontractor_agreements")

    language = models.CharField(
        max_length=2, choices=LANGUAGE, default="ar",
        help_text="Chosen once when the agreement is created -- its printed PDF is single-language, laid out "
                   "right-to-left for Arabic, rather than mixing both languages on the page.",
    )

    scope_description = models.TextField(help_text="What this subcontractor is engaged to execute")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")

    signed_document = models.FileField(
        upload_to=agreement_document_path, validators=[validate_document_file], null=True, blank=True,
        help_text="The signed agreement document",
    )

    total_value = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="subcontractor_agreements_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["vendor"]),
        ]

    def save(self, *args, **kwargs):
        if not self.agreement_number:
            ts = timezone.now().strftime("%Y%m%d%H%M%S%f")[:-3]
            base = f"SCA-{self.project_id}-{ts}"
            number, n = base, 1
            while SubcontractorAgreement.objects.filter(agreement_number=number).exists():
                n += 1
                number = f"{base}-{n}"
            self.agreement_number = number
        super().save(*args, **kwargs)

    def recalculate_total(self):
        total = self.lines.aggregate(s=models.Sum("total_price"))["s"] or Decimal("0.00")
        SubcontractorAgreement.objects.filter(pk=self.pk).update(total_value=d2(total))

    @property
    def paid_to_date(self):
        return d2(self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0.00"))

    @property
    def balance_remaining(self):
        return d2(self.total_value) - self.paid_to_date

    def __str__(self):
        return self.agreement_number


class SubcontractorAgreementLine(models.Model):
    agreement = models.ForeignKey(SubcontractorAgreement, on_delete=models.CASCADE, related_name="lines")
    sub_item = models.ForeignKey(
        "reports.ProjectPhaseSubItem", on_delete=models.PROTECT, related_name="subcontractor_agreement_lines",
        help_text="The project BOQ item this scope of work is charged to",
    )
    description = models.CharField(max_length=255, blank=True, help_text="Defaults to the BOQ item's own name if left blank")

    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    total_price = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0)

    class Meta:
        ordering = ["agreement", "id"]

    def save(self, *args, **kwargs):
        self.total_price = d2(d2(self.quantity) * d2(self.unit_price))
        super().save(*args, **kwargs)
        self.agreement.recalculate_total()

    def delete(self, *args, **kwargs):
        agreement = self.agreement
        super().delete(*args, **kwargs)
        agreement.recalculate_total()

    def __str__(self):
        return f"{self.agreement.agreement_number} - {self.description or self.sub_item.name_ar}"


class SubcontractorAgreementPayment(models.Model):
    """A payment made against the agreement's total value -- not tied to one line, since a
    Musana'a payment is normally certified against overall progress of the whole scope."""
    agreement = models.ForeignKey(SubcontractorAgreement, on_delete=models.CASCADE, related_name="payments")

    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    payment_date = models.DateField()
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey("accounts.CustomUser", on_delete=models.SET_NULL, null=True, blank=True, related_name="subcontractor_agreement_payments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        return f"{self.agreement.agreement_number} - {self.amount} on {self.payment_date}"
