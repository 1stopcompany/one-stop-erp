# Construction Reports API Documentation

## Overview

Complete REST API documentation for the Construction Reports Management System. This API allows programmatic access to all report management functionality.

---

## Base URL

```
http://localhost:8000/api/
```

---

## Authentication

All API endpoints require authentication. Use Django's session authentication or token authentication.

### Session Authentication
```bash
curl -X GET http://localhost:8000/api/reports/ \
  -H "Cookie: sessionid=your-session-id"
```

### Token Authentication (Optional Setup)
```bash
pip install djangorestframework
```

---

## Daily Reports API

### List Daily Reports

**Endpoint**: `GET /api/reports/daily/`

**Description**: Retrieve all daily reports

**Query Parameters**:
- `status`: Filter by status (draft, submitted, approved, archived)
- `project`: Filter by project ID
- `date_from`: Filter reports from date (YYYY-MM-DD)
- `date_to`: Filter reports to date (YYYY-MM-DD)
- `page`: Pagination page number
- `limit`: Results per page (default: 20)

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?status=approved&limit=10" \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "count": 42,
  "next": "http://localhost:8000/api/reports/daily/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "report_number": "DCR-001-20251218-001",
      "project": {
        "id": 1,
        "name": "Shopping Mall Renovation"
      },
      "site_engineer": {
        "id": 1,
        "username": "engineer1",
        "first_name": "Ahmed",
        "last_name": "Engineer"
      },
      "report_date": "2025-12-18",
      "weather": "sunny",
      "temperature": 25,
      "status": "approved",
      "remarks": "Good progress on foundation work",
      "created_at": "2025-12-18T10:30:00Z",
      "updated_at": "2025-12-18T14:45:00Z",
      "submitted_at": "2025-12-18T11:00:00Z",
      "approved_at": "2025-12-18T14:45:00Z",
      "approved_by": {
        "id": 2,
        "username": "manager1",
        "first_name": "John",
        "last_name": "Manager"
      }
    }
  ]
}
```

---

### Get Daily Report Detail

**Endpoint**: `GET /api/reports/daily/{id}/`

**Description**: Retrieve a specific daily report with all related data

**Example Request**:
```bash
curl -X GET http://localhost:8000/api/reports/daily/1/ \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "id": 1,
  "report_number": "DCR-001-20251218-001",
  "project": {
    "id": 1,
    "name": "Shopping Mall Renovation",
    "location": "Downtown"
  },
  "site_engineer": {
    "id": 1,
    "username": "engineer1",
    "first_name": "Ahmed",
    "last_name": "Engineer"
  },
  "report_date": "2025-12-18",
  "weather": "sunny",
  "temperature": 25,
  "status": "approved",
  "remarks": "Good progress on foundation work",
  "workforce": [
    {
      "id": 1,
      "category": "Laborers",
      "count": 25
    },
    {
      "id": 2,
      "category": "Engineers",
      "count": 5
    }
  ],
  "equipment": [
    {
      "id": 1,
      "name": "Excavator",
      "quantity": 2,
      "status": "operational"
    }
  ],
  "activities": [
    {
      "id": 1,
      "description": "Foundation excavation",
      "progress_percentage": 85
    }
  ],
  "materials": [
    {
      "id": 1,
      "name": "Concrete",
      "quantity": 50.5,
      "unit": "cubic meters"
    }
  ],
  "visitors": [
    {
      "id": 1,
      "name": "John Doe",
      "purpose": "Site inspection",
      "time_in": "09:00:00",
      "time_out": "11:30:00"
    }
  ],
  "attachments": [
    {
      "id": 1,
      "file": "http://localhost:8000/media/reports/2025/12/18/photo.jpg",
      "description": "Site photo",
      "uploaded_at": "2025-12-18T10:30:00Z"
    }
  ],
  "created_at": "2025-12-18T10:30:00Z",
  "updated_at": "2025-12-18T14:45:00Z",
  "submitted_at": "2025-12-18T11:00:00Z",
  "approved_at": "2025-12-18T14:45:00Z"
}
```

---

### Create Daily Report

**Endpoint**: `POST /api/reports/daily/`

**Description**: Create a new daily report

**Request Body**:
```json
{
  "project": 1,
  "report_date": "2025-12-18",
  "weather": "sunny",
  "temperature": 25,
  "remarks": "Good progress on foundation work",
  "workforce": [
    {
      "category": "Laborers",
      "count": 25
    }
  ],
  "equipment": [
    {
      "name": "Excavator",
      "quantity": 2,
      "status": "operational"
    }
  ],
  "activities": [
    {
      "description": "Foundation excavation",
      "progress_percentage": 85
    }
  ],
  "materials": [
    {
      "name": "Concrete",
      "quantity": 50.5,
      "unit": "cubic meters"
    }
  ]
}
```

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/reports/daily/ \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "project": 1,
    "report_date": "2025-12-18",
    "weather": "sunny",
    "temperature": 25,
    "remarks": "Good progress"
  }'
```

