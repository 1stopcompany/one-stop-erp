from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from equipment import claims
from equipment.models import EquipmentClaim


@login_required
def accounting_dashboard(request):
    can_see = claims.can_see_payables(request.user)
    ready = EquipmentClaim.objects.filter(status=EquipmentClaim.POSTED, reviewed_at__isnull=False).count() if can_see else 0
    from . import payment_claims as claim_service
    visible = claim_service.visible_claims(request.user)
    from .models import PaymentClaim
    return render(request, "accounting/dashboard.html", {
        "claims_waiting_me": sum(1 for c in visible.exclude(status__in=(PaymentClaim.DRAFT, PaymentClaim.PAID, PaymentClaim.APPROVED, PaymentClaim.REJECTED)) if claim_service.can_sign(request.user, c)),
        "claims_to_pay": sum(1 for c in visible.filter(status=PaymentClaim.APPROVED) if claim_service.can_pay(request.user, c)),
        "claims_open": visible.exclude(status=PaymentClaim.PAID).count(),
        "module_name": "Accounting & Finance",
        "module_icon": "💰",
        "can_see_payables": can_see,
        "payables_ready": ready,
    })


@login_required
def payables(request):
    """Everything posted for payment: the rental claims of the rented heavy equipment, with the engineer's review state."""
    if not claims.can_see_payables(request.user):
        return HttpResponseForbidden('Only the accounting can open the payables.')
    status = request.GET.get('status', 'open')
    cycle = request.GET.get('cycle', '')
    qs = EquipmentClaim.objects.select_related('tool', 'project', 'vendor', 'reviewed_by', 'adjusted_by')
    if cycle:
        qs = qs.filter(cycle_end=cycle)
    to_pay = qs.filter(status=EquipmentClaim.POSTED)
    if status == 'open':
        shown = to_pay
    elif status == 'paid':
        shown = qs.filter(status=EquipmentClaim.PAID)
    else:
        shown = qs.exclude(status=EquipmentClaim.CANCELLED)
    ready = to_pay.filter(reviewed_at__isnull=False)
    waiting = to_pay.filter(reviewed_at__isnull=True)
    total = lambda q: q.aggregate(t=Sum('amount'))['t'] or Decimal('0')
    return render(request, 'accounting/payables.html', {
        'claims': list(shown[:400]), 'status': status, 'cycle': cycle,
        'cycles': EquipmentClaim.objects.order_by('-cycle_end').values_list('cycle_end', flat=True).distinct(),
        'ready_total': total(ready), 'ready_count': ready.count(), 'waiting_total': total(waiting), 'waiting_count': waiting.count(),
        'vendor_totals': claims.totals_by_vendor(ready), 'can_pay': claims.can_pay(request.user),
    })


@login_required
@require_POST
def payable_pay(request, pk):
    claim = get_object_or_404(EquipmentClaim, pk=pk)
    try:
        claims.pay_claim(claim, request.user, reference=request.POST.get('reference', '').strip())
        messages.success(request, f'{claim.tool.code} claim marked as paid.')
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, '; '.join(error.messages) if isinstance(error, ValidationError) else str(error))
    return redirect(request.META.get('HTTP_REFERER') or 'accounting:payables')


@login_required
@require_POST
def payable_reopen(request, pk):
    claim = get_object_or_404(EquipmentClaim, pk=pk)
    try:
        claims.reopen_claim(claim, request.user)
        messages.warning(request, f'The payment of {claim.tool.code} was reopened.')
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, '; '.join(error.messages) if isinstance(error, ValidationError) else str(error))
    return redirect(request.META.get('HTTP_REFERER') or 'accounting:payables')
