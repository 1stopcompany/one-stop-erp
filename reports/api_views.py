"""
API Views for Daily Report AJAX Operations

These views handle AJAX requests for adding and deleting report items.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from datetime import datetime
from decimal import Decimal
from .models import (
    DailyReport, DailyEquipment,
    DailyMaterial, DailyVisitor, ReportAttachment,
    MonthlyReport, FloorActivity, ExternalWork, MaterialSupply, UpcomingWork,
    DailyReportWorkerAttendance, DailyReportCrew, DailyReportActivityProgress, DailyReportQAQC, DailyReportNextDayPlan,
    MonthlyProgressCategoryItem, MonthlyKeyActivity, MonthlyIssueRiskDelay, MonthlyReviewComment,
)
from .master_data_models import EquipmentMaster
from .site_event_models import SiteEvent
from .owner_financial_models import OwnerFinancialReport, OwnerReportPriceComparisonItem, OwnerReportPhaseUpdate
from .progress_models import ProjectPhase, ProjectPhaseSubItem, ProjectPhaseProgressEntry, ProjectMilestone, ProjectPhasePhoto
from projects.models import Project
import json


def _can_edit_daily_report(user, report) -> bool:
    """
    Daily reports are the site engineer's own (see the roles agreed for
    this app: only the site engineer creates/edits Daily reports, not the
    project manager) -- admins bypass this, like every other permission
    check in this module.
    """
    return user.is_admin() or report.site_engineer_id == user.id


# Canonical keys for the Daily Report detail page's section accordion, matching each section's
# `heading-<key>`/`collapse-<key>` ids in the template. Used to validate a saved section order.
DAILY_REPORT_SECTION_KEYS = {
    'activity-progress', 'worker-attendance', 'equipment', 'materials',
    'visitors', 'attachments', 'qaqc', 'site-events', 'next-day-plan',
}


@login_required
@require_http_methods(["POST"])
def save_daily_report_section_order(request):
    """
    Save this user's own preferred section order for the Daily Report page (its move-up/move-down
    controls), so it applies the same way to every Daily Report they open -- not tied to one
    report. An empty/missing `order` resets to the page's own default order.
    """
    try:
        raw = request.POST.get('order', '')
        keys = [k for k in raw.split(',') if k]
        if keys:
            if set(keys) - DAILY_REPORT_SECTION_KEYS:
                return JsonResponse({'success': False, 'message': 'Unknown section in order.'}, status=400)
            request.user.daily_report_section_order = keys
        else:
            request.user.daily_report_section_order = None
        request.user.save(update_fields=['daily_report_section_order'])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_equipment(request, report_id):
    """Add equipment to daily report -- chosen from the equipment list and linked to one of this
    report's own logged activities, both required so equipment usage stays tied to real master data
    and to a specific piece of work rather than a free-text name floating on its own."""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)

        data = request.POST
        if not data.get('equipment_master'):
            return JsonResponse({'success': False, 'message': 'Equipment (from the list) is required.'}, status=400)
        if not data.get('activity'):
            return JsonResponse({'success': False, 'message': 'The activity this equipment was used for is required.'}, status=400)
        equipment_master = get_object_or_404(EquipmentMaster, pk=data.get('equipment_master'), is_active=True)
        activity = get_object_or_404(DailyReportActivityProgress, pk=data.get('activity'), report=report)

        equipment = DailyEquipment.objects.create(
            report=report,
            equipment_master=equipment_master,
            activity=activity,
            hours_worked=float(data.get('hours_worked', 0)),
            quantity_idle=int(data.get('quantity_idle', 0))
        )

        return JsonResponse({
            'success': True,
            'message': 'Equipment added successfully',
            'id': equipment.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_equipment(request, report_id, equipment_id):
    """Delete equipment from daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        equipment = get_object_or_404(DailyEquipment, pk=equipment_id, report=report)
        equipment.delete()
        
        return JsonResponse({'success': True, 'message': 'Equipment deleted'})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_material(request, report_id):
    """Add material to daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        
        data = request.POST
        material = DailyMaterial.objects.create(
            report=report,
            material_description=data.get('material_description'),
            quantity=float(data.get('quantity', 0)),
            unit=data.get('unit')
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Material added successfully',
            'id': material.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_material(request, report_id, material_id):
    """Delete material from daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        material = get_object_or_404(DailyMaterial, pk=material_id, report=report)
        material.delete()
        
        return JsonResponse({'success': True, 'message': 'Material deleted'})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_visitor(request, report_id):
    """Add visitor to daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        
        data = request.POST
        visitor = DailyVisitor.objects.create(
            report=report,
            visitor_name=data.get('visitor_name'),
            representing=data.get('representing', ''),
            visit_time=data.get('visit_time') or timezone.localtime().time(),
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Visitor added successfully',
            'id': visitor.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_visitor(request, report_id, visitor_id):
    """Delete visitor from daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        visitor = get_object_or_404(DailyVisitor, pk=visitor_id, report=report)
        visitor.delete()
        
        return JsonResponse({'success': True, 'message': 'Visitor deleted'})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_attachment(request, report_id):
    """Add attachment to daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        
        attachment = ReportAttachment.objects.create(
            report_type='daily',
            report_id=report.id,
            file=request.FILES.get('file'),
            description=request.POST.get('caption', ''),
            location=request.POST.get('location', ''),
            attachment_type=request.POST.get('attachment_type', 'photo'),
            uploaded_by=request.user,
        )
        
        return JsonResponse({
            'success': True,
            'message': 'Attachment added successfully',
            'id': attachment.id
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_attachment(request, report_id, attachment_id):
    """Delete attachment from daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        attachment = get_object_or_404(ReportAttachment, pk=attachment_id, report_type='daily', report_id=report.id)
        attachment.delete()

        return JsonResponse({'success': True, 'message': 'Attachment deleted'})
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