**Response** (201 Created):
```json
{
  "id": 1,
  "report_number": "DCR-001-20251218-001",
  "project": 1,
  "site_engineer": 1,
  "report_date": "2025-12-18",
  "weather": "sunny",
  "temperature": 25,
  "status": "draft",
  "remarks": "Good progress",
  "created_at": "2025-12-18T10:30:00Z"
}
```

---

### Update Daily Report

**Endpoint**: `PUT /api/reports/daily/{id}/`

**Description**: Update a daily report (only draft reports)

**Request Body**:
```json
{
  "weather": "cloudy",
  "temperature": 22,
  "remarks": "Updated remarks"
}
```

**Response** (200 OK):
```json
{
  "id": 1,
  "report_number": "DCR-001-20251218-001",
  "weather": "cloudy",
  "temperature": 22,
  "remarks": "Updated remarks",
  "updated_at": "2025-12-18T15:00:00Z"
}
```

---

### Submit Daily Report

**Endpoint**: `POST /api/reports/daily/{id}/submit/`

**Description**: Submit a daily report for approval

**Request Body**: Empty

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/reports/daily/1/submit/ \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "id": 1,
  "status": "submitted",
  "submitted_at": "2025-12-18T11:00:00Z",
  "message": "Report submitted successfully"
}
```

---

### Approve Daily Report

**Endpoint**: `POST /api/reports/daily/{id}/approve/`

**Description**: Approve a daily report (manager only)

**Request Body**: Empty

**Example Request**:
```bash
curl -X POST http://localhost:8000/api/reports/daily/1/approve/ \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "id": 1,
  "status": "approved",
  "approved_at": "2025-12-18T14:45:00Z",
  "approved_by": 2,
  "message": "Report approved successfully"
}
```

---

### Export Daily Report to PDF

**Endpoint**: `GET /api/reports/daily/{id}/export-pdf/`

**Description**: Export daily report as PDF

**Example Request**:
```bash
curl -X GET http://localhost:8000/api/reports/daily/1/export-pdf/ \
  -H "Authorization: Bearer your-token" \
  -o report.pdf
```

**Response** (200 OK): PDF file

---

## Monthly Reports API

### List Monthly Reports

**Endpoint**: `GET /api/reports/monthly/`

**Description**: Retrieve all monthly reports

**Query Parameters**:
- `status`: Filter by status
- `project`: Filter by project ID
- `month`: Filter by month (YYYY-MM)
- `page`: Pagination page number
- `limit`: Results per page

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/reports/monthly/?status=approved" \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "count": 12,
  "results": [
    {
      "id": 1,
      "report_number": "MR-001-202512-001",
      "project": {
        "id": 1,
        "name": "Shopping Mall Renovation"
      },
      "site_engineer": {
        "id": 1,
        "username": "engineer1"
      },
      "reporting_month": "2025-12-01",
      "status": "approved",
      "remarks": "Monthly progress report",
      "created_at": "2025-12-18T10:30:00Z"
    }
  ]
}
```

---

### Get Monthly Report Detail

**Endpoint**: `GET /api/reports/monthly/{id}/`

**Description**: Retrieve a specific monthly report

**Example Request**:
```bash
curl -X GET http://localhost:8000/api/reports/monthly/1/ \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "id": 1,
  "report_number": "MR-001-202512-001",
  "project": {
    "id": 1,
    "name": "Shopping Mall Renovation"
  },
  "reporting_month": "2025-12-01",
  "status": "approved",
  "remarks": "Monthly progress report",
  "floor_activities": [
    {
      "id": 1,
      "floor_number": 1,
      "description": "Ground floor renovation",
      "completion_percentage": 75
    }
  ],
  "external_works": [
    {
      "id": 1,
      "description": "Electrical wiring",
      "contractor": "ElectroWorks Inc",
      "status": "ongoing"
    }
  ],
  "material_supplies": [
    {
      "id": 1,
      "material_name": "Concrete",
      "quantity": 500,
      "unit": "cubic meters",
      "supplier": "BuildMaterials Ltd"
    }
  ],
  "upcoming_works": [
    {
      "id": 1,
      "description": "Interior finishing",
      "planned_start_date": "2025-12-25",
      "estimated_duration_days": 30
    }
  ]
}
```

