
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, Count
from datetime import datetime, timedelta
import json
import logging
from rest_framework.views import APIView
from rest_framework.exceptions import APIException, PermissionDenied
from django.shortcuts import get_object_or_404


def local_day_range_utc(day):
    """
    (start, end) aware-UTC datetimes spanning local midnight-to-midnight
    for `day`, for a >=/< range filter instead of a `__date` lookup.
    Django compiles `timestamp__date=...` to
    `DATE(CONVERT_TZ(timestamp, 'UTC', '<TIME_ZONE>'))` on MySQL, which
    silently matches nothing (no error) if the server's
    mysql.time_zone_name tables were never loaded via mysql_tzinfo_to_sql
    -- a common out-of-the-box MySQL state. A plain range on the stored
    UTC value needs no server-side named-timezone lookup at all.
    """
    start = timezone.make_aware(datetime.combine(day, datetime.min.time()))
    return start, start + timedelta(days=1)


class MyEmployeeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # يرجّع الموظف المرتبط بالمستخدم الحالي
        emp = get_object_or_404(Employee.objects.select_related('department', 'position'), user=request.user)

        return Response({
            "id": emp.id,
            "employee_id": emp.employee_id,
            "full_name": emp.full_name,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "department": emp.department.name if emp.department_id else None,
            "position": emp.position.title if emp.position_id else None,
            "email": emp.email,
            "phone_number": emp.phone_number,
            "employment_status": emp.employment_status,
            "employment_type": emp.employment_type,
            "hire_date": emp.hire_date,
            "emergency_contact_name": emp.emergency_contact_name,
            "emergency_contact_relationship": emp.emergency_contact_relationship,
            "emergency_contact_phone": emp.emergency_contact_phone,
        }, status=status.HTTP_200_OK)

logger = logging.getLogger(__name__)


class AIAssistantThrottle(UserRateThrottle):
    """Custom throttle for AI assistant queries"""
    scope = 'ai_assistant'


class SecureLocationThrottle(UserRateThrottle):
    """Custom throttle for location-sensitive operations"""
    scope = 'location_updates'
    rate = '200/hour'

from .models import (
    Employee, CheckInLocation, LocationHistory,
    EmployeeStatus, Geofence, LeaveRequest, Payslip
)
from .serializers import (
    EmployeeLocationSerializer, CheckInLocationSerializer,
    LocationHistorySerializer, EmployeeStatusSerializer,
    GeofenceSerializer, AIQuerySerializer, AIResponseSerializer,
    LocationUpdateSerializer, CheckInRequestSerializer,
    CheckOutRequestSerializer, LeaveRequestSerializer, PayslipSerializer
)
from .services.Location_Service import LocationService, AIAssistantService


