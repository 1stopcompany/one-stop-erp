
from datetime import datetime, timedelta
from django.db import models
from django.conf import settings
from django.core.validators import RegexValidator
from django.utils import timezone
import math


class SalaryStructure(models.Model):
    """
    A reusable pay policy: how many hours count as a standard month/day,
    and the multipliers applied to hours worked beyond that. This holds
    the *policy*, not the amount -- each Employee keeps their own
    individual `salary` field; the structure just says how that salary
    converts to an hourly rate and how overtime/weekend hours are paid.
    """

    name = models.CharField(max_length=100, unique=True)
    monthly_working_hours = models.PositiveIntegerField(
        default=240,  # 30-day month x 8 hours/day -- confirmed against a real payroll sheet, not the generic 160
        help_text='Standard hours/month a salary is divided by to get the hourly rate (30 days x daily_working_hours)'
    )
    daily_working_hours = models.PositiveIntegerField(
        default=8, help_text='Hours per day before extra hours count as overtime'
    )
    break_hours = models.DecimalField(
        max_digits=4, decimal_places=2, default=1,
        help_text='Unpaid break subtracted from a day\'s check-in/out span before splitting it into regular/overtime hours'
    )
    overtime_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=1.5)
    weekend_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=1.5)
    holiday_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=2.0)
    is_default = models.BooleanField(
        default=False, help_text='Used for any employee with no salary structure of their own'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DailyWorker(models.Model):
    """
    A day-labor / casual worker paid per day worked, who commonly moves
    between several open projects within the same month (today on
    project A, tomorrow on project B). Kept deliberately separate from
    Employee, which requires HR fields (address, emergency contact, a
    login account, ...) this kind of worker realistically never has on
    file.

    This is the one shared identity a site engineer picks from -- via
    reports.DailyReportWorkerAttendance.daily_worker -- no matter which
    project's daily report they're filling in on a given day, so a
    monthly payroll run can aggregate one worker's hours correctly across
    every project they touched that month. See
    timesheets.services.daily_worker_payroll_service.
    """

    full_name = models.CharField(max_length=150)
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    trade = models.CharField(max_length=100, blank=True, help_text='e.g. "عامل طوبار", "فني ميكانيك"')
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2, help_text='Wage for one full 8-hour day')
    id_document = models.FileField(
        upload_to='daily_worker_ids/', null=True, blank=True,
        help_text='Scanned ID/identity document, captured once when this worker is first added to the roster'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f'{self.full_name} ({self.trade})' if self.trade else self.full_name

    @property
    def hourly_rate(self):
        return self.daily_rate / 8


class Department(models.Model):
    """Department model to organize employees"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    manager = models.ForeignKey(
        'Employee', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='managed_departments'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Position(models.Model):
    """Position/Role model for employee job titles"""
    title = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    salary_min = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    default_labor_classification = models.ForeignKey(
        'reports.LaborClassification', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
        help_text='Daily Report trade to pre-select when an employee with this position is picked for '
                   'worker attendance (e.g. Site Engineer -> Project Management/Site Engineer), so their '
                   'own presence can be logged without re-typing a trade that their position already implies'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title


class Employee(models.Model):
    """Employee model with comprehensive information"""
    
    # Employment Status Choices
    EMPLOYMENT_STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('terminated', 'Terminated'),
        ('on_leave', 'On Leave'),
    ]
    
    # Employment Type Choices
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('intern', 'Intern'),
    ]

    # Personal Information
    employee_id = models.CharField(
        max_length=20, 
        unique=True,
        validators=[RegexValidator(r'^[A-Z0-9]+$', 'Employee ID must contain only uppercase letters and numbers')]
    )
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(
        max_length=15,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Phone number must be valid')]
    )
    date_of_birth = models.DateField(null=True, blank=True)
    
    # Address Information
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='United States')
    
    # Employment Information
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='employees')
    # Current project assignment -- lets a site engineer/supervisor's HR
    # record be matched against the project they're actually reporting on
    # (used to populate the Daily Report's worker-attendance employee
    # picker, and to scope which employees show up for a given project).
    # Deliberately a single FK, not a history/M2M: this is "which project
    # is this person on right now", not a full assignment-history record.
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='hr_employees',
        help_text='Project this employee is currently assigned to, if any'
    )
    employment_status = models.CharField(max_length=20, choices=EMPLOYMENT_STATUS_CHOICES, default='active')
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPE_CHOICES, default='full_time')
    hire_date = models.DateField()
    termination_date = models.DateField(null=True, blank=True)
    salary = models.DecimalField(max_digits=10, decimal_places=2)
    salary_structure = models.ForeignKey(
        SalaryStructure,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employees',
        help_text='Pay policy (overtime/weekend rules) for this employee; falls back to the default structure if unset'
    )

    # Manager Relationship
    manager = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='direct_reports'
    )
    
    # Payroll / identity -- needed to generate a real payslip and pay it out
    national_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_account_number = models.CharField(max_length=50, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(upload_to='employee_photos/', null=True, blank=True)
    annual_leave_days = models.PositiveIntegerField(
        default=14,
        help_text='No longer used to compute leave balance -- that is now tenure-based automatically '
                   '(14 days/year under 5 years of service, 21 days/year at 5+), see '
                   'services.attendance_service._annual_leave_allocation. Kept only for legacy records.'
    )

    # Extended personal details
    GENDER_CHOICES = [('male', 'Male'), ('female', 'Female'), ('other', 'Other')]
    MARITAL_STATUS_CHOICES = [
        ('single', 'Single'), ('married', 'Married'), ('divorced', 'Divorced'), ('widowed', 'Widowed'),
    ]
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES, blank=True)
    marital_status = models.CharField(max_length=10, choices=MARITAL_STATUS_CHOICES, blank=True)
    nationality = models.CharField(max_length=50, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    driver_license = models.CharField(max_length=50, blank=True)
    father_name = models.CharField(max_length=100, blank=True)
    mother_name = models.CharField(max_length=100, blank=True)
    spouse_name = models.CharField(max_length=100, blank=True)
    personal_email = models.EmailField(blank=True, help_text='Personal email, separate from the work email above')
    hobbies = models.CharField(max_length=255, blank=True)

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=100)
    emergency_contact_phone = models.CharField(
        max_length=15,
        validators=[RegexValidator(r'^\+?1?\d{9,15}$', 'Phone number must be valid')]
    )
    emergency_contact_relationship = models.CharField(max_length=50)
    
    # System Fields
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='employee_profile'
    )
    payroll_order = models.PositiveIntegerField(
        default=0,
        help_text='Position of the employee in the payroll sheet and its exports (1 = first), set with the up/down arrows on '
                  'the Payroll Run page; 0 = not placed yet (listed after the placed ones, alphabetically)',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_employees'
    )

    class Meta:
        ordering = ['last_name', 'first_name']
        indexes = [
            models.Index(fields=['employee_id']),
            models.Index(fields=['email']),
            models.Index(fields=['last_name', 'first_name']),
            models.Index(fields=['department', 'employment_status']),
        ]

    def __str__(self):
        return f'{self.first_name} {self.last_name} ({self.employee_id})'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    @property
    def is_active(self):
        return self.employment_status == 'active'

    def get_years_of_service(self):
        """Calculate years of service"""
        end_date = self.termination_date or timezone.now().date()
        return (end_date - self.hire_date).days // 365


class EmploymentStatusHistory(models.Model):
    """
    One row per employment_status change, kept even after Employee.employment_status
    moves on -- this is the audit trail behind the Job tab's "Update Status" button,
    so HR can see e.g. exactly when someone went from active to on_leave to terminated.
    """
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='status_history')
    status = models.CharField(max_length=20, choices=Employee.EMPLOYMENT_STATUS_CHOICES)
    effective_date = models.DateField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee_status_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date', '-changed_at']
        verbose_name_plural = 'Employment status history'

    def __str__(self):
        return f'{self.employee.full_name} -> {self.get_status_display()} ({self.effective_date})'


class EmploymentTypeHistory(models.Model):
    """Same audit-trail pattern as EmploymentStatusHistory, but for employment_type changes."""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='type_history')
    employment_type = models.CharField(max_length=20, choices=Employee.EMPLOYMENT_TYPE_CHOICES)
    effective_date = models.DateField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='employee_type_changes',
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date', '-changed_at']
        verbose_name_plural = 'Employment type history'

    def __str__(self):
        return f'{self.employee.full_name} -> {self.get_employment_type_display()} ({self.effective_date})'


class EmployeeDocument(models.Model):
    """Model to store employee documents"""
    
    DOCUMENT_TYPE_CHOICES = [
        ('resume', 'Resume'),
        ('contract', 'Contract'),
        ('id_copy', 'ID Copy'),
        ('certificate', 'Certificate'),
        ('performance_review', 'Performance Review'),
        ('other', 'Other'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='employee_documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_employee_documents'
    )

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.employee.full_name} - {self.title}'

class EmployeeNote(models.Model):
    """Model to store notes about employees"""
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_confidential = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='employee_notes_created'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.employee.full_name} - {self.title}'


class WorkExperience(models.Model):
    """A previous job an employee held before joining, shown on their profile page."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='work_experiences')
    company = models.CharField(max_length=200, verbose_name='Previous Company')
    job_title = models.CharField(max_length=150)
    start_date = models.DateField(verbose_name='From')
    end_date = models.DateField(verbose_name='To', null=True, blank=True)
    description = models.TextField(blank=True, verbose_name='Job Description')

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f'{self.employee.full_name} - {self.job_title} at {self.company}'


class Education(models.Model):
    """A school/degree an employee completed, shown on their profile page."""

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='education_history')
    school_name = models.CharField(max_length=200)
    degree = models.CharField(max_length=150)
    field_of_study = models.CharField(max_length=150, blank=True)
    year_of_completion = models.PositiveIntegerField(null=True, blank=True)
    result = models.CharField(max_length=50, blank=True, help_text='e.g. "4.0 out of 4.0" or "85%"')
    additional_notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-year_of_completion']
        verbose_name_plural = 'Education'

    def __str__(self):
        return f'{self.employee.full_name} - {self.degree}, {self.school_name}'


