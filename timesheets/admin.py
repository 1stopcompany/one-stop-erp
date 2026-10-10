
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Department, Position, Employee, EmployeeDocument, EmployeeNote,
    CheckInLocation, Geofence, LocationHistory, EmployeeStatus, LeaveRequest,
    LeavePermission, SalaryStructure, Payslip, Holiday, DailyWorker,
    WorkExperience, Education, Dependent, DailyAttendanceRecord,
    EmploymentStatusHistory, EmploymentTypeHistory, DailyWorkerPayslip,
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'manager', 'employee_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['name', 'description']
    ordering = ['name']

    def employee_count(self, obj):
        return obj.employees.count()
    employee_count.short_description = 'Employee Count'


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ['title', 'default_labor_classification', 'salary_range', 'employee_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['title', 'description']
    ordering = ['title']

    def salary_range(self, obj):
        if obj.salary_min and obj.salary_max:
            return f"₪{obj.salary_min:,.2f} - ₪{obj.salary_max:,.2f}"
        return "Not specified"
    salary_range.short_description = 'Salary Range'

    def employee_count(self, obj):
        return obj.employees.count()
    employee_count.short_description = 'Employee Count'


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = [
        'employee_id', 'full_name', 'email', 'department',
        'position', 'project', 'employment_status', 'hire_date'
    ]
    list_filter = [
        'employment_status', 'employment_type', 'department',
        'position', 'project', 'hire_date'
    ]
    search_fields = [
        'employee_id', 'first_name', 'last_name', 'email', 
        'phone_number'
    ]
    ordering = ['last_name', 'first_name']
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                'employee_id', 'first_name', 'last_name', 'email', 
                'phone_number', 'date_of_birth'
            )
        }),
        ('Address', {
            'fields': (
                'address_line1', 'address_line2', 'city', 'state', 
                'postal_code', 'country'
            )
        }),
        ('Employment Information', {
            'fields': (
                'department', 'position', 'project', 'employment_status',
                'employment_type', 'hire_date', 'termination_date',
                'salary', 'manager'
            )
        }),
        ('Emergency Contact', {
            'fields': (
                'emergency_contact_name', 'emergency_contact_phone', 
                'emergency_contact_relationship'
            )
        }),
        ('System Information', {
            'fields': ('user', 'created_by'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'
    full_name.admin_order_field = 'last_name'


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'title', 'document_type', 'uploaded_at', 'uploaded_by']
    list_filter = ['document_type', 'uploaded_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'title']
    ordering = ['-uploaded_at']


@admin.register(EmployeeNote)
class EmployeeNoteAdmin(admin.ModelAdmin):
    list_display = ['employee', 'title', 'is_confidential', 'created_at', 'created_by']
    list_filter = ['is_confidential', 'created_at']
    search_fields = ['employee__first_name', 'employee__last_name', 'title', 'content']
    ordering = ['-created_at']



@admin.register(CheckInLocation)
class CheckInLocationAdmin(admin.ModelAdmin):
    list_display = ['employee', 'project', 'check_type', 'timestamp', 'is_within_geofence', 'location_string']
    list_filter = ['check_type', 'is_within_geofence', 'project', 'timestamp']
    search_fields = ['employee__full_name', 'employee__employee_id']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def location_string(self, obj):
        return f"{'{obj.latitude}'}, {'{obj.longitude}'}"
    location_string.short_description = 'Location'


@admin.register(Geofence)
class GeofenceAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'center_latitude', 'center_longitude', 'radius', 'is_active', 'created_at']
    list_filter = ['is_active', 'project', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(LocationHistory)
class LocationHistoryAdmin(admin.ModelAdmin):
    list_display = ['employee', 'timestamp', 'latitude', 'longitude', 'accuracy']
    list_filter = ['timestamp']
    search_fields = ['employee__full_name', 'employee__employee_id']
    readonly_fields = ['timestamp']
    ordering = ['-timestamp']


@admin.register(EmployeeStatus)
class EmployeeStatusAdmin(admin.ModelAdmin):
    list_display = ['employee', 'status', 'current_geofence', 'last_update', 'is_online']
    list_filter = ['status', 'current_geofence']
    search_fields = ['employee__full_name', 'employee__employee_id']
    readonly_fields = ['last_update']
    
    def is_online(self, obj):
        return obj.is_online
    is_online.boolean = True
    is_online.short_description = 'Online'


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ['employee', 'request_type', 'start_date', 'end_date', 'status', 'submitted_date']
    list_filter = ['status', 'request_type']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    readonly_fields = ['submitted_date']
    ordering = ['-submitted_date']
    actions = ['approve_requests', 'reject_requests']

    @admin.action(description='Approve selected requests')
    def approve_requests(self, request, queryset):
        from django.utils import timezone
        queryset.filter(status='pending').update(
            status='approved', reviewed_by=request.user, reviewed_date=timezone.now(),
        )

    @admin.action(description='Reject selected requests')
    def reject_requests(self, request, queryset):
        from django.utils import timezone
        queryset.filter(status='pending').update(
            status='rejected', reviewed_by=request.user, reviewed_date=timezone.now(),
        )


@admin.register(LeavePermission)
class LeavePermissionAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'start_time', 'end_time', 'status', 'submitted_date']
    list_filter = ['status']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    readonly_fields = ['submitted_date']
    ordering = ['-date']
    actions = ['approve_permissions', 'reject_permissions']

    @admin.action(description='Approve selected permissions')
    def approve_permissions(self, request, queryset):
        queryset.filter(status='pending').update(status='approved', reviewed_by=request.user)

    @admin.action(description='Reject selected permissions')
    def reject_permissions(self, request, queryset):
        queryset.filter(status='pending').update(status='rejected', reviewed_by=request.user)


@admin.register(SalaryStructure)
class SalaryStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'monthly_working_hours', 'daily_working_hours', 'break_hours',
                     'overtime_multiplier', 'weekend_multiplier', 'holiday_multiplier',
                     'is_default', 'is_active']
    list_filter = ['is_default', 'is_active']
    search_fields = ['name']


@admin.register(Holiday)
class HolidayAdmin(admin.ModelAdmin):
    list_display = ['name', 'date']
    ordering = ['date']
    search_fields = ['name']


@admin.register(DailyWorker)
class DailyWorkerAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'trade', 'daily_rate', 'national_id', 'is_active']
    list_filter = ['is_active', 'trade']
    search_fields = ['full_name', 'national_id']
    ordering = ['full_name']


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ['employee', 'period_start', 'period_end', 'status', 'pay_basis', 'base_pay', 'overtime_hours',
                     'gross_pay', 'other_deductions', 'advances', 'net_pay', 'tax', 'generated_at']
    list_filter = ['status', 'pay_basis', 'period_start']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    readonly_fields = ['generated_at', 'pay_basis', 'salary_structure', 'hourly_rate',
                       'regular_hours', 'weekend_hours', 'holiday_hours', 'base_pay',
                       'weekend_pay', 'holiday_pay', 'gross_pay', 'net_pay',
                       'posted_at', 'posted_by']
    ordering = ['-period_start']