class CheckInLocationViewSet(viewsets.ModelViewSet):
    """ViewSet for check-in/out locations"""
    queryset = CheckInLocation.objects.all()
    serializer_class = CheckInLocationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = CheckInLocation.objects.select_related('employee')
        
        # Filter by employee
        employee_id = self.request.query_params.get('employee_id')
        if employee_id:
            queryset = queryset.filter(employee_id=employee_id)
        
        # Filter by check type
        check_type = self.request.query_params.get('check_type')
        if check_type in ['in', 'out']:
            queryset = queryset.filter(check_type=check_type)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__gte=local_day_range_utc(start_date)[0])
            except ValueError:
                pass

        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(timestamp__lt=local_day_range_utc(end_date)[1])
            except ValueError:
                pass
        
        return queryset.order_by('-timestamp')
    
    @action(detail=False, methods=['get'])
    def today(self, request):
        """Get today's check-ins/outs"""
        today_start, today_end = local_day_range_utc(timezone.now().date())
        queryset = self.get_queryset().filter(timestamp__gte=today_start, timestamp__lt=today_end)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get check-in/out summary"""
        today_start, today_end = local_day_range_utc(timezone.now().date())

        summary = {
            'total_employees': Employee.objects.count(),
            'checked_in_today': CheckInLocation.objects.filter(
                timestamp__gte=today_start, timestamp__lt=today_end,
                check_type='in'
            ).count(),
            'checked_out_today': CheckInLocation.objects.filter(
                timestamp__gte=today_start, timestamp__lt=today_end,
                check_type='out'
            ).count(),
            'currently_online': EmployeeStatus.objects.filter(
                status='checked_in',
                last_update__gte=timezone.now() - timedelta(minutes=10)
            ).count()
        }
        
        return Response(summary)


class EmployeeStatusViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for employee status"""
    queryset = EmployeeStatus.objects.select_related('employee', 'current_geofence')
    serializer_class = EmployeeStatusSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        queryset = self.queryset
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by online status
        online_only = self.request.query_params.get('online_only')
        if online_only and online_only.lower() == 'true':
            cutoff_time = timezone.now() - timedelta(minutes=10)
            queryset = queryset.filter(last_update__gte=cutoff_time)
        
        return queryset.order_by('employee__first_name', 'employee__last_name')
    
    @action(detail=False, methods=['get'])
    def online(self, request):
        """Get currently online employees"""
        cutoff_time = timezone.now() - timedelta(minutes=10)
        queryset = self.get_queryset().filter(last_update__gte=cutoff_time)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def by_location(self, request):
        """Get employees grouped by location/geofence"""
        queryset = self.get_queryset()
        
        # Group by geofence
        locations = {}
        for status in queryset:
            location_name = status.current_geofence.name if status.current_geofence else 'Unknown'
            if location_name not in locations:
                locations[location_name] = []
            
            locations[location_name].append({
                'employee_id': status.employee.id,
                'employee_name': status.employee.full_name,
                'status': status.status,
                'last_update': status.last_update,
                'is_online': status.is_online
            })
        
        return Response(locations)


class LeaveRequestViewSet(viewsets.ModelViewSet):
    """An employee's own vacation/leave requests -- mobile app 'Requests' screen.

    Scoped to the logged-in user's own Employee record: an employee only
    ever sees, creates, or deletes their own requests here. Approval by a
    manager happens elsewhere (Django admin for now); a request can only
    be edited or deleted by its owner while it is still 'pending'.
    """
    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LeaveRequest.objects.filter(employee__user=self.request.user).select_related('employee')

    def perform_create(self, serializer):
        employee = get_object_or_404(Employee, user=self.request.user)
        serializer.save(employee=employee)

    def _deny_unless_pending(self, instance):
        if instance.status != 'pending':
            raise PermissionDenied('Only a pending request can be changed or withdrawn.')

    def perform_update(self, serializer):
        self._deny_unless_pending(self.get_object())
        serializer.save()

    def perform_destroy(self, instance):
        self._deny_unless_pending(instance)
        instance.delete()


class PayslipViewSet(viewsets.ReadOnlyModelViewSet):
    """
    An employee's own payslips -- mobile app 'Payslips' screen. Read-only:
    HR reviews, edits and posts payslips from the web Payroll Run screen
    only, an employee here can only ever see their own, never anyone
    else's, and never change one.
    """
    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Payslip.objects.filter(employee__user=self.request.user).exclude(status='excluded').order_by('-period_start')

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        """The same formatted payslip PDF as the web app, downloadable from the mobile app."""
        from django.http import HttpResponse
        from .pdf import generate_payslip_pdf

        payslip = self.get_object()
        pdf_bytes = generate_payslip_pdf(payslip)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename=payslip-{payslip.period_start.strftime("%Y-%m")}.pdf'
        return response


