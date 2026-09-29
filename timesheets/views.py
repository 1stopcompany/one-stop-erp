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
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.generic import DetailView, TemplateView

from .auth_views import hr_manager_required, hr_required
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

    context = {
        "employee": employee,
        "records": records,
        "period_start": period_start,
        "month_param": period_start.strftime("%Y-%m"),
        "status_choices": DailyAttendanceRecord.STATUS_CHOICES,
        "present_count": sum(1 for r in records if r.status == 'present'),
        "absent_count": sum(1 for r in records if r.status == 'absent'),
        "unpaid_leave_count": sum(1 for r in records if r.status == 'unpaid_leave'),
        "undertime": undertime,
    }
    return render(request, "timesheets/daily_time_record.html", context)


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
    template_name = "timesheets/employee_map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # json_script cannot serialize a Django QuerySet directly. Convert the
        # records into a plain list of dictionaries before sending them to the
        # template. Timestamps are formatted as strings to keep the payload
        # predictable for JavaScript and across database backends.
        location_records = (
            CheckInLocation.objects
            .select_related("employee")
            .order_by("-timestamp")[:500]
        )

        context["locations"] = [
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "employee": location.employee.full_name,
                "type": location.get_check_type_display(),
                "timestamp": timezone.localtime(location.timestamp).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "address": location.address or "",
                "within_geofence": location.is_within_geofence,
            }
            for location in location_records
        ]
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
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    payslips = []
    for emp in Employee.objects.filter(employment_status="active").select_related("department", "position"):
        existing = Payslip.objects.filter(employee=emp, period_start=period_start, period_end=period_end).first()
        if existing and existing.status == 'posted':
            payslips.append(existing)
            continue
        payslip = compute_payslip_salaried(
            emp, period_start, period_end,
            overtime_hours=existing.overtime_hours if existing else 0,
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            tax=existing.tax if existing else 0,
            generated_by=request.user,
        )
        payslips.append(payslip)

    payslips.sort(key=lambda p: p.employee.full_name)
    is_posted = bool(payslips) and all(p.status == 'posted' for p in payslips)

    context = {
        "payslips": payslips,
        "period_start": period_start,
        "period_end": period_end,
        "month_param": period_start.strftime("%Y-%m"),
        "is_posted": is_posted,
        "total_net": sum((p.net_pay for p in payslips), Decimal('0')),
    }
    return render(request, "timesheets/payroll_run.html", context)


@hr_manager_required
@require_http_methods(["POST"])
def payroll_run_update_row(request, pk):
    """Update one employee's HR-entered payroll figures for this run (blocked once posted)."""
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    payslip = get_object_or_404(Payslip, pk=pk)
    if payslip.status == 'posted':
        messages.error(request, 'This payroll run has already been posted and can no longer be edited.')
        return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")

    def _decimal(field, default='0'):
        raw = request.POST.get(field, '').strip()
        try:
            return Decimal(raw) if raw else Decimal(default)
        except InvalidOperation:
            return Decimal(default)

    compute_payslip_salaried(
        payslip.employee, payslip.period_start, payslip.period_end,
        overtime_hours=_decimal('overtime_hours'),
        other_allowances=_decimal('other_allowances'),
        other_deductions=_decimal('other_deductions'),
        advances=_decimal('advances'),
        tax=_decimal('tax'),
        generated_by=request.user,
    )
    messages.success(request, f'Updated {payslip.employee.full_name}.')
    return redirect(f"{reverse('timesheets:payroll_run')}?month={payslip.period_start.strftime('%Y-%m')}")


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


