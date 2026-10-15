"""
Payment claims (المطالبات المالية للدفع) -- the company's own claim form, the one that used to be an Excel sheet per claim.

A claim asks the accounting to pay a vendor / beneficiary (a supplier, a contractor, a driver, a rental company ...) for a project or for the main
office. The project manager prepares it, and it then collects the signatures of the finance, the executive director and the general manager --
each one's approval IS his signature (his name and the date print in the signature row of the form). The accountant records the payment
(cash and / or cheques) once the last signature is in.

    draft -> submitted (project manager signed) -> finance_approved -> executive_approved -> approved (general manager signed) -> paid
                         any signer may send it back: rejected (with the reason), the preparer corrects it and signs again
"""
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

MAIN_OFFICE_PREFIX = 'MAIN OFFICE SUP'   # the numbering series of claims that belong to no project

# The ticks of "requirements for submitting the claim" in the order of the printed form: right column, middle column, left column, each from top to bottom.
REQUIREMENTS = (
    ('delivery_note', 'ارسالية / سند استلام'),
    ('tax_invoices_copy', 'صورة عن الفواتير الضريبية للمورد'),
    ('original_invoice', 'استلام الفاتورة الاصلية'),
    ('tax_deduction_cert', 'شهادة خصم مصدر ساري المفعول'),
    ('signed_boq', 'جدول كميات موقع من مدير المشروع'),
    ('vendor_statement', 'كشف حساب من المورد / مطالبة مالية'),
    ('company_statement', 'كشف حساب من البرنامج المحاسبي للشركة'),
    ('agreement_or_po', 'اتفاقية المورد / أمر الشراء'),
    ('guarantee_cheque', 'شيك ضمان'),
    ('project_purchase_request', 'طلب شراء من المشروع'),
    ('final_clearance', 'مطالبة نهائية / مخالصة نهائية'),
    ('maintenance_bond', 'كفالة صيانة / حسن تنفيذ من المورد'),
)


class PaymentClaimSequence(models.Model):
    """The running number of one claim series: TAB-009 -> the next is TAB-010. One series per project (by its symbol), plus the main office's."""

    prefix = models.CharField(max_length=60, unique=True, help_text=_('Printed before the number, e.g. TAB or MAIN OFFICE SUP'))
    separator = models.CharField(max_length=2, default='-', blank=True, help_text=_('Between the prefix and the number: "-" (TAB-010) or "." (YAN.004)'))
    digits = models.PositiveSmallIntegerField(default=3, help_text=_('How many digits the number is padded to (3: 010, 4: 0014)'))
    last_number = models.PositiveIntegerField(default=0, help_text=_('The last number already used; the next claim gets this + 1'))
    project_symbol = models.CharField(max_length=30, blank=True, help_text=_('The project symbol this series serves when it differs from the prefix (e.g. project YCN uses prefix YAN)'))

    class Meta:
        ordering = ['prefix']
        verbose_name = _('Payment claim numbering')
        verbose_name_plural = _('Payment claim numbering')

    def __str__(self):
        return f'{self.prefix} (last {self.last_number})'

    def format(self, number):
        return f'{self.prefix}{self.separator}{number:0{self.digits}d}'

    @classmethod
    def next_number_for(cls, project):
        """Take the next number of the project's series (creating the series on first use) and return it formatted."""
        with transaction.atomic():
            if project is None:
                sequence, _created = cls.objects.select_for_update().get_or_create(prefix=MAIN_OFFICE_PREFIX, defaults={'digits': 4})
            else:
                symbol = project.project_symbol
                sequence = (cls.objects.select_for_update().filter(project_symbol=symbol).first()
                            or cls.objects.select_for_update().filter(prefix=symbol).first())
                if sequence is None:
                    sequence = cls.objects.create(prefix=symbol)
            sequence.last_number += 1
            sequence.save(update_fields=['last_number'])
            return sequence.format(sequence.last_number)