class Dependent(models.Model):
    """A family member dependent on an employee (spouse, child, ...), shown on their profile page."""

    RELATIONSHIP_CHOICES = [
        ('spouse', 'Spouse'),
        ('child', 'Child'),
        ('parent', 'Parent'),
        ('other', 'Other'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='dependents')
    name = models.CharField(max_length=150)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.employee.full_name} - {self.name} ({self.get_relationship_display()})'


class DailyAttendanceRecord(models.Model):
    """
    One row per employee per calendar day -- the Daily Time Record (DTR)
    the client asked for as the real basis for monthly payroll: not just
    a display of GPS pings, but the reviewable, editable record of
    whether someone was present, on paid leave, on unpaid leave, or
    absent that day, which is what timesheets.services.attendance_service
    and payroll_service actually key off when deciding whether a leave
    day counts against the employee's paid balance or becomes an unpaid
    deduction on their payslip (see LeaveRequest.employee.annual_leave_days).

    Generated automatically for a month (see
    attendance_service.generate_daily_attendance) from real GPS
    check-ins, approved leave requests, Fridays and Holiday dates -- but
    every field stays editable afterward, since the auto-classification
    is a starting point HR reviews, not a final answer (e.g. a system
    outage might need a present day corrected to on_leave by hand).
    """

    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('on_leave', 'On Leave (Paid)'),
        ('unpaid_leave', 'Unpaid Leave'),
        ('rest_day', 'Rest Day'),
        ('holiday', 'Holiday'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='daily_attendance')
    date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='present')
    clock_in = models.TimeField(null=True, blank=True)
    clock_out = models.TimeField(null=True, blank=True)
    late_minutes = models.PositiveIntegerField(default=0)
    undertime_minutes = models.PositiveIntegerField(default=0)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('employee', 'date')]
        ordering = ['date']
        indexes = [models.Index(fields=['employee', 'date'])]

    def __str__(self):
        return f'{self.employee.full_name} - {self.date} ({self.get_status_display()})'


