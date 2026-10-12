"""
Monthly rental claims (المطالبة المالية) of the RENTED heavy equipment.

The payment cycle runs from the 26th of one month to the 25th of the next and closes on the 25th. Once it is closed, every rented heavy
equipment that worked in it on a project gets ONE claim for that project: the hours (or days) are counted from the project's submitted
daily reports and priced at the equipment's rental rate. The claim goes to the Accounting page ("Payables") for payment; the project's
engineer reviews it there and may change the amount (a reason is required and kept); the accountant pays it only after that review,
and a paid claim is locked.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import EquipmentClaim, Tool

CYCLE_DAY = 25
COUNTED_STATUSES = ('submitted', 'engineering_approved', 'approved')   # a draft or rejected report is not counted
ZERO = Decimal('0')


def cycle_for_end(end):
    """(start, end) of the cycle that ends on `end` (a 25th): 26th of the previous month .. 25th."""
    first_of_month = end.replace(day=1)
    previous_month_end = first_of_month - timedelta(days=1)
    start = previous_month_end.replace(day=CYCLE_DAY) + timedelta(days=1)
    return start, end


def last_closed_cycle_end(today=None):
    """The most recent 25th that is already over (the cycle closes at the end of the 25th, so the 26th is the first day it can be settled)."""
    today = today or timezone.localdate()
    this_month = today.replace(day=CYCLE_DAY)
    if today > this_month:
        return this_month
    previous_month_end = today.replace(day=1) - timedelta(days=1)
    return previous_month_end.replace(day=CYCLE_DAY)


def _money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def usage_rows(tool, project, start, end):
    """The daily-report rows (one per report day) that make up a claim, oldest first."""
    from reports.models import DailyEquipment
    return (DailyEquipment.objects.filter(tool=tool, report__project=project, report__report_date__gte=start, report__report_date__lte=end,
                                          report__status__in=COUNTED_STATUSES, report__deleted_at__isnull=True)
            .select_related('report', 'activity').order_by('report__report_date', 'pk'))


def calculate(tool, project, start, end):
    """(days, hours, idle_hours, amount) for one equipment on one project in a cycle."""
    days, hours, idle = set(), ZERO, ZERO
    for row in usage_rows(tool, project, start, end):
        if row.hours_worked and row.hours_worked > 0:
            days.add(row.report.report_date)
        hours += row.hours_worked or ZERO
        idle += row.idle_hours or ZERO
    rate = tool.rental_rate or ZERO
    if tool.rental_rate_unit == 'hour':
        amount = hours * rate
    elif tool.rental_rate_unit == 'month':
        amount = rate if days else ZERO     # a monthly rate is claimed in full for a month it worked in; the engineer can prorate it
    else:
        amount = Decimal(len(days)) * rate
    return len(days), hours, idle, _money(amount)


@transaction.atomic
def generate_claims(end=None, project=None, dry_run=False):
    """
    Create the claims of the cycle that ended on `end` (default: the last closed cycle). Safe to repeat: a (tool, project, cycle) that
    already has a claim is left alone. Returns the list of claims created (or that would be, as unsaved objects, with dry_run).
    """
    end = end or last_closed_cycle_end()
    if end.day != CYCLE_DAY:
        raise ValidationError(f'A cycle ends on the {CYCLE_DAY}th; {end} is not.')
    start, end = cycle_for_end(end)
    from reports.models import DailyEquipment
    rows = DailyEquipment.objects.filter(
        tool__ownership=Tool.RENTED, tool__kind=Tool.KIND_HEAVY, report__report_date__gte=start, report__report_date__lte=end,
        report__status__in=COUNTED_STATUSES, report__deleted_at__isnull=True)
    if project:
        rows = rows.filter(report__project=project)
    pairs = sorted({(row[0], row[1]) for row in rows.values_list('tool_id', 'report__project_id')})
    made = []
    for tool_id, project_id in pairs:
        if EquipmentClaim.objects.filter(tool_id=tool_id, project_id=project_id, cycle_end=end).exists():
            continue
        tool = Tool.objects.select_related('rental_vendor').get(pk=tool_id)
        days, hours, idle, amount = calculate(tool, _project(project_id), start, end)
        claim = EquipmentClaim(
            tool=tool, project_id=project_id, vendor=tool.rental_vendor, cycle_start=start, cycle_end=end, days_worked=days, hours_worked=hours,
            idle_hours=idle, rate=tool.rental_rate or ZERO, rate_unit=tool.rental_rate_unit, calculated_amount=amount, amount=amount)
        if not dry_run:
            claim.save()
        made.append(claim)
    return made


def _project(project_id):
    from projects.models import Project
    return Project.objects.get(pk=project_id)


# ------------------------------------------------------------------ who may do what
def can_review(user, claim):
    """Admin, the managers, and the engineer / manager of the claim's own project."""
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager():
        return True
    return claim.project.site_engineer_id == user.pk or claim.project.manager_id == user.pk