@login_required
def export_payroll_excel(request):
    """
    One row per active employee for a given calendar month (default: the
    current month; pass ?month=YYYY-MM for another one), on the fixed
    monthly-salary basis (see payroll_service.compute_payslip_salaried) --
    reflects whatever the payroll_run review screen currently holds for
    that month (draft or posted).

    Overtime hours / other allowances / other deductions / advances / tax
    are HR-entered figures, not auto-computed -- if a Payslip already
    exists for an employee+month, those figures are carried forward (and
    a posted payslip is left untouched) so this never wipes out reviewed
    data; otherwise they default to 0 for a first pass.
    """
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Payroll"

    headers = [
        "Employee ID", "Name", "Department",
        "Base Pay", "Overtime Hours", "Overtime Pay", "Other Allowances",
        "Gross Pay", "Unpaid Leave Days", "Unpaid Leave Deduction",
        "Other Deductions", "Advances", "Net Pay", "Tax (info only)",
    ]
    ws.append(headers)
    money_cols = [4, 6, 7, 8, 10, 11, 12, 13, 14]

    totals = [0.0] * len(headers)
    row_idx = 1
    for emp in Employee.objects.filter(employment_status="active").select_related("department").order_by("last_name", "first_name"):
        existing = Payslip.objects.filter(employee=emp, period_start=period_start, period_end=period_end).first()
        payslip = compute_payslip_salaried(
            emp, period_start, period_end,
            overtime_hours=existing.overtime_hours if existing else 0,
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            tax=existing.tax if existing else 0,
            generated_by=request.user,
        )

        row = [
            emp.employee_id, emp.full_name, emp.department.name if emp.department_id else "",
            float(payslip.base_pay), float(payslip.overtime_hours), float(payslip.overtime_pay),
            float(payslip.other_allowances), float(payslip.gross_pay),
            float(payslip.unpaid_leave_days), float(payslip.unpaid_leave_deduction),
            float(payslip.other_deductions), float(payslip.advances), float(payslip.net_pay), float(payslip.tax),
        ]
        ws.append(row)
        row_idx += 1
        for i, v in enumerate(row):
            if isinstance(v, (int, float)):
                totals[i] += v

    total_row_idx = row_idx + 1
    total_row = ["", "TOTAL", ""] + [totals[i] for i in range(3, len(headers))]
    ws.append(total_row)

    for r in range(2, row_idx + 1):
        for c in money_cols:
            ws.cell(row=r, column=c).number_format = "#,##0.00"
    for c in money_cols:
        ws.cell(row=total_row_idx, column=c).number_format = "#,##0.00"

    _style_excel_header(ws, len(headers))
    _style_excel_totals_row(ws, total_row_idx, len(headers))
    _autosize_excel_columns(ws, [12, 22, 16, 12, 10, 12, 12, 12, 12, 14, 12, 12, 12, 12])
    ws.title = "Payroll"

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f"attachment; filename=payroll-{period_start.strftime('%Y-%m')}.xlsx"
    wb.save(response)
    return response


@login_required
def export_payroll_pdf(request):
    """PDF twin of export_payroll_excel -- same figures, formatted for printing/sharing (see timesheets/pdf.py)."""
    from .models import Payslip
    from .services.payroll_service import compute_payslip_salaried
    from .pdf import generate_payroll_run_pdf

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

    payslips = []
    for emp in Employee.objects.filter(employment_status="active").select_related("department", "position").order_by("last_name", "first_name"):
        existing = Payslip.objects.filter(employee=emp, period_start=period_start, period_end=period_end).first()
        if existing and existing.status == "posted":
            payslips.append(existing)
            continue
        payslips.append(compute_payslip_salaried(
            emp, period_start, period_end,
            overtime_hours=existing.overtime_hours if existing else 0,
            other_allowances=existing.other_allowances if existing else 0,
            other_deductions=existing.other_deductions if existing else 0,
            advances=existing.advances if existing else 0,
            tax=existing.tax if existing else 0,
            generated_by=request.user,
        ))

    is_posted = bool(payslips) and all(p.status == "posted" for p in payslips)
    generated_by = request.user.get_full_name() or request.user.username

    pdf_bytes = generate_payroll_run_pdf(payslips, period_start, is_posted, generated_by=generated_by)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
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

    Two sheets: "Summary" (one row per worker, company-wide totals) and
    "Details" (one row per worker per project, with each project's share
    of that worker's pay this month).
    """
    import calendar
    from .services.daily_worker_payroll_service import compute_all_daily_workers_summary

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


@hr_manager_required
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
    from .services.daily_worker_payroll_service import compute_daily_worker_payslip, compute_daily_worker_statement

    period_start, period_end = _resolve_month_period(request.GET.get("month"))

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
    }
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
            float(w.other_allowances), float(w.other_deductions), float(w.advances), float(w.net_pay),
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