from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from procurement.models import Warehouse
from projects.models import Project

from . import services
from .models import Tool, ToolMaintenance, ToolTransfer


def _error_text(error):
    return '; '.join(error.messages) if isinstance(error, ValidationError) else str(error)


def _run(request, action, *args, **kwargs):
    """Call a service function and turn its refusals into a message instead of a crash page."""
    try:
        return action(*args, **kwargs)
    except (ValidationError, PermissionDenied) as error:
        messages.error(request, _error_text(error) or 'Not allowed.')
    return None


def _usable_projects(user):
    projects = Project.objects.exclude(status__in=('completed', 'archived')).order_by('project_symbol')
    if user.is_site_engineer():
        projects = projects.filter(site_engineer=user)
    elif user.is_project_manager():
        projects = projects.filter(manager=user)
    return projects


def _claims_waiting(user):
    """How many rental claims of the user's projects still wait for the engineer's review."""
    from .views_claims import _visible
    from .models import EquipmentClaim
    return _visible(user).filter(status=EquipmentClaim.POSTED, reviewed_at__isnull=True).count()


# ------------------------------------------------------------------ dashboard
@login_required
def equipment_dashboard(request):
    user = request.user
    waiting_approval = ToolTransfer.objects.filter(status=ToolTransfer.REQUESTED).select_related('tool', 'to_project', 'to_warehouse', 'from_project', 'from_warehouse', 'requested_by')
    waiting_handover = ToolTransfer.objects.filter(status=ToolTransfer.APPROVED).select_related('tool', 'to_project', 'to_warehouse', 'from_project', 'from_warehouse', 'requested_by')
    context = {
        'claims_waiting': _claims_waiting(user),
        'tool_count': Tool.objects.exclude(status=Tool.STATUS_SCRAPPED).filter(kind=Tool.KIND_TOOL).count(),
        'heavy_count': Tool.objects.exclude(status=Tool.STATUS_SCRAPPED).filter(kind=Tool.KIND_HEAVY).count(),
        'by_status': {row['status']: row['n'] for row in Tool.objects.values('status').annotate(n=Count('id'))},
        'by_place': (Tool.objects.exclude(status=Tool.STATUS_SCRAPPED).values('project__project_symbol', 'warehouse__name').annotate(n=Count('id')).order_by('-n')),
        'waiting_approval': [t for t in waiting_approval if services.can_approve(user, t)],
        'waiting_approval_all': waiting_approval.count(),
        'waiting_handover': waiting_handover if services.can_complete(user) else [],
        'waiting_handover_all': waiting_handover.count(),
        'open_jobs': ToolMaintenance.objects.filter(status__in=(ToolMaintenance.OPEN, ToolMaintenance.IN_PROGRESS)).select_related('tool'),
        'can_manage': services.can_manage_tools(user),
    }
    return render(request, 'equipment/dashboard.html', context)


# ------------------------------------------------------------------ tools
def _filtered_tools(request):
    """The register as filtered by ?q= ?status= ?place= (shared by the list page and the printed catalogue)."""
    tools = Tool.objects.select_related('warehouse', 'project')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    place = request.GET.get('place', '')
    kind = request.GET.get('kind', '')
    if kind in dict(Tool.KIND_CHOICES):
        tools = tools.filter(kind=kind)
    if q:
        tools = tools.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(manufacturer__icontains=q) | Q(serial_no__icontains=q) | Q(category__icontains=q))
    if status:
        tools = tools.filter(status=status)
    if place.startswith('p'):
        tools = tools.filter(project_id=place[1:])
    elif place.startswith('w'):
        tools = tools.filter(warehouse_id=place[1:])
    elif not status:
        tools = tools.exclude(status=Tool.STATUS_SCRAPPED)
    return tools, q, status, place


@login_required
def tool_list(request):
    tools, q, status, place = _filtered_tools(request)
    return render(request, 'equipment/tool_list.html', {
        'tools': tools, 'q': q, 'status': status, 'place': place, 'statuses': Tool.STATUS_CHOICES, 'kind': request.GET.get('kind', ''), 'kinds': Tool.KIND_CHOICES,
        'places': [(f'w{w.pk}', w.name) for w in Warehouse.objects.filter(is_active=True)]
                  + [(f'p{p.pk}', f'Project {p.project_symbol}') for p in Project.objects.filter(tools__isnull=False).distinct().order_by('project_symbol')],
        'can_manage': services.can_manage_tools(request.user),
    })


