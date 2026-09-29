# Deployment Guide - Construction Reports System

## Deployment Overview

Complete guide for deploying the Construction Reports Management System to production environments.

---

## Pre-Deployment Checklist

- [ ] Code review completed
- [ ] All tests passing
- [ ] Database migrations tested
- [ ] Static files collected
- [ ] Environment variables configured
- [ ] SSL certificate obtained
- [ ] Backup strategy in place
- [ ] Monitoring configured
- [ ] Documentation updated
- [ ] Security audit completed

---

## Deployment Options

### 1. Heroku Deployment

#### Prerequisites
```bash
pip install heroku
heroku login
```

#### Create Heroku App
```bash
heroku create your-app-name
```

#### Configure Environment
```bash
heroku config:set DEBUG=False
heroku config:set SECRET_KEY=your-secret-key
heroku config:set ALLOWED_HOSTS=your-app-name.herokuapp.com
```

#### Deploy
```bash
git push heroku main
heroku run python manage.py migrate
heroku run python manage.py createsuperuser
```

#### Procfile
```
web: gunicorn config.wsgi --log-file -
release: python manage.py migrate
```

#### runtime.txt
```
python-3.11.0
```

---

### 2. AWS EC2 Deployment

#### Instance Setup
```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update
sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3-pip python3-venv nginx postgresql postgresql-contrib
```

#### Clone Project
```bash
git clone your-repo-url
cd site_engineer_reports
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Configure PostgreSQL
```bash
sudo -u postgres psql
CREATE DATABASE reports_db;
CREATE USER reports_user WITH PASSWORD 'secure_password';
ALTER ROLE reports_user SET client_encoding TO 'utf8';
ALTER ROLE reports_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE reports_user SET default_transaction_deferrable TO on;
ALTER ROLE reports_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE reports_db TO reports_user;
\q
```

#### Update settings.py
```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'reports_db',
        'USER': 'reports_user',
        'PASSWORD': 'secure_password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'www.your-domain.com']
SECRET_KEY = 'your-production-secret-key'
STATIC_ROOT = '/home/ubuntu/site_engineer_reports/staticfiles'
```

#### Run Migrations
```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --noinput
```

#### Configure Gunicorn
```bash
pip install gunicorn
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

#### Create Systemd Service
```bash
sudo nano /etc/systemd/system/gunicorn.service
```

```ini
[Unit]
Description=gunicorn daemon for django project
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/site_engineer_reports
ExecStart=/home/ubuntu/site_engineer_reports/venv/bin/gunicorn \
          --workers 3 \
          --bind unix:/home/ubuntu/site_engineer_reports/gunicorn.sock \
          config.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl start gunicorn
sudo systemctl enable gunicorn
```

#### Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/reports
```

```nginx
upstream django {
    server unix:/home/ubuntu/site_engineer_reports/gunicorn.sock;
}

server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com www.your-domain.com;
    
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    client_max_body_size 100M;
    
    location /static/ {
        alias /home/ubuntu/site_engineer_reports/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    location /media/ {
        alias /home/ubuntu/site_engineer_reports/media/;
        expires 7d;
    }
    
    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/reports /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### SSL Certificate (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d your-domain.com -d www.your-domain.com
```

---

### 3. Docker Deployment

#### Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "config.wsgi:application"]
```

#### docker-compose.yml
```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: reports_db
      POSTGRES_USER: reports_user
      POSTGRES_PASSWORD: secure_password
    ports:
      - "5432:5432"

  web:
    build: .
    command: >
      sh -c "python manage.py migrate &&
             python manage.py createsuperuser --noinput &&
             gunicorn --bind 0.0.0.0:8000 config.wsgi:application"
    volumes:
      - .:/app
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    ports:
      - "8000:8000"
    environment:
      DEBUG: "False"
      SECRET_KEY: "your-secret-key"
      DATABASE_URL: "postgresql://reports_user:secure_password@db:5432/reports_db"
      ALLOWED_HOSTS: "localhost,127.0.0.1"
    depends_on:
      - db

  nginx:
    image: nginx:latest
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - static_volume:/app/staticfiles:ro
      - media_volume:/app/media:ro
    ports:
      - "80:80"
      - "443:443"
    depends_on:
      - web

volumes:
  postgres_data:
  static_volume:
  media_volume:
```

#### Deploy with Docker
```bash
docker-compose up -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

---

### 4. DigitalOcean App Platform

#### app.yaml
```yaml
name: construction-reports
services:
- name: web
  github:
    repo: your-username/site_engineer_reports
    branch: main
  build_command: pip install -r requirements.txt && python manage.py collectstatic --noinput
  run_command: gunicorn config.wsgi:application --bind 0.0.0.0:8080
  http_port: 8080
  envs:
  - key: DEBUG
    value: "False"
  - key: SECRET_KEY
    scope: RUN_AND_BUILD_TIME
    value: ${SECRET_KEY}
  - key: ALLOWED_HOSTS
    value: ${APP_DOMAIN}
  - key: DATABASE_URL
    scope: RUN_AND_BUILD_TIME
    value: ${db.connection_string}

databases:
- name: db
  engine: PG
  version: "15"
```

---

## Environment Configuration

### Production settings.py
```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
DEBUG = False
SECRET_KEY = os.environ.get('SECRET_KEY')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',')

# HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_SECURITY_POLICY = {
    'default-src': ("'self'",),
}

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST'),
        'PORT': os.environ.get('DB_PORT', '5432'),
    }
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/1'),
    }
}

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/error.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}

# Email
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL')
```

### .env.production
```
DEBUG=False
SECRET_KEY=your-very-long-secret-key-here
ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DB_NAME=reports_db
DB_USER=reports_user
DB_PASSWORD=secure_password
DB_HOST=localhost
DB_PORT=5432
REDIS_URL=redis://localhost:6379/1
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@your-domain.com
```

---

## Database Migration Strategy

### Zero-Downtime Migrations
```bash
# 1. Create migration
python manage.py makemigrations

# 2. Test migration locally
python manage.py migrate --plan

# 3. Backup production database
pg_dump production_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 4. Run migration
python manage.py migrate

# 5. Verify
python manage.py check
```

### Rollback Procedure
```bash
# If migration fails
python manage.py migrate app_name 0001

# Restore from backup
psql production_db < backup_file.sql
```

---

## Monitoring & Logging

### Application Monitoring
```bash
# Install monitoring tools
pip install sentry-sdk
pip install django-extensions
```

### Sentry Configuration
```python
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

sentry_sdk.init(
    dsn="your-sentry-dsn",
    integrations=[DjangoIntegration()],
    traces_sample_rate=0.1,
    send_default_pii=False
)
```

### Log Aggregation
```python
# Use ELK Stack or similar
LOGGING = {
    'version': 1,
    'handlers': {
        'syslog': {
            'level': 'INFO',
            'class': 'logging.handlers.SysLogHandler',
            'address': '/dev/log',
        },
    },
}
```

---

## Performance Optimization

### Caching Strategy
```python
# Cache database queries
from django.views.decorators.cache import cache_page

@cache_page(60 * 15)  # 15 minutes
def expensive_view(request):
    pass
```

### Database Optimization
```bash
# Analyze queries
python manage.py shell_plus

>>> from django.db import connection
>>> from django.test.utils import CaptureQueriesContext
>>> with CaptureQueriesContext(connection) as ctx:
...     # Run your code
>>> print(f"Queries: {len(ctx)}")
```

### Static File Optimization
```bash
# Compress static files
pip install django-compressor
python manage.py compress
```

---

## Backup Strategy

### Automated Backups
```bash
# Create backup script
#!/bin/bash
BACKUP_DIR="/backups/django"
DB_NAME="reports_db"
DATE=$(date +%Y%m%d_%H%M%S)

# Database backup
pg_dump $DB_NAME | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Media files backup
tar -czf $BACKUP_DIR/media_$DATE.tar.gz /app/media

# Keep only last 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
```

### Schedule with Cron
```bash
0 2 * * * /path/to/backup.sh
```

---

## Security Hardening

### Django Security
```python
# settings.py
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_SECURITY_POLICY = {
    'default-src': ("'self'",),
    'script-src': ("'self'", "'unsafe-inline'"),
    'style-src': ("'self'", "'unsafe-inline'"),
}
```

### Server Security
```bash
# Firewall configuration
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Fail2ban for brute force protection
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

### Regular Updates
```bash
# Keep dependencies updated
pip install --upgrade pip
pip list --outdated
pip install --upgrade -r requirements.txt
```

---

## Health Checks

### Application Health Endpoint
```python
# urls.py
from django.http import JsonResponse

def health_check(request):
    return JsonResponse({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

urlpatterns = [
    path('health/', health_check),
]
```

### Monitoring Script
```bash
#!/bin/bash
HEALTH_URL="https://your-domain.com/health/"
RESPONSE=$(curl -s $HEALTH_URL)

if [[ $RESPONSE == *"healthy"* ]]; then
    echo "Application is healthy"
else
    echo "Application is down"
    # Send alert
fi
```

---

## Troubleshooting

### Common Issues

#### 500 Internal Server Error
```bash
# Check logs
tail -f /var/log/nginx/error.log
tail -f /var/log/django/error.log

# Check database connection
python manage.py dbshell

# Check static files
python manage.py collectstatic --noinput
```

#### Database Connection Issues
```bash
# Test connection
psql -h localhost -U reports_user -d reports_db

# Check credentials
echo $DATABASE_URL

# Restart database
sudo systemctl restart postgresql
```

#### Memory Issues
```bash
# Check memory usage
free -h

# Increase gunicorn workers
gunicorn --workers 2 config.wsgi:application

# Use memory profiling
pip install memory-profiler
python -m memory_profiler script.py
```

---

## Rollback Procedure

### If Deployment Fails
```bash
# 1. Stop application
sudo systemctl stop gunicorn

# 2. Restore previous version
git checkout previous-commit
source venv/bin/activate
pip install -r requirements.txt

# 3. Rollback database
psql reports_db < backup.sql

# 4. Restart application
sudo systemctl start gunicorn

# 5. Verify
curl https://your-domain.com/health/
```

---

## Post-Deployment Checklist

- [ ] Application is running
- [ ] Database migrations successful
- [ ] Static files loaded correctly
- [ ] SSL certificate valid
- [ ] Email notifications working
- [ ] Monitoring configured
- [ ] Backups running
- [ ] Users can login
- [ ] Reports can be created
- [ ] PDF export working
- [ ] Performance acceptable
- [ ] Logs being collected

---

**Last Updated**: December 19, 2025  
**Version**: 1.0.0  
**Status**: Production Ready