def can_pay(user):
    return user.is_admin() or user.is_accountant()


def can_see_payables(user):
    return user.is_admin() or user.is_accountant() or user.is_general_manager()


def _audit(user, claim, text):
    from accounts.models import UserAuditLog
    UserAuditLog.objects.create(user=user, action='update', content_type='equipment.EquipmentClaim', object_id=claim.pk,
                                description=f'{claim.tool.code} claim {claim.cycle_end:%m/%Y} ({claim.project.project_symbol}): {text}')


# ------------------------------------------------------------------ the engineer's review, the accountant's payment
@transaction.atomic
def review_claim(claim, user, new_amount=None, reason=''):
    """Confirm the amount as calculated, or change it (a reason is then required). Not possible once paid."""
    claim = EquipmentClaim.objects.select_for_update().select_related('tool', 'project').get(pk=claim.pk)
    if claim.status == EquipmentClaim.PAID:
        raise ValidationError('This claim is already paid and cannot be changed.')
    if claim.status == EquipmentClaim.CANCELLED:
        raise ValidationError('This claim was cancelled.')
    if not can_review(user, claim):
        raise PermissionDenied('Only the project engineer or a manager can review this claim.')
    text = 'confirmed'
    if new_amount is not None and _money(new_amount) != claim.amount:
        if not (reason or '').strip():
            raise ValidationError('Write the reason for changing the amount.')
        text = f'amount {claim.amount} -> {_money(new_amount)}: {reason.strip()}'
        claim.amount = _money(new_amount)
        claim.adjustment_reason = reason.strip()[:300]
        claim.adjusted_by, claim.adjusted_at = user, timezone.now()
    claim.reviewed_by, claim.reviewed_at = user, timezone.now()
    claim.save()
    _audit(user, claim, text)
    return claim


@transaction.atomic
def pay_claim(claim, user, payment_date=None, reference=''):
    """The accountant pays a REVIEWED claim; from then on it is locked."""
    claim = EquipmentClaim.objects.select_for_update().select_related('tool', 'project').get(pk=claim.pk)
    if not can_pay(user):
        raise PermissionDenied('Only the accounting can pay a claim.')
    if claim.status != EquipmentClaim.POSTED:
        raise ValidationError('Only a posted claim can be paid.')
    if not claim.reviewed_at:
        raise ValidationError('The project engineer has not reviewed this claim yet.')
    claim.status, claim.paid_by, claim.paid_at = EquipmentClaim.PAID, user, timezone.now()
    claim.payment_date = payment_date or timezone.localdate()
    claim.payment_reference = (reference or '')[:100]
    claim.save()
    _audit(user, claim, f'paid {claim.amount} ({claim.payment_reference or "no reference"})')
    return claim


@transaction.atomic
def reopen_claim(claim, user):
    """Admin only: undo a payment that was recorded by mistake."""
    claim = EquipmentClaim.objects.select_for_update().select_related('tool', 'project').get(pk=claim.pk)
    if not user.is_admin():
        raise PermissionDenied('Only an administrator can reopen a paid claim.')
    if claim.status != EquipmentClaim.PAID:
        raise ValidationError('The claim is not paid.')
    claim.status, claim.paid_by, claim.paid_at, claim.payment_date, claim.payment_reference = EquipmentClaim.POSTED, None, None, None, ''
    claim.save()
    _audit(user, claim, 'payment reopened')
    return claim


def totals_by_vendor(claims):
    """[(vendor name, number of claims, total amount)] for a set of claims."""
    sums = defaultdict(lambda: [0, ZERO])
    for claim in claims:
        key = claim.vendor.name if claim.vendor_id else '—'
        sums[key][0] += 1
        sums[key][1] += claim.amount
    return sorted(((name, count, total) for name, (count, total) in sums.items()))
