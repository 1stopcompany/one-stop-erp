"""
Rules of the payment claims: who may do what and what each step changes (every step runs in one transaction and leaves an audit line).

    create        the project manager of the project (an administrator anywhere; the accountant for main-office claims and for equipment rental claims)
    sign          finance -> executive director -> general manager, in that order; an administrator may sign any step
    reject        whoever must sign next sends it back to the preparer, with a reason
    pay           the accountant (or an administrator) once the general manager has signed
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import REQUIREMENTS, PaymentClaim, PaymentClaimLine, PaymentClaimSequence

# the role(s) whose holders sign each step (settings.PAYMENT_CLAIM_SIGNER_ROLES overrides); "executive" is the executive director
SIGNER_ROLES = {'finance': ['accountant'], 'executive': ['engineering_manager'], 'general': ['general_manager']}
STEP_FIELDS = {'finance': ('finance_by', 'finance_at', PaymentClaim.FINANCE_APPROVED),
               'executive': ('executive_by', 'executive_at', PaymentClaim.EXECUTIVE_APPROVED),
               'general': ('general_by', 'general_at', PaymentClaim.APPROVED)}
STEP_LABELS = {'finance': 'Finance', 'executive': 'Executive director', 'general': 'General manager'}


def signer_roles(step):
    return (getattr(settings, 'PAYMENT_CLAIM_SIGNER_ROLES', None) or SIGNER_ROLES).get(step, [])


# ------------------------------------------------------------------ who may do what
def can_create(user, project=None):
    if user.is_admin():
        return True
    if project is None:
        return user.is_accountant()
    return user.is_project_manager() and project.manager_id == user.pk


def can_create_any(user):
    return user.is_admin() or user.is_accountant() or user.is_project_manager()


def projects_for_new_claim(user):
    from projects.models import Project
    qs = Project.objects.exclude(status__in=('archived',)).order_by('project_symbol')
    if user.is_admin():
        return qs
    if user.is_project_manager():
        return qs.filter(manager=user)
    return qs.none()


def visible_claims(user):
    qs = PaymentClaim.objects.select_related('project', 'vendor', 'created_by')
    if user.is_admin() or user.is_accountant() or user.is_engineering_manager() or user.is_general_manager():
        return qs
    if user.is_project_manager():
        return qs.filter(Q(project__manager=user) | Q(created_by=user))
    return qs.none()


def can_edit(user, claim):
    if not claim.is_editable:
        return False
    return user.is_admin() or claim.created_by_id == user.pk or (claim.project_id and claim.project.manager_id == user.pk and user.is_project_manager())


def can_sign(user, claim):
    step = claim.next_signer
    return bool(step) and (user.is_admin() or user.role in signer_roles(step))


def can_submit(user, claim):
    return can_edit(user, claim) and claim.lines.exists()


def can_pay(user, claim):
    return claim.status == PaymentClaim.APPROVED and (user.is_admin() or user.is_accountant())


def can_delete(user, claim):
    return claim.status == PaymentClaim.DRAFT and (user.is_admin() or claim.created_by_id == user.pk)


def _audit(user, claim, text):
    from accounts.models import UserAuditLog
    UserAuditLog.objects.create(user=user, action='update', content_type='accounting.PaymentClaim', object_id=claim.pk, description=f'{claim.number}: {text}')


# ------------------------------------------------------------------ create / edit
def _money(value, name, default=None):
    if value in (None, ''):
        return default
    try:
        return Decimal(str(value).replace(',', '').strip())
    except InvalidOperation:
        raise ValidationError(f'{name} is not a number.')


def apply_data(claim, data, lines):
    """Copy the form's values onto the claim and replace its lines. `data` is a plain dict of strings (request.POST-like)."""
    from procurement.models import Vendor
    vendor = Vendor.objects.filter(pk=data.get('vendor')).first() if data.get('vendor') else None
    claim.vendor = vendor
    claim.beneficiary_name = (data.get('beneficiary_name') or (vendor.name if vendor else '')).strip()
    if not claim.beneficiary_name:
        raise ValidationError('Write the vendor / beneficiary.')
    claim.claim_type = data.get('claim_type') if data.get('claim_type') in dict(PaymentClaim.TYPE_CHOICES) else PaymentClaim.INTERIM
    claim.claim_date = data.get('claim_date') or timezone.localdate()
    claim.nature_of_work = (data.get('nature_of_work') or '').strip()
    claim.original_contract_value = _money(data.get('original_contract_value'), 'The original contract value')
    claim.current_contract_value = _money(data.get('current_contract_value'), 'The current contract value')
    claim.previous_payments = _money(data.get('previous_payments'), 'The previous payments')
    claim.notes = (data.get('notes') or '').strip()
    claim.deduction_agreed = _money(data.get('deduction_agreed'), 'The agreed deduction', Decimal('0'))
    claim.deduction_source_retention = _money(data.get('deduction_source_retention'), 'The source-deduction retention', Decimal('0'))
    claim.deduction_other = _money(data.get('deduction_other'), 'The other deductions', Decimal('0'))
    claim.requirements = [key for key, _label in REQUIREMENTS if data.get(f'req_{key}')]
    clean_lines = []
    for statement, details, amount in lines:
        statement, details = (statement or '').strip(), (details or '').strip()
        value = _money(amount, 'A line amount', Decimal('0'))
        if statement or details or value:
            clean_lines.append((statement, details, value))
    return clean_lines


