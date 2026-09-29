# Advanced HR Module Integration Guide

This document outlines the integration of the advanced HR module into the existing timesheets application. The new module provides a comprehensive set of features for employee management, location tracking, and real-time communication.

## 1. Overview

The advanced HR module includes the following key components:

- **Models**: A rich data model for employees, departments, positions, documents, notes, and location tracking.
- **Views**: Web views for managing HR data and a location tracking dashboard.
- **API**: A RESTful API for mobile app integration, including endpoints for check-in/out, location updates, and an AI assistant.
- **WebSockets**: Real-time communication for location tracking and employee status updates.
- **Services**: A service layer to encapsulate business logic for location services and the AI assistant.

## 2. File Structure

The following files have been added or updated in the `timesheets` module:

- `models.py`: Contains the new data models.
- `views.py`: Contains the web views for the HR module.
- `api_views.py`: Contains the REST API views.
- `forms.py`: Contains forms for creating and editing HR data.
- `serializers.py`: Contains serializers for the REST API.
- `admin.py`: Configures the Django admin interface for the new models.
- `auth_views.py`: Contains custom authentication views and decorators.
- `services.py`: Contains business logic for location services and the AI assistant.
- `consumers.py`: Contains WebSocket consumers for real-time communication.
- `routing.py`: Configures WebSocket routing.
- `urls.py`: Main URL configuration for the timesheets module.
- `api_urls.py`: URL configuration for the REST API.

## 3. Key Features

### 3.1. Employee Management

- **Comprehensive Employee Profiles**: Store detailed information about employees, including personal data, address, employment details, and emergency contacts.
- **Document Management**: Upload and manage employee documents such as resumes, contracts, and certificates.
- **Notes**: Add and manage notes about employees, with an option for confidential notes.

### 3.2. Location Tracking

- **Real-time Location Updates**: Track employee locations in real-time using WebSockets.
- **Geofencing**: Define virtual boundaries and automatically track when employees enter or leave them.
- **Location History**: Store and view the location history of employees.
- **Check-in/out**: Allow employees to check in and out from their mobile devices, with GPS location capture.

### 3.3. Mobile App Integration

- **REST API**: A comprehensive REST API for mobile app integration.
- **Authentication**: Secure token-based authentication for the API.
- **Real-time Communication**: WebSocket support for real-time updates between the mobile app and the server.

### 3.4. AI Assistant

- **Natural Language Queries**: An AI assistant that can process natural language queries about HR data.
- **Extensible**: The AI assistant can be extended to support a wide range of queries and actions.

## 4. Setup and Configuration

To use the new HR module, you need to perform the following steps:

1.  **Install Dependencies**: Make sure you have all the required packages installed. The `requirements.txt` file should be updated to include `channels` and `django-ratelimit`.
2.  **Run Migrations**: Run `python manage.py makemigrations` and `python manage.py migrate` to create the new database tables.
3.  **Configure Channels**: Add `channels` to your `INSTALLED_APPS` and configure the `ASGI_APPLICATION` setting in your `settings.py` file.
4.  **Configure Google Maps API Key**: Add your Google Maps API key to your `settings.py` file to enable the location tracking dashboard.

## 5. API Endpoints

The following API endpoints are available for mobile app integration:

- `POST /timesheets/api/location/check-in/`: Check in an employee.
- `POST /timesheets/api/location/check-out/`: Check out an employee.
- `POST /timesheets/api/update-location/`: Update an employee's location.
- `POST /timesheets/api/ai-assistant/query/`: Send a query to the AI assistant.

For a full list of API endpoints, see the `api_urls.py` file.

## 6. WebSocket Channels

The following WebSocket channels are available for real-time communication:

- `ws/location/`: General location updates.
- `ws/employee/{employee_id}/`: Location updates for a specific employee.

## 7. Conclusion

The advanced HR module provides a powerful set of tools for managing your human resources and tracking employee locations. The module is designed to be extensible and can be customized to meet your specific needs.