def _tool_from_post(request, tool=None):
    post = request.POST
    tool = tool or Tool()
    tool.name = post.get('name', '').strip()
    if not tool.name:
        raise ValidationError('The tool name is required.')
    tool.category, tool.manufacturer = post.get('category', '').strip(), post.get('manufacturer', '').strip()
    tool.model_no, tool.serial_no = post.get('model_no', '').strip(), post.get('serial_no', '').strip()
    if post.get('kind') in dict(Tool.KIND_CHOICES) and not tool.pk:
        tool.kind = post['kind']   # the kind is fixed when the record is created
    if tool.kind == Tool.KIND_HEAVY:
        tool.plate_no, tool.operator = post.get('plate_no', '').strip(), post.get('operator', '').strip()
        tool.ownership = post.get('ownership') if post.get('ownership') in dict(Tool.OWNERSHIP_CHOICES) else Tool.OWNED
        from procurement.models import Vendor
        tool.rental_vendor = Vendor.objects.filter(pk=post.get('rental_vendor')).first() if tool.ownership == Tool.RENTED and post.get('rental_vendor') else None
        tool.rental_rate_unit = post.get('rental_rate_unit') if post.get('rental_rate_unit') in dict(Tool.RATE_UNIT_CHOICES) else 'day'
        try:
            tool.rental_rate = Decimal(post['rental_rate']) if post.get('rental_rate') and tool.ownership == Tool.RENTED else None
            tool.hour_meter = Decimal(post['hour_meter']) if post.get('hour_meter') else Decimal('0')
        except InvalidOperation:
            raise ValidationError('The rental rate / hour meter is not a number.')
    tool.notes = post.get('notes', '').strip()
    tool.purchase_date = post.get('purchase_date') or None
    try:
        tool.purchase_cost = Decimal(post['purchase_cost']) if post.get('purchase_cost') else None
    except InvalidOperation:
        raise ValidationError('The purchase cost is not a number.')
    if post.get('status') in dict(Tool.STATUS_CHOICES):
        tool.status = post['status']
    if request.FILES.get('photo'):
        tool.photo = request.FILES['photo']
    return tool


FORM_FIELDS = ('name', 'category', 'manufacturer', 'model_no', 'serial_no', 'purchase_date', 'purchase_cost', 'status', 'notes', 'kind', 'plate_no',
               'operator', 'ownership', 'rental_vendor', 'rental_rate', 'rental_rate_unit', 'hour_meter')


def _form_values(request, tool):
    """What the form fields show: what was just posted (after an error), else the tool's own values, else blanks."""
    if request.method == 'POST':
        return {name: request.POST.get(name, '') for name in FORM_FIELDS}
    values = {name: ('' if getattr(tool, name, None) is None else getattr(tool, name)) for name in FORM_FIELDS} if tool else {name: '' for name in FORM_FIELDS}
    values['status'] = values['status'] or Tool.STATUS_WORKING
    values['kind'] = values['kind'] or Tool.KIND_TOOL
    values['ownership'] = values['ownership'] or Tool.OWNED
    values['rental_rate_unit'] = values['rental_rate_unit'] or 'day'
    values['rental_vendor'] = request.POST.get('rental_vendor', '') if request.method == 'POST' else (tool.rental_vendor_id or '' if tool else '')
    return values


def _vendors():
    from procurement.models import Vendor
    return Vendor.objects.filter(is_active=True).order_by('name')


@login_required
def tool_add(request):
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    warehouses = Warehouse.objects.filter(is_active=True)
    if request.method == 'POST':
        try:
            tool = _tool_from_post(request)
            location = request.POST.get('location') or f"w{request.POST.get('warehouse', '')}"
            warehouse = project = None
            if location.startswith('p'):
                project = get_object_or_404(Project, pk=location[1:])
            else:
                warehouse = get_object_or_404(Warehouse, pk=location[1:], is_active=True)
            if project and tool.kind != Tool.KIND_HEAVY:
                raise ValidationError('A tool is received into a warehouse first; only heavy equipment can be registered straight on a project.')
            tool.save()
            services.receive_at(tool, request.user, warehouse=warehouse, project=project, note=request.POST.get('receive_note', '').strip())
            messages.success(request, f'{tool.code} was added and received {"into " + warehouse.name if warehouse else "on project " + project.project_symbol}.')
            return redirect('equipment:tool_detail', pk=tool.pk)
        except ValidationError as error:
            messages.error(request, _error_text(error))
    return render(request, 'equipment/tool_form.html', {'tool': None, 'warehouses': warehouses, 'statuses': Tool.STATUS_CHOICES, 'f': _form_values(request, None),
                                                         'projects': Project.objects.exclude(status__in=('completed', 'archived')).order_by('project_symbol'), 'kinds': Tool.KIND_CHOICES,
                                                         'ownerships': Tool.OWNERSHIP_CHOICES, 'rate_units': Tool.RATE_UNIT_CHOICES, 'vendors': _vendors()})