@admin.register(WorkExperience)
class WorkExperienceAdmin(admin.ModelAdmin):
    list_display = ['employee', 'company', 'job_title', 'start_date', 'end_date']
    search_fields = ['employee__first_name', 'employee__last_name', 'company', 'job_title']


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ['employee', 'school_name', 'degree', 'field_of_study', 'year_of_completion']
    search_fields = ['employee__first_name', 'employee__last_name', 'school_name', 'degree']


@admin.register(Dependent)
class DependentAdmin(admin.ModelAdmin):
    list_display = ['employee', 'name', 'relationship', 'date_of_birth']
    search_fields = ['employee__first_name', 'employee__last_name', 'name']


@admin.register(DailyAttendanceRecord)
class DailyAttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'status', 'clock_in', 'clock_out', 'late_minutes', 'undertime_minutes', 'overtime_hours']
    list_filter = ['status', 'date']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    ordering = ['-date']


@admin.register(EmploymentStatusHistory)
class EmploymentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['employee', 'status', 'effective_date', 'changed_by', 'changed_at']
    list_filter = ['status']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    ordering = ['-effective_date']


@admin.register(EmploymentTypeHistory)
class EmploymentTypeHistoryAdmin(admin.ModelAdmin):
    list_display = ['employee', 'employment_type', 'effective_date', 'changed_by', 'changed_at']
    list_filter = ['employment_type']
    search_fields = ['employee__first_name', 'employee__last_name', 'employee__employee_id']
    ordering = ['-effective_date']


@admin.register(DailyWorkerPayslip)
class DailyWorkerPayslipAdmin(admin.ModelAdmin):
    list_display = ['worker', 'period_start', 'period_end', 'status', 'total_days', 'gross_pay', 'net_pay']
    list_filter = ['status', 'period_start']
    search_fields = ['worker__full_name', 'worker__national_id']
    readonly_fields = ['generated_at', 'total_days', 'overtime_hours', 'base_pay', 'overtime_pay',
                       'gross_pay', 'net_pay', 'posted_at', 'posted_by']
    ordering = ['-period_start']

