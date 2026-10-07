import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, TemplateView

from .auth_views import hr_manager_required, hr_required, is_hr_manager, wages_access_required
from .forms import (
    DepartmentForm, EmployeeDocumentForm, EmployeeForm, EmployeeNoteForm,
    EmployeeSearchForm, GeofenceForm, PositionForm,
    WorkExperienceForm, EducationForm, DependentForm, DailyWorkerForm,
    SalaryStructureForm, HolidayForm, EmploymentStatusUpdateForm, EmploymentTypeUpdateForm,
)
from .models import (
    CheckInLocation, DailyAttendanceRecord, DailyWorker, Department, Employee, EmployeeStatus, Geofence,
    Holiday, LeaveRequest, LocationHistory, Payslip, Position, SalaryStructure,
    EmploymentStatusHistory, EmploymentTypeHistory,
)
from .services.work_hours import calculate_daily_hours


def local_day_range_utc(day):
    """
    (start, end) aware-UTC datetimes spanning local midnight-to-midnight
    for `day`, for a >=/< range filter instead of a `__date` lookup.
    Django compiles `timestamp__date=...` to
    `DATE(CONVERT_TZ(timestamp, 'UTC', '<TIME_ZONE>'))` on MySQL, which
    silently matches nothing (no error) if the server's
    mysql.time_zone_name tables were never loaded via
    mysql_tzinfo_to_sql -- a common out-of-the-box MySQL state, and
    exactly why "today's check-ins" showed 0 here regardless of real
    data. A plain range on the stored UTC value needs no server-side
    named-timezone lookup, so it isn't affected by that at all.
    """
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    return start, start + timedelta(days=1)


@hr_required
def dashboard(request):
    """Main HR dashboard: headcount, today's attendance, payroll/leave status, and quick links."""
    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Get basic statistics
    total_employees = Employee.objects.count()
    total_departments = Department.objects.count()
    total_positions = Position.objects.count()

    # Get today's check-ins if location tracking is available
    todays_checkins = 0
    try:
        _today_start, _today_end = local_day_range_utc(today)
        todays_checkins = CheckInLocation.objects.filter(
            timestamp__gte=_today_start, timestamp__lt=_today_end,
            check_type='in'
        ).count()
    except:
        pass

    # Get recent employees
    recent_hires = Employee.objects.order_by('-created_at')[:5]

    pending_leave_requests = LeaveRequest.objects.filter(status='pending').select_related('employee').order_by('submitted_date')[:5]
    pending_leave_count = LeaveRequest.objects.filter(status='pending').count()

    upcoming_holidays = Holiday.objects.filter(date__gte=today).order_by('date')[:3]

    payslips_this_month = Payslip.objects.filter(period_start=month_start).count()
    active_daily_workers = DailyWorker.objects.filter(is_active=True).count()

    context = {
        'total_employees': total_employees,
        'total_departments': total_departments,
        'total_positions': total_positions,
        'todays_checkins': todays_checkins,
        'recent_hires': recent_hires,
        'pending_leave_requests': pending_leave_requests,
        'pending_leave_count': pending_leave_count,
        'upcoming_holidays': upcoming_holidays,
        'payslips_this_month': payslips_this_month,
        'active_daily_workers': active_daily_workers,
        'current_month': month_start,
    }

    return render(request, 'timesheets/dashboard.html', context)


@hr_required
def user_guide(request):
    """Static in-app HR user guide (Arabic) -- covers every screen in this module."""
    return render(request, 'timesheets/user_guide.html')


@hr_required
def user_guide_pdf(request):
    """Illustrated PDF version of the user guide (drawn screen mockups + real data), see timesheets/manual_pdf.py."""
    from .manual_pdf import generate_hr_manual_pdf

    pdf_bytes = generate_hr_manual_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="hr-user-guide.pdf"'
    return response


def _filtered_employees(request):
    """Shared search/filter logic behind both the Employees page and its PDF export -- keeps the PDF an exact match of whatever is currently on screen."""
    form = EmployeeSearchForm(request.GET)
    employees = Employee.objects.select_related('department', 'position', 'manager').all()
    filter_bits = []

    if form.is_valid():
        search_query = form.cleaned_data.get('search_query')
        department = form.cleaned_data.get('department')
        position = form.cleaned_data.get('position')
        employment_status = form.cleaned_data.get('employment_status')

        if search_query:
            employees = employees.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(employee_id__icontains=search_query)
            )
            filter_bits.append(f'Search: "{search_query}"')

        if department:
            employees = employees.filter(department=department)
            filter_bits.append(f'Department: {department.name}')

        if position:
            employees = employees.filter(position=position)
            filter_bits.append(f'Position: {position.title}')

        if employment_status:
            employees = employees.filter(employment_status=employment_status)
            filter_bits.append(f'Status: {dict(Employee.EMPLOYMENT_STATUS_CHOICES).get(employment_status, employment_status)}')

    return form, employees, (' | '.join(filter_bits) if filter_bits else 'All Employees')


@hr_required
def employee_list(request):
    """List all employees with search and filter functionality"""
    form, employees, _filter_summary = _filtered_employees(request)

    # Pagination
    paginator = Paginator(employees, 20)  # Show 20 employees per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'form': form,
        'page_obj': page_obj,
        'employees': page_obj,
        'total_count': employees.count(),
    }

    return render(request, 'timesheets/employee_list.html', context)