@login_required
def tool_edit(request, pk):
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    tool = get_object_or_404(Tool, pk=pk)
    if request.method == 'POST':
        try:
            _tool_from_post(request, tool).save()
            messages.success(request, f'{tool.code} was updated.')
            return redirect('equipment:tool_detail', pk=tool.pk)
        except ValidationError as error:
            messages.error(request, _error_text(error))
    return render(request, 'equipment/tool_form.html', {'tool': tool, 'statuses': Tool.STATUS_CHOICES, 'f': _form_values(request, tool), 'kinds': Tool.KIND_CHOICES,
                                                         'ownerships': Tool.OWNERSHIP_CHOICES, 'rate_units': Tool.RATE_UNIT_CHOICES, 'vendors': _vendors()})


@login_required
def tool_detail(request, pk):
    tool = get_object_or_404(Tool.objects.select_related('warehouse', 'project'), pk=pk)
    user = request.user
    pending = tool.pending_transfer()
    return render(request, 'equipment/tool_detail.html', {
        'tool': tool, 'pending': pending, 'open_job': tool.open_maintenance(),
        'history': tool.transfers.exclude(status__in=(ToolTransfer.CANCELLED,)).select_related('from_project', 'from_warehouse', 'to_project', 'to_warehouse', 'requested_by', 'approved_by', 'completed_by'),
        'jobs': tool.maintenance_jobs.all(),
        'usage': tool.daily_usage.select_related('report', 'report__project', 'activity').order_by('-report__report_date')[:60],
        'usage_hours': sum(u.hours_worked for u in tool.daily_usage.all()),
        'projects': _usable_projects(user), 'warehouses': Warehouse.objects.filter(is_active=True),
        'can_request': services.can_request(user) and tool.status != Tool.STATUS_SCRAPPED and not pending,
        'can_manage': services.can_manage_tools(user), 'can_approve': bool(pending) and services.can_approve(user, pending),
        'can_complete': services.can_complete(user),
    })


@login_required
def tool_by_code(request, code):
    return redirect('equipment:tool_detail', pk=get_object_or_404(Tool, code__iexact=code).pk)


# ------------------------------------------------------------------ transfers
@login_required
@require_POST
def transfer_request(request, pk):
    tool = get_object_or_404(Tool, pk=pk)
    destination = request.POST.get('destination', '')
    to_project = Project.objects.filter(pk=destination[1:]).first() if destination.startswith('p') else None
    to_warehouse = Warehouse.objects.filter(pk=destination[1:], is_active=True).first() if destination.startswith('w') else None
    if not (to_project or to_warehouse):
        messages.error(request, 'Choose where the tool should go.')
    elif to_project and to_project not in _usable_projects(request.user):
        messages.error(request, 'You cannot request tools for this project.')
    else:
        transfer = _run(request, services.request_transfer, tool, request.user, to_project=to_project, to_warehouse=to_warehouse,
                        holder=request.POST.get('holder', '').strip(), note=request.POST.get('note', '').strip())
        if transfer:
            messages.success(request, f'Request sent: {tool.code} {transfer.from_label} -> {transfer.to_label}. It waits for a manager to approve it.')
    return redirect('equipment:tool_detail', pk=tool.pk)


@login_required
@require_POST
def transfer_action(request, pk, action):
    transfer = get_object_or_404(ToolTransfer.objects.select_related('tool'), pk=pk)
    post = request.POST
    if action == 'approve':
        done = _run(request, services.approve_transfer, transfer, request.user)
        if done:
            messages.success(request, 'Approved: the storekeeper can now complete the handover.')
    elif action == 'reject':
        done = _run(request, services.reject_transfer, transfer, request.user, post.get('reason', '').strip())
        if done:
            messages.warning(request, 'The request was rejected.')
    elif action == 'cancel':
        done = _run(request, services.cancel_transfer, transfer, request.user)
        if done:
            messages.info(request, 'The request was cancelled.')
    elif action == 'complete':
        done = _run(request, services.complete_transfer, transfer, request.user, return_condition=post.get('return_condition', ''),
                    return_note=post.get('return_note', '').strip(), holder=post.get('holder'), photo=request.FILES.get('photo'))
        if done:
            messages.success(request, f'Handover completed: {transfer.tool.code} is now at {done.to_label}.')
    else:
        raise PermissionDenied
    return redirect(request.POST.get('next') or reverse('equipment:tool_detail', args=[transfer.tool_id]))


@login_required
def transfer_list(request):
    transfers = ToolTransfer.objects.exclude(kind=ToolTransfer.KIND_OPENING).select_related('tool', 'from_project', 'from_warehouse', 'to_project', 'to_warehouse', 'requested_by', 'completed_by')
    status = request.GET.get('status', '')
    if status:
        transfers = transfers.filter(status=status)
    return render(request, 'equipment/transfer_list.html', {
        'transfers': transfers[:300], 'status': status, 'statuses': ToolTransfer.STATUS_CHOICES, 'can_complete': services.can_complete(request.user),
        'conditions': ToolTransfer.CONDITION_CHOICES,
    })