class LeaveRequest(models.Model):
    """An employee's request for vacation/sick/personal leave, submitted from the mobile app."""

    REQUEST_TYPE_CHOICES = [
        ('vacation', 'Vacation'),
        ('sick', 'Sick Leave'),
        ('personal', 'Personal Leave'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES, default='vacation')
    title = models.CharField(max_length=200, blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_date = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leave_requests_reviewed',
    )
    reviewed_date = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-submitted_date']
        indexes = [
            models.Index(fields=['employee', '-submitted_date']),
            models.Index(fields=['status']),
        ]

    @property
    def days(self):
        """
        Days this request counts against the employee's annual balance --
        Friday is excluded even when it falls inside the requested range,
        since it's the weekly rest day already, confirmed with the client
        (see attendance_service._leave_status_by_date, which applies the
        same exclusion when deciding paid vs. unpaid leave for payroll).
        """
        total = 0
        day = self.start_date
        while day <= self.end_date:
            if day.weekday() != 4:
                total += 1
            day += timedelta(days=1)
        return total

    def __str__(self):
        return f'{self.employee.full_name} - {self.get_request_type_display()} ({self.start_date} to {self.end_date})'


class LeavePermission(models.Model):
    """
    A short same-day leave permission ("إذن مغادرة") -- e.g. leaving 2
    hours early for a personal errand -- as distinct from a multi-day
    LeaveRequest. Tracked separately since it's a different real-world
    document with its own approval, not a fractional-day LeaveRequest.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_permissions')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    submitted_date = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='leave_permissions_reviewed',
    )

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['employee', '-date']),
        ]

    @property
    def hours(self):
        today = timezone.localdate()
        start = datetime.combine(today, self.start_time)
        end = datetime.combine(today, self.end_time)
        return round((end - start).total_seconds() / 3600, 2)

    def __str__(self):
        return f'{self.employee.full_name} - {self.date} ({self.start_time}-{self.end_time})'


class Holiday(models.Model):
    """
    A single paid public holiday date, worked hours on which are paid at
    a SalaryStructure's holiday_multiplier instead of the regular/weekend
    rate. Fixed-date holidays (New Year, Labour Day, Independence Day) can
    be seeded once per year with `manage.py seed_fixed_holidays`; the
    Islamic calendar ones (Eid al-Fitr, Eid al-Adha) shift every year and
    must be entered here by hand once the dates are announced.
    """

    date = models.DateField(unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.name} ({self.date})'


class Payslip(models.Model):
    """
    One computed pay run for one employee over one period. Regenerating a
    payslip for the same employee/period overwrites the previous figures
    while it is still 'draft' -- this is a computed result, not a ledger
    of payments made, until it is posted (ترحيل): see
    timesheets.views.payroll_run, which is the real entry point --
    generates/refreshes every active employee's draft payslip for a
    month, lets HR review and edit the manual figures (overtime,
    allowances, deductions, advances, tax) inline, and only then posts
    the run, after which those payslips are locked against further edits.

    Two pay bases, matching how the company actually runs payroll (verified
    against a real August-2026 salary sheet):

    - 'salaried' (permanent staff): base_pay is their fixed monthly salary,
      prorated only for a genuine partial period (new hire/termination) --
      NOT reduced for ordinary day-to-day attendance gaps, which are an HR
      review matter rather than an automatic deduction. Friday and public
      holidays are paid days already included in that fixed salary, so
      there is no separate weekend/holiday premium. Overtime hours are
      entered by HR (not auto-derived from GPS spans) and paid at
      SalaryStructure.overtime_multiplier x the hourly-equivalent rate
      (salary / monthly_working_hours).
      See timesheets.services.payroll_service.compute_payslip_salaried.

    - 'hourly' (e.g. daily-wage workers): base/overtime/weekend/holiday
      hours and pay are all derived automatically from real GPS
      check-in/out records. See
      timesheets.services.payroll_service.compute_payslip_hourly.

    Confirmed with the client and matching the real sheet: income tax is
    tracked here for information/reporting only and is deliberately NOT
    subtracted in net_pay -- it has its own calculation, handled
    separately (real take-home is unaffected by the tax figure shown).
    """

    PAY_BASIS_CHOICES = [
        ('salaried', 'Salaried (fixed monthly)'),
        ('hourly', 'Hourly (from GPS attendance)'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'),   # reviewable and editable -- a payroll run in progress
        ('posted', 'Posted'),  # ترحيل -- finalized, locked against further edits
        ('excluded', 'Excluded'),  # taken out of this month's run on purpose; not paid, not posted, can be restored
    ]

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payslips')
    period_start = models.DateField()
    period_end = models.DateField()
    pay_basis = models.CharField(max_length=10, choices=PAY_BASIS_CHOICES, default='salaried')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payslips_posted'
    )

    salary_structure = models.ForeignKey(
        SalaryStructure, on_delete=models.SET_NULL, null=True, related_name='payslips'
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)

    # 'hourly' basis only -- always 0 for 'salaried' payslips
    regular_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    weekend_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    holiday_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    weekend_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    holiday_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Both bases
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowances = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text='بدلات أخرى -- manual entry (e.g. transport, car)'
    )
    other_deductions = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text='مقتطعات -- manual entry, distinct from advances'
    )
    advances = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, help_text='سلف -- manual entry'
    )
    unpaid_leave_days = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text='Auto-counted from DailyAttendanceRecord rows marked \'unpaid_leave\' this period '
                   '(leave taken beyond the employee\'s annual_leave_days balance)'
    )
    unpaid_leave_deduction = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='unpaid_leave_days x (salary / 30) -- auto-computed, subtracted from net pay'
    )
    tax = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='الضريبة -- shown for information only; NOT subtracted from net_pay (separate process)'
    )
    manual_base_pay = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Typed by HR in the payroll run instead of the salary-based base pay (blank = automatic)',
    )
    manual_unpaid_leave_deduction = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Typed by HR instead of the automatic unpaid-leave deduction (blank = automatic)',
    )
    manual_actual_days = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text='Attendance days typed by HR instead of the days counted from GPS clock-ins (blank = automatic). Display only: does not change pay',
    )
    note = models.CharField(max_length=300, blank=True, help_text='Free note on this employee for this month')
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    generated_at = models.DateTimeField(auto_now=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payslips_generated'
    )

    def save(self, *args, **kwargs):
        # Keep gross/net self-consistent no matter where a figure was
        # edited from (the compute_payslip_* services, or a manual tweak
        # to e.g. other_deductions in Django admin) -- tax is deliberately
        # excluded, see the class docstring.
        self.gross_pay = (
            self.base_pay + self.overtime_pay + self.weekend_pay + self.holiday_pay + self.other_allowances
        )
        self.net_pay = self.gross_pay - self.other_deductions - self.advances - self.unpaid_leave_deduction
        # update_or_create() (used throughout payroll_service) passes
        # update_fields restricted to its `defaults` dict's keys when the
        # row already exists -- gross_pay/net_pay are deliberately never
        # in that dict (they're computed here, not supplied by callers),
        # so Django's UPDATE statement would silently omit both columns
        # and drop these two computed values on the floor. Force them
        # into update_fields whenever one is given.
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'gross_pay', 'net_pay'}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-period_start', 'employee']
        unique_together = [('employee', 'period_start', 'period_end')]

    def __str__(self):
        return f'{self.employee.full_name} - {self.period_start} to {self.period_end}'


class DailyWorkerPayslip(models.Model):
    """
    A day-labor worker's "كشف الصرف" (wages statement) for one month --
    the DailyWorker equivalent of Payslip, same review/edit/ترحيل workflow
    (see timesheets.views.wages_run): base_pay/overtime_pay are
    auto-computed from reports.DailyReportWorkerAttendance across every
    project the worker touched that month (see
    timesheets.services.daily_worker_payroll_service.compute_daily_worker_payslip),
    while other_allowances/other_deductions/advances are HR-entered by
    hand, exactly like the salaried Payslip. Regenerating the run for the
    same worker/period overwrites these figures while still 'draft'; once
    'posted' it is locked.
    """

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('posted', 'Posted'),
    ]

    worker = models.ForeignKey(DailyWorker, on_delete=models.CASCADE, related_name='payslips')
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    posted_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='daily_worker_payslips_posted',
    )
    accounting_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_wage_slips', help_text='The accountant who approved this month for payment',
    )
    accounting_approved_at = models.DateTimeField(
        null=True, blank=True, help_text='Set when the accountant approves; the payment voucher of the worker can be printed from then on',
    )

    total_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    base_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    overtime_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='بدلات أخرى -- manual entry')
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='مقتطعات -- manual entry')
    advances = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text='سلف -- manual entry')
    line_advances = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='سلف typed on the worker\'s per-project lines of the Manual Entry tab (not edited here)',
    )
    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    generated_at = models.DateTimeField(auto_now=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='daily_worker_payslips_generated',
    )

    @property
    def total_advances(self):
        """Advances taken off this month: the ones typed on the worker's project lines plus any entered on the row."""
        return self.advances + self.line_advances

    @property
    def income_tax(self):
        """
        Palestinian income tax on the month's gross pay, worked out as in the company's tax sheet (see
        timesheets.services.income_tax). Information only: it is never subtracted from net_pay.
        """
        from .services.income_tax import monthly_income_tax
        return monthly_income_tax(self.gross_pay)

    def save(self, *args, **kwargs):
        self.gross_pay = self.base_pay + self.overtime_pay + self.other_allowances
        self.net_pay = self.gross_pay - self.other_deductions - self.advances - self.line_advances
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            kwargs['update_fields'] = set(update_fields) | {'gross_pay', 'net_pay'}
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-period_start', 'worker']
        unique_together = [('worker', 'period_start', 'period_end')]

    def __str__(self):
        return f'{self.worker.full_name} - {self.period_start} to {self.period_end}'


class PayrollNote(models.Model):
    """A note written under the employee payroll table of one month (printed in its PDF and Excel); a month can have several."""

    period_start = models.DateField(db_index=True, help_text='First day of the month the note belongs to')
    text = models.CharField(max_length=500)
    order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='payroll_notes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['period_start', 'order', 'id']

    def __str__(self):
        return f'{self.period_start:%Y-%m}: {self.text[:40]}'


class DailyWorkerManualEntry(models.Model):
    """
    An exceptional, admin-only entry typed into the Wages Run's "Manual
    Entry" tab (كشف الصرف): for one worker on one project in one month, the
    TOTAL days worked, the daily rate (اليومية) and the overtime hours --
    everything else (base pay, overtime pay, total) is computed from those,
    exactly as for attendance taken from daily reports. It counts toward the
    worker's month and the project's total on top of any daily-report
    attendance (see timesheets.services.daily_worker_payroll_service), and
    stays visibly marked as manual.
    """

    worker = models.ForeignKey(DailyWorker, on_delete=models.CASCADE, related_name='manual_entries')
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, related_name='manual_wage_entries')
    period_start = models.DateField(help_text='First day of the month this entry belongs to')
    days = models.DecimalField(max_digits=6, decimal_places=2, default=0, help_text='Total full 8-hour days in the month')
    daily_rate = models.DecimalField(max_digits=8, decimal_places=2, help_text='اليومية -- wage for one full 8-hour day')
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    advances = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text='سلف -- advance deducted on this line')
    sub_name = models.CharField(
        max_length=120, blank=True,
        help_text='متفرقات -- an optional named sub-group inside the project (e.g. one odd job of a "miscellaneous" project); blank = the project itself',
    )
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='daily_worker_manual_entries',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['worker__full_name']
        unique_together = [('worker', 'project', 'period_start', 'sub_name')]
        verbose_name_plural = 'Daily worker manual entries'

    def __str__(self):
        return f'{self.worker.full_name} - {self.project} - {self.period_start:%Y-%m}'


