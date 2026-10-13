"""
Mobile API of the purchasing flow, one set of screens for each role (token authentication, like the rest of the mobile API):

  site engineer      writes material requests (purchase requisitions) for his projects, submits them, and receives deliveries of his POs
  project manager    approves / rejects the submitted requests of his projects, and follows their POs
  procurement / store / admin   follow every PO and record the goods received

    GET  /procurement/api/mobile/items/?q=                    search the item list (name, code, barcode)
    GET  /procurement/api/mobile/projects/                    the projects this user may request material for
    GET  /procurement/api/mobile/requisitions/?scope=mine|approve
    POST /procurement/api/mobile/requisitions/               create a draft {project, required_date, lines:[{item, quantity, unit, remarks}], submit:bool}
    GET  /procurement/api/mobile/requisitions/<id>/
    PUT  /procurement/api/mobile/requisitions/<id>/           replace a draft's date and lines
    POST /procurement/api/mobile/requisitions/<id>/<submit|approve|reject>/      (reject needs {reason})
    GET  /procurement/api/mobile/orders/                      the open POs of this user's scope with their receiving progress
    GET  /procurement/api/mobile/orders/<id>/
    POST /procurement/api/mobile/orders/<id>/receive/         {lines:[{line, quantity}], note}

Every rule is the same as on the web pages (procurement.views._can_*): the phone is only another way to do the same steps.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from projects.models import Project

from .models import (
    UNIT_CHOICES, ItemMaster, POReceipt, PurchaseOrder, PurchaseOrderLine, PurchaseRequisition, PurchaseRequisitionLine,
)
from .views import _can_approve_pr, _can_manage_pr, _can_work_procurement

UNITS = {value for value, _ in UNIT_CHOICES}
OPEN_PO_STATUSES = ('sent', 'confirmed', 'partial_received')


def _error(message, status=400):
    return Response({'detail': message}, status=status)


def _can_receive(user, po):
    """Record goods received against a PO: admin, procurement, the storekeeper, or the project's own engineer."""
    return user.is_admin() or user.is_procurement_officer() or user.is_storekeeper() or (user.is_site_engineer() and po.project.site_engineer_id == user.id)


def _projects_for_requests(user):
    if user.is_admin():
        return Project.objects.exclude(status__in=('completed', 'archived'))
    if user.is_site_engineer():
        return Project.objects.filter(site_engineer=user)
    return Project.objects.none()


def _item_data(item):
    return {'id': item.id, 'code': item.full_code, 'name': item.description, 'brand': item.brand, 'unit': item.unit or ''}


def _pr_summary(pr):
    return {
        'id': pr.id, 'number': pr.pr_number, 'project': {'id': pr.project_id, 'name': pr.project.name, 'symbol': pr.project.project_symbol},
        'status': pr.status, 'status_label': pr.get_status_display(), 'required_date': pr.required_date.isoformat(),
        'requested_by': (pr.requested_by.get_full_name() or pr.requested_by.username) if pr.requested_by_id else '',
        'lines_count': pr.lines.count(), 'created': pr.created_date.isoformat(),
    }


def _pr_detail(pr, user):
    data = _pr_summary(pr)
    data.update({
        'lines': [{'id': l.id, 'item': _item_data(l.item), 'quantity': str(l.quantity_requested), 'unit': l.unit, 'remarks': l.remarks}
                  for l in pr.lines.select_related('item')],
        'rejected_reason': getattr(pr, 'rejected_reason', '') or '',
        'approved_by': (pr.approved_by.get_full_name() or pr.approved_by.username) if pr.approved_by_id else '',
        'can_edit': pr.status == 'draft' and _can_manage_pr(user, pr),
        'can_submit': pr.status == 'draft' and _can_manage_pr(user, pr),
        'can_approve': pr.status == 'submitted' and _can_approve_pr(user, pr),
    })
    return data


def _po_summary(po):
    lines = list(po.lines.all())
    ordered = sum((l.quantity_ordered for l in lines), Decimal('0'))
    received = sum((l.quantity_received for l in lines), Decimal('0'))
    return {
        'id': po.id, 'number': po.po_number, 'vendor': po.vendor.name, 'project': {'id': po.project_id, 'name': po.project.name, 'symbol': po.project.project_symbol},
        'status': po.status, 'status_label': po.get_status_display(), 'lines_count': len(lines),
        'ordered': str(ordered), 'received': str(received), 'percent': int((received / ordered * 100)) if ordered else 0,
    }


