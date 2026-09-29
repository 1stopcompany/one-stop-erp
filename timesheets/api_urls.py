
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import api_views

# Create router for viewsets
router = DefaultRouter()
router.register(r'checkins', api_views.CheckInLocationViewSet)
router.register(r'employee-status', api_views.EmployeeStatusViewSet)
router.register(r'geofences', api_views.GeofenceViewSet)
router.register(r'requests', api_views.LeaveRequestViewSet, basename='leaverequest')
router.register(r'payslips', api_views.PayslipViewSet, basename='payslip')

# API URL patterns
urlpatterns = [
    path('', include(router.urls)),
    # Renamed the original check-in/out to location-based
    path('employees/me/', api_views.MyEmployeeView.as_view(), name='employee_me'),

    path('location/check-in/', api_views.location_check_in, name='api_location_check_in'),
    path('location/check-out/', api_views.location_check_out, name='api_location_check_out'),
    
    path('update-location/', api_views.update_location, name='api_update_location'),
    path('ai-assistant/query/', api_views.ai_assistant_query, name='api_ai_query'),
]