class CheckInLocation(models.Model):
    """Model to track employee check-in/out locations"""
    CHECK_TYPE_CHOICES = [
        ('in', 'Check In'),
        ('out', 'Check Out'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='check_locations')
    # Which project this check-in/out counts toward -- set automatically
    # from the matched geofence's project when the point falls inside one
    # (LocationService.process_check_in/out), falling back to the
    # employee's own current project assignment otherwise. This is what
    # lets a Daily Report pull "this employee's GPS hours today" scoped
    # to the right project.
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gps_checkins',
        help_text='Project this check-in/out is attributed to'
    )
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)
    check_type = models.CharField(max_length=10, choices=CHECK_TYPE_CHOICES)
    address = models.CharField(max_length=200, blank=True)
    is_within_geofence = models.BooleanField(default=False)
    accuracy = models.FloatField(null=True, blank=True, help_text="GPS accuracy in meters")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', '-timestamp']),
            models.Index(fields=['check_type', '-timestamp']),
            models.Index(fields=['project', '-timestamp']),
        ]
    
    def __str__(self):
        return f'{self.employee.full_name} - {self.get_check_type_display()} at {self.timestamp}'
    
    @property
    def location_string(self):
        return f'{self.latitude}, {self.longitude}'


class Geofence(models.Model):
    """Model to define virtual boundaries for automatic check-in/out"""
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    # Which project site this boundary represents. Optional (a geofence
    # could cover a shared yard/office not tied to one project), but
    # setting it is what lets a GPS check-in inside it be attributed to
    # that project automatically -- see CheckInLocation.project below.
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='geofences',
        help_text='Project site this geofence covers, if any'
    )
    center_latitude = models.FloatField()
    center_longitude = models.FloatField()
    radius = models.FloatField(help_text="Radius in meters")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def contains_point(self, latitude, longitude):
        """Check if a point is within the geofence using Haversine formula"""
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [self.center_latitude, self.center_longitude, latitude, longitude])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in meters
        r = 6371000
        distance = c * r
        
        return distance <= self.radius