class GeofenceViewSet(viewsets.ModelViewSet):
    """ViewSet for geofences"""
    queryset = Geofence.objects.all()
    serializer_class = GeofenceSerializer
    permission_classes = [IsAuthenticated]
    
    @action(detail=True, methods=['get'])
    def employees(self, request, pk=None):
        """Get employees currently in this geofence"""
        geofence = self.get_object()
        statuses = EmployeeStatus.objects.filter(current_geofence=geofence)
        serializer = EmployeeStatusSerializer(statuses, many=True)
        return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([SecureLocationThrottle])
@ratelimit(key='user', rate='100/h', method='POST')
@csrf_exempt
def location_check_in(request):
    """API endpoint for employee check-in with enhanced security (Location-based)"""
    
    # Log check-in attempt
    logger.info(f"Check-in attempt from user {request.user.username}")
    
    # Validate location data
    latitude = request.data.get('latitude')
    longitude = request.data.get('longitude')
    
    if latitude is None or longitude is None:
        return Response({
            'error': 'Location coordinates are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate coordinate ranges
    try:
        lat = float(latitude)
        lng = float(longitude)
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return Response({
                'error': 'Invalid coordinates'
            }, status=status.HTTP_400_BAD_REQUEST)
    except (ValueError, TypeError):
        return Response({
            'error': 'Invalid coordinate format'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = CheckInRequestSerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            result = LocationService.process_check_in(
                employee_id=serializer.validated_data['employee_id'],
                latitude=serializer.validated_data['latitude'],
                longitude=serializer.validated_data['longitude'],
                notes=serializer.validated_data.get('notes', ''),
                user=request.user
            )
            
            # Log successful check-in
            if result.get('success'):
                logger.info(f"Check-in successful for user {request.user.username}")
            else:
                logger.warning(f"Check-in failed for user {request.user.username}: {result.get('message')}")
            
            return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)
            
        except APIException:
            # e.g. ProjectNotReady (403 with a clear reason) -- let DRF answer
            # with it instead of hiding it behind a generic 500.
            raise
        except Exception as e:
            logger.error(f"Check-in error for user {request.user.username}: {str(e)}")
            return Response({
                'error': 'Check-in processing failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def location_check_out(request):
    """API endpoint for employee check-out (Location-based)"""
    serializer = CheckOutRequestSerializer(data=request.data)
    
    if serializer.is_valid():
        result = LocationService.process_check_out(
            employee_id=serializer.validated_data['employee_id'],
            latitude=serializer.validated_data['latitude'],
            longitude=serializer.validated_data['longitude'],
            notes=serializer.validated_data.get('notes', '')
        )
        
        return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_location(request):
    """API endpoint for real-time location updates"""
    serializer = LocationUpdateSerializer(data=request.data)
    
    if serializer.is_valid():
        result = LocationService.update_employee_location(
            employee_id=serializer.validated_data['employee_id'],
            latitude=serializer.validated_data['latitude'],
            longitude=serializer.validated_data['longitude'],
            accuracy=serializer.validated_data.get('accuracy')
        )
        
        return Response(result, status=status.HTTP_200_OK if result['success'] else status.HTTP_400_BAD_REQUEST)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@throttle_classes([AIAssistantThrottle])
@ratelimit(key='user', rate='50/h', method='POST')
@csrf_exempt
def ai_assistant_query(request):
    """API endpoint for AI assistant queries with enhanced security"""
    
    # Log the query attempt
    logger.info(f"AI query attempt from user {request.user.username}")
    
    serializer = AIQuerySerializer(data=request.data)
    
    if serializer.is_valid():
        try:
            result = AIAssistantService.process_query(
                query=serializer.validated_data['query'],
                user=request.user
            )
            
            response_serializer = AIResponseSerializer(data=result)
            if response_serializer.is_valid():
                return Response(response_serializer.data, status=status.HTTP_200_OK)
            else:
                logger.error(f"AI response serialization error: {response_serializer.errors}")
                return Response({
                    'error': 'AI response processing failed'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                
        except Exception as e:
            logger.error(f"AI query error for user {request.user.username}: {str(e)}")
            return Response({
                'error': 'AI query processing failed'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