class PaymentClaim(models.Model):
    DRAFT = 'draft'
    SUBMITTED = 'submitted'
    FINANCE_APPROVED = 'finance_approved'
    EXECUTIVE_APPROVED = 'executive_approved'
    APPROVED = 'approved'
    PAID = 'paid'
    REJECTED = 'rejected'
    STATUS_CHOICES = (
        (DRAFT, _('Draft')),
        (SUBMITTED, _('Waiting for finance')),
        (FINANCE_APPROVED, _('Waiting for the executive director')),
        (EXECUTIVE_APPROVED, _('Waiting for the general manager')),
        (APPROVED, _('Approved - ready to pay')),
        (PAID, _('Paid')),
        (REJECTED, _('Sent back')),
    )
    # who must sign next, by status
    NEXT_SIGNER = {SUBMITTED: 'finance', FINANCE_APPROVED: 'executive', EXECUTIVE_APPROVED: 'general'}

    INTERIM = 'interim'
    FINAL = 'final'
    TYPE_CHOICES = ((INTERIM, _('Interim claim (مرحلية)')), (FINAL, _('Final claim (نهائية)')))

    number = models.CharField(max_length=80, unique=True, editable=False, help_text=_('Assigned automatically from the project\'s series (TAB-010 ...)'))
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='payment_claims',
                                help_text=_('Empty = a main-office claim'))
    vendor = models.ForeignKey('procurement.Vendor', on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_claims')
    beneficiary_name = models.CharField(max_length=200, help_text=_('The vendor / beneficiary as written on the claim'))
    claim_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default=INTERIM)
    claim_date = models.DateField(default=timezone.localdate)
    nature_of_work = models.CharField(max_length=200, blank=True)
    original_contract_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    current_contract_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    previous_payments = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)

    deduction_agreed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'), help_text=_('Agreed deduction (خصم متفق عليه)'))
    deduction_source_retention = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'), help_text=_('Retention instead of a source-deduction certificate (حجز بدل خصم مصدر)'))
    deduction_other = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'), help_text=_('Other retentions / deductions'))

    requirements = models.JSONField(default=list, blank=True, help_text=_('Keys of the ticked requirements'))

    # the payment, recorded by the accountant at the end
    cash_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cash_date = models.DateField(null=True, blank=True)
    cheque_no = models.CharField(max_length=100, blank=True)
    cheque_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    cheque_due_date = models.DateField(null=True, blank=True)
    payment_note = models.CharField(max_length=300, blank=True, help_text=_('e.g. "paid 2000 by cheque" / "paid from the account"'))

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    equipment_claim = models.OneToOneField('equipment.EquipmentClaim', on_delete=models.SET_NULL, null=True, blank=True, related_name='payment_claim',
                                           help_text=_('The rental claim this form pays (paying the form marks it paid)'))

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    # the signatures: each is the person who approved and when
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    submitted_at = models.DateTimeField(null=True, blank=True)
    finance_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    finance_at = models.DateTimeField(null=True, blank=True)
    executive_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    executive_at = models.DateTimeField(null=True, blank=True)
    general_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    general_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    paid_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-claim_date', '-id']
        verbose_name = _('Payment claim')
        verbose_name_plural = _('Payment claims')

    def __str__(self):
        return f'{self.number} {self.beneficiary_name}'

    # ------------------------------------------------------------ amounts
    @property
    def total_amount(self):
        return sum((line.amount for line in self.lines.all()), Decimal('0'))

    @property
    def deductions_total(self):
        return (self.deduction_agreed or 0) + (self.deduction_source_retention or 0) + (self.deduction_other or 0)

    @property
    def net_due(self):
        """The final amount due for payment: the lines' total less the deductions."""
        return self.total_amount - self.deductions_total

    @property
    def requirement_items(self):
        ticked = set(self.requirements or [])
        return [(key, label, key in ticked) for key, label in REQUIREMENTS]

    @property
    def is_editable(self):
        return self.status in (self.DRAFT, self.REJECTED)

    @property
    def next_signer(self):
        return self.NEXT_SIGNER.get(self.status)

    @property
    def project_label(self):
        return f'{self.project.project_symbol} - {self.project.name}' if self.project_id else 'Main office / الإدارة العامة'


class PaymentClaimLine(models.Model):
    """One row of "claim details": the statement (البيان), its details and the amount."""

    claim = models.ForeignKey(PaymentClaim, on_delete=models.CASCADE, related_name='lines')
    statement = models.CharField(max_length=200, blank=True, help_text=_('البيان, e.g. "Claim details"'))
    details = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0'))
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['claim', 'order', 'id']

    def __str__(self):
        return f'{self.claim.number} - {self.statement or self.details[:30]}'