class LocationHistory(models.Model):
    """Model to store detailed location history for tracking"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='location_history')
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)
    accuracy = models.FloatField(null=True, blank=True)
    speed = models.FloatField(null=True, blank=True, help_text="Speed in m/s")
    heading = models.FloatField(null=True, blank=True, help_text="Direction in degrees")
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', '-timestamp']),
        ]
    
    def __str__(self):
        return f'{self.employee.full_name} at {self.timestamp}'


class EmployeeStatus(models.Model):
    """Model to track current employee status and location"""
    STATUS_CHOICES = [
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('on_break', 'On Break'),
        ('offline', 'Offline'),
    ]
    
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='current_status')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    current_latitude = models.FloatField(null=True, blank=True)
    current_longitude = models.FloatField(null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True)
    last_check_in = models.DateTimeField(null=True, blank=True)
    last_check_out = models.DateTimeField(null=True, blank=True)
    current_geofence = models.ForeignKey(Geofence, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name_plural = "Employee Statuses"
    
    def __str__(self):
        return f'{self.employee.full_name} - {self.get_status_display()}'
    
    @property
    def is_online(self):
        """Check if employee is currently online (updated within last 10 minutes)"""
        if not self.last_update:
            return False
        return (timezone.now() - self.last_update).total_seconds() < 600  # 10 minutes
    
    @property
    def current_location_string(self):
        if self.current_latitude and self.current_longitude:
            return f'{self.current_latitude}, {self.current_longitude}'
        return "Unknown"

