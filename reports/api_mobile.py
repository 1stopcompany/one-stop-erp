"""
Mobile API for the site engineer: record which day-labor workers worked today, from the phone.

The rows land in the project's Daily Report for that date (a draft one is opened when there is none yet), exactly where the
engineer would otherwise type them on the web page, and from there they flow into the wages (كشف الصرف) by project and by sub-group
(متفرقة). Token authentication, like the rest of the mobile API.

  GET  /reports/api/mobile/projects/                      the engineer's projects, whether they are ready, their subs
  GET  /reports/api/mobile/projects/<id>/workers/?date=   that day's rows, the previous day's rows, the recent crew
  POST /reports/api/mobile/projects/<id>/workers/         save the day's rows (replaces the day-labor rows of that report)
  GET  /reports/api/mobile/workers/?q=                    search the day-labor roster

Saving is refused on a project that is not ready (no insurance / unpriced BOQ ...) unless the user is an admin, like every
other operational record (see projects.readiness).
"""
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from projects import readiness
from projects.models import Project
from timesheets.models import DailyWorker

from .daily_detail_models import DailyReportWorkerAttendance, ProjectSub
from .models import DailyReport
from .services.trade_mapping import classification_for

EDITABLE_STATUSES = ('draft', 'rejected')


def _error(message, status=400):
    return Response({'detail': message}, status=status)


def _my_projects(user):
    if user.is_admin():
        return Project.objects.all()
    if user.is_site_engineer():
        return Project.objects.filter(site_engineer=user)
    return Project.objects.none()


def _project_for(user, pk):
    return get_object_or_404(_my_projects(user), pk=pk)


def _parse_day(raw):
    if not raw:
        return timezone.localdate()
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return None


def _readiness(project, user):
    """(can_save, reason): a project that is not ready blocks everyone but admins."""
    result = readiness.check(project)
    if result.ok or user.is_admin():
        return True, ''
    return False, f"'{project.name}' is not ready yet. {result.summary()}"


def _report_for(project, day, user):
    qs = DailyReport.objects.filter(project=project, report_date=day).order_by('id')
    if not user.is_admin():
        qs = qs.filter(site_engineer=user)
    return qs.first()


def _row(entry):
    return {
        'worker_id': entry.daily_worker_id, 'name': entry.worker_name,
        'trade': entry.daily_worker.trade if entry.daily_worker_id else '',
        'hours': float(max((entry.total_hours or 0) - (entry.overtime_hours or 0), 0)),
        'overtime_hours': float(entry.overtime_hours or 0), 'sub': entry.sub_name, 'note': entry.notes or '',
    }


def _day_rows(report):
    if report is None:
        return []
    entries = report.worker_attendance.filter(daily_worker__isnull=False).select_related('daily_worker').order_by('worker_name')
    return [_row(e) for e in entries]


def _subs(project):
    return list(ProjectSub.objects.filter(project=project, is_active=True).values_list('name', flat=True))


@api_view(['GET'])
def my_projects(request):
    """The engineer's projects with what the phone needs to know before the screen opens."""
    out = []
    for project in _my_projects(request.user).order_by('name'):
        can_save, reason = _readiness(project, request.user)
        out.append({'id': project.id, 'name': project.name, 'symbol': project.project_symbol,
                    'can_save': can_save, 'reason': reason, 'subs': _subs(project)})
    return Response(out)


@api_view(['GET', 'POST'])
def project_workers_day(request, pk):
    project = _project_for(request.user, pk)
    if request.method == 'POST':
        return _save_day(request, project)

    day = _parse_day(request.query_params.get('date'))
    if day is None:
        return _error('date must look like 2026-10-06.')
    report = _report_for(project, day, request.user)
    can_save, reason = _readiness(project, request.user)
    if report is not None and report.status not in EDITABLE_STATUSES:
        can_save, reason = False, f"This day's report is already {report.get_status_display().lower()}; ask for it to be returned to edit the workers."

    # the most recent earlier day with day-labor rows on this project, to copy with one tap
    previous = (DailyReportWorkerAttendance.objects
                .filter(report__project=project, report__report_date__lt=day, daily_worker__isnull=False)
                .aggregate(day=Max('report__report_date'))['day'])
    previous_rows = []
    if previous:
        previous_rows = _day_rows(_report_for(project, previous, request.user))

    # workers seen on this project in the last three weeks, most frequent first
    since = day - timedelta(days=21)
    recent = (DailyReportWorkerAttendance.objects
              .filter(report__project=project, report__report_date__gte=since, daily_worker__isnull=False)
              .values('daily_worker_id', 'daily_worker__full_name', 'daily_worker__trade')
              .annotate(times=Count('id')).order_by('-times', 'daily_worker__full_name')[:40])
    return Response({
        'project': {'id': project.id, 'name': project.name}, 'date': day.isoformat(),
        'can_save': can_save, 'reason': reason, 'subs': _subs(project),
        'report': {'exists': report is not None, 'status': report.status if report else '', 'number': report.report_number if report else ''},
        'rows': _day_rows(report),
        'previous': {'date': previous.isoformat() if previous else None, 'rows': previous_rows},
        'recent': [{'worker_id': r['daily_worker_id'], 'name': r['daily_worker__full_name'], 'trade': r['daily_worker__trade']} for r in recent],
    })


