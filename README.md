# One Stop Contracting Co. - ERP System

A comprehensive Enterprise Resource Planning (ERP) system built with Django for construction and contracting companies.

## Features

### HR & Timesheet Management
- Employee profile management
- GPS-based check-in/check-out
- Geofencing for work locations
- Attendance tracking and calendar
- Location history
- Vacation/leave request management
- Real-time location updates via WebSocket
- Document attachments

### Procurement Module
- Vendor management
- Item master data
- Bill of Quantities (BOQ)
- Purchase Requisitions (PR)
- Purchase Orders (PO)
- PO Receipts
- Vendor performance reports

### Cost Control Module
- Budget management
- Cost forecasting
- Budget alerts
- Cost reports
- Variance analysis
- CPI and FAC calculations

## Technology Stack

- **Backend**: Django 4.2.7
- **API**: Django REST Framework 3.14.0
- **Database**: PostgreSQL / SQLite
- **WebSocket**: Django Channels 4.0.0
- **Authentication**: Token-based (DRF)
- **Frontend Admin**: Custom styled Django Admin

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd site_engineer_reports
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Database

Edit `config/settings.py` and update the database configuration:

**For PostgreSQL (Recommended for Production):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'erp_database',
        'USER': 'your_db_user',
        'PASSWORD': 'your_db_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

**For SQLite (Development):**
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}
```

### 5. Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Create Superuser

```bash
python manage.py createsuperuser
```

### 7. Collect Static Files

```bash
python manage.py collectstatic
```

### 8. Run Development Server

```bash
python manage.py runserver
```

The application will be available at `http://127.0.0.1:8000/`

## Admin Interface

Access the admin interface at `http://127.0.0.1:8000/admin/`

The admin interface features a custom blue theme matching the mobile app design.

## API Endpoints

### Authentication
- `POST /api-token-auth/` - Get authentication token

### Employee & HR
- `GET /api/timesheets/employees/` - List employees
- `GET /api/timesheets/employees/me/` - Get current user profile
- `PATCH /api/timesheets/employees/me/` - Update profile

### Attendance
- `POST /api/timesheets/location/check-in/` - Check in
- `POST /api/timesheets/location/check-out/` - Check out
- `GET /api/timesheets/checkins/` - Get attendance history
- `POST /api/timesheets/update-location/` - Update location

### Requests
- `GET /api/timesheets/requests/` - List requests
- `POST /api/timesheets/requests/` - Create request
- `PATCH /api/timesheets/requests/{id}/` - Update request
- `DELETE /api/timesheets/requests/{id}/` - Delete request

### Geofences
- `GET /api/timesheets/geofences/` - List geofences

## WebSocket Endpoints

- `ws://localhost:8000/ws/location/` - General location updates
- `ws://localhost:8000/ws/employee/{employee_id}/` - Employee-specific updates

## Mobile App Integration

This Django backend is designed to work with the React Native mobile app. See `INTEGRATION_GUIDE.md` in the mobile app repository for detailed integration instructions.

### Key Integration Points

1. **API Base URL**: Update in mobile app's `lib/api.ts`
2. **CORS Configuration**: Already configured for localhost:8081
3. **Token Authentication**: Implemented and ready
4. **WebSocket Support**: Configured for real-time updates

## Project Structure

```
site_engineer_reports/
├── config/                 # Project configuration
│   ├── settings.py        # Django settings
│   ├── urls.py            # Main URL configuration
│   ├── wsgi.py            # WSGI configuration
│   └── asgi.py            # ASGI configuration (WebSocket)
├── timesheets/            # HR & Timesheet app
│   ├── models.py          # Database models
│   ├── views.py           # Web views
│   ├── api_views.py       # API views
│   ├── serializers.py     # DRF serializers
│   ├── forms.py           # Django forms
│   ├── admin.py           # Admin configuration
│   ├── urls.py            # Web URLs
│   ├── api_urls.py        # API URLs
│   ├── consumers.py       # WebSocket consumers
│   ├── routing.py         # WebSocket routing
│   └── services.py        # Business logic
├── procurement/           # Procurement app
├── cost_control/          # Cost Control app
├── static/                # Static files
│   └── admin/
│       └── css/
│           └── custom_admin.css  # Custom admin styles
├── media/                 # User-uploaded files
├── templates/             # HTML templates
├── manage.py              # Django management script
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Custom Admin Styling

The admin interface uses a custom blue theme located in `static/admin/css/custom_admin.css`. The theme features:

- Modern blue color scheme
- Improved typography
- Better form layouts
- Enhanced tables and buttons
- Responsive design
- Custom login page styling

## Development

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Creating API Tokens

```bash
python manage.py drf_create_token <username>
```

## Production Deployment

### 1. Update Settings

In `config/settings.py`:

```python
DEBUG = False
ALLOWED_HOSTS = ['your-domain.com']
SECRET_KEY = 'your-production-secret-key'
```

### 2. Configure Database

Use PostgreSQL for production:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'production_db',
        'USER': 'db_user',
        'PASSWORD': 'secure_password',
        'HOST': 'db_host',
        'PORT': '5432',
    }
}
```

### 3. Configure Static Files

```bash
python manage.py collectstatic --noinput
```

### 4. Use Gunicorn

```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

### 5. Configure Nginx

Example Nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /static/ {
        alias /path/to/staticfiles/;
    }

    location /media/ {
        alias /path/to/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 6. WebSocket with Daphne

For WebSocket support in production:

```bash
daphne -b 0.0.0.0 -p 8001 config.asgi:application
```

## Security Considerations

1. **Change SECRET_KEY** in production
2. **Use HTTPS** for all production traffic
3. **Enable security middleware** in settings
4. **Set proper CORS origins**
5. **Use environment variables** for sensitive data
6. **Regular security updates**

## Support

For issues or questions, please contact the development team.

## License

Proprietary - One Stop Contracting Co.