# ------------------------------------------------------------------ maintenance
@login_required
@require_POST
def maintenance_open(request, pk):
    tool = get_object_or_404(Tool, pk=pk)
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    problem = request.POST.get('problem', '').strip()
    if not problem:
        messages.error(request, 'Describe the problem.')
    elif _run(request, services.open_maintenance, tool, request.user, problem):
        messages.success(request, f'Maintenance job opened for {tool.code}.')
    return redirect('equipment:tool_detail', pk=tool.pk)


@login_required
@require_POST
def maintenance_update(request, pk):
    job = get_object_or_404(ToolMaintenance.objects.select_related('tool'), pk=pk)
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    post = request.POST
    try:
        cost = Decimal(post['cost']) if post.get('cost') else None
    except InvalidOperation:
        messages.error(request, 'The cost is not a number.')
        return redirect('equipment:tool_detail', pk=job.tool_id)
    if _run(request, services.update_maintenance, job, request.user, post.get('status', ''), vendor=post.get('vendor', '').strip(),
            parts=post.get('parts', '').strip(), cost=cost, result_note=post.get('result_note', '').strip()):
        messages.success(request, 'Maintenance job updated.')
    return redirect('equipment:tool_detail', pk=job.tool_id)


# ------------------------------------------------------------------ printed catalogue
@login_required
def catalog_pdf(request):
    """Every tool of the current filter, one row each: photo, QR + code, name, maker, condition, location."""
    tools, q, status, place = _filtered_tools(request)
    from .catalog_pdf import build_catalog_pdf
    parts = []
    if place.startswith('w'):
        warehouse = Warehouse.objects.filter(pk=place[1:]).first()
        parts.append(warehouse.name if warehouse else '')
    elif place.startswith('p'):
        project = Project.objects.filter(pk=place[1:]).first()
        parts.append(f'Project {project.project_symbol}' if project else '')
    if status:
        parts.append(dict(Tool.STATUS_CHOICES).get(status, ''))
    if q:
        parts.append(f'"{q}"')
    pdf = build_catalog_pdf(tools.order_by('code'), lambda tool: request.build_absolute_uri(reverse('equipment:tool_by_code', args=[tool.code])),
                            subtitle=' / '.join(p for p in parts if p))
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="tools-catalog.pdf"'
    return response


@login_required
@require_POST
def tool_photo(request, pk):
    """Replace the tool's current photo (outside a handover; the handover photos are kept in the history)."""
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    tool = get_object_or_404(Tool, pk=pk)
    photo = request.FILES.get('photo')
    if not photo:
        messages.error(request, 'Choose a photo.')
    else:
        try:
            services.check_photo(photo)
            tool.photo = photo
            tool.save(update_fields=['photo'])
            messages.success(request, f'The photo of {tool.code} was updated.')
        except ValidationError as error:
            messages.error(request, _error_text(error))
    return redirect('equipment:tool_detail', pk=tool.pk)


@login_required
def tool_sheet_pdf(request, pk):
    """Record sheet of one tool: details, current photo, its movement path with the handover photos, maintenance history."""
    tool = get_object_or_404(Tool.objects.select_related('warehouse', 'project'), pk=pk)
    from .tool_sheet_pdf import build_tool_sheet_pdf
    pdf = build_tool_sheet_pdf(tool, request.build_absolute_uri(reverse('equipment:tool_by_code', args=[tool.code])))
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{tool.code}-record.pdf"'
    return response


# ------------------------------------------------------------------ labels
@login_required
def labels_pdf(request):
    """?ids=1,2,3 for chosen tools; without ids, every tool that matches the list filters (q / status / place)."""
    if not services.can_manage_tools(request.user):
        raise PermissionDenied
    ids = [int(i) for i in request.GET.get('ids', '').split(',') if i.strip().isdigit()]
    tools = Tool.objects.exclude(status=Tool.STATUS_SCRAPPED)
    if ids:
        tools = tools.filter(pk__in=ids)
    elif request.GET.get('place', '').startswith('p'):
        tools = tools.filter(project_id=request.GET['place'][1:])
    elif request.GET.get('place', '').startswith('w'):
        tools = tools.filter(warehouse_id=request.GET['place'][1:])
    from .labels import build_labels_pdf
    pdf = build_labels_pdf(list(tools.order_by('code')), lambda tool: request.build_absolute_uri(reverse('equipment:tool_by_code', args=[tool.code])))
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="tool-labels.pdf"'
    return response