---

### Create Monthly Report

**Endpoint**: `POST /api/reports/monthly/`

**Description**: Create a new monthly report

**Request Body**:
```json
{
  "project": 1,
  "reporting_month": "2025-12-01",
  "remarks": "Monthly progress report",
  "floor_activities": [
    {
      "floor_number": 1,
      "description": "Ground floor renovation",
      "completion_percentage": 75
    }
  ]
}
```

**Response** (201 Created):
```json
{
  "id": 1,
  "report_number": "MR-001-202512-001",
  "status": "draft",
  "created_at": "2025-12-18T10:30:00Z"
}
```

---

### Submit Monthly Report

**Endpoint**: `POST /api/reports/monthly/{id}/submit/`

**Response** (200 OK):
```json
{
  "id": 1,
  "status": "submitted",
  "submitted_at": "2025-12-18T11:00:00Z"
}
```

---

### Approve Monthly Report

**Endpoint**: `POST /api/reports/monthly/{id}/approve/`

**Response** (200 OK):
```json
{
  "id": 1,
  "status": "approved",
  "approved_at": "2025-12-18T14:45:00Z"
}
```

---

## Projects API

### List Projects

**Endpoint**: `GET /api/projects/`

**Description**: Retrieve all projects

**Query Parameters**:
- `status`: Filter by status (planning, active, paused, completed)
- `manager`: Filter by manager ID
- `page`: Pagination page number

**Example Request**:
```bash
curl -X GET "http://localhost:8000/api/projects/?status=active" \
  -H "Authorization: Bearer your-token"
```

**Response** (200 OK):
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "name": "Shopping Mall Renovation",
      "description": "Complete renovation of shopping mall",
      "location": "Downtown",
      "status": "active",
      "manager": {
        "id": 2,
        "username": "manager1",
        "first_name": "John"
      },
      "start_date": "2025-01-01",
      "end_date": "2025-12-31",
      "budget": 1000000.00,
      "created_at": "2025-01-01T10:00:00Z"
    }
  ]
}
```

---

### Get Project Detail

**Endpoint**: `GET /api/projects/{id}/`

**Response** (200 OK):
```json
{
  "id": 1,
  "name": "Shopping Mall Renovation",
  "description": "Complete renovation",
  "location": "Downtown",
  "status": "active",
  "manager": 2,
  "site_engineers": [1, 3, 5],
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "budget": 1000000.00,
  "daily_reports_count": 42,
  "monthly_reports_count": 12
}
```

---

### Create Project

**Endpoint**: `POST /api/projects/`

**Request Body**:
```json
{
  "name": "New Construction Project",
  "description": "Project description",
  "location": "Location",
  "status": "active",
  "manager": 2,
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "budget": 500000.00
}
```

**Response** (201 Created):
```json
{
  "id": 2,
  "name": "New Construction Project",
  "created_at": "2025-12-18T10:30:00Z"
}
```

---

## Users API

### List Users

**Endpoint**: `GET /api/users/`

**Description**: Retrieve all users

**Query Parameters**:
- `role`: Filter by role (engineer, manager, admin)
- `search`: Search by username or name
- `page`: Pagination page number

**Response** (200 OK):
```json
{
  "count": 10,
  "results": [
    {
      "id": 1,
      "username": "engineer1",
      "first_name": "Ahmed",
      "last_name": "Engineer",
      "email": "engineer@example.com",
      "profile": {
        "role": "engineer",
        "phone": "123-456-7890",
        "department": "Engineering"
      }
    }
  ]
}
```

---

### Get Current User

**Endpoint**: `GET /api/users/me/`

**Description**: Get current authenticated user's information

**Response** (200 OK):
```json
{
  "id": 1,
  "username": "engineer1",
  "first_name": "Ahmed",
  "last_name": "Engineer",
  "email": "engineer@example.com",
  "profile": {
    "role": "engineer",
    "phone": "123-456-7890"
  }
}
```

---

## Dashboard API

### Get Dashboard Metrics

**Endpoint**: `GET /api/dashboard/metrics/`

**Description**: Get dashboard metrics for current user

**Response** (200 OK):
```json
{
  "user_role": "engineer",
  "daily_reports_today": 3,
  "daily_reports_submitted": 5,
  "daily_reports_approved": 38,
  "monthly_reports_pending": 2,
  "monthly_reports_approved": 7,
  "draft_reports": 1,
  "recent_reports": [
    {
      "id": 1,
      "report_number": "DCR-001",
      "type": "daily",
      "status": "approved",
      "date": "2025-12-18"
    }
  ]
}
```

---

## Audit Logs API

### List Audit Logs

**Endpoint**: `GET /api/audit-logs/`

**Description**: Retrieve audit logs

**Query Parameters**:
- `action`: Filter by action (create, update, approve, submit)
- `model_name`: Filter by model name
- `user`: Filter by user ID
- `date_from`: Filter from date
- `date_to`: Filter to date

**Response** (200 OK):
```json
{
  "count": 100,
  "results": [
    {
      "id": 1,
      "user": {
        "id": 1,
        "username": "engineer1"
      },
      "action": "create",
      "model_name": "DailyReport",
      "object_id": 1,
      "description": "Created daily report DCR-001",
      "ip_address": "192.168.1.1",
      "timestamp": "2025-12-18T10:30:00Z"
    }
  ]
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid request",
  "details": {
    "field_name": ["Error message"]
  }
}
```

### 401 Unauthorized
```json
{
  "error": "Authentication required",
  "message": "Please log in to access this resource"
}
```

### 403 Forbidden
```json
{
  "error": "Permission denied",
  "message": "You do not have permission to access this resource"
}
```

### 404 Not Found
```json
{
  "error": "Not found",
  "message": "The requested resource was not found"
}
```

### 500 Server Error
```json
{
  "error": "Internal server error",
  "message": "An unexpected error occurred"
}
```

---

## Rate Limiting

API requests are limited to:
- 100 requests per minute for authenticated users
- 10 requests per minute for anonymous users

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1639832400
```

