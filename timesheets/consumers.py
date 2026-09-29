
import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Employee, CheckInLocation, LocationHistory, EmployeeStatus, Geofence


class LocationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for general location updates"""
    
    async def connect(self):
        # Check if user is authenticated
        if self.scope["user"].is_anonymous:
            await self.close()
            return
        
        self.room_group_name = 'location_updates'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'location_update')
            
            if message_type == 'location_update':
                await self.handle_location_update(data)
            elif message_type == 'check_in':
                await self.handle_check_in(data)
            elif message_type == 'check_out':
                await self.handle_check_out(data)
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'error': f'Error processing message: {str(e)}'
            }))
    
    async def handle_location_update(self, data):
        """Handle real-time location updates"""
        employee_id = data.get('employee_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        accuracy = data.get('accuracy')
        
        if not all([employee_id, latitude, longitude]):
            await self.send(text_data=json.dumps({
                'error': 'Missing required location data'
            }))
            return
        
        # Save location to database
        location_data = await self.save_location_update(
            employee_id, latitude, longitude, accuracy
        )
        
        if location_data:
            # Broadcast to all connected clients
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'location_broadcast',
                    'data': location_data
                }
            )
    
    async def handle_check_in(self, data):
        """Handle check-in requests"""
        employee_id = data.get('employee_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        result = await self.process_check_in(employee_id, latitude, longitude)
        
        await self.send(text_data=json.dumps({
            'type': 'check_in_response',
            'success': result['success'],
            'message': result['message'],
            'data': result.get('data', {})
        }))
    
    async def handle_check_out(self, data):
        """Handle check-out requests"""
        employee_id = data.get('employee_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        result = await self.process_check_out(employee_id, latitude, longitude)
        
        await self.send(text_data=json.dumps({
            'type': 'check_out_response',
            'success': result['success'],
            'message': result['message'],
            'data': result.get('data', {})
        }))
    
    async def location_broadcast(self, event):
        """Send location update to WebSocket"""
        await self.send(text_data=json.dumps({
            'type': 'location_update',
            'data': event['data']
        }))
    
    @database_sync_to_async
    def save_location_update(self, employee_id, latitude, longitude, accuracy=None):
        """Save location update to database"""
        try:
            employee = Employee.objects.get(id=employee_id)
            
            # Save to location history
            LocationHistory.objects.create(
                employee=employee,
                latitude=latitude,
                longitude=longitude,
                accuracy=accuracy
            )
            
            # Update employee status
            status, created = EmployeeStatus.objects.get_or_create(
                employee=employee,
                defaults={
                    'status': 'offline',
                    'current_latitude': latitude,
                    'current_longitude': longitude
                }
            )
            
            if not created:
                status.current_latitude = latitude
                status.current_longitude = longitude
                status.last_update = timezone.now()
                status.save()
            
            # Check geofences
            geofences = Geofence.objects.filter(is_active=True)
            within_geofence = None
            
            for geofence in geofences:
                if geofence.contains_point(latitude, longitude):
                    within_geofence = geofence
                    break
            
            status.current_geofence = within_geofence
            status.save()
            
            return {
                'employee_id': employee_id,
                'employee_name': employee.full_name,
                'latitude': latitude,
                'longitude': longitude,
                'timestamp': timezone.now().isoformat(),
                'geofence': within_geofence.name if within_geofence else None,
                'status': status.status
            }
            
        except Employee.DoesNotExist:
            return None
        except Exception as e:
            print(f"Error saving location: {e}")
            return None
    
    @database_sync_to_async
    def process_check_in(self, employee_id, latitude, longitude):
        """Process check-in request"""
        try:
            employee = Employee.objects.get(id=employee_id)
            
            # Check if already checked in today
            today = timezone.now().date()
            existing_checkin = CheckInLocation.objects.filter(
                employee=employee,
                check_type='in',
                timestamp__date=today
            ).first()
            
            if existing_checkin:
                return {
                    'success': False,
                    'message': 'Already checked in today'
                }
            
            # Check geofences
            geofences = Geofence.objects.filter(is_active=True)
            within_geofence = False
            geofence_name = None
            
            for geofence in geofences:
                if geofence.contains_point(latitude, longitude):
                    within_geofence = True
                    geofence_name = geofence.name
                    break
            
            # Create check-in record
            checkin = CheckInLocation.objects.create(
                employee=employee,
                latitude=latitude,
                longitude=longitude,
                check_type='in',
                is_within_geofence=within_geofence
            )
            
            # Update employee status
            status, created = EmployeeStatus.objects.get_or_create(
                employee=employee,
                defaults={'status': 'checked_in'}
            )
            
            status.status = 'checked_in'
            status.current_latitude = latitude
            status.current_longitude = longitude
            status.last_check_in = checkin.timestamp
            status.save()
            
            return {
                'success': True,
                'message': f'Checked in successfully{" at " + geofence_name if geofence_name else ""}',
                'data': {
                    'timestamp': checkin.timestamp.isoformat(),
                    'location': f"{latitude}, {longitude}",
                    'geofence': geofence_name
                }
            }
            
        except Employee.DoesNotExist:
            return {
                'success': False,
                'message': 'Employee not found'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error processing check-in: {str(e)}'
            }
    
    @database_sync_to_async
    def process_check_out(self, employee_id, latitude, longitude):
        """Process check-out request"""
        try:
            employee = Employee.objects.get(id=employee_id)
            
            # Check if checked in today
            today = timezone.now().date()
            checkin = CheckInLocation.objects.filter(
                employee=employee,
                check_type='in',
                timestamp__date=today
            ).first()
            
            if not checkin:
                return {
                    'success': False,
                    'message': 'No check-in found for today'
                }
            
            # Check if already checked out
            checkout = CheckInLocation.objects.filter(
                employee=employee,
                check_type='out',
                timestamp__date=today
            ).first()
            
            if checkout:
                return {
                    'success': False,
                    'message': 'Already checked out today'
                }
            
            # Create check-out record
            checkout = CheckInLocation.objects.create(
                employee=employee,
                latitude=latitude,
                longitude=longitude,
                check_type='out'
            )
            
            # Update employee status
            status = EmployeeStatus.objects.get(employee=employee)
            status.status = 'checked_out'
            status.current_latitude = latitude
            status.current_longitude = longitude
            status.last_check_out = checkout.timestamp
            status.save()
            
            return {
                'success': True,
                'message': 'Checked out successfully',
                'data': {
                    'timestamp': checkout.timestamp.isoformat(),
                    'location': f"{latitude}, {longitude}",
                    'work_duration': str(checkout.timestamp - checkin.timestamp)
                }
            }
            
        except Employee.DoesNotExist:
            return {
                'success': False,
                'message': 'Employee not found'
            }
        except EmployeeStatus.DoesNotExist:
            return {
                'success': False,
                'message': 'Employee status not found'
            }
        except Exception as e:
            return {
                'success': False,
                'message': f'Error processing check-out: {str(e)}'
            }


class EmployeeLocationConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for individual employee location tracking"""
    
    async def connect(self):
        self.employee_id = self.scope['url_route']['kwargs']['employee_id']
        self.room_group_name = f'employee_{self.employee_id}'
        
        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
    
    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        data = json.loads(text_data)
        
        # Send message to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'location_message',
                'data': data
            }
        )
    
    async def location_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps(event['data']))