@transaction.atomic
def create_claim(user, project, data, lines):
    if not can_create(user, project):
        raise PermissionDenied('You cannot create a claim for this project.')
    claim = PaymentClaim(project=project, created_by=user, number='pending')
    clean_lines = apply_data(claim, data, lines)
    claim.number = PaymentClaimSequence.next_number_for(project)
    claim.save()
    for order, (statement, details, amount) in enumerate(clean_lines):
        PaymentClaimLine.objects.create(claim=claim, statement=statement, details=details, amount=amount, order=order)
    _audit(user, claim, 'created')
    return claim


@transaction.atomic
def update_claim(user, claim, data, lines):
    claim = PaymentClaim.objects.select_for_update().get(pk=claim.pk)
    if not can_edit(user, claim):
        raise PermissionDenied('This claim cannot be edited.')
    clean_lines = apply_data(claim, data, lines)
    claim.save()
    claim.lines.all().delete()
    for order, (statement, details, amount) in enumerate(clean_lines):
        PaymentClaimLine.objects.create(claim=claim, statement=statement, details=details, amount=amount, order=order)
    _audit(user, claim, 'edited')
    return claim


@transaction.atomic
def delete_claim(user, claim):
    claim = PaymentClaim.objects.select_for_update().get(pk=claim.pk)
    if not can_delete(user, claim):
        raise PermissionDenied('Only a draft can be deleted, by its preparer.')
    _audit(user, claim, 'deleted')
    claim.delete()


# ------------------------------------------------------------------ the signatures
@transaction.atomic
def submit(user, claim):
    """The preparer sends the claim: that is his signature (the project manager's column of the form)."""
    claim = PaymentClaim.objects.select_for_update().get(pk=claim.pk)
    if not can_edit(user, claim):
        raise PermissionDenied('You cannot submit this claim.')
    if not claim.lines.exists():
        raise ValidationError('Add at least one claim detail line.')
    if claim.net_due <= 0:
        raise ValidationError('The final amount due must be more than zero.')
    claim.status, claim.submitted_by, claim.submitted_at = PaymentClaim.SUBMITTED, user, timezone.now()
    claim.finance_by = claim.executive_by = claim.general_by = None
    claim.finance_at = claim.executive_at = claim.general_at = None
    claim.rejected_by, claim.rejected_at, claim.rejection_reason = None, None, ''
    claim.save()
    _audit(user, claim, 'submitted (signed by the preparer)')
    return claim


@transaction.atomic
def sign(user, claim):
    """Finance, the executive director or the general manager approves his step -- that is his signature."""
    claim = PaymentClaim.objects.select_for_update().get(pk=claim.pk)
    step = claim.next_signer
    if not step:
        raise ValidationError('This claim is not waiting for a signature.')
    if not can_sign(user, claim):
        raise PermissionDenied(f'Only the {STEP_LABELS[step].lower()} signs this step.')
    by_field, at_field, new_status = STEP_FIELDS[step]
    setattr(claim, by_field, user)
    setattr(claim, at_field, timezone.now())
    claim.status = new_status
    claim.save()
    _audit(user, claim, f'signed as {STEP_LABELS[step].lower()}')
    return claim


@transaction.atomic
def reject(user, claim, reason):
    claim = PaymentClaim.objects.select_for_update().get(pk=claim.pk)
    if not claim.next_signer:
        raise ValidationError('This claim is not waiting for a signature.')
    if not can_sign(user, claim):
        raise PermissionDenied('You cannot send this claim back.')
    if not (reason or '').strip():
        raise ValidationError('Write why the claim is sent back.')
    claim.status, claim.rejected_by, claim.rejected_at, claim.rejection_reason = PaymentClaim.REJECTED, user, timezone.now(), reason.strip()[:300]
    claim.finance_by = claim.executive_by = claim.general_by = None
    claim.finance_at = claim.executive_at = claim.general_at = None
    claim.save()
    _audit(user, claim, f'sent back: {claim.rejection_reason}')
    return claim