@hr_required
def employee_list_pdf(request):
    """The Employees list as a system-formatted PDF, replacing the browser's own print dialog."""
    from .pdf import generate_employee_list_pdf

    _form, employees, filter_summary = _filtered_employees(request)
    pdf_bytes = generate_employee_list_pdf(
        list(employees.order_by('last_name', 'first_name')), filter_summary=filter_summary,
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = "inline; filename=employees.pdf"
    return response


@hr_required
def employee_detail(request, employee_id):
    """Display detailed information about an employee, including leave, permissions and payroll history."""
    employee = get_object_or_404(Employee, pk=employee_id)
    documents = employee.documents.all()[:5]  # Show latest 5 documents
    notes = employee.notes.all()[:5]  # Show latest 5 notes

    leave_requests = employee.leave_requests.all()[:10]
    leave_permissions = employee.leave_permissions.all()[:10]
    payslips = employee.payslips.order_by('-period_start')[:12]
    work_experiences = employee.work_experiences.all()
    education_history = employee.education_history.all()
    dependents = employee.dependents.all()
    status_history = employee.status_history.all()[:10]
    type_history = employee.type_history.all()[:10]

    from .services.attendance_service import compute_leave_summary
    today = timezone.localdate()
    leave_summary_this_year = compute_leave_summary(employee, today.year)
    leave_days_used_this_year = leave_summary_this_year['total_used']
    leave_balance = leave_summary_this_year['remaining']

    context = {
        'employee': employee,
        'documents': documents,
        'notes': notes,
        'leave_requests': leave_requests,
        'leave_permissions': leave_permissions,
        'payslips': payslips,
        'leave_days_used_this_year': leave_days_used_this_year,
        'leave_balance': leave_balance,
        'work_experiences': work_experiences,
        'education_history': education_history,
        'dependents': dependents,
        'status_history': status_history,
        'type_history': type_history,
        'can_edit': request.user.has_perm('timesheets.change_employee'),
    }

    return render(request, 'timesheets/employee_detail.html', context)


@hr_required
def employee_detail_pdf(request, employee_id):
    """
    The employee profile as a system-formatted PDF, replacing the browser's own
    Ctrl+P print dialog (whose margins/paper size depend on the visiting browser,
    not the system) for the "Print" action on the employee detail page.
    """
    from .pdf import generate_employee_profile_pdf

    employee = get_object_or_404(Employee, pk=employee_id)
    pdf_bytes = generate_employee_profile_pdf(employee)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"inline; filename=employee-{employee.employee_id}.pdf"
    return response


@hr_required
def employee_leave_summary(request, employee_id):
    """
    An employee's annual leave summary (كشف ملخص الإجازات): balance,
    total used, remaining, and a month-by-month breakdown of days taken
    for the selected year -- see attendance_service.compute_leave_summary.
    """
    from .services.attendance_service import compute_leave_summary

    employee = get_object_or_404(Employee, pk=employee_id)
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
    except ValueError:
        year = today.year

    summary = compute_leave_summary(employee, year)
    month_rows = [
        {'month': month, 'name': date(year, month, 1).strftime('%B'), 'days': summary['by_month'][month]}
        for month in range(1, 13)
    ]

    context = {
        'employee': employee,
        'year': year,
        'summary': summary,
        'month_rows': month_rows,
        'available_years': range(today.year - 4, today.year + 1),
    }
    return render(request, 'timesheets/employee_leave_summary.html', context)


@hr_required
def employee_leave_summary_pdf(request, employee_id):
    """PDF twin of employee_leave_summary (see timesheets/pdf.py)."""
    from .services.attendance_service import compute_leave_summary
    from .pdf import generate_leave_summary_pdf

    employee = get_object_or_404(Employee, pk=employee_id)
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
    except ValueError:
        year = today.year

    summary = compute_leave_summary(employee, year)
    pdf_bytes = generate_leave_summary_pdf(summary)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=leave-summary-{employee.employee_id}-{year}.pdf'
    return response


@hr_manager_required
def employee_add(request):
    """Add a new employee"""
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES)
        if form.is_valid():
            employee = form.save(commit=False)
            employee.created_by = request.user
            employee.save()
            messages.success(request, f'Employee {employee.full_name} has been added successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmployeeForm()
    
    context = {
        'form': form,
        'title': 'Add New Employee',
        'submit_text': 'Add Employee',
    }

    return render(request, 'timesheets/employee_form.html', context)


@hr_manager_required
def employee_edit(request, employee_id):
    """Edit an existing employee"""
    employee = get_object_or_404(Employee, pk=employee_id)
    
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=employee)
        if form.is_valid():
            form.save()
            messages.success(request, f'Employee {employee.full_name} has been updated successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmployeeForm(instance=employee)
    
    context = {
        'form': form,
        'employee': employee,
        'title': f'Edit {employee.full_name}',
        'submit_text': 'Update Employee',
    }

    return render(request, 'timesheets/employee_form.html', context)


@hr_required
def department_list(request):
    """List all departments"""
    departments = Department.objects.select_related('manager').all()
    
    context = {
        'departments': departments,
        'can_add': request.user.has_perm('timesheets.add_department'),
    }

    return render(request, 'timesheets/department_list.html', context)


@hr_manager_required
def department_add(request):
    """Add a new department"""
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            department = form.save()
            messages.success(request, f'Department {department.name} has been added successfully.')
            return redirect('timesheets:department_list')
    else:
        form = DepartmentForm()
    
    context = {
        'form': form,
        'title': 'Add New Department',
        'submit_text': 'Add Department',
    }

    return render(request, 'timesheets/department_form.html', context)


@hr_required
def position_list(request):
    """List all positions"""
    positions = Position.objects.all()
    
    context = {
        'positions': positions,
        'can_add': request.user.has_perm('timesheets.add_position'),
    }

    return render(request, 'timesheets/position_list.html', context)


@hr_manager_required
def position_add(request):
    """Add a new position"""
    if request.method == 'POST':
        form = PositionForm(request.POST)
        if form.is_valid():
            position = form.save()
            messages.success(request, f'Position {position.title} has been added successfully.')
            return redirect('timesheets:position_list')
    else:
        form = PositionForm()
    
    context = {
        'form': form,
        'title': 'Add New Position',
        'submit_text': 'Add Position',
    }

    return render(request, 'timesheets/position_form.html', context)


@hr_manager_required
def employee_document_add(request, employee_id):
    """Add a document for an employee"""
    employee = get_object_or_404(Employee, pk=employee_id)
    
    if request.method == 'POST':
        form = EmployeeDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.employee = employee
            document.uploaded_by = request.user
            document.save()
            messages.success(request, 'Document has been uploaded successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmployeeDocumentForm()
    
    context = {
        'form': form,
        'employee': employee,
        'title': f'Add Document for {employee.full_name}',
        'submit_text': 'Upload Document',
    }

    return render(request, 'timesheets/document_form.html', context)


@hr_manager_required
def employee_note_add(request, employee_id):
    """Add a note for an employee"""
    employee = get_object_or_404(Employee, pk=employee_id)
    
    if request.method == 'POST':
        form = EmployeeNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.employee = employee
            note.created_by = request.user
            note.save()
            messages.success(request, 'Note has been added successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmployeeNoteForm()
    
    context = {
        'form': form,
        'employee': employee,
        'title': f'Add Note for {employee.full_name}',
        'submit_text': 'Add Note',
    }

    return render(request, 'timesheets/note_form.html', context)


@hr_manager_required
def employee_work_experience_add(request, employee_id):
    """Add a previous job to an employee's profile"""
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        form = WorkExperienceForm(request.POST)
        if form.is_valid():
            experience = form.save(commit=False)
            experience.employee = employee
            experience.save()
            messages.success(request, 'Work experience has been added successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = WorkExperienceForm()

    context = {
        'form': form,
        'employee': employee,
        'title': f'Add Work Experience for {employee.full_name}',
        'submit_text': 'Add Experience',
    }

    return render(request, 'timesheets/work_experience_form.html', context)


@hr_manager_required
def employee_education_add(request, employee_id):
    """Add a school/degree to an employee's profile"""
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        form = EducationForm(request.POST)
        if form.is_valid():
            education = form.save(commit=False)
            education.employee = employee
            education.save()
            messages.success(request, 'Education has been added successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EducationForm()

    context = {
        'form': form,
        'employee': employee,
        'title': f'Add Education for {employee.full_name}',
        'submit_text': 'Add Education',
    }

    return render(request, 'timesheets/education_form.html', context)


@hr_manager_required
def employee_dependent_add(request, employee_id):
    """Add a family dependent to an employee's profile"""
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        form = DependentForm(request.POST)
        if form.is_valid():
            dependent = form.save(commit=False)
            dependent.employee = employee
            dependent.save()
            messages.success(request, 'Dependent has been added successfully.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = DependentForm()

    context = {
        'form': form,
        'employee': employee,
        'title': f'Add Dependent for {employee.full_name}',
        'submit_text': 'Add Dependent',
    }

    return render(request, 'timesheets/dependent_form.html', context)


@hr_manager_required
def employee_status_update(request, employee_id):
    """Change an employee's employment_status and log it to EmploymentStatusHistory."""
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        form = EmploymentStatusUpdateForm(request.POST)
        if form.is_valid():
            history = form.save(commit=False)
            history.employee = employee
            history.changed_by = request.user
            history.save()
            employee.employment_status = history.status
            employee.save(update_fields=['employment_status'])
            messages.success(request, f'Employment status updated to {history.get_status_display()}.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmploymentStatusUpdateForm(initial={'status': employee.employment_status})

    context = {
        'form': form,
        'employee': employee,
        'title': f'Update Employment Status for {employee.full_name}',
        'submit_text': 'Update Status',
    }

    return render(request, 'timesheets/work_experience_form.html', context)


@hr_manager_required
def employee_type_update(request, employee_id):
    """Change an employee's employment_type and log it to EmploymentTypeHistory."""
    employee = get_object_or_404(Employee, pk=employee_id)

    if request.method == 'POST':
        form = EmploymentTypeUpdateForm(request.POST)
        if form.is_valid():
            history = form.save(commit=False)
            history.employee = employee
            history.changed_by = request.user
            history.save()
            employee.employment_type = history.employment_type
            employee.save(update_fields=['employment_type'])
            messages.success(request, f'Employment type updated to {history.get_employment_type_display()}.')
            return redirect('timesheets:employee_detail', employee_id=employee.pk)
    else:
        form = EmploymentTypeUpdateForm(initial={'employment_type': employee.employment_type})

    context = {
        'form': form,
        'employee': employee,
        'title': f'Update Employment Type for {employee.full_name}',
        'submit_text': 'Update Type',
    }

    return render(request, 'timesheets/work_experience_form.html', context)


@hr_required
def leave_request_list(request):
    """
    List every leave request, in-app (not Django admin, which needs
    is_staff and looks/behaves nothing like the rest of the HR module) --
    with approve/reject actions for whoever can manage them.
    """
    status_filter = request.GET.get('status', '')
    leave_requests = LeaveRequest.objects.select_related('employee').order_by('-submitted_date')
    if status_filter in ('pending', 'approved', 'rejected'):
        leave_requests = leave_requests.filter(status=status_filter)

    context = {
        'leave_requests': leave_requests,
        'status_filter': status_filter,
        'pending_count': LeaveRequest.objects.filter(status='pending').count(),
        'can_review': request.user.has_perm('timesheets.change_leaverequest'),
    }
    return render(request, 'timesheets/leave_request_list.html', context)


@hr_manager_required
def leave_request_review(request, pk, action):
    """Approve or reject a pending leave request."""
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if action in ('approve', 'reject') and leave_request.status == 'pending':
        leave_request.status = 'approved' if action == 'approve' else 'rejected'
        leave_request.reviewed_by = request.user
        leave_request.reviewed_date = timezone.now()
        leave_request.save(update_fields=['status', 'reviewed_by', 'reviewed_date'])
        messages.success(
            request,
            f'Leave request for {leave_request.employee.full_name} has been '
            f'{"approved" if action == "approve" else "rejected"}.'
        )
    return redirect('timesheets:leave_request_list')


@hr_required
def daily_worker_list(request):
    """List the shared day-labor worker roster, in-app instead of Django admin."""
    workers = DailyWorker.objects.all()
    context = {
        'workers': workers,
        'can_add': request.user.has_perm('timesheets.add_dailyworker'),
    }
    return render(request, 'timesheets/daily_worker_list.html', context)


@hr_manager_required
def daily_worker_add(request):
    """Add a new day-labor worker to the shared roster"""
    if request.method == 'POST':
        form = DailyWorkerForm(request.POST, request.FILES)
        if form.is_valid():
            worker = form.save()
            messages.success(request, f'{worker.full_name} has been added to the day-labor roster.')
            return redirect('timesheets:daily_worker_list')
    else:
        form = DailyWorkerForm()

    context = {
        'form': form,
        'title': 'Add Day-Labor Worker',
        'submit_text': 'Add Worker',
    }
    return render(request, 'timesheets/daily_worker_form.html', context)


@hr_required
def daily_worker_attendance(request, worker_id):
    """
    A day-labor worker's daily attendance across every project they
    touched this month -- pulled straight from
    reports.DailyReportWorkerAttendance (the same rows a site engineer
    enters on their project's daily report), grouped by day instead of
    by project so HR can actually see this worker's "دوام" at a glance,
    the same way an Employee's DTR does.
    """
    from reports.daily_detail_models import DailyReportWorkerAttendance

    worker = get_object_or_404(DailyWorker, pk=worker_id)
    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    entries = list(
        DailyReportWorkerAttendance.objects.filter(
            daily_worker=worker, report__report_date__gte=period_start, report__report_date__lte=period_end,
        ).select_related('report', 'report__project').order_by('report__report_date')
    )

    total_regular_hours = sum((max(Decimal('0'), (e.total_hours or Decimal('0')) - (e.overtime_hours or Decimal('0'))) for e in entries), Decimal('0'))
    total_overtime_hours = sum((e.overtime_hours or Decimal('0') for e in entries), Decimal('0'))

    context = {
        "worker": worker,
        "entries": entries,
        "period_start": period_start,
        "month_param": period_start.strftime("%Y-%m"),
        "days_worked": len(entries),
        "total_days": (total_regular_hours / Decimal(8)).quantize(Decimal('0.01')),
        "total_regular_hours": total_regular_hours,
        "total_overtime_hours": total_overtime_hours,
    }
    return render(request, "timesheets/daily_worker_attendance.html", context)


@hr_required
def payslip_list(request):
    """Browse every generated payslip, in-app instead of Django admin."""
    month_param = request.GET.get('month', '')
    payslips = Payslip.objects.select_related('employee').order_by('-period_start', 'employee__first_name')
    if month_param:
        try:
            month_start = datetime.strptime(month_param, '%Y-%m').date()
            payslips = payslips.filter(period_start=month_start)
        except ValueError:
            pass

    context = {
        'payslips': payslips,
        'month_param': month_param,
    }
    return render(request, 'timesheets/payslip_list.html', context)


@login_required
def payslip_pdf(request, pk):
    """
    One payslip as a formatted PDF -- HR can open any employee's from
    All Payslips / the employee's Payroll tab, and an employee (the
    mobile app's PayslipViewSet.pdf action reuses the same generator)
    can open their own, but never anyone else's.
    """
    payslip = get_object_or_404(Payslip, pk=pk)
    is_owner = payslip.employee.user_id == request.user.id
    is_hr = (
        request.user.is_staff or request.user.has_perm('timesheets.view_employee')
        or request.user.groups.filter(name='HR Personnel').exists()
    )
    if not (is_owner or is_hr):
        return HttpResponseForbidden("You don't have permission to view this payslip.")

    from .pdf import generate_payslip_pdf
    pdf_bytes = generate_payslip_pdf(payslip)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=payslip-{payslip.employee.employee_id}-{payslip.period_start.strftime("%Y-%m")}.pdf'
    return response


@hr_required
def salary_structure_list(request):
    """List pay policies (hours/overtime/weekend/holiday multipliers), in-app instead of Django admin."""
    structures = SalaryStructure.objects.all()
    context = {
        'structures': structures,
        'can_add': request.user.has_perm('timesheets.add_salarystructure'),
    }
    return render(request, 'timesheets/salary_structure_list.html', context)


@hr_manager_required
def salary_structure_add(request):
    """Add a new salary/pay policy structure"""
    if request.method == 'POST':
        form = SalaryStructureForm(request.POST)
        if form.is_valid():
            structure = form.save()
            messages.success(request, f'Salary structure "{structure.name}" has been added successfully.')
            return redirect('timesheets:salary_structure_list')
    else:
        form = SalaryStructureForm()

    context = {
        'form': form,
        'title': 'Add Salary Structure',
        'submit_text': 'Add Structure',
    }
    return render(request, 'timesheets/salary_structure_form.html', context)


@hr_required
def holiday_list(request):
    """List public holidays, in-app instead of Django admin."""
    holidays = Holiday.objects.all()
    context = {
        'holidays': holidays,
        'can_add': request.user.has_perm('timesheets.add_holiday'),
    }
    return render(request, 'timesheets/holiday_list.html', context)


@hr_manager_required
def holiday_add(request):
    """Add a public holiday date"""
    if request.method == 'POST':
        form = HolidayForm(request.POST)
        if form.is_valid():
            holiday = form.save()
            messages.success(request, f'{holiday.name} ({holiday.date}) has been added.')
            return redirect('timesheets:holiday_list')
    else:
        form = HolidayForm()

    context = {
        'form': form,
        'title': 'Add Holiday',
        'submit_text': 'Add Holiday',
    }
    return render(request, 'timesheets/holiday_form.html', context)


@hr_required
@require_http_methods(["GET"])
def employee_search_api(request):
    """API endpoint for employee search (for AJAX requests)"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse({'employees': []})
    
    employees = Employee.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(employee_id__icontains=query)
    ).filter(employment_status='active')[:10]
    
    employee_data = [
        {
            'id': emp.pk,
            'name': emp.full_name,
            'employee_id': emp.employee_id,
            'department': emp.department.name,
            'position': emp.position.title,
        }
        for emp in employees
    ]
    
    return JsonResponse({'employees': employee_data})


from django.utils import timezone
from .models import CheckInLocation, EmployeeStatus, Geofence, LocationHistory


@login_required
def location_tracking(request):
    """Location tracking dashboard"""
    today = timezone.now().date()
    
    # Get today's check-ins
    _today_start, _today_end = local_day_range_utc(today)
    todays_checkins = CheckInLocation.objects.filter(
        timestamp__gte=_today_start, timestamp__lt=_today_end,
        check_type='in'
    ).select_related('employee').order_by('-timestamp')
    
    # Get current employee statuses
    employee_statuses = EmployeeStatus.objects.select_related('employee', 'current_geofence').all()
    
    # Get active geofences
    geofences = Geofence.objects.filter(is_active=True)
    
    context = {
        'todays_checkins': todays_checkins,
        'employee_statuses': employee_statuses,
        'geofences': geofences,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''), # Make sure to add this to your settings
    }

    return render(request, 'timesheets/location_tracking.html', context)


@hr_manager_required
def geofence_list(request):
    """List all geofences"""
    geofences = Geofence.objects.all()
    context = {'geofences': geofences}
    return render(request, 'timesheets/geofence_list.html', context)


@hr_manager_required
def geofence_add(request):
    """Add a new geofence"""
    if request.method == 'POST':
        form = GeofenceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Geofence has been added successfully.')
            return redirect('timesheets:geofence_list')
    else:
        form = GeofenceForm()
    
    context = {
        'form': form,
        'title': 'Add New Geofence',
        'submit_text': 'Add Geofence',
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''),
    }

    return render(request, 'timesheets/geofence_form.html', context)


@hr_required
def location_history(request, employee_id):
    """Display location history for an employee"""
    employee = get_object_or_404(Employee, pk=employee_id)
    
    # Get date from query params
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            selected_date = timezone.now().date()
    else:
        selected_date = timezone.now().date()
    
    _hist_start, _hist_end = local_day_range_utc(selected_date)
    history = LocationHistory.objects.filter(
        employee=employee,
        timestamp__gte=_hist_start, timestamp__lt=_hist_end,
    ).order_by('timestamp')
    
    context = {
        'employee': employee,
        'history': history,
        'selected_date': selected_date,
        'google_maps_api_key': getattr(settings, 'GOOGLE_MAPS_API_KEY', ''),
    }

    return render(request, 'timesheets/location_history.html', context)

class EmployeeTimesheetView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = "timesheets/employee_timesheet.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        records = (
            CheckInLocation.objects
            .filter(employee=self.object)
            .order_by("timestamp")
        )

        context["records"] = records
        context["daily_hours"] = calculate_daily_hours(records)

        return context


@hr_required
def daily_time_record(request, employee_id):
    """
    The Daily Time Record (DTR) for one employee, one month: the real
    basis a monthly payroll run is prepared from -- not just a display of
    GPS pings, but the reviewable/editable record of present/absent/on
    leave/unpaid leave days per timesheets.services.attendance_service,
    which payroll_service.compute_payslip_salaried reads directly to
    auto-deduct any day marked 'unpaid_leave' (leave taken after the
    employee's annual balance was already used up).
    """
    from .services.attendance_service import generate_daily_attendance, compute_undertime_deduction

    employee = get_object_or_404(Employee, pk=employee_id)
    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    records = generate_daily_attendance(employee, period_start, period_end)
    undertime = compute_undertime_deduction(employee, period_start.year)

    from projects.models import Project
    from .services.project_hours import day_allocations, month_breakdown, pay_rates
    allocations = day_allocations(employee, period_start, period_end)
    for r in records:
        info = allocations.get(r.date)
        r.alloc = info
        r.alloc_json = json.dumps([
            {"project": row["project"].pk, "regular": str(row["regular"]), "overtime": str(row["overtime"])} for row in info["rows"]
        ]) if info else "[]"
    breakdown, breakdown_totals = month_breakdown(employee, period_start, period_end)

    context = {
        "employee": employee,
        "records": records,
        "breakdown": breakdown,
        "breakdown_totals": breakdown_totals,
        "projects": Project.objects.exclude(status="archived").order_by("name"),
        "can_split": is_hr_manager(request.user),
        "ot_multiplier": pay_rates(employee)[1],
        "period_start": period_start,
        "month_param": period_start.strftime("%Y-%m"),
        "status_choices": DailyAttendanceRecord.STATUS_CHOICES,
        "present_count": sum(1 for r in records if r.status == 'present'),
        "absent_count": sum(1 for r in records if r.status == 'absent'),
        "unpaid_leave_count": sum(1 for r in records if r.status == 'unpaid_leave'),
        "undertime": undertime,
    }
    return render(request, "timesheets/daily_time_record.html", context)


@hr_manager_required
@require_http_methods(["POST"])
def dtr_fill_defaults(request, employee_id):
    """One click: the empty working days of the month (no check-in, not Friday / holiday / leave / future) get the default 08:00-16:00."""
    from .services.attendance_service import fill_default_hours

    employee = get_object_or_404(Employee, pk=employee_id)
    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    filled = fill_default_hours(employee, period_start, period_end)
    messages.success(request, f"{filled} empty working day(s) set to 08:00-16:00." if filled else "No empty working days to fill.")
    return redirect(f"{reverse('timesheets:daily_time_record', args=[employee.pk])}?month={period_start.strftime('%Y-%m')}")


@hr_manager_required
@require_http_methods(["POST"])
def dtr_project_hours_save(request, employee_id):
    """Split (or reset) one day of an employee's DTR over projects: rows of project + regular hours + overtime hours."""
    from projects.models import Project
    from .models import EmployeeProjectHours

    employee = get_object_or_404(Employee, pk=employee_id)
    try:
        day = datetime.strptime(request.POST.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        messages.error(request, "Bad date.")
        return redirect("timesheets:daily_time_record", employee_id=employee.pk)
    back = f"{reverse('timesheets:daily_time_record', args=[employee.pk])}?month={day.strftime('%Y-%m')}"

    if request.POST.get("action") == "reset":
        EmployeeProjectHours.objects.filter(employee=employee, date=day).delete()
        messages.success(request, f"{day}: back to the hours from the daily reports.")
        return redirect(back)

    def _hours(raw):
        try:
            value = Decimal((raw or "0").strip() or "0")
        except InvalidOperation:
            return None
        return value if Decimal("0") <= value <= Decimal("24") else None

    merged = {}
    for project_id, regular, overtime in zip(
        request.POST.getlist("project"), request.POST.getlist("regular"), request.POST.getlist("overtime")
    ):
        if not project_id:
            continue
        regular_h, overtime_h = _hours(regular), _hours(overtime)
        if regular_h is None or overtime_h is None:
            messages.error(request, "Hours must be numbers between 0 and 24.")
            return redirect(back)
        if regular_h == 0 and overtime_h == 0:
            continue
        item = merged.setdefault(int(project_id), [Decimal("0"), Decimal("0")])
        item[0] += regular_h
        item[1] += overtime_h
    if any(r + o > 24 for r, o in merged.values()) or sum(r + o for r, o in merged.values()) > 24:
        messages.error(request, "A day cannot have more than 24 hours in total.")
        return redirect(back)
    projects = {p.pk: p for p in Project.objects.filter(pk__in=merged)}

    with transaction.atomic():
        EmployeeProjectHours.objects.filter(employee=employee, date=day).delete()
        for project_id, (regular_h, overtime_h) in merged.items():
            if project_id in projects:
                EmployeeProjectHours.objects.create(
                    employee=employee, project=projects[project_id], date=day, regular_hours=regular_h,
                    overtime_hours=overtime_h, updated_by=request.user,
                )
    messages.success(request, f"{day}: hours split over {len(merged)} project(s).")
    return redirect(back)


@hr_required
def export_dtr_excel(request, employee_id):
    """DTR Excel export: one row per day plus a formatted summary/totals block, mirrors the on-screen table."""
    from .services.attendance_service import generate_daily_attendance
    from .pdf import STATUS_LABELS

    employee = get_object_or_404(Employee, pk=employee_id)
    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    records = generate_daily_attendance(employee, period_start, period_end)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DTR"

    ws.append([f"Daily Time Record - {employee.full_name} - {period_start.strftime('%B %Y')}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    headers = ["Date", "Day", "Status", "Clock In", "Clock Out", "Late (min)", "Undertime (min)", "Overtime (h)", "Notes"]
    ws.append(headers)
    header_row = ws.max_row

    status_fills = {
        "unpaid_leave": PatternFill(start_color="FFE0B2", end_color="FFE0B2", fill_type="solid"),
        "absent": PatternFill(start_color="F8D7DA", end_color="F8D7DA", fill_type="solid"),
    }
    counts = {}
    total_overtime = 0
    total_late = 0
    total_undertime = 0
    for r in records:
        counts[r.status] = counts.get(r.status, 0) + 1
        total_overtime += float(r.overtime_hours)
        total_late += r.late_minutes
        total_undertime += r.undertime_minutes
        ws.append([
            r.date.strftime("%Y-%m-%d"), r.date.strftime("%A"), STATUS_LABELS.get(r.status, r.status),
            r.clock_in.strftime("%H:%M") if r.clock_in else "", r.clock_out.strftime("%H:%M") if r.clock_out else "",
            r.late_minutes, r.undertime_minutes, float(r.overtime_hours), r.notes,
        ])
        if r.status in status_fills:
            for c in range(1, len(headers) + 1):
                ws.cell(row=ws.max_row, column=c).fill = status_fills[r.status]

    _style_excel_header(ws, len(headers), row=header_row)
    _autosize_excel_columns(ws, [12, 12, 14, 10, 10, 11, 14, 12, 30])

    ws.append([])
    ws.append(["Summary"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, size=12)
    summary_rows = [
        ("Present", counts.get("present", 0)), ("Absent", counts.get("absent", 0)),
        ("On Leave", counts.get("on_leave", 0)), ("Unpaid Leave", counts.get("unpaid_leave", 0)),
        ("Rest Day", counts.get("rest_day", 0)), ("Holiday", counts.get("holiday", 0)),
        ("Total Overtime (h)", total_overtime), ("Total Late (min)", total_late),
        ("Total Undertime (min)", total_undertime),
    ]
    for label, value in summary_rows:
        ws.append([label, value])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename=dtr-{employee.employee_id}-{period_start.strftime('%Y-%m')}.xlsx"
    wb.save(response)
    return response


@hr_required
def export_dtr_pdf(request, employee_id):
    """PDF twin of export_dtr_excel (see timesheets/pdf.py)."""
    from .services.attendance_service import generate_daily_attendance
    from .pdf import generate_dtr_pdf

    employee = get_object_or_404(Employee, pk=employee_id)
    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    records = generate_daily_attendance(employee, period_start, period_end)
    generated_by = request.user.get_full_name() or request.user.username

    pdf_bytes = generate_dtr_pdf(employee, records, period_start, generated_by=generated_by)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=dtr-{employee.employee_id}-{period_start.strftime('%Y-%m')}.pdf"
    return response


@hr_manager_required
@require_http_methods(["POST"])
def daily_time_record_update_row(request, pk):
    """Correct one day's status/clock times/late/undertime/overtime on an employee's DTR."""
    record = get_object_or_404(DailyAttendanceRecord, pk=pk)

    status = request.POST.get('status')
    if status in dict(DailyAttendanceRecord.STATUS_CHOICES):
        record.status = status

    def _time(field):
        raw = request.POST.get(field, '').strip()
        if not raw:
            return None
        try:
            return datetime.strptime(raw, '%H:%M').time()
        except ValueError:
            return None

    def _int(field):
        raw = request.POST.get(field, '').strip()
        return int(raw) if raw.isdigit() else 0

    def _decimal(field):
        raw = request.POST.get(field, '').strip()
        try:
            return Decimal(raw) if raw else Decimal('0')
        except InvalidOperation:
            return Decimal('0')

    record.clock_in = _time('clock_in')
    record.clock_out = _time('clock_out')
    record.late_minutes = _int('late_minutes')
    record.undertime_minutes = _int('undertime_minutes')
    record.overtime_hours = _decimal('overtime_hours')
    record.notes = request.POST.get('notes', '')[:255]
    record.save()

    messages.success(request, f'Updated {record.date} for {record.employee.full_name}.')
    return redirect(
        f"{reverse('timesheets:daily_time_record', args=[record.employee_id])}?month={record.date.strftime('%Y-%m')}"
    )


class EmployeeAttendanceSummaryView(LoginRequiredMixin, DetailView):
    model = Employee
    template_name = "timesheets/attendance_summary.html"
    context_object_name = "employee"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        records = (
            CheckInLocation.objects
            .filter(employee=self.object)
            .order_by("timestamp")
        )

        daily_hours = calculate_daily_hours(records)

        monthly = {}
        for day, seconds in daily_hours.items():
            key = day.replace(day=1)
            monthly.setdefault(key, 0)
            monthly[key] += seconds / 3600

        context["monthly_summary"] = sorted(monthly.items(), reverse=True)
        return context

class EmployeeMapView(LoginRequiredMixin, TemplateView):
    """One calendar day at a time: who clocked in/out that day (list) and where (map pins). Default day: today."""
    template_name = "timesheets/employee_map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        today = timezone.localdate()
        try:
            day = datetime.strptime(self.request.GET.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            day = today

        tz = timezone.get_current_timezone()
        start = timezone.make_aware(datetime.combine(day, datetime.min.time()), tz)
        records = (
            CheckInLocation.objects
            .filter(timestamp__gte=start, timestamp__lt=start + timedelta(days=1))
            .select_related("employee", "employee__position", "project")
            .order_by("timestamp")
        )

        # json_script cannot serialize a QuerySet: plain dicts, timestamps as strings.
        locations, people = [], {}
        for location in records:
            local = timezone.localtime(location.timestamp)
            locations.append({
                "latitude": location.latitude,
                "longitude": location.longitude,
                "employee": location.employee.full_name,
                "employee_id": location.employee_id,
                "kind": location.check_type,
                "type": location.get_check_type_display(),
                "timestamp": local.strftime("%Y-%m-%d %H:%M:%S"),
                "time": local.strftime("%H:%M"),
                "address": location.address or "",
                "within_geofence": location.is_within_geofence,
            })
            person = people.setdefault(location.employee_id, {
                "id": location.employee_id,
                "name": location.employee.full_name,
                "position": location.employee.position.title if location.employee.position_id else "",
                "project": "", "first_in": None, "last_out": None, "outside": False,
            })
            if location.project_id and not person["project"]:
                person["project"] = location.project.name
            if not location.is_within_geofence:
                person["outside"] = True
            if location.check_type == "in" and person["first_in"] is None:
                person["first_in"] = local
            elif location.check_type == "out":
                person["last_out"] = local
        rows = []
        for person in sorted(people.values(), key=lambda x: x["first_in"] or x["last_out"]):
            hours = None
            if person["first_in"] and person["last_out"] and person["last_out"] > person["first_in"]:
                hours = round((person["last_out"] - person["first_in"]).total_seconds() / 3600, 1)
            rows.append({**person, "first_in": person["first_in"].strftime("%H:%M") if person["first_in"] else "",
                         "last_out": person["last_out"].strftime("%H:%M") if person["last_out"] else "", "hours": hours})

        context.update({
            "locations": locations,
            "people": rows,
            "day": day,
            "day_param": day.isoformat(),
            "prev_day": (day - timedelta(days=1)).isoformat(),
            "next_day": (day + timedelta(days=1)).isoformat() if day < today else "",
            "is_today": day == today,
            "today_param": today.isoformat(),
            "still_in": sum(1 for r in rows if r["first_in"] and not r["last_out"]),
        })
        return context


def _resolve_month_period(month_param):
    """('YYYY-MM' or None) -> (period_start, period_end) for that calendar month, default: the current month."""
    import calendar
    today = timezone.localdate()
    if month_param:
        try:
            period_start = datetime.strptime(month_param, "%Y-%m").date()
        except ValueError:
            period_start = today.replace(day=1)
    else:
        period_start = today.replace(day=1)
    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    return period_start, period_start.replace(day=last_day)


def _style_excel_header(ws, ncols, row=1):
    """Bold white-on-blue header row + frozen panes, shared by every HR Excel export."""
    header_fill = PatternFill(start_color="1F4788", end_color="1F4788", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


def _style_excel_totals_row(ws, row, ncols):
    """Bold, top-bordered, tinted totals row -- so a grand total is never just another row."""
    total_font = Font(bold=True)
    top_border = Border(top=Side(style="thin"))
    fill = PatternFill(start_color="DDE6F5", end_color="DDE6F5", fill_type="solid")
    for col in range(1, ncols + 1):
        cell = ws.cell(row=row, column=col)
        cell.font = total_font
        cell.border = top_border
        cell.fill = fill


def _autosize_excel_columns(ws, widths):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _payroll_employees(period_start, period_end):
    """
    The employees in a month's payroll run: every active employee, plus anyone added to the run by hand (they
    have a payslip for the month), minus those taken out of it on purpose (payslip status "excluded").
    """
    from .models import Payslip

    held = Payslip.objects.filter(period_start=period_start, period_end=period_end)
    excluded = set(held.filter(status='excluded').values_list('employee_id', flat=True))
    added = set(held.exclude(status='excluded').values_list('employee_id', flat=True))
    employees = list(
        Employee.objects.filter(Q(employment_status='active') | Q(pk__in=added)).exclude(pk__in=excluded)
        .select_related('department', 'position')
    )
    employees.sort(key=_payroll_sort_key)
    return employees


def _payroll_sort_key(employee):
    """The order of the payroll sheet: the placed employees by their position, then the not yet placed ones by name."""
    return (employee.payroll_order == 0, employee.payroll_order, employee.full_name)


@hr_manager_required
def payroll_run(request):
    """
    The real payroll workflow, in order: (1) generate/refresh this
    month's draft payslip for every active employee, (2) review and edit
    the HR-entered figures (overtime, allowances, deductions, advances,
    tax) right here, (3) "ترحيل" (Post) once it looks right -- after
    that, this month's payslips are locked and Export just reflects what
    was posted. Export is still available from here, but it's the last
    step, not the first.
    """
    from .models import Payslip, PayrollNote
    from .services.payroll_service import compute_payslip_salaried

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    payslips = []
    for emp in _payroll_employees(period_start, period_end):
        existing = Payslip.objects.filter(employee=emp, period_start=period_start, period_end=period_end).first()
        if existing and existing.status == 'posted':
            payslips.append(existing)
            continue
        # the overtime hours the employee's project split (DTR / daily reports) already shows are the starting figure; HR can overtype
        from .services.project_hours import month_breakdown
        split_rows, split_totals = month_breakdown(emp, period_start, period_end)
        typed_overtime = existing.overtime_hours if existing else 0
        payslip = compute_payslip_salaried(
            emp, period_start, period_end,
            overtime_hours=typed_overtime if typed_overtime else split_totals['overtime_hours'],
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            tax=existing.tax if existing else 0,
            generated_by=request.user,
        )
        payslips.append(payslip)

    payslips.sort(key=lambda p: _payroll_sort_key(p.employee))
    from .services.attendance_service import count_actual_days
    from .services.project_hours import month_breakdown
    for p in payslips:
        p.project_split, p.project_split_totals = month_breakdown(p.employee, period_start, period_end)
        p.auto_actual_days = count_actual_days(p.employee, period_start, period_end)   # days he really clocked in
        p.actual_days = p.auto_actual_days if p.manual_actual_days is None else p.manual_actual_days
    is_posted = bool(payslips) and all(p.status == 'posted' for p in payslips)

    context = {
        "payslips": payslips,
        "period_start": period_start,
        "period_end": period_end,
        "month_param": period_start.strftime("%Y-%m"),
        "is_posted": is_posted,
        "total_net": sum((p.net_pay for p in payslips), Decimal('0')),
        "totals": {
            key: sum((getattr(p, key) for p in payslips), Decimal('0'))
            for key in ('base_pay', 'overtime_hours', 'overtime_pay', 'other_allowances', 'gross_pay', 'other_deductions',
                        'unpaid_leave_deduction', 'advances', 'tax', 'net_pay')
        },
        "excluded": list(
            Payslip.objects.filter(period_start=period_start, period_end=period_end, status='excluded')
            .select_related('employee').order_by('employee__first_name', 'employee__last_name')
        ),
        # employees that are not in the run (left the company, on leave ...) but can be put in by hand
        "addable": list(
            Employee.objects.exclude(employment_status='active')
            .exclude(pk__in=[p.employee_id for p in payslips])
            .exclude(payslips__period_start=period_start, payslips__period_end=period_end, payslips__status='excluded')
            .order_by('first_name', 'last_name')
        ),
        "is_admin_user": request.user.is_admin(),
        "posted_count": sum(1 for p in payslips if p.status == "posted"),
        "notes": list(PayrollNote.objects.filter(period_start=period_start)),
    }
    return render(request, "timesheets/payroll_run.html", context)


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_update_row(request, pk):
    """Update one employee's HR-entered payroll figures for this run (blocked once posted)."""
    from .models import Payslip
    from .services.payroll_service import auto_base_pay, auto_unpaid_leave, compute_payslip_salaried

    payslip = get_object_or_404(Payslip, pk=pk)
    if payslip.status == 'excluded':
        messages.error(request, 'This employee is excluded from the month; restore them first.')
        return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")
    if payslip.status == 'posted':
        messages.error(request, 'This payroll run has already been posted and can no longer be edited.')
        return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")

    def _decimal(field, default='0'):
        raw = request.POST.get(field, '').strip()
        try:
            return Decimal(raw) if raw else Decimal(default)
        except InvalidOperation:
            return Decimal(default)

    def _typed_or_auto(field, auto_value):
        """A figure HR typed over the automatic one is kept as a manual override; the automatic value (or blank) means automatic."""
        raw = request.POST.get(field, '').strip()
        if not raw:
            return None
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return None
        return None if abs(value - auto_value) < Decimal('0.01') else value

    employee, start, end = payslip.employee, payslip.period_start, payslip.period_end
    extra = {}
    if 'deductions' in request.POST:
        # مقتطعات as in the company's sheet: one number that already contains the unpaid-leave deduction. What is above that
        # deduction is the typed "other deductions"; a smaller number replaces the unpaid-leave deduction itself.
        total = _decimal('deductions')
        unpaid = payslip.unpaid_leave_deduction
        if total >= unpaid:
            other_deductions = total - unpaid
        else:
            other_deductions = Decimal('0')
            extra['manual_unpaid_leave_deduction'] = total
    else:
        other_deductions = _decimal('other_deductions')
        extra['manual_unpaid_leave_deduction'] = _typed_or_auto('unpaid_leave_deduction', auto_unpaid_leave(employee, start, end)[1])
    compute_payslip_salaried(
        employee, start, end,
        overtime_hours=_decimal('overtime_hours'),
        other_allowances=_decimal('other_allowances'),
        other_deductions=other_deductions,
        advances=_decimal('advances'),
        tax=_decimal('tax'),
        generated_by=request.user,
        manual_base_pay=_typed_or_auto('base_pay', auto_base_pay(employee, start, end)),
        **extra,
    )
    if 'actual_days' in request.POST:
        # attendance days typed over the counted ones are kept as a manual figure; the counted value (or blank) means automatic
        from .services.attendance_service import count_actual_days
        raw = request.POST.get('actual_days', '').strip()
        try:
            typed = Decimal(raw) if raw else None
        except InvalidOperation:
            typed = None
        if typed is not None and (typed < 0 or typed > 366):
            typed = None
        if typed is not None and abs(typed - count_actual_days(employee, start, end)) < Decimal('0.01'):
            typed = None
        Payslip.objects.filter(pk=payslip.pk).update(manual_actual_days=typed)
    messages.success(request, f'Updated {payslip.employee.full_name}.')
    return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")


@hr_manager_required
@require_http_methods(["POST"])
def payroll_note_save(request):
    """Add a note under the month's payroll table (no `pk`), or change one (`pk`); an empty text on an existing note deletes it."""
    from .models import PayrollNote

    period_start, _ = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:payroll_run')}?month={period_start.strftime('%Y-%m')}#payroll-notes")
    text = " ".join((request.POST.get("text") or "").split())[:500]
    pk = request.POST.get("pk")
    if pk:
        note = get_object_or_404(PayrollNote, pk=pk)
        if not text:
            note.delete()
            messages.info(request, 'The note was deleted.')
        else:
            note.text = text
            note.save(update_fields=['text'])
        return back
    if not text:
        messages.error(request, 'Write the note first.')
        return back
    last = PayrollNote.objects.filter(period_start=period_start).order_by('-order').first()
    PayrollNote.objects.create(period_start=period_start, text=text, order=(last.order + 1) if last else 1, created_by=request.user)
    return back


@hr_manager_required
@require_http_methods(["POST"])
def payroll_note_delete(request, pk):
    from .models import PayrollNote

    note = get_object_or_404(PayrollNote, pk=pk)
    month = note.period_start.strftime('%Y-%m')
    note.delete()
    return redirect(f"{reverse('timesheets:payroll_run')}?month={month}#payroll-notes")


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_reorder(request):
    """
    Save the order the employees were dragged into on the Payroll Run page (also used by its Excel and PDF). `ids` is the
    employees' ids in the new order. The order belongs to the employee, so it carries over to the next months; it changes
    nothing about money, so it is also allowed on a posted month. Anybody in the month who is not listed keeps his place after them.
    """
    from django.db import transaction

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    employees = _payroll_employees(period_start, period_end)
    known = {e.pk: e for e in employees}
    wanted = []
    for raw in (request.POST.get("ids") or "").split(","):
        if raw.strip().isdigit() and int(raw) in known and int(raw) not in wanted:
            wanted.append(int(raw))
    ordered = [known[i] for i in wanted] + [e for e in employees if e.pk not in wanted]
    with transaction.atomic():
        for position, employee in enumerate(ordered, start=1):
            if employee.payroll_order != position:
                Employee.objects.filter(pk=employee.pk).update(payroll_order=position)
    return JsonResponse({"ok": True, "count": len(ordered)})


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_reopen(request):
    """
    Admin only: take posted payslips back to draft so their figures can be typed again (then saved and posted again).
    With `pk` it reopens that one employee, without it every posted payslip of the month. Nothing else changes: the
    figures stay as they were until they are edited, and an excluded employee stays excluded.
    """
    import logging
    from .models import Payslip

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:payroll_run')}?month={period_start.strftime('%Y-%m')}")
    if not request.user.is_admin():
        messages.error(request, 'Only an admin can reopen posted payroll.')
        return back
    posted = Payslip.objects.filter(period_start=period_start, period_end=period_end, status='posted')
    pk = request.POST.get("pk")
    if pk:
        posted = posted.filter(pk=pk)
    names = list(posted.select_related('employee').values_list('employee__first_name', 'employee__last_name'))
    count = posted.update(status='draft', posted_at=None, posted_by=None)
    if not count:
        messages.info(request, 'Nothing to reopen.')
    elif pk and names:
        messages.warning(request, f'{names[0][0]} {names[0][1]} was reopened for editing. Save the changes, then post the payroll again.')
    else:
        messages.warning(request, f'{period_start:%B %Y} was reopened for editing ({count} employee(s)). Save the changes, then post the payroll again.')
    logging.getLogger(__name__).warning('Payroll %s reopened by %s (%s payslips%s)', period_start.strftime('%Y-%m'),
                                         request.user.username, count, f', pk={pk}' if pk else '')
    return back


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_exclude(request, pk):
    """
    Take one employee out of this month's run (so posting the month leaves them out). Nothing is deleted: they are listed
    under "Excluded" and can be put back. A posted payslip can be excluded by an admin only.
    """
    from .models import Payslip

    payslip = get_object_or_404(Payslip, pk=pk)
    month = payslip.period_start.strftime('%Y-%m')
    if payslip.status == 'posted' and not request.user.is_admin():
        messages.error(request, 'Only an admin can take an employee out of a posted month.')
    else:
        payslip.status, payslip.posted_at, payslip.posted_by = 'excluded', None, None
        payslip.save()
        messages.success(request, f'{payslip.employee.full_name} was taken out of the {payslip.period_start:%B %Y} payroll. They can be restored below.')
    return redirect(f"{reverse('timesheets:payroll_run')}?month={month}")


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_restore(request, pk):
    """Put an excluded employee back into the month's run (as a draft, recalculated)."""
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    payslip = get_object_or_404(Payslip, pk=pk, status='excluded')
    payslip.status = 'draft'
    payslip.save()
    compute_payslip_salaried(payslip.employee, payslip.period_start, payslip.period_end, generated_by=request.user,
                             overtime_hours=payslip.overtime_hours, other_allowances=payslip.other_allowances,
                             other_deductions=payslip.other_deductions, advances=payslip.advances, tax=payslip.tax)
    messages.success(request, f'{payslip.employee.full_name} is back in the {payslip.period_start:%B %Y} payroll.')
    return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_add(request):
    """Add an employee who is not in the run (not an active employee: left, on leave ...) to this month's payroll by hand."""
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:payroll_run')}?month={period_start.strftime('%Y-%m')}")
    employee = Employee.objects.filter(pk=request.POST.get("employee") or None).first()
    if not employee:
        messages.error(request, 'Pick an employee to add.')
        return back
    if Payslip.objects.filter(employee=employee, period_start=period_start, period_end=period_end, status='posted').exists():
        messages.error(request, f'{employee.full_name} is already posted for this month.')
        return back
    Payslip.objects.filter(employee=employee, period_start=period_start, period_end=period_end, status='excluded').update(status='draft')
    compute_payslip_salaried(employee, period_start, period_end, generated_by=request.user)
    messages.success(request, f'{employee.full_name} was added to the {period_start:%B %Y} payroll. Review their figures, then save.')
    return back


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_post(request):
    """ترحيل -- finalize this month's draft payslips, locking them against further edits."""
    from .models import Payslip

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    updated = Payslip.objects.filter(
        period_start=period_start, period_end=period_end, status='draft',
    ).update(status='posted', posted_by=request.user, posted_at=timezone.now())

    if updated:
        messages.success(request, f'Posted payroll for {period_start.strftime("%B %Y")} ({updated} employee(s)).')
    else:
        messages.info(request, 'Nothing to post -- this payroll run is already posted or empty.')
    return redirect(f"{reverse('timesheets:payroll_run')}?month={period_start.strftime('%Y-%m')}")


def _payroll_slips_for_export(request, period_start, period_end):
    """The month's payslips in the order of the sheet (the same people and order as the Payroll Run page)."""
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    slips = []
    for emp in _payroll_employees(period_start, period_end):
        existing = Payslip.objects.filter(employee=emp, period_start=period_start, period_end=period_end).first()
        if existing and existing.status == "posted":
            slips.append(existing)
            continue
        from .services.project_hours import month_breakdown
        typed_overtime = existing.overtime_hours if existing else 0
        slips.append(compute_payslip_salaried(
            emp, period_start, period_end,
            overtime_hours=typed_overtime if typed_overtime else month_breakdown(emp, period_start, period_end)[1]['overtime_hours'],
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            tax=existing.tax if existing else 0,
            generated_by=request.user,
        ))
    return slips


@login_required
def export_payroll_excel(request):
    """
    The employee payroll of a month (?month=YYYY-MM) as the company's salary sheet: same columns, right-to-left, one landscape
    page, totals, prepared/reviewed line and the notes written under the table (see timesheets.payroll_sheet_excel). It reflects what the
    Payroll Run page holds for that month (draft or posted); employees taken out of the month are left out.
    """
    from .models import PayrollNote
    from .payroll_sheet_excel import build_payroll_workbook

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    slips = _payroll_slips_for_export(request, period_start, period_end)
    notes = list(PayrollNote.objects.filter(period_start=period_start).values_list('text', flat=True))
    wb = build_payroll_workbook(slips, period_start, notes, period_end)
    from .payroll_project_split import add_split_sheet, split_data
    people, projects = split_data(slips, period_start, period_end)
    add_split_sheet(wb, people, projects, period_start, period_end)
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename=payroll-{period_start.strftime('%Y-%m')}.xlsx"
    wb.save(response)
    return response


@login_required
def export_payroll_pdf(request):
    """PDF twin of export_payroll_excel: the company's salary sheet, same numbers and the same notes."""
    from .models import PayrollNote
    from .payroll_sheet_pdf import generate_payroll_sheet_pdf

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    slips = _payroll_slips_for_export(request, period_start, period_end)
    notes = list(PayrollNote.objects.filter(period_start=period_start).values_list('text', flat=True))
    from .payroll_project_split import generate_split_pdf, merge_pdfs, split_data
    people, projects = split_data(slips, period_start, period_end)
    pdf = merge_pdfs(generate_payroll_sheet_pdf(slips, period_start, notes, period_end),
                     generate_split_pdf(people, projects, period_start, period_end))
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=payroll-{period_start.strftime('%Y-%m')}.pdf"
    return response


@login_required
def export_daily_workers_payroll_excel(request):
    """
    Monthly pay for day-labor workers (?month=YYYY-MM, default: current
    month), pulled from reports.DailyReportWorkerAttendance rows already
    logged against whichever project's daily report a site engineer
    filled in -- a worker who moved between several projects this month
    has their hours from every one of them picked up automatically. See
    timesheets.services.daily_worker_payroll_service.

    Three sheets: "Summary" (one row per worker, company-wide totals),
    "By Project" (one row per project, totalled across every worker who
    worked there) and "Details" (one row per worker per project, with each
    project's share of that worker's pay this month).
    """
    import calendar
    from .services.daily_worker_payroll_service import compute_all_daily_workers_summary, project_totals

    month_param = request.GET.get("month")
    today = timezone.localdate()
    if month_param:
        try:
            period_start = datetime.strptime(month_param, "%Y-%m").date()
        except ValueError:
            period_start = today.replace(day=1)
    else:
        period_start = today.replace(day=1)
    last_day = calendar.monthrange(period_start.year, period_start.month)[1]
    period_end = period_start.replace(day=last_day)

    statements = compute_all_daily_workers_summary(period_start, period_end)

    wb = openpyxl.Workbook()
    summary_ws = wb.active
    summary_ws.title = "Summary"
    summary_ws.append(["Worker", "National ID", "Trade", "Total Days", "Overtime Hours", "Total Pay", "Projects Worked"])
    for s in statements:
        summary_ws.append([
            s["worker"].full_name, s["worker"].national_id or "", s["worker"].trade,
            float(s["total_days"]), float(s["total_overtime_hours"]), float(s["total_pay"]),
            len(s["by_project"]),
        ])

    project_ws = wb.create_sheet("By Project")
    project_ws.append(["Project", "Workers", "Days", "Overtime Hours", "Base Pay", "Overtime Pay", "Total Pay"])
    for row in project_totals(statements):
        project_ws.append([
            row["project"].name if row["project"] else "(no project)", row["workers"],
            float(row["days"]), float(row["overtime_hours"]),
            float(row["base_pay"]), float(row["overtime_pay"]), float(row["pay"]),
        ])

    detail_ws = wb.create_sheet("Details")
    detail_ws.append(["Worker", "National ID", "Project", "Days", "Overtime Hours", "Base Pay", "Overtime Pay", "Pay", "Share %"])
    for s in statements:
        for row in s["by_project"]:
            detail_ws.append([
                s["worker"].full_name, s["worker"].national_id or "",
                row["project"].name if row["project"] else "(no project)",
                float(row["days"]), float(row["overtime_hours"]),
                float(row["base_pay"]), float(row["overtime_pay"]), float(row["pay"]), float(row["pay_share_pct"]),
            ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f"attachment; filename=daily-workers-payroll-{period_start.strftime('%Y-%m')}.xlsx"
    wb.save(response)
    return response


def _user_note(note):
    """A note somebody typed on a manual line; the markers the importer / Duplicate used to leave are not notes."""
    note = note or ''
    return '' if note.startswith(('Imported from', 'Copied from')) else note


@wages_access_required
def wages_run(request):
    """
    كشف الصرف -- the day-labor equivalent of payroll_run: (1)
    generate/refresh this month's draft DailyWorkerPayslip for every
    active worker who has at least one attendance entry that month, (2)
    review and edit the HR-entered figures (allowances, deductions,
    advances) inline, (3) "ترحيل" (Post) once it looks right. Never
    exports straight to Excel/PDF without this review step first, same
    principle as the salaried Payroll Run.
    """
    from .models import DailyWorkerPayslip
    from .services.daily_worker_payroll_service import (
        compute_all_daily_workers_summary, compute_daily_worker_payslip, compute_daily_worker_statement, project_totals,
        prune_empty_draft_slips,
    )

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    prune_empty_draft_slips(period_start, period_end)  # rows whose entries were cleared must not linger as zeros
    wage_slips = []
    for worker in DailyWorker.objects.filter(is_active=True).order_by('full_name'):
        existing = DailyWorkerPayslip.objects.filter(worker=worker, period_start=period_start, period_end=period_end).first()
        if existing and existing.status == 'posted':
            wage_slips.append(existing)
            continue
        statement = compute_daily_worker_statement(worker, period_start, period_end)
        if not statement['by_project'] and not existing:
            continue  # no attendance this month and never had a slip -- nothing to review
        wage_slips.append(compute_daily_worker_payslip(
            worker, period_start, period_end,
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            generated_by=request.user,
        ))

    is_posted = bool(wage_slips) and all(w.status == 'posted' for w in wage_slips)

    context = {
        "wage_slips": wage_slips,
        "period_start": period_start,
        "period_end": period_end,
        "month_param": period_start.strftime("%Y-%m"),
        "is_posted": is_posted,
        "total_net": sum((w.net_pay for w in wage_slips), Decimal('0')),
        "project_totals": project_totals(compute_all_daily_workers_summary(period_start, period_end)),
        "active_tab": request.GET.get("tab") if request.GET.get("tab") in ("sheet", "manual") else "run",
        # who may do what: HR prepares and posts, the accountant approves (then the payment vouchers can be printed)
        "can_edit_wages": is_hr_manager(request.user) or request.user.is_admin(),
        "can_approve": request.user.is_admin() or request.user.is_accountant(),
        "approved_count": sum(1 for w in wage_slips if w.accounting_approved_at),
        "all_approved": bool(wage_slips) and all(w.accounting_approved_at for w in wage_slips),
    }
    if context["active_tab"] == "manual" and not request.user.is_admin():
        context["active_tab"] = "run"
    from .services.daily_worker_payroll_service import wages_sheet
    if request.GET.get("tab") == "sheet":
        context["sheet"] = wages_sheet(period_start, period_end)
    if request.user.is_admin():
        from projects.models import Project
        from .models import DailyWorkerManualEntry
        manual_project = Project.objects.filter(pk=request.GET.get("manual_project") or None).first()
        manual_rows = []
        if manual_project:
            saved = list(DailyWorkerManualEntry.objects.filter(
                project=manual_project, period_start=period_start,
            ).select_related('worker'))
            posted = set(
                DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end, status='posted')
                .values_list('worker_id', flat=True)
            )
            # Only workers already entered for this project/month are listed (others are added by name), grouped by sub-group (متفرقات).
            blocks = {}
            for entry in sorted(saved, key=lambda e: (e.sub_name, e.worker.full_name)):
                blocks.setdefault(entry.sub_name, []).append({
                    "worker": {"id": entry.worker_id, "name": entry.worker.full_name, "trade": entry.worker.trade or "—",
                               "national_id": entry.worker.national_id or "—"},
                    "note": _user_note(entry.note),
                    "days": str(entry.days), "rate": str(entry.daily_rate), "ot": str(entry.overtime_hours),
                    "advances": str(entry.advances), "locked": entry.worker_id in posted,
                })
            manual_rows = saved
            context["manual_blocks"] = [{"name": name, "rows": rows} for name, rows in blocks.items()]
            context["manual_has_subs"] = any(name for name in blocks)
            from reports.daily_detail_models import ProjectSub
            context["project_subs"] = list(ProjectSub.objects.filter(project=manual_project, is_active=True).values_list("name", flat=True))
            labels = {}
            roster = []
            for worker in DailyWorker.objects.filter(is_active=True).order_by('full_name'):
                label = f"{worker.full_name} — {worker.trade}" if worker.trade else worker.full_name
                if label in labels:
                    label = f"{label} #{worker.pk}"
                labels[label] = worker.pk
                roster.append({"id": worker.pk, "label": label, "name": worker.full_name, "trade": worker.trade or "—",
                               "rate": str(worker.daily_rate), "national_id": worker.national_id or "—",
                               "locked": worker.pk in posted})
            context["manual_roster"] = roster
        from django.db.models import Count
        context.update({
            "month_projects": list(
                DailyWorkerManualEntry.objects.filter(period_start=period_start)
                .values('project_id', 'project__name').annotate(n=Count('id')).order_by('project__name')
            ),
            "can_add_manual": True,
            "month_total_lines": DailyWorkerManualEntry.objects.filter(period_start=period_start).count(),
            "manual_projects": Project.objects.order_by('name'),
            "manual_project": manual_project,
            "manual_rows": manual_rows,
        })
    return render(request, "timesheets/wages_run.html", context)


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_update_row(request, pk):
    """Edit one worker's allowances/deductions/advances for this month's كشف الصرف, while still draft."""
    from .models import DailyWorkerPayslip
    from .services.daily_worker_payroll_service import compute_daily_worker_payslip

    wage_slip = get_object_or_404(DailyWorkerPayslip, pk=pk)
    if wage_slip.status == 'posted':
        messages.error(request, 'This كشف صرف is already posted and can no longer be edited.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={wage_slip.period_start.strftime('%Y-%m')}")

    def _decimal(field, default='0'):
        raw = request.POST.get(field, '').strip()
        try:
            return Decimal(raw) if raw else Decimal(default)
        except InvalidOperation:
            return Decimal(default)

    compute_daily_worker_payslip(
        wage_slip.worker, wage_slip.period_start, wage_slip.period_end,
        other_allowances=_decimal('other_allowances'), other_deductions=_decimal('other_deductions'),
        advances=_decimal('advances'), generated_by=request.user,
    )
    messages.success(request, f'Updated {wage_slip.worker.full_name}.')
    return redirect(f"{reverse('timesheets:wages_run')}?month={wage_slip.period_start.strftime('%Y-%m')}")


from .services.daily_worker_payroll_service import prune_empty_draft_slips  # noqa: E402


def _month_is_posted_for(worker, period_start, period_end):
    from .models import DailyWorkerPayslip
    return DailyWorkerPayslip.objects.filter(
        worker=worker, period_start=period_start, period_end=period_end, status='posted',
    ).exists()


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_manual_save(request):
    """
    Exceptional, admin-only: the Wages Run's Manual Entry tab. For one project and
    month the form lists exactly the workers added by name (`workers`), each with
    TOTAL days, daily rate (اليومية) and overtime hours; base pay, overtime pay and
    the total are computed from them (see daily_worker_payroll_service). Saving makes
    the project/month match the form: listed workers are added or updated, and any
    earlier manual entry for a worker no longer listed (removed by mistake) is deleted.
    A worker whose month is already posted is left untouched.
    """
    from django.db import transaction
    from projects.models import Project
    from .models import DailyWorkerManualEntry

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    project = Project.objects.filter(pk=request.POST.get("project") or None).first()
    month = period_start.strftime('%Y-%m')
    back = redirect(
        f"{reverse('timesheets:wages_run')}?month={month}&tab=manual" + (f"&manual_project={project.pk}" if project else "")
    )

    if not request.user.is_admin():
        messages.error(request, 'Only an admin can use manual entry.')
        return back
    if not project:
        messages.error(request, 'Pick a project first.')
        return back

    def _num(name, ceiling):
        raw = request.POST.get(name, '').strip()
        if not raw:
            return Decimal('0')
        value = Decimal(raw)
        if value < 0 or value > ceiling:
            raise InvalidOperation
        return value

    # One form row per (worker, sub-group): `rows` lists their indexes; each row names its worker (w_), the block it sits
    # in (blk_) and the block's sub-group name (subname_<block>; blank = the project itself).
    rows = []
    for idx in request.POST.getlist("rows"):
        wid = request.POST.get(f"w_{idx}", "")
        if wid.isdigit():
            sub = " ".join(request.POST.get(f"subname_{request.POST.get(f'blk_{idx}', '0')}", "").split())[:120]
            rows.append((idx, int(wid), sub))
    listed = {(wid, sub) for _, wid, sub in rows}
    workers = {w.pk: w for w in DailyWorker.objects.filter(is_active=True, pk__in={wid for _, wid, _ in rows})}

    seen = set()
    for _, wid, sub in rows:
        if (wid, sub) in seen:
            name = workers[wid].full_name if wid in workers else f'#{wid}'
            messages.error(request, f"{name} is listed twice under {sub or 'the project itself'} (nothing was saved). Keep one line per worker in each sub.")
            return back
        seen.add((wid, sub))

    saved = removed = 0
    skipped_posted = []
    try:
        with transaction.atomic():
            for idx, wid, sub in rows:
                worker = workers.get(wid)
                if worker is None:
                    continue
                if _month_is_posted_for(worker, period_start, period_end):
                    skipped_posted.append(worker.full_name)
                    continue
                days = _num(f"days_{idx}", Decimal('366'))
                overtime = _num(f"ot_{idx}", Decimal('1000'))
                advances = _num(f"adv_{idx}", Decimal('10000000'))
                rate_raw = request.POST.get(f"rate_{idx}", '').strip()
                rate = Decimal(rate_raw) if rate_raw else worker.daily_rate
                if rate < 0:
                    raise InvalidOperation
                if days == 0 and overtime == 0 and advances == 0:
                    removed += DailyWorkerManualEntry.objects.filter(
                        worker=worker, project=project, period_start=period_start, sub_name=sub).delete()[0]
                    continue
                DailyWorkerManualEntry.objects.update_or_create(
                    worker=worker, project=project, period_start=period_start, sub_name=sub,
                    defaults={'days': days, 'daily_rate': rate, 'overtime_hours': overtime, 'advances': advances,
                              'note': request.POST.get(f"note_{idx}", "").strip()[:300], 'created_by': request.user},
                )
                saved += 1
            # Any line entered before but no longer in the form was removed on purpose.
            for entry in DailyWorkerManualEntry.objects.filter(project=project, period_start=period_start).select_related('worker'):
                if (entry.worker_id, entry.sub_name) in listed:
                    continue
                if _month_is_posted_for(entry.worker, period_start, period_end):
                    skipped_posted.append(entry.worker.full_name)
                    continue
                entry.delete()
                removed += 1
    except InvalidOperation:
        messages.error(request, 'Please enter valid, non-negative numbers (nothing was saved).')
        return back

    prune_empty_draft_slips(period_start, period_end)
    messages.success(request, f'{project.name}: saved {saved} line(s), removed {removed}.')
    if skipped_posted:
        messages.warning(request, 'Already posted, left unchanged: ' + ', '.join(skipped_posted))
    return back


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_manual_duplicate(request):
    """
    Admin-only: copy the manual entries of the ticked projects of one month into another, so next month starts
    from this month's workers, paid wages, days and overtime and is then adjusted by hand (a project that
    isn't running next month is simply left unticked). Advances belong to one
    month only, so they are copied just when asked. Lines that already exist in the target month are left as
    they are, and a worker whose target month is already posted is skipped.
    """
    from .models import DailyWorkerManualEntry

    source_start, source_end = _resolve_month_period(request.POST.get("month"))
    raw_target = (request.POST.get("target_month") or "").strip()
    try:
        datetime.strptime(raw_target, "%Y-%m")
    except ValueError:
        messages.error(request, 'Choose the month to copy into.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={source_start.strftime('%Y-%m')}&tab=manual")
    target_start, target_end = _resolve_month_period(raw_target)
    back = redirect(f"{reverse('timesheets:wages_run')}?month={target_start.strftime('%Y-%m')}&tab=manual")

    if not request.user.is_admin():
        messages.error(request, 'Only an admin can duplicate manual entries.')
        return back
    if target_start == source_start:
        messages.error(request, 'Pick a different month than the one being copied.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={source_start.strftime('%Y-%m')}&tab=manual")

    chosen = [int(x) for x in request.POST.getlist("projects") if x.isdigit()]
    if not chosen:
        messages.error(request, 'Tick at least one project to copy.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={source_start.strftime('%Y-%m')}&tab=manual")

    with_advances = request.POST.get("with_advances") == "on"
    copied = existing = skipped_posted = 0
    for entry in DailyWorkerManualEntry.objects.filter(period_start=source_start, project_id__in=chosen).select_related('worker'):
        if _month_is_posted_for(entry.worker, target_start, target_end):
            skipped_posted += 1
            continue
        _, created = DailyWorkerManualEntry.objects.get_or_create(
            worker=entry.worker, project=entry.project, period_start=target_start, sub_name=entry.sub_name,
            defaults={
                'days': entry.days, 'daily_rate': entry.daily_rate, 'overtime_hours': entry.overtime_hours,
                'advances': entry.advances if with_advances else 0,
                'note': _user_note(entry.note), 'created_by': request.user,
            },
        )
        if created:
            copied += 1
        else:
            existing += 1

    if not (copied or existing or skipped_posted):
        messages.warning(request, f'There were no manual entries in {source_start:%B %Y} to copy.')
    else:
        messages.success(request, f'Copied {copied} line(s) from {source_start:%B %Y} into {target_start:%B %Y}.')
        if existing:
            messages.info(request, f'{existing} line(s) already existed in {target_start:%B %Y} and were left as they are.')
        if skipped_posted:
            messages.warning(request, f'{skipped_posted} line(s) skipped: their {target_start:%B %Y} wages are already posted.')
    return back


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_manual_clear_project(request):
    """Admin-only: take a whole project out of a month by deleting all its manual entries there (posted workers stay)."""
    from projects.models import Project
    from .models import DailyWorkerManualEntry

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    project = Project.objects.filter(pk=request.POST.get("project") or None).first()
    back = redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}&tab=manual")
    if not request.user.is_admin():
        messages.error(request, 'Only an admin can remove manual entries.')
        return back
    if not project:
        messages.error(request, 'Pick a project first.')
        return back

    removed = kept = 0
    for entry in DailyWorkerManualEntry.objects.filter(project=project, period_start=period_start).select_related('worker'):
        if _month_is_posted_for(entry.worker, period_start, period_end):
            kept += 1
            continue
        entry.delete()
        removed += 1
    prune_empty_draft_slips(period_start, period_end)
    messages.success(request, f'{project.name}: removed {removed} line(s) from {period_start:%B %Y}.')
    if kept:
        messages.warning(request, f'{kept} line(s) kept: wages for those workers are already posted.')
    return back


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_manual_clear_month(request):
    """Admin-only "clear all": delete every manual entry (all projects) of one month. Posted workers' lines stay."""
    from .models import DailyWorkerManualEntry

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}&tab=manual")
    if not request.user.is_admin():
        messages.error(request, 'Only an admin can clear manual entries.')
        return back

    removed = kept = 0
    for entry in DailyWorkerManualEntry.objects.filter(period_start=period_start).select_related('worker'):
        if _month_is_posted_for(entry.worker, period_start, period_end):
            kept += 1
            continue
        entry.delete()
        removed += 1
    prune_empty_draft_slips(period_start, period_end)
    messages.success(request, f'Cleared {removed} manual line(s) from {period_start:%B %Y}.')
    if kept:
        messages.warning(request, f'{kept} line(s) kept: wages for those workers are already posted.')
    return back


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_delete_row(request, pk):
    """
    Delete one worker's row from a month's Wages Run, drafts and (admin only) posted ones alike. The worker's
    manual entries for that month go with it, so the row does not come back. Attendance recorded in daily reports
    belongs to those reports and is not touched here: if the worker still has some, the row is generated again
    and the message says where it comes from.
    """
    from .models import DailyWorkerManualEntry, DailyWorkerPayslip
    from .services.daily_worker_payroll_service import compute_daily_worker_statement

    slip = get_object_or_404(DailyWorkerPayslip, pk=pk)
    back = redirect(f"{reverse('timesheets:wages_run')}?month={slip.period_start.strftime('%Y-%m')}")
    if slip.status == 'posted' and not request.user.is_admin():
        messages.error(request, 'Only an admin can delete a posted row.')
        return back

    worker, start, end = slip.worker, slip.period_start, slip.period_end
    manual = DailyWorkerManualEntry.objects.filter(worker=worker, period_start=start).delete()[0]
    slip.delete()
    messages.success(request, f"Deleted {worker.full_name}'s row for {start:%B %Y}" + (f" and {manual} manual line(s)." if manual else "."))

    remaining = compute_daily_worker_statement(worker, start, end)['by_project']
    if remaining:
        names = ', '.join(row['project'].name for row in remaining if row['project'])
        messages.warning(
            request,
            f"{worker.full_name} still has attendance in daily reports ({names}), so the row will appear again. "
            "Remove that attendance from the daily report to get rid of it.",
        )
    return back


@wages_access_required
@require_http_methods(["POST"])
def wages_run_approve(request):
    """
    اعتماد المحاسبة -- the accountant approves the month's posted wages for payment. From then on each worker's payment
    voucher (سند صرف + قسيمة عامل مياومة) can be printed, one by one or all together. Only an accountant or an admin may do it,
    and only for wages that HR has already posted.
    """
    from .models import DailyWorkerPayslip

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}")
    if not (request.user.is_admin() or request.user.is_accountant()):
        messages.error(request, 'Only the accountant can approve wages.')
        return back
    posted = DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end, status='posted')
    if not posted.exists():
        messages.error(request, 'Post the wages first; the accountant approves posted wages only.')
        return back
    approved = posted.filter(accounting_approved_at__isnull=True).update(
        accounting_approved_at=timezone.now(), accounting_approved_by=request.user,
    )
    if approved:
        messages.success(request, f'Approved the wages of {period_start.strftime("%B %Y")} ({approved} worker(s)). The payment vouchers can now be printed.')
    else:
        messages.info(request, 'Everything posted for this month was already approved.')
    return back


@wages_access_required
@require_http_methods(["POST"])
def wages_run_unapprove(request):
    """Admin only: take the accountant's approval back (the vouchers are locked again until it is given once more)."""
    from .models import DailyWorkerPayslip

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    back = redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}")
    if not request.user.is_admin():
        messages.error(request, 'Only an admin can withdraw the accounting approval.')
        return back
    count = DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end).update(
        accounting_approved_at=None, accounting_approved_by=None)
    messages.warning(request, f'Accounting approval withdrawn ({count} worker(s)).')
    return back


def _voucher_response(slips, request, name):
    from .voucher_pdf import generate_wage_vouchers_pdf

    include_termination = request.GET.get("termination") != "0"
    response = HttpResponse(generate_wage_vouchers_pdf(slips, include_termination=include_termination), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{name}.pdf"'
    return response


@wages_access_required
def wage_voucher_pdf(request, pk):
    """One worker's payment voucher; available only after the accountant approved the month."""
    from .models import DailyWorkerPayslip

    slip = get_object_or_404(DailyWorkerPayslip.objects.select_related('worker'), pk=pk)
    if not slip.accounting_approved_at:
        messages.error(request, 'The payment voucher is available after the accountant approves the wages.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={slip.period_start.strftime('%Y-%m')}")
    return _voucher_response([slip], request, f"voucher-{slip.worker.pk}-{slip.period_start.strftime('%Y-%m')}")


@wages_access_required
def wage_vouchers_pdf(request):
    """Every approved worker's payment voucher of the month in one PDF, by name, ready to print and sign."""
    from .models import DailyWorkerPayslip

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    slips = list(DailyWorkerPayslip.objects.filter(
        period_start=period_start, period_end=period_end, accounting_approved_at__isnull=False,
    ).select_related('worker').order_by('worker__full_name'))
    if not slips:
        messages.error(request, 'No approved wages for this month yet; the vouchers are printed after the accountant approves.')
        return redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}")
    return _voucher_response(slips, request, f"vouchers-{period_start.strftime('%Y-%m')}")


@hr_manager_required
@require_http_methods(["POST"])
def wages_run_post(request):
    """ترحيل -- finalize this month's draft wage slips, locking them against further edits."""
    from .models import DailyWorkerPayslip

    period_start, period_end = _resolve_month_period(request.POST.get("month"))
    updated = DailyWorkerPayslip.objects.filter(
        period_start=period_start, period_end=period_end, status='draft',
    ).update(status='posted', posted_by=request.user, posted_at=timezone.now())

    if updated:
        messages.success(request, f'Posted wages for {period_start.strftime("%B %Y")} ({updated} worker(s)).')
    else:
        messages.info(request, 'Nothing to post -- this wages run is already posted or empty.')
    return redirect(f"{reverse('timesheets:wages_run')}?month={period_start.strftime('%Y-%m')}")


@login_required
def export_wages_excel(request):
    """Formatted Excel twin of the wages_run review screen -- styled header + a clear totals row."""
    from .models import DailyWorkerPayslip

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    wage_slips = list(
        DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end)
        .select_related('worker').order_by('worker__full_name')
    )

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Wages"
    headers = ["Worker", "Trade", "Days", "Overtime Hours", "Base Pay", "Overtime Pay",
               "Gross Pay", "Other Allowances", "Other Deductions", "Advances", "Net Pay"]
    ws.append(headers)
    money_cols = [5, 6, 7, 8, 9, 10, 11]

    totals = [0.0] * len(headers)
    row_idx = 1
    for w in wage_slips:
        row = [
            w.worker.full_name, w.worker.trade or "", float(w.total_days), float(w.overtime_hours),
            float(w.base_pay), float(w.overtime_pay), float(w.gross_pay),
            float(w.other_allowances), float(w.other_deductions), float(w.total_advances), float(w.net_pay),
        ]
        ws.append(row)
        row_idx += 1
        for i, v in enumerate(row):
            if isinstance(v, (int, float)):
                totals[i] += v

    total_row_idx = row_idx + 1
    ws.append(["TOTAL", ""] + [totals[i] for i in range(2, len(headers))])

    for r in range(2, row_idx + 1):
        for c in money_cols:
            ws.cell(row=r, column=c).number_format = "#,##0.00"
    for c in money_cols:
        ws.cell(row=total_row_idx, column=c).number_format = "#,##0.00"

    _style_excel_header(ws, len(headers))
    _style_excel_totals_row(ws, total_row_idx, len(headers))
    _autosize_excel_columns(ws, [22, 14, 10, 14, 12, 12, 12, 14, 14, 12, 12])

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename=wages-{period_start.strftime('%Y-%m')}.xlsx"
    wb.save(response)
    return response


@login_required
def export_wages_sheet_pdf(request):
    """The month in the company's own "كشف اجور عمال" layout: one table per project (see timesheets/pdf.py)."""
    from .wages_sheet_pdf import generate_wages_sheet_pdf
    from .services.daily_worker_payroll_service import wages_sheet

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    sheet = wages_sheet(period_start, period_end)
    pdf_bytes = generate_wages_sheet_pdf(sheet, generated_by=request.user.get_full_name() or request.user.username)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"inline; filename=wages-sheet-{period_start.strftime('%Y-%m')}.pdf"
    return response


@login_required
def export_wages_sheet_excel(request):
    """Excel twin of export_wages_sheet_pdf, with the sheet's own formulas (see timesheets/wages_sheet_excel.py)."""
    from .services.daily_worker_payroll_service import wages_sheet
    from .wages_sheet_excel import build_wages_sheet_workbook

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    wb = build_wages_sheet_workbook(wages_sheet(period_start, period_end))
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f"attachment; filename=FIN-WRK-{period_start.strftime('%m-%Y')}.xlsx"
    wb.save(response)
    return response


@login_required
def export_wages_pdf(request):
    """PDF twin of export_wages_excel (see timesheets/pdf.py)."""
    from .models import DailyWorkerPayslip
    from .pdf import generate_wages_run_pdf

    period_start, period_end = _resolve_month_period(request.GET.get("month"))
    wage_slips = list(
        DailyWorkerPayslip.objects.filter(period_start=period_start, period_end=period_end)
        .select_related('worker').order_by('worker__full_name')
    )
    is_posted = bool(wage_slips) and all(w.status == 'posted' for w in wage_slips)
    generated_by = request.user.get_full_name() or request.user.username

    pdf_bytes = generate_wages_run_pdf(wage_slips, period_start, is_posted, generated_by=generated_by)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=wages-{period_start.strftime('%Y-%m')}.pdf"
    return response


@hr_required
def wage_slip_pdf(request, pk):
    """One worker's wage slip as a formatted PDF, same role as payslip_pdf for salaried employees."""
    from .models import DailyWorkerPayslip
    from .pdf import generate_wage_slip_pdf

    wage_slip = get_object_or_404(DailyWorkerPayslip, pk=pk)
    pdf_bytes = generate_wage_slip_pdf(wage_slip)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f"inline; filename=wage-slip-{wage_slip.worker.pk}-{wage_slip.period_start.strftime('%Y-%m')}.pdf"
    return response