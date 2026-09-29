
from rest_framework import serializers
from .models import Employee, CheckInLocation, LocationHistory, EmployeeStatus, Geofence, LeaveRequest, Payslip


class EmployeeLocationSerializer(serializers.ModelSerializer):
    """Serializer for employee location data"""
    employee_name = serializers.SerializerMethodField()
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    
    class Meta:
        model = CheckInLocation
        fields = ['id', 'employee_id', 'employee_name', 'latitude', 'longitude', 
                 'timestamp', 'check_type', 'address', 'is_within_geofence', 'accuracy']
    
    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


class CheckInLocationSerializer(serializers.ModelSerializer):
    """Serializer for check-in/out locations"""
    employee_name = serializers.SerializerMethodField()
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    
    class Meta:
        model = CheckInLocation
        fields = ['id', 'employee', 'employee_name', 'employee_id', 'latitude', 
                 'longitude', 'timestamp', 'check_type', 'address', 
                 'is_within_geofence', 'accuracy', 'notes']
        read_only_fields = ['timestamp']
    
    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


class LocationHistorySerializer(serializers.ModelSerializer):
    """Serializer for location history"""
    employee_name = serializers.SerializerMethodField()
    
    class Meta:
        model = LocationHistory
        fields = ['id', 'employee', 'employee_name', 'latitude', 'longitude', 
                 'timestamp', 'accuracy', 'speed', 'heading']
        read_only_fields = ['timestamp']
    
    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


class EmployeeStatusSerializer(serializers.ModelSerializer):
    """Serializer for employee status"""
    employee_name = serializers.SerializerMethodField()
    employee_id = serializers.CharField(source='employee.employee_id', read_only=True)
    department = serializers.CharField(source='employee.department.name', read_only=True)
    position = serializers.CharField(source='employee.position.title', read_only=True)
    geofence_name = serializers.CharField(source='current_geofence.name', read_only=True)
    is_online = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = EmployeeStatus
        fields = ['employee', 'employee_name', 'employee_id', 'department', 
                 'position', 'status', 'current_latitude', 'current_longitude', 
                 'last_update', 'last_check_in', 'last_check_out', 
                 'geofence_name', 'is_online']

    def get_employee_name(self, obj):
        return f"{obj.employee.first_name} {obj.employee.last_name}"


class GeofenceSerializer(serializers.ModelSerializer):
    """Serializer for geofences"""
    
    class Meta:
        model = Geofence
        fields = ['id', 'name', 'description', 'center_latitude', 
                 'center_longitude', 'radius', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class LeaveRequestSerializer(serializers.ModelSerializer):
    """Serializer for an employee's own vacation/leave requests (mobile app)."""
    days = serializers.IntegerField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'request_type', 'title', 'start_date', 'end_date', 'days',
            'reason', 'status', 'submitted_date', 'reviewed_date', 'review_note',
        ]
        read_only_fields = ['status', 'submitted_date', 'reviewed_date', 'review_note']

    def validate(self, attrs):
        start = attrs.get('start_date', getattr(self.instance, 'start_date', None))
        end = attrs.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError({'end_date': 'End date cannot be before start date.'})
        return attrs


class PayslipSerializer(serializers.ModelSerializer):
    """An employee's own payslip -- mobile app 'Payslips' screen (read-only: HR reviews/edits from the web Payroll Run screen)."""

    class Meta:
        model = Payslip
        fields = [
            'id', 'period_start', 'period_end', 'status', 'pay_basis',
            'base_pay', 'overtime_hours', 'overtime_pay', 'other_allowances',
            'unpaid_leave_days', 'unpaid_leave_deduction', 'other_deductions', 'advances',
            'gross_pay', 'tax', 'net_pay', 'posted_at', 'generated_at',
        ]
        read_only_fields = fields


class AIQuerySerializer(serializers.Serializer):
    """Serializer for AI assistant queries"""
    query = serializers.CharField(max_length=500)
    context = serializers.DictField(required=False)
    
    def validate_query(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Query must be at least 3 characters long")
        return value.strip()


class AIResponseSerializer(serializers.Serializer):
    """Serializer for AI assistant responses"""
    query = serializers.CharField()
    response = serializers.CharField()
    data = serializers.DictField(required=False)
    confidence = serializers.FloatField(required=False)
    timestamp = serializers.DateTimeField()


class LocationUpdateSerializer(serializers.Serializer):
    """Serializer for real-time location updates"""
    employee_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    accuracy = serializers.FloatField(required=False)
    timestamp = serializers.DateTimeField(required=False)
    
    def validate_latitude(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        return value
    
    def validate_longitude(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        return value


class CheckInRequestSerializer(serializers.Serializer):
    """Serializer for check-in requests"""
    employee_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_latitude(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        return value
    
    def validate_longitude(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        return value

class CheckOutRequestSerializer(serializers.Serializer):
    """Serializer for check-out requests"""
    employee_id = serializers.IntegerField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    notes = serializers.CharField(required=False, allow_blank=True)
    
    def validate_latitude(self, value):
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90")
        return value
    
    def validate_longitude(self, value):
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180")
        return value
