import logging

from django.db import transaction
from django.utils import timezone

from timesheets.models import (
    CheckInLocation,
    Employee,
    EmployeeStatus,
    Geofence,
    LocationHistory,
)

logger = logging.getLogger(__name__)


class LocationService:
    """Business logic for attendance location, geofencing, and status updates."""

    @staticmethod
    def reverse_geocode(latitude, longitude):
        # External reverse-geocoding can be connected later.
        return f"Lat: {latitude:.4f}, Lon: {longitude:.4f} (Simulated Address)"

    @staticmethod
    def matching_geofence(latitude, longitude):
        for geofence in Geofence.objects.filter(is_active=True):
            if geofence.contains_point(latitude, longitude):
                return geofence
        return None

    @staticmethod
    def is_within_geofence(latitude, longitude):
        return LocationService.matching_geofence(latitude, longitude) is not None

    @staticmethod
    @transaction.atomic
    def process_check_in(employee_id, latitude, longitude, notes="", user=None):
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return {"success": False, "message": "Employee not found."}

        geofence = LocationService.matching_geofence(latitude, longitude)
        address = LocationService.reverse_geocode(latitude, longitude)

        # Attribute the check-in to a project: prefer the matched
        # geofence's own project (this is *where* they physically are),
        # falling back to the employee's current assignment if the point
        # didn't land inside any geofence (e.g. GPS drift, off-site work).
        project = (geofence.project if geofence else None) or employee.project

        record = CheckInLocation.objects.create(
            employee=employee,
            project=project,
            latitude=latitude,
            longitude=longitude,
            check_type="in",
            address=address,
            is_within_geofence=geofence is not None,
            notes=notes or "",
        )

        EmployeeStatus.objects.update_or_create(
            employee=employee,
            defaults={
                "status": "checked_in",
                "last_check_in": timezone.now(),
                "current_latitude": latitude,
                "current_longitude": longitude,
                "current_geofence": geofence,
            },
        )

        LocationHistory.objects.create(
            employee=employee,
            latitude=latitude,
            longitude=longitude,
        )

        return {
            "success": True,
            "message": "Check-in successful.",
            "location_id": record.id,
            "is_within_geofence": geofence is not None,
        }

    @staticmethod
    @transaction.atomic
    def process_check_out(employee_id, latitude, longitude, notes=""):
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return {"success": False, "message": "Employee not found."}

        geofence = LocationService.matching_geofence(latitude, longitude)
        address = LocationService.reverse_geocode(latitude, longitude)
        project = (geofence.project if geofence else None) or employee.project

        record = CheckInLocation.objects.create(
            employee=employee,
            project=project,
            latitude=latitude,
            longitude=longitude,
            check_type="out",
            address=address,
            is_within_geofence=geofence is not None,
            notes=notes or "",
        )

        EmployeeStatus.objects.update_or_create(
            employee=employee,
            defaults={
                "status": "checked_out",
                "last_check_out": timezone.now(),
                "current_latitude": latitude,
                "current_longitude": longitude,
                "current_geofence": geofence,
            },
        )

        LocationHistory.objects.create(
            employee=employee,
            latitude=latitude,
            longitude=longitude,
        )

        return {
            "success": True,
            "message": "Check-out successful.",
            "location_id": record.id,
            "is_within_geofence": geofence is not None,
        }

    @staticmethod
    @transaction.atomic
    def update_employee_location(employee_id, latitude, longitude, accuracy=None):
        try:
            employee = Employee.objects.get(pk=employee_id)
        except Employee.DoesNotExist:
            return {"success": False, "message": "Employee not found."}

        geofence = LocationService.matching_geofence(latitude, longitude)
        history = LocationHistory.objects.create(
            employee=employee,
            latitude=latitude,
            longitude=longitude,
            accuracy=accuracy,
        )

        status, _ = EmployeeStatus.objects.get_or_create(employee=employee)
        status.current_latitude = latitude
        status.current_longitude = longitude
        status.current_geofence = geofence
        status.save(
            update_fields=[
                "current_latitude",
                "current_longitude",
                "current_geofence",
                "last_update",
            ]
        )

        return {
            "success": True,
            "message": "Location updated.",
            "location_history_id": history.id,
            "is_within_geofence": geofence is not None,
        }


class AIAssistantService:
    """Temporary local response until an approved AI provider is connected."""

    @staticmethod
    def process_query(query, context=None, user=None):
        return {
            "query": query,
            "response": f"AI Assistant response for query: '{query}'",
            "data": {},
            "confidence": 0.0,
            "timestamp": timezone.now().isoformat(),
        }