---

## Pagination

Default page size: 20 items

Request:
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?page=2&limit=50"
```

Response includes:
```json
{
  "count": 100,
  "next": "http://localhost:8000/api/reports/daily/?page=3",
  "previous": "http://localhost:8000/api/reports/daily/?page=1",
  "results": [...]
}
```

---

## Filtering & Search

### Date Range Filter
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?date_from=2025-12-01&date_to=2025-12-31"
```

### Status Filter
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?status=approved"
```

### Project Filter
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?project=1"
```

### Search
```bash
curl -X GET "http://localhost:8000/api/reports/daily/?search=DCR-001"
```

---

## Webhooks (Optional)

Configure webhooks for events:
- Report created
- Report submitted
- Report approved
- Report rejected

Webhook payload:
```json
{
  "event": "report.created",
  "timestamp": "2025-12-18T10:30:00Z",
  "data": {
    "id": 1,
    "report_number": "DCR-001",
    "type": "daily"
  }
}
```

---

## Code Examples

### Python (requests)
```python
import requests

# Get daily reports
response = requests.get(
    'http://localhost:8000/api/reports/daily/',
    headers={'Authorization': 'Bearer your-token'}
)
reports = response.json()

# Create new report
data = {
    'project': 1,
    'report_date': '2025-12-18',
    'weather': 'sunny',
    'temperature': 25
}
response = requests.post(
    'http://localhost:8000/api/reports/daily/',
    json=data,
    headers={'Authorization': 'Bearer your-token'}
)
```

### JavaScript (fetch)
```javascript
// Get daily reports
fetch('http://localhost:8000/api/reports/daily/', {
  headers: {
    'Authorization': 'Bearer your-token'
  }
})
.then(response => response.json())
.then(data => console.log(data));

// Create new report
fetch('http://localhost:8000/api/reports/daily/', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your-token',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    project: 1,
    report_date: '2025-12-18',
    weather: 'sunny',
    temperature: 25
  })
})
.then(response => response.json())
.then(data => console.log(data));
```

### cURL
```bash
# Get reports
curl -X GET http://localhost:8000/api/reports/daily/ \
  -H "Authorization: Bearer your-token"

# Create report
curl -X POST http://localhost:8000/api/reports/daily/ \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{"project": 1, "report_date": "2025-12-18"}'
```

---

## API Versioning

Current API version: v1

Future versions will be available at:
- `/api/v2/`
- `/api/v3/`

---

**Last Updated**: December 19, 2025  
**Status**: Production Ready  
**Version**: 1.0.0
