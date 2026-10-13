"""
Mobile API of the tools / heavy-equipment register (token authentication, like the rest of the mobile API): scan the QR label of a tool,
see where it is and what is pending on it, request a handover, approve it, and let the storekeeper complete it with a photo taken on the spot.

    GET  /equipment/api/mobile/tools/?q=                    search by code, name, maker, serial no
    GET  /equipment/api/mobile/tools/by-code/<code>/        one tool (what a QR scan opens)
    GET  /equipment/api/mobile/tools/<id>/
    GET  /equipment/api/mobile/destinations/                projects + warehouses this user may send a tool to
    POST /equipment/api/mobile/tools/<id>/request/          {destination: "p<project id>" | "w<warehouse id>", holder, note}
    GET  /equipment/api/mobile/transfers/?scope=handover|approve|mine
    POST /equipment/api/mobile/transfers/<id>/approve/
    POST /equipment/api/mobile/transfers/<id>/reject/       {reason}
    POST /equipment/api/mobile/transfers/<id>/cancel/
    POST /equipment/api/mobile/transfers/<id>/complete/     multipart: photo (required), return_condition, return_note, holder

The rules are the web ones (equipment.services): the phone is only another way to do the same steps.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view
from rest_framework.response import Response

from procurement.models import Warehouse

from . import services
from .models import Tool, ToolTransfer
from .views import _usable_projects

TRANSFER_RELATED = ('tool', 'from_project', 'from_warehouse', 'to_project', 'to_warehouse', 'requested_by', 'completed_by')


def _error(message, status=400):
    return Response({'detail': message}, status=status)


def _refusal(error):
    if isinstance(error, PermissionDenied):
        return _error(str(error) or 'Not allowed.', 403)
    return _error('; '.join(error.messages) if isinstance(error, ValidationError) else str(error))


def _allowed(user):
    return 'equipment' in user.mobile_tabs()


def _person(user):
    return (user.get_full_name() or user.username) if user else ''


def _photo(request, field):
    return request.build_absolute_uri(field.url) if field else None


def _transfer_data(request, transfer):
    user = request.user
    open_ = transfer.status in (ToolTransfer.REQUESTED, ToolTransfer.APPROVED)
    return {
        'id': transfer.id, 'status': transfer.status, 'status_label': transfer.get_status_display(),
        'kind': transfer.kind, 'kind_label': transfer.get_kind_display(),
        'tool': {'id': transfer.tool_id, 'code': transfer.tool.code, 'name': transfer.tool.name, 'photo': _photo(request, transfer.tool.photo)},
        'from': transfer.from_label, 'to': transfer.to_label, 'holder': transfer.holder, 'note': transfer.note,
        'requested_by': _person(transfer.requested_by), 'requested_at': transfer.requested_at.isoformat(),
        'completed_at': transfer.completed_at.isoformat() if transfer.completed_at else None,
        'rejection_reason': transfer.rejection_reason, 'photo': _photo(request, transfer.photo),
        'return_condition': transfer.return_condition, 'return_condition_label': transfer.get_return_condition_display() if transfer.return_condition else '',
        'needs_condition': transfer.kind == ToolTransfer.KIND_RETURN,
        'can_approve': transfer.status == ToolTransfer.REQUESTED and services.can_approve(user, transfer),
        'can_complete': transfer.status == ToolTransfer.APPROVED and services.can_complete(user),
        'can_cancel': open_ and (transfer.requested_by_id == user.pk or user.is_admin()),
    }


def _tool_data(request, tool):
    user = request.user
    pending = tool.pending_transfer()
    history = tool.transfers.filter(status=ToolTransfer.COMPLETED).select_related(*TRANSFER_RELATED)[:6]
    return {
        'id': tool.id, 'code': tool.code, 'name': tool.name, 'kind': tool.kind, 'kind_label': tool.get_kind_display(),
        'category': tool.category, 'manufacturer': tool.manufacturer, 'model_no': tool.model_no, 'serial_no': tool.serial_no,
        'plate_no': tool.plate_no, 'operator': tool.operator, 'status': tool.status, 'status_label': tool.get_status_display(),
        'location': tool.location_label, 'holder': tool.holder, 'photo': _photo(request, tool.photo),
        'in_maintenance': bool(tool.open_maintenance()),
        'pending': _transfer_data(request, pending) if pending else None,
        'can_request': services.can_request(user) and tool.status != Tool.STATUS_SCRAPPED and not pending,
        'history': [_transfer_data(request, t) for t in history],
    }


def _tool_summary(request, tool):
    return {'id': tool.id, 'code': tool.code, 'name': tool.name, 'kind': tool.kind, 'status': tool.status, 'status_label': tool.get_status_display(),
            'location': tool.location_label, 'photo': _photo(request, tool.photo)}


# ------------------------------------------------------------------ tools
@api_view(['GET'])
def mobile_tools(request):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    q = (request.GET.get('q') or '').strip()
    tools = Tool.objects.exclude(status=Tool.STATUS_SCRAPPED).select_related('warehouse', 'project')
    if q:
        tools = tools.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q) | Q(serial_no__icontains=q) | Q(plate_no__icontains=q))
    return Response([_tool_summary(request, t) for t in tools.order_by('code')[:25]])


@api_view(['GET'])
def mobile_tool_by_code(request, code):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    tool = Tool.objects.select_related('warehouse', 'project').filter(code__iexact=code.strip()).first()
    if not tool:
        return _error(f'No tool has the code {code}.', 404)
    return Response(_tool_data(request, tool))


@api_view(['GET'])
def mobile_tool_detail(request, pk):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    return Response(_tool_data(request, get_object_or_404(Tool.objects.select_related('warehouse', 'project'), pk=pk)))


@api_view(['GET'])
def mobile_destinations(request):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    return Response({
        'projects': [{'key': f'p{p.pk}', 'label': f'{p.project_symbol} - {p.name}'} for p in _usable_projects(request.user)],
        'warehouses': [{'key': f'w{w.pk}', 'label': w.name} for w in Warehouse.objects.filter(is_active=True).order_by('name')],
    })


@api_view(['POST'])
def mobile_tool_request(request, pk):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    tool = get_object_or_404(Tool, pk=pk)
    destination = str(request.data.get('destination', ''))
    to_project = to_warehouse = None
    if destination.startswith('p'):
        to_project = _usable_projects(request.user).filter(pk=destination[1:] or 0).first()
        if not to_project:
            return _error('You cannot request tools for this project.', 403)
    elif destination.startswith('w'):
        to_warehouse = Warehouse.objects.filter(pk=destination[1:] or 0, is_active=True).first()
    if not (to_project or to_warehouse):
        return _error('Choose where the tool should go.')
    try:
        transfer = services.request_transfer(tool, request.user, to_project=to_project, to_warehouse=to_warehouse,
                                             holder=str(request.data.get('holder', '')).strip()[:100], note=str(request.data.get('note', '')).strip())
    except (ValidationError, PermissionDenied) as error:
        return _refusal(error)
    transfer = ToolTransfer.objects.select_related(*TRANSFER_RELATED).get(pk=transfer.pk)
    return Response(_transfer_data(request, transfer), status=201)


# ------------------------------------------------------------------ transfers
@api_view(['GET'])
def mobile_transfers(request):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    user, scope = request.user, request.GET.get('scope', 'mine')
    transfers = ToolTransfer.objects.exclude(kind=ToolTransfer.KIND_OPENING).select_related(*TRANSFER_RELATED)
    if scope == 'handover':
        rows = list(transfers.filter(status=ToolTransfer.APPROVED)) if services.can_complete(user) else []
    elif scope == 'approve':
        rows = [t for t in transfers.filter(status=ToolTransfer.REQUESTED) if services.can_approve(user, t)]
    else:
        rows = list(transfers.filter(requested_by=user)[:30])
    return Response([_transfer_data(request, t) for t in rows])


@api_view(['POST'])
def mobile_transfer_action(request, pk, action):
    if not _allowed(request.user):
        return _error('Not allowed.', 403)
    transfer = get_object_or_404(ToolTransfer, pk=pk)
    user, data = request.user, request.data
    try:
        if action == 'approve':
            services.approve_transfer(transfer, user)
        elif action == 'reject':
            services.reject_transfer(transfer, user, str(data.get('reason', '')).strip())
        elif action == 'cancel':
            services.cancel_transfer(transfer, user)
        elif action == 'complete':
            holder = data.get('holder')
            services.complete_transfer(transfer, user, return_condition=str(data.get('return_condition', '')), return_note=str(data.get('return_note', '')).strip(),
                                       holder=str(holder).strip()[:100] if holder is not None else None, photo=request.FILES.get('photo'))
        else:
            return _error('Unknown action.', 404)
    except (ValidationError, PermissionDenied) as error:
        return _refusal(error)
    return Response(_transfer_data(request, ToolTransfer.objects.select_related(*TRANSFER_RELATED).get(pk=transfer.pk)))
