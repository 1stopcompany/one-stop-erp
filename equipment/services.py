"""
Rules of the tools register: who may do what, and what each step changes.

    request_transfer()   site engineer / project manager (and admin) asks to move a tool
    approve_transfer()   a manager approves (or reject_transfer())
    complete_transfer()  the storekeeper does the handover; the tool's location changes only here
    receive_into_warehouse()  first entry of a tool into a warehouse (opening record)

Everything runs in one database transaction and writes a UserAuditLog line.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Tool, ToolMaintenance, ToolTransfer


# ------------------------------------------------------------------ who may do what
def can_request(user, project=None):
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager() or user.is_storekeeper():
        return True
    if user.is_site_engineer():
        return project is None or project.site_engineer_id == user.pk
    if user.is_project_manager():
        return project is None or project.manager_id == user.pk
    return False


def can_approve(user, transfer):
    if user.is_admin() or user.is_engineering_manager() or user.is_general_manager():
        return True
    # the manager of the project that gives or receives the tool
    if user.is_project_manager():
        return any(p and p.manager_id == user.pk for p in (transfer.to_project, transfer.from_project))
    return False


def can_complete(user):
    return user.is_admin() or user.is_storekeeper()


def can_manage_tools(user):
    """Add / edit tools, open maintenance."""
    return user.is_admin() or user.is_storekeeper() or user.is_engineering_manager()


def _audit(user, tool, text):
    from accounts.models import UserAuditLog
    UserAuditLog.objects.create(user=user, action='update', content_type='equipment.Tool', object_id=tool.pk, description=f'{tool.code}: {text}')


# ------------------------------------------------------------------ opening entry
@transaction.atomic
def receive_into_warehouse(tool, warehouse, user, note='', when=None):
    """First entry of a tool into a warehouse; leaves a completed 'opening' record in its history."""
    when = when or timezone.now()
    tool.warehouse, tool.project = warehouse, None
    tool.save()
    ToolTransfer.objects.create(
        tool=tool, kind=ToolTransfer.KIND_OPENING, status=ToolTransfer.COMPLETED, to_warehouse=warehouse, note=note,
        requested_by=user, requested_at=when, approved_by=user, approved_at=when, completed_by=user, completed_at=when)
    _audit(user, tool, f'received into {warehouse.name}')


# ------------------------------------------------------------------ request -> approve -> complete
@transaction.atomic
def request_transfer(tool, user, to_project=None, to_warehouse=None, holder='', note=''):
    if bool(to_project) == bool(to_warehouse):
        raise ValidationError('Choose either a project or a warehouse as the destination.')
    if tool.status == Tool.STATUS_SCRAPPED:
        raise ValidationError('A scrapped tool cannot be moved.')
    if tool.pending_transfer():
        raise ValidationError('This tool already has an open transfer request.')
    if to_project and tool.status not in Tool.AVAILABLE_STATUSES:
        raise ValidationError(f'{tool.code} is {tool.get_status_display().lower()} and cannot be sent to a project.')
    if (to_project and to_project.pk == tool.project_id) or (to_warehouse and to_warehouse.pk == tool.warehouse_id):
        raise ValidationError('The tool is already there.')
    if not can_request(user, to_project or tool.project):
        raise PermissionDenied('You cannot request this transfer.')
    if tool.project_id and to_warehouse:
        kind = ToolTransfer.KIND_RETURN
    elif tool.warehouse_id and to_project:
        kind = ToolTransfer.KIND_ISSUE
    else:
        kind = ToolTransfer.KIND_TRANSFER
    transfer = ToolTransfer.objects.create(
        tool=tool, kind=kind, from_warehouse=tool.warehouse, from_project=tool.project, to_warehouse=to_warehouse, to_project=to_project,
        holder=holder, note=note, requested_by=user)
    _audit(user, tool, f'transfer requested {transfer.from_label} -> {transfer.to_label}')
    return transfer


@transaction.atomic
def approve_transfer(transfer, user):
    transfer = ToolTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status != ToolTransfer.REQUESTED:
        raise ValidationError('Only a requested transfer can be approved.')
    if not can_approve(user, transfer):
        raise PermissionDenied('You cannot approve this transfer.')
    transfer.status, transfer.approved_by, transfer.approved_at = ToolTransfer.APPROVED, user, timezone.now()
    transfer.save()
    _audit(user, transfer.tool, f'transfer approved {transfer.from_label} -> {transfer.to_label}')
    return transfer


@transaction.atomic
def reject_transfer(transfer, user, reason=''):
    transfer = ToolTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status not in (ToolTransfer.REQUESTED, ToolTransfer.APPROVED):
        raise ValidationError('This transfer is already closed.')
    if not (can_approve(user, transfer) or can_complete(user)):
        raise PermissionDenied('You cannot reject this transfer.')
    transfer.status, transfer.rejection_reason = ToolTransfer.REJECTED, reason[:300]
    transfer.approved_by, transfer.approved_at = user, timezone.now()
    transfer.save()
    _audit(user, transfer.tool, f'transfer rejected: {reason}')
    return transfer


@transaction.atomic
def cancel_transfer(transfer, user):
    transfer = ToolTransfer.objects.select_for_update().get(pk=transfer.pk)
    if transfer.status not in (ToolTransfer.REQUESTED, ToolTransfer.APPROVED):
        raise ValidationError('This transfer is already closed.')
    if not (transfer.requested_by_id == user.pk or user.is_admin()):
        raise PermissionDenied('Only the requester or an admin can cancel it.')
    transfer.status = ToolTransfer.CANCELLED
    transfer.save()
    _audit(user, transfer.tool, 'transfer cancelled')
    return transfer


@transaction.atomic
def complete_transfer(transfer, user, return_condition='', return_note='', holder=None):
    """The storekeeper hands the tool over. Coming back from a project, the condition must be recorded."""
    transfer = ToolTransfer.objects.select_for_update().select_related('tool').get(pk=transfer.pk)
    tool = transfer.tool
    if transfer.status != ToolTransfer.APPROVED:
        raise ValidationError('Only an approved transfer can be completed.')
    if not can_complete(user):
        raise PermissionDenied('Only the storekeeper completes a handover.')
    if tool.project_id != transfer.from_project_id or tool.warehouse_id != transfer.from_warehouse_id:
        raise ValidationError('The tool is no longer where the request said; cancel it and request again.')
    comes_back = transfer.kind == ToolTransfer.KIND_RETURN
    if comes_back and return_condition not in dict(ToolTransfer.CONDITION_CHOICES):
        raise ValidationError('Record the condition of the tool coming back: good, needs maintenance or scrap.')
    tool.warehouse, tool.project = transfer.to_warehouse, transfer.to_project
    tool.holder = holder if holder is not None else (transfer.holder if transfer.to_project_id else '')
    if comes_back:
        transfer.return_condition, transfer.return_note = return_condition, return_note[:300]
        if return_condition == ToolTransfer.CONDITION_MAINTENANCE:
            tool.status = Tool.STATUS_NEEDS_MAINTENANCE
            ToolMaintenance.objects.create(tool=tool, problem=return_note or 'Returned from project needing maintenance', opened_by=user)
        elif return_condition == ToolTransfer.CONDITION_SCRAP:
            tool.status = Tool.STATUS_SCRAPPED
    tool.save()
    transfer.status, transfer.completed_by, transfer.completed_at = ToolTransfer.COMPLETED, user, timezone.now()
    transfer.save()
    _audit(user, tool, f'handover completed {transfer.from_label} -> {transfer.to_label}' + (f' ({transfer.get_return_condition_display()})' if comes_back else ''))
    return transfer


# ------------------------------------------------------------------ maintenance
@transaction.atomic
def open_maintenance(tool, user, problem):
    if tool.status == Tool.STATUS_SCRAPPED:
        raise ValidationError('A scrapped tool cannot be sent for maintenance.')
    if tool.open_maintenance():
        raise ValidationError('This tool already has an open maintenance job.')
    job = ToolMaintenance.objects.create(tool=tool, problem=problem, opened_by=user)
    tool.status = Tool.STATUS_NEEDS_MAINTENANCE
    tool.save(update_fields=['status'])
    _audit(user, tool, f'maintenance opened: {problem}')
    return job


@transaction.atomic
def update_maintenance(job, user, status, vendor='', parts='', cost=None, result_note=''):
    tool = job.tool
    if status not in dict(ToolMaintenance.STATUS_CHOICES):
        raise ValidationError('Unknown status.')
    today = timezone.localdate()
    job.status, job.vendor, job.parts, job.result_note = status, vendor or job.vendor, parts or job.parts, result_note or job.result_note
    if cost is not None:
        job.cost = cost
    if status == ToolMaintenance.IN_PROGRESS:
        job.started_date = job.started_date or today
        tool.status = Tool.STATUS_IN_MAINTENANCE
    elif status == ToolMaintenance.DONE:
        job.finished_date, job.closed_by = today, user
        tool.status = Tool.STATUS_WORKING
    elif status == ToolMaintenance.SCRAPPED:
        job.finished_date, job.closed_by = today, user
        tool.status = Tool.STATUS_SCRAPPED
    elif status == ToolMaintenance.CANCELLED:
        job.closed_by = user
        tool.status = Tool.STATUS_WORKING if tool.status in (Tool.STATUS_NEEDS_MAINTENANCE, Tool.STATUS_IN_MAINTENANCE) else tool.status
    job.save()
    tool.save(update_fields=['status'])
    _audit(user, tool, f'maintenance {job.get_status_display().lower()}')
    return job