# ------------------------------------------------------------------ payment
@transaction.atomic
def pay(user, claim, data):
    """The accountant records how the claim was paid (cash and / or cheque) -- the claim is closed."""
    claim = PaymentClaim.objects.select_for_update().select_related('equipment_claim').get(pk=claim.pk)
    if not can_pay(user, claim):
        raise PermissionDenied('Only the accountant pays an approved claim.')
    claim.cash_amount = _money(data.get('cash_amount'), 'The cash amount')
    claim.cash_date = data.get('cash_date') or None
    claim.cheque_no = (data.get('cheque_no') or '').strip()
    claim.cheque_amount = _money(data.get('cheque_amount'), 'The cheque amount')
    claim.cheque_due_date = data.get('cheque_due_date') or None
    claim.payment_note = (data.get('payment_note') or '').strip()[:300]
    if not ((claim.cash_amount or 0) > 0 or (claim.cheque_amount or 0) > 0 or claim.payment_note):
        raise ValidationError('Record the payment: a cash amount, a cheque, or a note.')
    claim.status, claim.paid_by, claim.paid_at = PaymentClaim.PAID, user, timezone.now()
    claim.save()
    if claim.equipment_claim_id:
        from equipment import claims as equipment_claims
        equipment = claim.equipment_claim
        if equipment.status == equipment.POSTED and equipment.reviewed_at:
            equipment_claims.pay_claim(equipment, user, payment_date=claim.cash_date or claim.cheque_due_date or timezone.localdate(), reference=claim.number)
    _audit(user, claim, 'paid')
    return claim


@transaction.atomic
def reopen(user, claim):
    """Administrator only: undo a payment recorded by mistake (the claim goes back to Approved)."""
    claim = PaymentClaim.objects.select_for_update().select_related('equipment_claim').get(pk=claim.pk)
    if not user.is_admin():
        raise PermissionDenied('Only an administrator can reopen a paid claim.')
    if claim.status != PaymentClaim.PAID:
        raise ValidationError('The claim is not paid.')
    claim.status, claim.paid_by, claim.paid_at = PaymentClaim.APPROVED, None, None
    claim.save()
    if claim.equipment_claim_id and claim.equipment_claim.status == claim.equipment_claim.PAID:
        from equipment import claims as equipment_claims
        equipment_claims.reopen_claim(claim.equipment_claim, user)
    _audit(user, claim, 'payment reopened')
    return claim


# ------------------------------------------------------------------ from the rented-equipment claims
@transaction.atomic
def from_equipment_claim(user, equipment):
    """Make the formal claim form for a reviewed rental claim (vendor, project, amount and the details are filled in)."""
    from equipment.models import EquipmentClaim
    equipment = EquipmentClaim.objects.select_for_update().select_related('tool', 'project', 'vendor').get(pk=equipment.pk)
    if not (user.is_admin() or user.is_accountant() or (user.is_project_manager() and equipment.project.manager_id == user.pk)):
        raise PermissionDenied('You cannot create this claim.')
    if equipment.status != EquipmentClaim.POSTED or not equipment.reviewed_at:
        raise ValidationError('Only a reviewed rental claim that is not paid yet can become a payment claim.')
    if PaymentClaim.objects.filter(equipment_claim=equipment).exists():
        raise ValidationError('A payment claim already exists for this rental claim.')
    claim = PaymentClaim(project=equipment.project, vendor=equipment.vendor, created_by=user, equipment_claim=equipment, number='pending',
                         beneficiary_name=equipment.vendor.name if equipment.vendor else equipment.tool.name, claim_type=PaymentClaim.INTERIM,
                         nature_of_work=f'Equipment rental - {equipment.tool.name}', current_contract_value=None)
    claim.number = PaymentClaimSequence.next_number_for(equipment.project)
    claim.save()
    detail = (f'{equipment.tool.code} {equipment.tool.name}: rental {equipment.cycle_label} - {equipment.days_worked} day(s) / '
              f'{equipment.hours_worked} h' + (f'. {equipment.adjustment_reason}' if equipment.is_adjusted and equipment.adjustment_reason else ''))
    PaymentClaimLine.objects.create(claim=claim, statement='Rental claim', details=detail, amount=equipment.amount, order=0)
    _audit(user, claim, f'created from rental claim {equipment.pk}')
    return claim
