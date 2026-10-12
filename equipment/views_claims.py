"""Rental claims: the engineer's review pages (here) and the accountant's "Payables" page (accounting/views.py uses the same service)."""
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import claims
from .models import EquipmentClaim


def _visible(user):
    qs = EquipmentClaim.objects.select_related('tool', 'project', 'vendor', 'reviewed_by', 'adjusted_by')
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager() or user.is_accountant():
        return qs
    return qs.filter(Q(project__site_engineer=user) | Q(project__manager=user))


@login_required
def claim_list(request):
    """The claims of the user's own projects (everything for admin / managers), newest cycle first; the ones waiting for a review first."""
    status = request.GET.get('status', '')
    qs = _visible(request.user)
    if status == 'review':
        qs = qs.filter(status=EquipmentClaim.POSTED, reviewed_at__isnull=True)
    elif status in dict(EquipmentClaim.STATUS_CHOICES):
        qs = qs.filter(status=status)
    rows = list(qs[:300])
    return render(request, 'equipment/claim_list.html', {
        'claims': rows, 'status': status, 'waiting': sum(1 for c in rows if c.status == EquipmentClaim.POSTED and not c.reviewed_at),
        'can_review': lambda c: claims.can_review(request.user, c),
    })


@login_required
def claim_detail(request, pk):
    claim = get_object_or_404(_visible(request.user), pk=pk)
    return render(request, 'equipment/claim_detail.html', {
        'claim': claim, 'rows': claims.usage_rows(claim.tool, claim.project, claim.cycle_start, claim.cycle_end),
        'can_review': claims.can_review(request.user, claim) and claim.status == EquipmentClaim.POSTED,
    })


@login_required
@require_POST
def claim_review(request, pk):
    """Confirm the claim, or change its amount (with the reason)."""
    claim = get_object_or_404(_visible(request.user), pk=pk)
    raw = request.POST.get('amount', '').strip().replace(',', '')
    try:
        new_amount = Decimal(raw) if raw else None
    except InvalidOperation:
        messages.error(request, 'The amount is not a number.')
        return redirect('equipment:claim_detail', pk=pk)
    try:
        claim = claims.review_claim(claim, request.user, new_amount=new_amount, reason=request.POST.get('reason', ''))
        messages.success(request, 'Reviewed. The claim is ready for the accounting to pay.' + (' The amount was changed.' if claim.is_adjusted else ''))
    except ValidationError as error:
        messages.error(request, '; '.join(error.messages))
    except PermissionDenied as error:
        messages.error(request, str(error))
    return redirect('equipment:claim_detail', pk=pk)