def _decimal(raw, label, high):
    try:
        value = Decimal(str(raw if raw not in (None, '') else 0))
    except InvalidOperation:
        raise ValueError(f'{label} is not a number.')
    if value < 0 or value > high:
        raise ValueError(f'{label} must be between 0 and {high}.')
    return value


def _save_day(request, project):
    data = request.data
    day = _parse_day(data.get('date'))
    if day is None:
        return _error('date must look like 2026-10-06.')
    if day > timezone.localdate():
        return _error("A day that has not happened yet can't be recorded.")
    can_save, reason = _readiness(project, request.user)
    if not can_save:
        return _error(reason, status=403)

    rows = data.get('rows') or []
    if not isinstance(rows, list):
        return _error('rows must be a list.')
    allowed_subs = set(_subs(project))
    clean, seen = [], set()
    for position, raw in enumerate(rows, start=1):
        try:
            worker_id = int(raw.get('worker_id'))
        except (TypeError, ValueError, AttributeError):
            return _error(f'Row {position}: pick the worker from the list.')
        if worker_id in seen:
            return _error(f'Row {position}: this worker is listed twice.')
        seen.add(worker_id)
        sub = ' '.join(str(raw.get('sub') or '').split())
        if sub and sub not in allowed_subs:
            return _error(f"Row {position}: '{sub}' is not one of this project's subs.")
        try:
            hours, overtime = _decimal(raw.get('hours'), 'Hours', 24), _decimal(raw.get('overtime_hours'), 'Overtime hours', 24)
        except ValueError as exc:
            return _error(f'Row {position}: {exc}')
        clean.append({'worker_id': worker_id, 'sub': sub, 'hours': hours, 'overtime': overtime, 'note': str(raw.get('note') or '')[:250]})

    workers = {w.pk: w for w in DailyWorker.objects.filter(pk__in=seen, is_active=True)}
    missing = seen - set(workers)
    if missing:
        return _error('Some of the workers are not in the active roster.')

    with transaction.atomic():
        report = _report_for(project, day, request.user)
        if report is None:
            report = DailyReport.objects.create(
                project=project, site_engineer=request.user, report_date=day, status='draft', weather_conditions='sunny',
            )
        elif report.status not in EDITABLE_STATUSES:
            return _error(f"This day's report is already {report.get_status_display().lower()}; it can't be changed from here.", status=409)
        cache = {}
        existing = {e.daily_worker_id: e for e in report.worker_attendance.filter(daily_worker__isnull=False)}
        for gone in set(existing) - seen:
            existing[gone].delete()
        for item in clean:
            worker = workers[item['worker_id']]
            fields = dict(
                worker_name=worker.full_name, sub_name=item['sub'], labor_classification=classification_for(worker.trade, cache),
                overtime_hours=item['overtime'], total_hours=item['hours'] + item['overtime'], notes=item['note'],
            )
            entry = existing.get(worker.pk)
            if entry is None:
                DailyReportWorkerAttendance.objects.create(report=report, daily_worker=worker, **fields)
            else:
                for key, value in fields.items():
                    setattr(entry, key, value)
                entry.save()
    return Response({'saved': len(clean), 'report': {'number': report.report_number, 'status': report.status}, 'rows': _day_rows(report)})


@api_view(['GET'])
def search_workers(request):
    """Active day-labor roster, filtered by name, trade or national ID."""
    if not (request.user.is_admin() or request.user.is_site_engineer()):
        return _error('Only a site engineer can record the workers.', status=403)
    q = (request.query_params.get('q') or '').strip()
    qs = DailyWorker.objects.filter(is_active=True)
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(trade__icontains=q) | Q(national_id__icontains=q))
    return Response([{'worker_id': w.pk, 'name': w.full_name, 'trade': w.trade, 'national_id': w.national_id or ''}
                     for w in qs.order_by('full_name')[:30]])