def _po_detail(po, user):
    data = _po_summary(po)
    data['can_receive'] = po.status in OPEN_PO_STATUSES and _can_receive(user, po)
    data['lines'] = [{
        'id': l.id, 'item': _item_data(l.item), 'unit': l.unit, 'ordered': str(l.quantity_ordered), 'received': str(l.quantity_received),
        'remaining': str(max(l.quantity_ordered - l.quantity_received, Decimal('0'))),
    } for l in po.lines.select_related('item')]
    return data


# ------------------------------------------------------------------ catalogue
@api_view(['GET'])
def mobile_items(request):
    q = (request.GET.get('q') or '').strip()
    items = ItemMaster.objects.all()
    if q:
        items = items.filter(Q(description__icontains=q) | Q(full_code__icontains=q) | Q(short_code__icontains=q) | Q(barcode_value__iexact=q) | Q(source_code__icontains=q))
    return Response([_item_data(i) for i in items.order_by('description')[:25]])


@api_view(['GET'])
def mobile_request_projects(request):
    return Response([{'id': p.id, 'name': p.name, 'symbol': p.project_symbol} for p in _projects_for_requests(request.user).order_by('project_symbol')])


# ------------------------------------------------------------------ requisitions
def _scoped_prs(user, scope):
    qs = PurchaseRequisition.objects.select_related('project', 'requested_by', 'approved_by')
    if scope == 'approve':
        if user.is_admin():
            return qs.filter(status='submitted')
        if user.is_project_manager():
            return qs.filter(status='submitted', project__manager=user)
        return qs.none()
    if user.is_admin():
        return qs
    if user.is_procurement_officer():
        return qs.filter(Q(requested_by=user) | Q(status__in=('approved', 'in_procurement')))
    if user.is_site_engineer():
        return qs.filter(Q(project__site_engineer=user) | Q(requested_by=user))
    if user.is_project_manager():
        return qs.filter(project__manager=user)
    return qs.none()


def _save_lines(pr, lines):
    """Replace the lines of a draft; returns an error text or None."""
    if not isinstance(lines, list) or not lines:
        return 'Add at least one item.'
    cleaned = []
    for index, row in enumerate(lines, start=1):
        item = ItemMaster.objects.filter(pk=row.get('item')).first()
        if not item:
            return f'Line {index}: choose an item from the list.'
        try:
            quantity = Decimal(str(row.get('quantity') or '0'))
        except InvalidOperation:
            return f'Line {index}: the quantity is not a number.'
        if quantity <= 0:
            return f'Line {index}: the quantity must be more than zero.'
        unit = row.get('unit') or item.unit
        if unit not in UNITS:
            return f'Line {index}: choose the unit.'
        cleaned.append((item, quantity, unit, (row.get('remarks') or '')[:500]))
    pr.lines.all().delete()
    for order, (item, quantity, unit, remarks) in enumerate(cleaned):
        PurchaseRequisitionLine.objects.create(pr=pr, item=item, quantity_requested=quantity, unit=unit, remarks=remarks, order=order)
    return None


def _submit(pr):
    if pr.project.status == 'planning':
        return f'{pr.project.name} is still in Planning: finish its start-up stages before requesting material.'
    if not pr.lines.exists():
        return 'Add at least one item before submitting.'
    pr.status, pr.submitted_date = 'submitted', timezone.now()
    pr.save()
    return None


@api_view(['GET', 'POST'])
def mobile_requisitions(request):
    user = request.user
    if request.method == 'GET':
        scope = request.GET.get('scope', 'mine')
        return Response([_pr_summary(pr) for pr in _scoped_prs(user, scope).order_by('-created_date')[:80]])

    if not (user.is_site_engineer() or user.is_admin()):
        return _error('Only a site engineer can write a material request.', 403)
    data = request.data
    project = _projects_for_requests(user).filter(pk=data.get('project')).first()
    if not project:
        return _error('Choose one of your projects.')
    try:
        required = timezone.datetime.strptime(str(data.get('required_date') or ''), '%Y-%m-%d').date()
    except ValueError:
        return _error('Choose the date the material is needed by.')
    with transaction.atomic():
        pr = PurchaseRequisition.objects.create(project=project, required_date=required, requested_by=user)
        problem = _save_lines(pr, data.get('lines'))
        if problem:
            transaction.set_rollback(True)
            return _error(problem)
        if data.get('submit'):
            problem = _submit(pr)
            if problem:
                transaction.set_rollback(True)
                return _error(problem)
    return Response(_pr_detail(pr, user), status=201)