@login_required
@require_http_methods(["POST"])
def edit_daily_attachment(request, report_id, attachment_id):
    """
    Edit an existing daily report attachment's caption/location/type, and
    optionally replace its file. POST (not PATCH) is deliberate: Django
    only parses a multipart body into request.POST/request.FILES for
    method == 'POST' -- for PATCH/PUT it leaves both empty regardless of
    content type, so a multipart PATCH would silently see no fields and
    no file at all.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        attachment = get_object_or_404(ReportAttachment, pk=attachment_id, report_type='daily', report_id=report.id)

        if 'caption' in request.POST:
            attachment.description = request.POST.get('caption', '').strip()
        if 'location' in request.POST:
            attachment.location = request.POST.get('location', '').strip()
        if request.POST.get('attachment_type'):
            attachment.attachment_type = request.POST['attachment_type']
        if request.FILES.get('file'):
            attachment.file = request.FILES['file']
        attachment.save()

        return JsonResponse({
            'success': True,
            'message': 'Attachment updated successfully',
            'id': attachment.id,
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)


# ==================== WORKER ATTENDANCE (named workers, Section 2) ====================

@login_required
@require_http_methods(["POST"])
def add_labor_classification(request):
    """
    Add a trade to the master list (reports.LaborClassification) from the Daily Report page's worker form, so a missing trade
    does not block the attendance entry. Anyone who can edit daily reports may add one; it is listed for everybody from then on.
    """
    from .master_data_models import LaborClassification, WorkforceCategory
    name = ' '.join(request.POST.get('name', '').split())
    if not name:
        return JsonResponse({'success': False, 'message': 'The trade name is required.'}, status=400)
    category = WorkforceCategory.objects.filter(pk=request.POST.get('category') or None, is_active=True).first()
    if category is None:
        return JsonResponse({'success': False, 'message': 'Pick the category of this trade.'}, status=400)
    trade, created = LaborClassification.objects.get_or_create(category=category, name=name, defaults={'is_active': True})
    if not trade.is_active:
        trade.is_active = True
        trade.save(update_fields=['is_active'])
    return JsonResponse({'success': True, 'created': created, 'id': trade.id, 'label': f'{category.name} - {trade.name}'})


@login_required
@require_http_methods(["POST"])
def add_equipment_master(request):
    """
    Add a piece of equipment to the shared equipment list from inside a Daily Report ("+ Add New Equipment" on the Add Equipment
    window), so the engineer is never stuck when the machine is not listed yet. The list is company-wide; a name that is already there
    (any capitals) is reused instead of duplicated, and an old inactive one is switched back on.
    """
    name = " ".join((request.POST.get('name') or '').split())
    if not name:
        return JsonResponse({'success': False, 'message': 'Equipment name is required.'}, status=400)
    existing = EquipmentMaster.objects.filter(name__iexact=name).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.save(update_fields=['is_active'])
        return JsonResponse({'success': True, 'created': False, 'id': existing.id, 'name': existing.name})
    equipment = EquipmentMaster.objects.create(
        name=name[:150], category=(request.POST.get('category') or '').strip()[:100],
        manufacturer=(request.POST.get('manufacturer') or '').strip()[:100], model=(request.POST.get('model') or '').strip()[:100],
        is_active=True,
    )
    return JsonResponse({'success': True, 'created': True, 'id': equipment.id, 'name': equipment.name})


@login_required
@require_http_methods(["POST"])
def add_daily_worker(request):
    """
    Add a new day laborer to the shared roster (timesheets.DailyWorker) from inside the Daily
    Report page's "Add Worker Attendance" flow, so a name that isn't in the history list yet
    doesn't have to be typed as free text -- it's captured properly (with their ID document) and
    immediately selectable, here and on every future report. Not report-scoped: this roster is
    shared company-wide, the same one timesheets:daily_worker_list manages.
    """
    from timesheets.models import DailyWorker
    try:
        data = request.POST
        full_name = data.get('full_name', '').strip()
        if not full_name:
            return JsonResponse({'success': False, 'message': 'Worker name is required.'}, status=400)
        if not data.get('daily_rate'):
            return JsonResponse({'success': False, 'message': 'Daily rate is required.'}, status=400)
        if not request.FILES.get('id_document'):
            return JsonResponse({'success': False, 'message': 'An ID/identity document upload is required to add a new worker.'}, status=400)

        national_id = data.get('national_id', '').strip() or None
        if national_id and DailyWorker.objects.filter(national_id=national_id).exists():
            return JsonResponse({'success': False, 'message': 'A worker with this national ID is already on the roster.'}, status=400)

        worker = DailyWorker.objects.create(
            full_name=full_name,
            national_id=national_id,
            trade=data.get('trade', ''),
            daily_rate=Decimal(data.get('daily_rate')),
            id_document=request.FILES.get('id_document'),
        )
        return JsonResponse({
            'success': True,
            'message': 'Worker added to the roster',
            'id': worker.id,
            'full_name': worker.full_name,
            'trade': worker.trade,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_crew(request, report_id):
    """
    Add a named crew to this daily report -- a group of workers executing one activity, under
    one subcontractor agreement (or a plain in-house contractor name) -- so a project with
    several crews working the same day can group worker attendance under the right one instead
    of repeating the same activity/contractor on every individual worker row.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'success': False, 'message': 'Crew name is required.'}, status=400)

        activity_id = data.get('activity') or None
        if activity_id:
            get_object_or_404(DailyReportActivityProgress, pk=activity_id, report=report)

        agreement_id = data.get('agreement') or None
        if agreement_id:
            from subcontractors.models import SubcontractorAgreement
            get_object_or_404(SubcontractorAgreement, pk=agreement_id, project=report.project)

        crew = DailyReportCrew.objects.create(
            report=report,
            name=name,
            activity_id=activity_id,
            agreement_id=agreement_id,
            contractor_name=data.get('contractor_name', ''),
        )
        return JsonResponse({
            'success': True,
            'message': 'Crew added',
            'id': crew.id,
            'name': crew.name,
            'contractor_name': crew.contractor_name,
            'activity_description': crew.activity.activity_description if crew.activity_id else '',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def edit_daily_crew(request, report_id, crew_id):
    """
    Fix a crew's own Activity/Agreement/Contractor after it was created -- most commonly to link
    it to an activity that wasn't logged yet (or wasn't picked) at the moment the crew was added,
    since every worker under this crew, and the labor-cost-vs-productivity summary, follow it.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        crew = get_object_or_404(DailyReportCrew, pk=crew_id, report=report)
        data = request.POST

        if 'name' in data:
            name = data.get('name', '').strip()
            if not name:
                return JsonResponse({'success': False, 'message': 'Crew name is required.'}, status=400)
            crew.name = name
        if 'activity' in data:
            activity_id = data.get('activity') or None
            if activity_id:
                get_object_or_404(DailyReportActivityProgress, pk=activity_id, report=report)
            crew.activity_id = activity_id
        if 'agreement' in data:
            agreement_id = data.get('agreement') or None
            if agreement_id:
                from subcontractors.models import SubcontractorAgreement
                get_object_or_404(SubcontractorAgreement, pk=agreement_id, project=report.project)
            crew.agreement_id = agreement_id
        if 'contractor_name' in data:
            crew.contractor_name = data.get('contractor_name', '')
        crew.save()

        # Every worker attendance row under this crew re-derives its own contractor_name/
        # activity_location from the crew on save -- refresh them now so an edit here (e.g.
        # linking the crew to an activity for the first time) reaches rows already added under it.
        for attendance in crew.workers.all():
            attendance.save()

        return JsonResponse({
            'success': True,
            'message': 'Crew updated',
            'id': crew.id,
            'name': crew.name,
            'contractor_name': crew.contractor_name,
            'activity_description': crew.activity.activity_description if crew.activity_id else '',
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_crew(request, report_id, crew_id):
    """
    Delete a crew, but only once no worker attendance row is still linked to it -- the FK itself
    is SET_NULL (a worker wouldn't vanish if its crew did), but silently orphaning workers off a
    crew this way would freeze their contractor_name/activity_location at whatever the crew had
    last set, without it reading as a real per-worker choice. Reassign or remove those workers
    first, then the now-empty crew can be deleted.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        crew = get_object_or_404(DailyReportCrew, pk=crew_id, report=report)
        worker_count = crew.workers.count()
        if worker_count:
            return JsonResponse({
                'success': False,
                'message': f'{worker_count} worker(s) are still under this crew. Remove or reassign them first, '
                           f'then delete the crew.',
            }, status=400)
        crew.delete()
        return JsonResponse({'success': True, 'message': 'Crew deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def add_daily_worker_attendance(request, report_id):
    """Add a named-worker attendance row to a daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST

        # Trade/classification is required going forward so Section 2 of the
        # printed report can be grouped and subtotalled by trade (see
        # generate_daily_report_pdf) -- rows imported or created before this
        # check existed may still be blank, but every new one must set it.
        if not data.get('labor_classification'):
            return JsonResponse({'success': False, 'message': 'Labor classification (trade) is required.'}, status=400)

        # The worker's name must come from a real, reusable identity -- either an HR employee
        # record or the shared day-labor roster (timesheets.DailyWorker) -- rather than being
        # typed fresh on every report, so the same person's hours can be tracked/aggregated
        # correctly across reports and projects. New rows going forward must pick one; historical
        # rows created before this rule (free-text worker_name only) are left as they are.
        employee_id = data.get('employee') or None
        daily_worker_id = data.get('daily_worker') or None
        if not employee_id and not daily_worker_id:
            return JsonResponse({
                'success': False,
                'message': 'Select the worker from the list (HR employee or day-labor roster), or add them to the roster first.'
            }, status=400)

        worker_name = data.get('worker_name', '').strip()
        if not worker_name and daily_worker_id:
            from timesheets.models import DailyWorker
            worker_name = get_object_or_404(DailyWorker, pk=daily_worker_id).full_name

        crew_id = data.get('crew') or None
        if crew_id:
            get_object_or_404(DailyReportCrew, pk=crew_id, report=report)

        # DailyReportWorkerAttendance.save() computes total_hours from
        # time_in/time_out/break_hours/overtime_hours via datetime.combine()
        # and Decimal arithmetic -- .create() does not parse raw POST
        # strings into those types on its own, so do it explicitly here.
        def _parse_time(value):
            return datetime.strptime(value, '%H:%M').time() if value else None

        def _parse_decimal(value, default='0'):
            return Decimal(value) if value else Decimal(default)

        entry = DailyReportWorkerAttendance.objects.create(
            report=report,
            worker_name=worker_name,
            labor_classification_id=data.get('labor_classification') or None,
            employee_id=employee_id,
            daily_worker_id=daily_worker_id,
            crew_id=crew_id,
            contractor_name=data.get('contractor_name', ''),
            activity_location=data.get('activity_location', ''),
            time_in=_parse_time(data.get('time_in')),
            time_out=_parse_time(data.get('time_out')),
            break_hours=_parse_decimal(data.get('break_hours')),
            overtime_hours=_parse_decimal(data.get('overtime_hours')),
            total_hours=_parse_decimal(data.get('total_hours')),
            notes=data.get('notes', ''),
        )
        return JsonResponse({'success': True, 'message': 'Worker attendance added', 'id': entry.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def edit_daily_worker_attendance(request, report_id, entry_id):
    """
    Edit an existing worker-attendance row. POST (not PATCH) for the same
    reason as edit_daily_attachment: not strictly needed here (this form
    has no file upload), but kept consistent with every other edit
    endpoint on this report so the client-side pattern stays uniform.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        entry = get_object_or_404(DailyReportWorkerAttendance, pk=entry_id, report=report)
        data = request.POST

        # Same rule as add_daily_worker_attendance: a row being edited must
        # come away with a trade set, even if it didn't have one before.
        if 'labor_classification' in data and not data.get('labor_classification'):
            return JsonResponse({'success': False, 'message': 'Labor classification (trade) is required.'}, status=400)

        def _parse_time(value):
            return datetime.strptime(value, '%H:%M').time() if value else None

        def _parse_decimal(value, default='0'):
            return Decimal(value) if value else Decimal(default)

        if 'worker_name' in data:
            entry.worker_name = data.get('worker_name', '')
        if 'labor_classification' in data:
            entry.labor_classification_id = data.get('labor_classification') or None
        if 'employee' in data:
            entry.employee_id = data.get('employee') or None
        if 'daily_worker' in data:
            entry.daily_worker_id = data.get('daily_worker') or None
        if 'crew' in data:
            entry.crew_id = data.get('crew') or None
        if 'contractor_name' in data:
            entry.contractor_name = data.get('contractor_name', '')
        if 'activity_location' in data:
            entry.activity_location = data.get('activity_location', '')
        if 'time_in' in data:
            entry.time_in = _parse_time(data.get('time_in'))
        if 'time_out' in data:
            entry.time_out = _parse_time(data.get('time_out'))
        if 'break_hours' in data:
            entry.break_hours = _parse_decimal(data.get('break_hours'))
        if 'overtime_hours' in data:
            entry.overtime_hours = _parse_decimal(data.get('overtime_hours'))
        if 'total_hours' in data:
            entry.total_hours = _parse_decimal(data.get('total_hours'))
        if 'notes' in data:
            entry.notes = data.get('notes', '')
        entry.save()
        return JsonResponse({'success': True, 'message': 'Worker attendance updated', 'id': entry.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def pull_gps_daily_worker_attendance(request, report_id, entry_id):
    """
    Fill this attendance row's time_in/time_out from the linked HR
    employee's real GPS check-in/out (timesheets.CheckInLocation) for the
    report's date -- earliest 'in' and latest 'out' that day. Requires
    the row to already be linked to an Employee (see the `employee`
    picker on Add/Edit Worker Attendance); total_hours is recomputed by
    DailyReportWorkerAttendance.save() from the new times.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        entry = get_object_or_404(DailyReportWorkerAttendance, pk=entry_id, report=report)

        if not entry.employee_id:
            return JsonResponse({'success': False, 'message': 'This row has no linked HR employee to pull GPS data from.'}, status=400)

        from timesheets.models import CheckInLocation
        from .daily_detail_models import local_day_range_utc
        start, end = local_day_range_utc(report.report_date)
        day_records = CheckInLocation.objects.filter(
            employee_id=entry.employee_id, timestamp__gte=start, timestamp__lt=end,
        ).order_by('timestamp')
        first_in = day_records.filter(check_type='in').first()
        last_out = day_records.filter(check_type='out').last()

        if not first_in and not last_out:
            return JsonResponse({'success': False, 'message': 'No GPS check-in/out found for this employee on this report date.'}, status=404)

        if first_in:
            entry.time_in = timezone.localtime(first_in.timestamp).time()
        if last_out:
            entry.time_out = timezone.localtime(last_out.timestamp).time()
        # Force total_hours to be recomputed from the new GPS-sourced
        # times rather than keeping whatever was there before.
        entry.total_hours = Decimal('0')
        entry.save()
        return JsonResponse({
            'success': True, 'message': 'GPS hours pulled', 'id': entry.id,
            'time_in': entry.time_in.strftime('%H:%M') if entry.time_in else None,
            'time_out': entry.time_out.strftime('%H:%M') if entry.time_out else None,
            'total_hours': str(entry.total_hours),
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_worker_attendance(request, report_id, entry_id):
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        entry = get_object_or_404(DailyReportWorkerAttendance, pk=entry_id, report=report)
        entry.delete()
        return JsonResponse({'success': True, 'message': 'Worker attendance deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ==================== ACTIVITY PROGRESS (Section 1) ====================

@login_required
@require_http_methods(["POST"])
def add_daily_activity_progress(request, report_id):
    """Add an activity-progress row (with qty/cumulative/% and optional BOQ sub-item link)"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST

        activity_description = data.get('activity_description', '')
        quantity_today = Decimal(data.get('quantity_today') or 0)
        # Cumulative is auto-calculated from this same activity's own history on this project
        # (see DailyReportActivityProgress.cumulative_before) when left at 0/blank -- same rule
        # as total_hours auto-calc on worker attendance -- so it isn't retyped by hand on every
        # report; an explicit nonzero value (e.g. a manual correction) is kept as given.
        if data.get('quantity_cumulative'):
            quantity_cumulative = Decimal(data.get('quantity_cumulative'))
        else:
            prior = DailyReportActivityProgress.cumulative_before(
                report.project, activity_description, report.report_date
            )
            quantity_cumulative = prior + quantity_today

        entry = DailyReportActivityProgress.objects.create(
            report=report,
            sub_item_id=data.get('sub_item') or None,
            activity_description=activity_description,
            location=data.get('location', ''),
            unit=data.get('unit', ''),
            total_quantity=data.get('total_quantity') or None,
            quantity_today=quantity_today,
            quantity_cumulative=quantity_cumulative,
            completion_percentage=data.get('completion_percentage') or 0,
            status=data.get('status', 'in_progress'),
            reference_notes=data.get('reference_notes', ''),
        )
        return JsonResponse({'success': True, 'message': 'Activity progress added', 'id': entry.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_activity_progress(request, report_id, entry_id):
    """
    Delete an activity-progress row, but only once nothing on this report is still linked to it --
    a Crew executing it (DailyReportCrew.activity) or equipment logged against it
    (DailyEquipment.activity). Both FKs are SET_NULL, not CASCADE, so nothing would vanish if
    this delete went through anyway -- but the Crew's/Equipment's own link to real, meaningful
    work would silently disappear along with it. Unlink or delete those first.
    """
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        entry = get_object_or_404(DailyReportActivityProgress, pk=entry_id, report=report)

        crew_count = entry.crews.count()
        equipment_count = entry.equipment_used.count()
        if crew_count or equipment_count:
            parts = []
            if crew_count:
                parts.append(f'{crew_count} crew(s)')
            if equipment_count:
                parts.append(f'{equipment_count} equipment entry/entries')
            return JsonResponse({
                'success': False,
                'message': f'Still linked to {" and ".join(parts)}. Unlink or remove those first, then delete this activity.',
            }, status=400)

        entry.delete()
        return JsonResponse({'success': True, 'message': 'Activity progress deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ==================== QA/QC & HSE (Section 4, one per report) ====================

@login_required
@require_http_methods(["POST"])
def save_daily_qaqc(request, report_id):
    """Create or update the single QA/QC & HSE section for a daily report"""
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST

        qaqc, _created = DailyReportQAQC.objects.update_or_create(
            report=report,
            defaults={
                'inspection_status': data.get('inspection_status', 'not_applicable'),
                'ir_mir_test_reference': data.get('ir_mir_test_reference', ''),
                'toolbox_talk_conducted': data.get('toolbox_talk_conducted') in ('on', 'true', '1', 'True'),
                'toolbox_talk_topic': data.get('toolbox_talk_topic', ''),
                'incident_occurred': data.get('incident_occurred') in ('on', 'true', '1', 'True'),
                'near_miss_occurred': data.get('near_miss_occurred') in ('on', 'true', '1', 'True'),
                'ppe_site_cleanliness_status': data.get('ppe_site_cleanliness_status', ''),
                'ncr_hse_reference': data.get('ncr_hse_reference', ''),
                'notes': data.get('notes', ''),
            },
        )
        return JsonResponse({'success': True, 'message': 'QA/QC & HSE saved', 'id': qaqc.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ==================== NEXT DAY PLAN (Section 6) ====================

@login_required
@require_http_methods(["POST"])
def add_daily_next_day_plan(request, report_id):
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST

        entry = DailyReportNextDayPlan.objects.create(
            report=report,
            sub_item_id=data.get('sub_item') or None,
            planned_activity=data.get('planned_activity', ''),
            location=data.get('location', ''),
            manpower_required=data.get('manpower_required') or None,
            resources_required=data.get('resources_required', ''),
            requirement_notes=data.get('requirement_notes', ''),
            responsible_party=data.get('responsible_party', ''),
            priority=data.get('priority', ''),
            readiness=data.get('readiness', ''),
            remarks=data.get('remarks', ''),
        )
        return JsonResponse({'success': True, 'message': 'Next-day plan item added', 'id': entry.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_next_day_plan(request, report_id, entry_id):
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        entry = get_object_or_404(DailyReportNextDayPlan, pk=entry_id, report=report)
        entry.delete()
        return JsonResponse({'success': True, 'message': 'Next-day plan item deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


# ==================== SITE EVENTS (Section 5: Delay/SI/RFI/NCR/HSE) ====================

@login_required
@require_http_methods(["POST"])
def add_daily_site_event(request, report_id):
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        data = request.POST

        event = SiteEvent.objects.create(
            project=report.project,
            daily_report=report,
            event_type=data.get('event_type', 'other'),
            reference=data.get('reference', ''),
            event_date=report.report_date,
            description=data.get('description', ''),
            required_action=data.get('required_action', ''),
            responsible_party=data.get('responsible_party', ''),
            target_date=data.get('target_date') or None,
            time_impact_hours=data.get('time_impact_hours') or None,
            remarks=data.get('remarks', ''),
            created_by=request.user,
        )
        return JsonResponse({'success': True, 'message': 'Site event added', 'id': event.id})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_daily_site_event(request, report_id, event_id):
    try:
        report = get_object_or_404(DailyReport, pk=report_id)
        if not _can_edit_daily_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        event = get_object_or_404(SiteEvent, pk=event_id, daily_report=report)
        event.delete()
        return JsonResponse({'success': True, 'message': 'Site event deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["PATCH"])
def update_daily_report_remarks(request, report_id):
    """Quick inline edit for the daily report's free-text remarks, without going through the full report edit form."""
    report = get_object_or_404(DailyReport, pk=report_id)
    if not _can_edit_daily_report(request.user, report):
        return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)

    data = _payload(request)
    if 'remarks' not in data:
        return JsonResponse({'success': False, 'message': "'remarks' field is required"}, status=400)
    report.remarks = (data.get('remarks') or '').strip()
    report.save(update_fields=['remarks'])
    return JsonResponse({'success': True, 'remarks': report.remarks})


@login_required
@require_http_methods(["PATCH"])
def update_daily_report_work_hours_note(request, report_id):
    """Quick inline edit for the site engineer's staff/labor man-hours split note."""
    report = get_object_or_404(DailyReport, pk=report_id)
    if not _can_edit_daily_report(request.user, report):
        return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)

    data = _payload(request)
    if 'work_hours_note' not in data:
        return JsonResponse({'success': False, 'message': "'work_hours_note' field is required"}, status=400)
    report.work_hours_note = (data.get('work_hours_note') or '').strip()
    report.save(update_fields=['work_hours_note'])
    return JsonResponse({'success': True, 'work_hours_note': report.work_hours_note})


def _truthy_callable(obj, name: str) -> bool:
    """Support user.is_admin() / user.is_admin patterns safely."""
    if not hasattr(obj, name):
        return False
    attr = getattr(obj, name)
    return attr() if callable(attr) else bool(attr)

def _can_edit_report(user, report) -> bool:
    if user.is_anonymous:
        return False
    if getattr(report, "site_engineer_id", None) and report.site_engineer_id == user.id:
        return True
    if getattr(report, "created_by_id", None) and report.created_by_id == user.id:
        return True
    if _truthy_callable(user, "is_admin"):
        return True
    if _truthy_callable(user, "is_project_manager"):
        return getattr(report, "project_id", None) and getattr(getattr(report, "project", None), "manager_id", None) == user.id
    return False

def _payload(request):
    """Return dict payload for JSON or form-encoded."""
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
    return request.POST.dict()

def _json_error(message, status=400):
    return JsonResponse({"ok": False, "error": message}, status=status)


# -----------------------
# Monthly Report APIs
# -----------------------

@login_required
@require_http_methods(["GET", "POST"])
def monthly_floor_activity_list_create(request, report_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(FloorActivity.objects.filter(report=report).values(
            "id", "floor_id", "activity_description", "completion_percentage"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = FloorActivity.objects.create(
        report=report,
        floor_id=int(data.get("floor_id") or 0),
        activity_description=data.get("activity_description", "").strip(),
        completion_percentage=int(data.get("completion_percentage") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id, "floor_id": obj.floor_id, "activity_description": obj.activity_description, "completion_percentage": obj.completion_percentage}, status=201)


@login_required
@require_http_methods(["DELETE"])
def monthly_floor_activity_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(FloorActivity, pk=item_id, report=report)
    obj.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_external_work_list_create(request, report_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(ExternalWork.objects.filter(report=report).values("id", "work_description", "completion_percentage"))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = ExternalWork.objects.create(
        report=report,
        work_description=data.get("work_description", "").strip(),
        completion_percentage=int(data.get("completion_percentage") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id, "work_description": obj.work_description, "completion_percentage": obj.completion_percentage}, status=201)


@login_required
@require_http_methods(["DELETE"])
def monthly_external_work_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(ExternalWork, pk=item_id, report=report)
    obj.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_material_supply_list_create(request, report_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(MaterialSupply.objects.filter(report=report).values(
            "id", "material_type", "material_description", "quantity", "unit",
            "delivered_quantity", "used_quantity", "remaining_notes",
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = MaterialSupply.objects.create(
        report=report,
        material_type=data.get("material_type", "").strip(),
        material_description=data.get("material_description", "").strip(),
        quantity=float(data.get("quantity") or 0),
        unit=data.get("unit", "").strip(),
        delivered_quantity=data.get("delivered_quantity") or None,
        used_quantity=data.get("used_quantity") or None,
        remaining_notes=data.get("remaining_notes", "").strip(),
    )
    return JsonResponse({
        "ok": True, "id": obj.id, "material_type": obj.material_type,
        "material_description": obj.material_description, "quantity": obj.quantity, "unit": obj.unit,
        "delivered_quantity": obj.delivered_quantity, "used_quantity": obj.used_quantity, "remaining_notes": obj.remaining_notes,
    }, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def monthly_material_supply_update_delete(request, report_id, item_id):
    """Edit or delete a material-status row (delivered/used quantities and notes -- EDGE "Materials Status" table)."""
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MaterialSupply, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("material_type", "material_description", "unit"):
        if field in data:
            setattr(obj, field, (data[field] or "").strip())
    if "delivered_quantity" in data:
        obj.delivered_quantity = data["delivered_quantity"] or None
    if "used_quantity" in data:
        obj.used_quantity = data["used_quantity"] or None
    if "remaining_notes" in data:
        obj.remaining_notes = (data["remaining_notes"] or "").strip()
    obj.save()
    return JsonResponse({
        "ok": True, "id": obj.id, "material_type": obj.material_type,
        "delivered_quantity": obj.delivered_quantity,
        "used_quantity": obj.used_quantity, "remaining_notes": obj.remaining_notes,
    })


@login_required
@require_http_methods(["POST"])
def monthly_material_supply_add_quantity(request, report_id, item_id):
    """
    Add this period's usage on top of a material row's existing
    (cumulative) quantity, rather than overwriting it -- same idea as
    owner_report_price_item_add_quantity on the Owner Financial report,
    just without that model's price-tracking fields.
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MaterialSupply, pk=item_id, report=report)

    data = _payload(request)
    try:
        additional = Decimal(str(data.get("additional_quantity") or "0"))
    except Exception:
        return _json_error("Invalid quantity", status=400)
    if additional <= 0:
        return _json_error("Additional quantity must be greater than zero", status=400)

    obj.quantity = obj.quantity + additional
    obj.save(update_fields=["quantity"])
    return JsonResponse({"ok": True, "id": obj.id, "quantity": obj.quantity})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_upcoming_work_list_create(request, report_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(UpcomingWork.objects.filter(report=report).values(
            "id", "work_description", "planned_start_date", "planned_end_date"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = UpcomingWork.objects.create(
        report=report,
        work_description=data.get("work_description", "").strip(),
        planned_start_date=data.get("planned_start_date") or None,
        planned_end_date=data.get("planned_end_date") or None,
    )
    return JsonResponse({
        "ok": True, "id": obj.id,
        "work_description": obj.work_description,
        "planned_start_date": obj.planned_start_date,
        "planned_end_date": obj.planned_end_date,
    }, status=201)


@login_required
@require_http_methods(["DELETE"])
def monthly_upcoming_work_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(UpcomingWork, pk=item_id, report=report)
    obj.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_progress_category_item_list_create(request, report_id):
    """"Progress Summary" table rows (EDGE monthly report, Section 3)."""
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(MonthlyProgressCategoryItem.objects.filter(report=report).values(
            "id", "item_name", "planned_value", "actual_value", "order"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = MonthlyProgressCategoryItem.objects.create(
        report=report,
        item_name=data.get("item_name", "").strip(),
        planned_value=data.get("planned_value", "").strip(),
        actual_value=data.get("actual_value", "").strip(),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def monthly_progress_category_item_update_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MonthlyProgressCategoryItem, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("item_name", "planned_value", "actual_value"):
        if field in data:
            setattr(obj, field, (data[field] or "").strip())
    obj.save()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_key_activity_list_create(request, report_id):
    """"Key Activities Carried Out This Month" (EDGE monthly report, Section 4)."""
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(MonthlyKeyActivity.objects.filter(report=report).values(
            "id", "activity", "status", "remarks", "order"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = MonthlyKeyActivity.objects.create(
        report=report,
        activity=data.get("activity", "").strip(),
        status=data.get("status", "in_progress"),
        remarks=data.get("remarks", "").strip(),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def monthly_key_activity_update_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MonthlyKeyActivity, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    if "activity" in data:
        obj.activity = (data["activity"] or "").strip()
    if "status" in data and data["status"]:
        obj.status = data["status"]
    if "remarks" in data:
        obj.remarks = (data["remarks"] or "").strip()
    obj.save()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_issue_risk_delay_list_create(request, report_id):
    """"Issues, Risks & Delays" (EDGE monthly report, Section 8)."""
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(MonthlyIssueRiskDelay.objects.filter(report=report).values(
            "id", "description", "impact", "mitigation", "order"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = MonthlyIssueRiskDelay.objects.create(
        report=report,
        description=data.get("description", "").strip(),
        impact=data.get("impact", "").strip(),
        mitigation=data.get("mitigation", "").strip(),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def monthly_issue_risk_delay_update_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MonthlyIssueRiskDelay, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("description", "impact", "mitigation"):
        if field in data:
            setattr(obj, field, (data[field] or "").strip())
    obj.save()
    return JsonResponse({"ok": True})


_MONTHLY_REPORT_NARRATIVE_FIELDS = (
    "executive_summary", "schedule_variance_note",
    "hse_lti_note", "hse_near_misses_note", "hse_toolbox_talks_note",
    "hse_site_inspections_note", "hse_corrective_actions_note",
    "qc_inspections_note", "qc_nonconformances_note", "qc_pending_submittals_note",
    "next_month_plan", "general_description", "photos_external_link",
)


@login_required
@require_http_methods(["PATCH"])
def monthly_report_update_narrative(request, report_id):
    """
    Quick inline edit for one of the monthly report's free-text narrative
    fields (executive summary, HSE metrics, QC notes, next month's plan,
    ...), without going through the full report edit form.
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    update_fields = [f for f in _MONTHLY_REPORT_NARRATIVE_FIELDS if f in data]
    if not update_fields:
        return _json_error("No recognized fields in payload", status=400)

    for field in update_fields:
        setattr(report, field, (data[field] or "").strip())
    report.save(update_fields=update_fields)
    return JsonResponse({"ok": True, **{f: getattr(report, f) for f in update_fields}})


@login_required
@require_http_methods(["GET", "POST"])
def monthly_report_photo_list_create(request, report_id):
    """Photographic Record section (EDGE monthly report, Section 12)."""
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(report.phase_photos.values("id", "phase_id", "sub_item_id", "caption", "taken_date", "order"))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    phase = get_object_or_404(ProjectPhase, pk=request.POST.get("phase"), project=report.project)
    if not request.FILES.get("photo"):
        return _json_error("A photo file is required", status=400)

    photo = ProjectPhasePhoto.objects.create(
        phase=phase,
        sub_item_id=request.POST.get("sub_item") or None,
        photo=request.FILES.get("photo"),
        caption=request.POST.get("caption", "").strip(),
        taken_date=request.POST.get("taken_date") or timezone.localdate(),
        monthly_report=report,
        uploaded_by=request.user,
    )
    return JsonResponse({"ok": True, "id": photo.id, "url": photo.photo.url})


@login_required
@require_http_methods(["POST", "DELETE"])
def monthly_report_photo_update_delete(request, report_id, photo_id):
    """
    POST (not PATCH) is deliberate here: edits may attach a replacement
    image file, and Django only parses a multipart request body into
    request.POST/request.FILES for method == 'POST' -- for PATCH/PUT it
    leaves both empty regardless of content type.
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    photo = get_object_or_404(ProjectPhasePhoto, pk=photo_id, monthly_report=report)

    if request.method == "DELETE":
        photo.delete()
        return JsonResponse({"ok": True})

    if "phase" in request.POST and request.POST["phase"]:
        photo.phase = get_object_or_404(ProjectPhase, pk=request.POST["phase"], project=report.project)
    if "sub_item" in request.POST:
        photo.sub_item_id = request.POST.get("sub_item") or None
    if "caption" in request.POST:
        photo.caption = request.POST.get("caption", "").strip()
    if "taken_date" in request.POST and request.POST["taken_date"]:
        photo.taken_date = request.POST["taken_date"]
    if request.FILES.get("photo"):
        photo.photo = request.FILES["photo"]
    photo.save()
    return JsonResponse({
        "ok": True, "id": photo.id, "caption": photo.caption, "url": photo.photo.url,
    })


@login_required
@require_http_methods(["POST"])
def add_monthly_attachment(request, report_id):
    """Add a supporting-document attachment to a monthly report (EDGE "Appendix" section)."""
    try:
        report = get_object_or_404(MonthlyReport, pk=report_id)
        if not _can_edit_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)

        attachment = ReportAttachment.objects.create(
            report_type='monthly',
            report_id=report.id,
            file=request.FILES.get('file'),
            description=request.POST.get('caption', ''),
            location=request.POST.get('location', ''),
            attachment_type=request.POST.get('attachment_type', 'document'),
            uploaded_by=request.user,
        )

        return JsonResponse({
            'success': True,
            'message': 'Attachment added successfully',
            'id': attachment.id,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def edit_monthly_attachment(request, report_id, attachment_id):
    """
    Edit an existing monthly report attachment's caption/location/type, and
    optionally replace its file. POST (not PATCH) is deliberate: Django
    only parses a multipart body into request.POST/request.FILES for
    method == 'POST' -- for PATCH/PUT it leaves both empty regardless of
    content type, so a multipart PATCH would silently see no fields and
    no file at all.
    """
    try:
        report = get_object_or_404(MonthlyReport, pk=report_id)
        if not _can_edit_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        attachment = get_object_or_404(ReportAttachment, pk=attachment_id, report_type='monthly', report_id=report.id)

        if 'caption' in request.POST:
            attachment.description = request.POST.get('caption', '').strip()
        if 'location' in request.POST:
            attachment.location = request.POST.get('location', '').strip()
        if request.POST.get('attachment_type'):
            attachment.attachment_type = request.POST['attachment_type']
        if request.FILES.get('file'):
            attachment.file = request.FILES['file']
        attachment.save()

        return JsonResponse({
            'success': True,
            'message': 'Attachment updated successfully',
            'id': attachment.id,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_monthly_attachment(request, report_id, attachment_id):
    """Delete an attachment from a monthly report."""
    try:
        report = get_object_or_404(MonthlyReport, pk=report_id)
        if not _can_edit_report(request.user, report):
            return JsonResponse({'success': False, 'message': 'Not allowed'}, status=403)
        attachment = get_object_or_404(ReportAttachment, pk=attachment_id, report_type='monthly', report_id=report.id)
        attachment.delete()
        return JsonResponse({'success': True, 'message': 'Attachment deleted'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def monthly_review_comment_list_create(request, report_id):
    """
    "Response to Comments" log: feedback from the external supervision/
    consultant (e.g. EDGE) on a submitted period, and the contractor's
    response to each -- addressed before the report is reissued as the
    next revision (see monthly_report_new_revision below).
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)

    if request.method == "GET":
        rows = list(MonthlyReviewComment.objects.filter(report=report).values(
            "id", "reference", "comment_text", "response_text", "status", "order"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = MonthlyReviewComment.objects.create(
        report=report,
        reference=data.get("reference", "").strip(),
        comment_text=data.get("comment_text", "").strip(),
        response_text=data.get("response_text", "").strip(),
        status=data.get("status", "open"),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({"ok": True, "id": obj.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def monthly_review_comment_update_delete(request, report_id, item_id):
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(MonthlyReviewComment, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("reference", "comment_text", "response_text"):
        if field in data:
            setattr(obj, field, (data[field] or "").strip())
    if "status" in data and data["status"]:
        obj.status = data["status"]
    obj.save()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def monthly_report_new_revision(request, report_id):
    """
    Bump this report to its next revision after the external supervision/
    consultant sends back review comments (the real EDGE report's
    "R02.07.2026.Rev02" pattern): increments revision_number, records an
    optional revision_note, and -- if the report had been submitted/
    rejected/reviewed -- resets it to draft with the internal approval
    fields cleared so the site engineer can edit and resubmit it. This is
    distinct from "Copy for Next Period" on the Owner Financial report:
    it revises the SAME reporting period in place rather than starting a
    new one.
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    report.revision_number += 1
    report.revision_note = data.get("revision_note", "").strip()
    report.status = 'draft'
    report.reviewed_by = None
    report.review_date = None
    report.approved_by = None
    report.approval_date = None
    report.rejection_reason = ''
    report.save()
    return JsonResponse({"ok": True, "revision_number": report.revision_number})


# Kept in sync with reports.views.MONTHLY_REPORT_DEFAULT_SECTION_ORDER --
# see that constant's docstring for why "floors" isn't in this list.
_MONTHLY_REPORT_DEFAULT_SECTION_ORDER = [
    'overview', 'progress', 'activities', 'materials', 'external',
    'hse_qc', 'issues', 'upcoming', 'boq', 'photos', 'appendix',
    'review_comments', 'approvals',
]


def _resolve_monthly_section_order(report):
    stored = [s.strip() for s in (report.section_order or '').split(',') if s.strip()]
    known = set(_MONTHLY_REPORT_DEFAULT_SECTION_ORDER)
    ordered = [s for s in stored if s in known]
    ordered += [s for s in _MONTHLY_REPORT_DEFAULT_SECTION_ORDER if s not in ordered]
    return ordered


@login_required
@require_http_methods(["POST"])
def monthly_report_reorder_section(request, report_id):
    """
    Move one report-page section (Overview, Progress Summary, ...) up or
    down relative to its siblings -- same up/down-swap pattern as
    owner_report_phase_update_move, just persisted as an ordered id list
    (MonthlyReport.section_order) instead of per-row `order` integers,
    since these sections are fixed template blocks, not database rows.
    """
    report = get_object_or_404(MonthlyReport, pk=report_id)
    if not (
        request.user.is_admin()
        or request.user == report.site_engineer
        or (request.user.is_project_manager() and report.project.manager_id == request.user.id)
    ):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    section_id = data.get("section_id", "")
    direction = data.get("direction", "")
    if section_id not in _MONTHLY_REPORT_DEFAULT_SECTION_ORDER or direction not in ("up", "down"):
        return _json_error("Invalid section_id/direction", status=400)

    order = _resolve_monthly_section_order(report)
    i = order.index(section_id)
    j = i - 1 if direction == "up" else i + 1
    if 0 <= j < len(order):
        order[i], order[j] = order[j], order[i]
    report.section_order = ",".join(order)
    report.save(update_fields=["section_order"])
    return JsonResponse({"ok": True, "section_order": order})


# -----------------------
# Owner Financial Report APIs
# -----------------------

@login_required
@require_http_methods(["GET", "POST"])
def owner_report_price_item_list_create(request, report_id):
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)

    if request.method == "GET":
        rows = list(OwnerReportPriceComparisonItem.objects.filter(report=report).values(
            "id", "item_type", "item_name", "unit", "quantity", "old_unit_price", "new_unit_price", "price_difference"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = OwnerReportPriceComparisonItem.objects.create(
        report=report,
        item_type=data.get("item_type", "material"),
        item_name=data.get("item_name", "").strip(),
        unit=data.get("unit", "").strip(),
        quantity=Decimal(data.get("quantity") or "0"),
        old_unit_price=Decimal(data.get("old_unit_price") or "0"),
        new_unit_price=Decimal(data.get("new_unit_price") or "0"),
    )
    return JsonResponse({
        "ok": True, "id": obj.id, "item_name": obj.item_name, "price_difference": str(obj.price_difference),
    }, status=201)


@login_required
@require_http_methods(["DELETE"])
def owner_report_price_item_delete(request, report_id, item_id):
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(OwnerReportPriceComparisonItem, pk=item_id, report=report)
    obj.delete()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def owner_report_price_item_add_quantity(request, report_id, item_id):
    """
    Add this period's usage on top of a price-comparison item's existing
    (cumulative) quantity, rather than overwriting it -- the quantity
    field tracks the running total across periods (see its help_text and
    the "Copy for Next Period" docstring).
    """
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(OwnerReportPriceComparisonItem, pk=item_id, report=report)

    data = _payload(request)
    try:
        additional = Decimal(str(data.get("additional_quantity") or "0"))
    except Exception:
        return _json_error("Invalid quantity", status=400)
    if additional <= 0:
        return _json_error("Additional quantity must be greater than zero", status=400)

    obj.quantity = obj.quantity + additional
    obj.save()  # recomputes price_difference against the new cumulative quantity
    return JsonResponse({
        "ok": True, "id": obj.id, "quantity": str(obj.quantity), "price_difference": str(obj.price_difference),
    })


@login_required
@require_http_methods(["GET", "POST"])
def owner_report_phase_update_list_create(request, report_id):
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)

    if request.method == "GET":
        rows = list(OwnerReportPhaseUpdate.objects.filter(report=report).values(
            "id", "phase_id", "status", "work_performed", "order"
        ))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    obj = OwnerReportPhaseUpdate.objects.create(
        report=report,
        phase_id=int(data.get("phase_id") or 0),
        status=data.get("status", "in_progress"),
        work_performed=data.get("work_performed", "").strip(),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({
        "ok": True, "id": obj.id, "phase_id": obj.phase_id, "status": obj.status,
        "work_performed": obj.work_performed,
    }, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def owner_report_phase_update_update_delete(request, report_id, item_id):
    """Edit an existing phase status row's phase/status/work_performed text, or delete it."""
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(OwnerReportPhaseUpdate, pk=item_id, report=report)

    if request.method == "DELETE":
        obj.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    if "phase_id" in data and data["phase_id"]:
        obj.phase_id = int(data["phase_id"])
    if "status" in data and data["status"]:
        obj.status = data["status"]
    if "work_performed" in data:
        obj.work_performed = data["work_performed"].strip()
    obj.save()
    return JsonResponse({
        "ok": True, "id": obj.id, "phase_id": obj.phase_id, "status": obj.status,
        "work_performed": obj.work_performed,
    })


@login_required
@require_http_methods(["POST"])
def owner_report_phase_update_move(request, report_id, item_id):
    """
    Move a phase status row up or down in display order, by swapping its
    `order` value with the adjacent row's (adjacent = next/previous by
    current order among this report's phase updates).
    """
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    obj = get_object_or_404(OwnerReportPhaseUpdate, pk=item_id, report=report)

    data = _payload(request)
    direction = data.get("direction")
    if direction not in ("up", "down"):
        return _json_error("direction must be 'up' or 'down'", status=400)

    siblings = list(OwnerReportPhaseUpdate.objects.filter(report=report).order_by("order", "id"))
    idx = next((i for i, s in enumerate(siblings) if s.id == obj.id), None)
    if idx is None:
        return _json_error("Item not found in report", status=404)

    neighbor_idx = idx - 1 if direction == "up" else idx + 1
    if neighbor_idx < 0 or neighbor_idx >= len(siblings):
        return JsonResponse({"ok": True, "moved": False})  # already at that end

    neighbor = siblings[neighbor_idx]
    obj.order, neighbor.order = neighbor.order, obj.order
    # Two rows sharing the same `order` value (e.g. both left at the
    # default 0) would otherwise swap to identical values and not
    # visibly move -- fall back to swapping by position among siblings.
    if obj.order == neighbor.order:
        obj.order, neighbor.order = neighbor_idx, idx
    obj.save(update_fields=["order"])
    neighbor.save(update_fields=["order"])
    return JsonResponse({"ok": True, "moved": True})


_OWNER_REPORT_NARRATIVE_FIELDS = (
    "progress_summary", "next_month_expected_works", "next_month_expected_completion_pct",
    "material_price_note", "closing_note",
)


@login_required
@require_http_methods(["PATCH"])
def owner_financial_report_update_narrative(request, report_id):
    """
    Quick inline edit for one of the owner financial report's free-text
    narrative fields (progress summary, next month's expected works,
    material price note, closing note) or the expected-completion %,
    without going through the full report edit form.
    """
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    data = _payload(request)
    update_fields = []
    for field in _OWNER_REPORT_NARRATIVE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "next_month_expected_completion_pct":
            value = Decimal(str(value)) if value not in (None, "") else None
        else:
            value = (value or "").strip()
        setattr(report, field, value)
        update_fields.append(field)

    if not update_fields:
        return _json_error("No recognized fields in payload", status=400)

    report.save(update_fields=update_fields)
    return JsonResponse({"ok": True, **{f: str(getattr(report, f)) for f in update_fields}})


# -----------------------
# BOQ Editor (Project Phases / Sub-items / Progress Entries)
# -----------------------

def _can_edit_boq(user, project) -> bool:
    if user.is_anonymous:
        return False
    if _truthy_callable(user, "is_admin") or _truthy_callable(user, "is_engineering_manager"):
        return True
    if _truthy_callable(user, "is_project_manager"):
        return project.manager_id == user.id
    return False


_PRICING_TEXT_FIELDS = ("unit",)
_PRICING_DECIMAL_FIELDS = ("quantity", "budget_unit_price", "contract_unit_price")


def _apply_pricing(obj, data):
    """Copy unit / quantity / prices from a request payload onto a phase or sub-item. Raises ValueError on bad numbers."""
    for field in _PRICING_TEXT_FIELDS:
        if field in data:
            setattr(obj, field, (data[field] or "").strip()[:20])
    for field in _PRICING_DECIMAL_FIELDS:
        if field not in data:
            continue
        raw = str(data[field] if data[field] is not None else "").strip().replace(",", "")
        if raw == "":
            value = None if field == "quantity" else Decimal("0")
        else:
            try:
                value = Decimal(raw)
            except Exception:
                raise ValueError(f"'{field}' must be a number")
            if value < 0:
                raise ValueError(f"'{field}' can't be negative")
        setattr(obj, field, value)


@login_required
@require_http_methods(["POST"])
def boq_phase_create(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    data = _payload(request)
    phase = ProjectPhase(
        project=project,
        code=data.get("code", "").strip(),
        name_ar=data.get("name_ar", "").strip(),
        name_en=data.get("name_en", "").strip(),
        section=data.get("section", "").strip()[:100],
        weight_percentage=Decimal(data.get("weight_percentage") or "0"),
        order=int(data.get("order") or 0),
    )
    try:
        _apply_pricing(phase, data)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    phase.save()
    phase.sync_whole_item()
    return JsonResponse({"ok": True, "id": phase.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def boq_phase_update_delete(request, project_id, phase_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    phase = get_object_or_404(ProjectPhase, pk=phase_id, project=project)

    if request.method == "DELETE":
        phase.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("code", "name_ar", "name_en"):
        if field in data:
            setattr(phase, field, data[field].strip())
    if "section" in data:
        phase.section = data["section"].strip()[:100]
    if "weight_percentage" in data:
        phase.weight_percentage = Decimal(data["weight_percentage"] or "0")
    if "order" in data:
        phase.order = int(data["order"] or 0)
    try:
        _apply_pricing(phase, data)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    phase.save()
    phase.sync_whole_item()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def boq_subitem_create(request, project_id, phase_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    phase = get_object_or_404(ProjectPhase, pk=phase_id, project=project)
    data = _payload(request)
    sub_item = ProjectPhaseSubItem(
        phase=phase,
        code=data.get("code", "").strip()[:20],
        name_ar=data.get("name_ar", "").strip(),
        name_en=data.get("name_en", "").strip(),
        weight_percentage=Decimal(data.get("weight_percentage") or "0"),
        planned_start_date=data.get("planned_start_date") or None,
        planned_completion_date=data.get("planned_completion_date") or None,
        order=int(data.get("order") or 0),
    )
    try:
        _apply_pricing(sub_item, data)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    sub_item.save()
    phase.sync_whole_item()  # a real sub-item takes over from the phase's automatic "whole item"
    return JsonResponse({"ok": True, "id": sub_item.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def boq_subitem_update_delete(request, project_id, subitem_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    sub_item = get_object_or_404(ProjectPhaseSubItem, pk=subitem_id, phase__project=project)

    if request.method == "DELETE":
        phase = sub_item.phase
        sub_item.delete()
        phase.sync_whole_item()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("name_ar", "name_en"):
        if field in data:
            setattr(sub_item, field, data[field].strip())
    if "code" in data:
        sub_item.code = data["code"].strip()[:20]
    try:
        _apply_pricing(sub_item, data)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    if "weight_percentage" in data:
        sub_item.weight_percentage = Decimal(data["weight_percentage"] or "0")
    if "planned_start_date" in data:
        sub_item.planned_start_date = data["planned_start_date"] or None
    if "planned_completion_date" in data:
        sub_item.planned_completion_date = data["planned_completion_date"] or None
    if "order" in data:
        sub_item.order = int(data["order"] or 0)
    sub_item.save()
    return JsonResponse({"ok": True})


@login_required
@require_http_methods(["POST"])
def boq_recalculate_weights(request, project_id):
    """Set every weight from the contract prices (each item's share of the total contract value)."""
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    from .progress_models import recalculate_weights_from_contract
    try:
        total = recalculate_weights_from_contract(project)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse({"ok": True, "contract_total": str(total)})


@login_required
@require_http_methods(["POST"])
def boq_progress_entry_create(request, project_id, subitem_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    sub_item = get_object_or_404(ProjectPhaseSubItem, pk=subitem_id, phase__project=project)
    data = _payload(request)
    try:
        entry = ProjectPhaseProgressEntry.objects.create(
            sub_item=sub_item,
            report_date=data.get("report_date") or timezone.localdate(),
            execution_percentage=Decimal(data.get("execution_percentage") or "0"),
            notes=data.get("notes", "").strip(),
            recorded_by=request.user,
        )
    except Exception as exc:
        return _json_error(str(exc), status=400)
    return JsonResponse({
        "ok": True, "id": entry.id,
        "execution_percentage": str(entry.execution_percentage),
        "report_date": str(entry.report_date),
    }, status=201)


# -----------------------
# Milestone Editor (ProjectMilestone, tied to a BOQ Phase)
# -----------------------

@login_required
@require_http_methods(["POST"])
def milestone_create(request, project_id, phase_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    phase = get_object_or_404(ProjectPhase, pk=phase_id, project=project)
    data = _payload(request)
    if not data.get("baseline_date"):
        return _json_error("baseline_date is required", status=400)
    milestone = ProjectMilestone.objects.create(
        phase=phase,
        name_ar=data.get("name_ar", "").strip(),
        name_en=data.get("name_en", "").strip(),
        baseline_date=data["baseline_date"],
        forecast_date=data.get("forecast_date") or None,
        actual_date=data.get("actual_date") or None,
        notes=data.get("notes", "").strip(),
        order=int(data.get("order") or 0),
    )
    return JsonResponse({"ok": True, "id": milestone.id}, status=201)


@login_required
@require_http_methods(["PATCH", "DELETE"])
def milestone_update_delete(request, project_id, milestone_id):
    project = get_object_or_404(Project, pk=project_id)
    if not _can_edit_boq(request.user, project):
        return _json_error("Not allowed", status=403)
    milestone = get_object_or_404(ProjectMilestone, pk=milestone_id, phase__project=project)

    if request.method == "DELETE":
        milestone.delete()
        return JsonResponse({"ok": True})

    data = _payload(request)
    for field in ("name_ar", "name_en", "notes"):
        if field in data:
            setattr(milestone, field, data[field].strip())
    if "phase_id" in data and data["phase_id"]:
        milestone.phase = get_object_or_404(ProjectPhase, pk=data["phase_id"], project=project)
    if "baseline_date" in data and data["baseline_date"]:
        milestone.baseline_date = data["baseline_date"]
    if "forecast_date" in data:
        milestone.forecast_date = data["forecast_date"] or None
    if "actual_date" in data:
        milestone.actual_date = data["actual_date"] or None
    if "order" in data:
        milestone.order = int(data["order"] or 0)
    milestone.save()
    return JsonResponse({"ok": True})


# -----------------------
# Project Phase Photo Gallery
# -----------------------

@login_required
@require_http_methods(["POST"])
def add_phase_photo(request, project_id):
    phase = get_object_or_404(ProjectPhase, pk=request.POST.get('phase'), project_id=project_id)
    photo = ProjectPhasePhoto.objects.create(
        phase=phase,
        sub_item_id=request.POST.get('sub_item') or None,
        photo=request.FILES.get('photo'),
        caption=request.POST.get('caption', ''),
        taken_date=request.POST.get('taken_date') or timezone.localdate(),
        uploaded_by=request.user,
    )
    return JsonResponse({'success': True, 'id': photo.id, 'url': photo.photo.url})


@login_required
@require_http_methods(["DELETE"])
def delete_phase_photo(request, project_id, photo_id):
    photo = get_object_or_404(ProjectPhasePhoto, pk=photo_id, phase__project_id=project_id)
    photo.delete()
    return JsonResponse({'success': True})


# -----------------------
# Owner Financial Report Photos (add/edit/delete from inside the report itself,
# as opposed to the project-wide phase photo gallery above)
# -----------------------

@login_required
@require_http_methods(["GET", "POST"])
def owner_report_photo_list_create(request, report_id):
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)

    if request.method == "GET":
        rows = list(report.phase_photos.values("id", "phase_id", "sub_item_id", "caption", "taken_date", "order"))
        return JsonResponse({"ok": True, "results": rows})

    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)

    phase = get_object_or_404(ProjectPhase, pk=request.POST.get("phase"), project=report.project)
    if not request.FILES.get("photo"):
        return _json_error("A photo file is required", status=400)

    photo = ProjectPhasePhoto.objects.create(
        phase=phase,
        sub_item_id=request.POST.get("sub_item") or None,
        photo=request.FILES.get("photo"),
        caption=request.POST.get("caption", "").strip(),
        taken_date=request.POST.get("taken_date") or timezone.localdate(),
        owner_financial_report=report,
        uploaded_by=request.user,
    )
    return JsonResponse({"ok": True, "id": photo.id, "url": photo.photo.url})


@login_required
@require_http_methods(["POST", "DELETE"])
def owner_report_photo_update_delete(request, report_id, photo_id):
    """
    POST (not PATCH) is deliberate here: edits may attach a replacement
    image file, and Django only parses a multipart request body into
    request.POST/request.FILES for method == 'POST' -- for PATCH/PUT it
    leaves both empty regardless of content type, so a multipart PATCH
    would silently see no fields and no file at all.
    """
    report = get_object_or_404(OwnerFinancialReport, pk=report_id)
    if not _can_edit_report(request.user, report):
        return _json_error("Not allowed", status=403)
    photo = get_object_or_404(ProjectPhasePhoto, pk=photo_id, owner_financial_report=report)

    if request.method == "DELETE":
        photo.delete()
        return JsonResponse({"ok": True})

    if "phase" in request.POST and request.POST["phase"]:
        photo.phase = get_object_or_404(ProjectPhase, pk=request.POST["phase"], project=report.project)
    if "sub_item" in request.POST:
        photo.sub_item_id = request.POST.get("sub_item") or None
    if "caption" in request.POST:
        photo.caption = request.POST.get("caption", "").strip()
    if "taken_date" in request.POST and request.POST["taken_date"]:
        photo.taken_date = request.POST["taken_date"]
    if request.FILES.get("photo"):
        photo.photo = request.FILES["photo"]
    photo.save()
    return JsonResponse({
        "ok": True, "id": photo.id, "caption": photo.caption, "url": photo.photo.url,
    })