@api_view(['GET', 'PUT'])
def mobile_requisition_detail(request, pk):
    user = request.user
    pr = get_object_or_404(_scoped_prs(user, 'mine') | _scoped_prs(user, 'approve'), pk=pk)
    if request.method == 'GET':
        return Response(_pr_detail(pr, user))
    if not (pr.status == 'draft' and _can_manage_pr(user, pr)):
        return _error('Only your own draft can be edited.', 403)
    data = request.data
    with transaction.atomic():
        if data.get('required_date'):
            try:
                pr.required_date = timezone.datetime.strptime(str(data['required_date']), '%Y-%m-%d').date()
            except ValueError:
                return _error('The date is not valid.')
            pr.save()
        problem = _save_lines(pr, data.get('lines'))
        if problem:
            transaction.set_rollback(True)
            return _error(problem)
        if data.get('submit'):
            problem = _submit(pr)
            if problem:
                transaction.set_rollback(True)
                return _error(problem)
    pr.refresh_from_db()
    return Response(_pr_detail(pr, user))


@api_view(['POST'])
def mobile_requisition_action(request, pk, action):
    user = request.user
    pr = get_object_or_404(_scoped_prs(user, 'mine') | _scoped_prs(user, 'approve'), pk=pk)
    if action == 'submit':
        if not (pr.status == 'draft' and _can_manage_pr(user, pr)):
            return _error('You cannot submit this request.', 403)
        problem = _submit(pr)
        if problem:
            return _error(problem)
    elif action in ('approve', 'reject'):
        if not (pr.status == 'submitted' and _can_approve_pr(user, pr)):
            return _error('Only the project manager can approve or reject a submitted request.', 403)
        pr.status, pr.approved_by, pr.approved_date = ('approved' if action == 'approve' else 'rejected'), user, timezone.now()
        if action == 'reject':
            reason = (request.data.get('reason') or '').strip()
            if not reason:
                return _error('Write the reason for rejecting it.')
            pr.rejected_reason = reason[:500]
        pr.save()
    else:
        return _error('Unknown action.', 404)
    pr.refresh_from_db()
    return Response(_pr_detail(pr, user))


# ------------------------------------------------------------------ purchase orders and receiving
def _scoped_pos(user, prefetch=True):
    qs = PurchaseOrder.objects.select_related('project', 'vendor')
    if prefetch:
        qs = qs.prefetch_related('lines')
    if user.is_admin() or user.is_procurement_officer() or user.is_storekeeper() or user.is_engineering_manager() or user.is_general_manager():
        return qs
    if user.is_site_engineer():
        return qs.filter(project__site_engineer=user)
    if user.is_project_manager():
        return qs.filter(project__manager=user)
    return qs.none()


@api_view(['GET'])
def mobile_orders(request):
    scope = request.GET.get('scope', 'open')
    qs = _scoped_pos(request.user)
    qs = qs.filter(status__in=OPEN_PO_STATUSES) if scope == 'open' else qs.exclude(status='draft')
    return Response([_po_summary(po) for po in qs.order_by('-id')[:80]])


@api_view(['GET'])
def mobile_order_detail(request, pk):
    po = get_object_or_404(_scoped_pos(request.user), pk=pk)
    return Response(_po_detail(po, request.user))


@api_view(['POST'])
def mobile_order_receive(request, pk):
    """Record what arrived against the PO's lines (the same receipts as the web page: stock and the PO status follow by themselves)."""
    user = request.user
    # no prefetched lines here: the receipt signals recompute the PO's status from po.lines, and a prefetched copy would still hold the old quantities
    po = get_object_or_404(_scoped_pos(user, prefetch=False), pk=pk)
    if not _can_receive(user, po):
        return _error('You cannot record receipts for this order.', 403)
    if po.status not in OPEN_PO_STATUSES:
        return _error('This order is not open for receiving.')
    rows = request.data.get('lines')
    if not isinstance(rows, list) or not rows:
        return _error('Enter the quantity received for at least one line.')
    note = (request.data.get('note') or '')[:300]
    made = 0
    with transaction.atomic():
        for row in rows:
            line = po.lines.select_for_update().filter(pk=row.get('line')).first()
            if not line:
                transaction.set_rollback(True)
                return _error('One of the lines does not belong to this order.')
            name = line.item.description   # read before a refusal marks the transaction for rollback: no query is allowed after that
            try:
                quantity = Decimal(str(row.get('quantity') or '0'))
            except InvalidOperation:
                transaction.set_rollback(True)
                return _error(f'{name}: the quantity is not a number.')
            if quantity <= 0:
                continue
            remaining = line.quantity_ordered - line.quantity_received
            if quantity > remaining:
                transaction.set_rollback(True)
                return _error(f'{name}: only {remaining} {line.unit} are still expected.')
            POReceipt.objects.create(po_line=line, quantity_received=quantity, received_by=user, remarks=note)
            made += 1
    if not made:
        return _error('Enter a quantity above zero.')
    po.refresh_from_db()
    return Response(_po_detail(PurchaseOrder.objects.select_related('project', 'vendor').prefetch_related('lines').get(pk=po.pk), user))
