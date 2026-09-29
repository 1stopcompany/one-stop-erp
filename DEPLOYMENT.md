# Deployment Guide - Site Engineer Reports System

This guide covers deploying the Site Engineer Reports System to production on Windows, Linux, and cloud platforms.

## Table of Contents

1. [Development Setup](#development-setup)
2. [Windows Deployment](#windows-deployment)
3. [Linux/Ubuntu Deployment](#linuxubuntu-deployment)
4. [PostgreSQL Configuration](#postgresql-configuration)
5. [Production Settings](#production-settings)
6. [Docker Deployment](#docker-deployment)
7. [Cloud Deployment](#cloud-deployment)
8. [SSL/HTTPS Setup](#ssltls-setup)
9. [Monitoring & Maintenance](#monitoring--maintenance)

## Development Setup

### Quick Start (All Platforms)

```bash
# 1. Clone/extract project
cd site_engineer_reports

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run migrations
python manage.py migrate

# 6. Create sample data (optional)
python manage.py shell < create_fixtures.py

# 7. Create superuser
python manage.py createsuperuser

# 8. Run development server
python manage.py runserver
```

Access at: http://localhost:8000

## Windows Deployment

### Option 1: Using Batch Script (Easiest)

```bash
# Simply double-click run_windows.bat
# Or run from command prompt:
run_windows.bat
```

### Option 2: Manual Setup

#### Prerequisites
- Python 3.11+ (https://www.python.org/downloads/)
- PostgreSQL 12+ (optional, for production)
- Git (https://git-scm.com/)

#### Step-by-Step

```powershell
# 1. Open Command Prompt or PowerShell
# 2. Navigate to project directory
cd C:\path\to\site_engineer_reports

# 3. Create virtual environment
python -m venv venv

# 4. Activate virtual environment
venv\Scripts\activate

# 5. Upgrade pip
python -m pip install --upgrade pip

# 6. Install dependencies
pip install -r requirements.txt

# 7. Run migrations
python manage.py migrate

# 8. Create superuser
python manage.py createsuperuser

# 9. Run server
python manage.py runserver
```

### Windows Server IIS Deployment

#### Install FastCGI

1. Open Server Manager → Add Roles and Features
2. Select "Application Server" → "Web Server (IIS)" → "Application Development" → "CGI"
3. Install FastCGI

#### Configure IIS

1. Create new website in IIS Manager
2. Point to project directory
3. Create web.config:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <system.webServer>
        <handlers>
            <add name="FastCGI" path="*" verb="*" modules="FastCgiModule" scriptProcessor="C:\Python311\python.exe|C:\Python311\lib\site-packages\wfastcgi.py" resourceType="Unspecified" requireAccess="Script" />
        </handlers>
        <rewrite>
            <rules>
                <rule name="Django" stopProcessing="true">
                    <match url="^(?!static)" />
                    <action type="Rewrite" url="wsgi.py" />
                </rule>
            </rules>
        </rewrite>
    </system.webServer>
</configuration>
```

## Linux/Ubuntu Deployment

### Using Bash Script

```bash
# Make script executable
chmod +x run_linux.sh

# Run script
./run_linux.sh
```

### Manual Setup

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install Python and dependencies
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql postgresql-contrib nginx

# 3. Create project directory
sudo mkdir -p /var/www/site_engineer_reports
cd /var/www/site_engineer_reports

# 4. Clone project (or copy files)
# git clone <repository> .

# 5. Create virtual environment
python3.11 -m venv venv

# 6. Activate and install
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 7. Create .env file
sudo nano .env
```

### Systemd Service Setup

Create `/etc/systemd/system/site-engineer.service`:

```ini
[Unit]
Description=Site Engineer Reports System
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/site_engineer_reports
ExecStart=/var/www/site_engineer_reports/venv/bin/gunicorn \
    --workers 4 \
    --bind unix:/var/www/site_engineer_reports/site_engineer.sock \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable site-engineer
sudo systemctl start site-engineer
sudo systemctl status site-engineer
```

### Nginx Configuration

Create `/etc/nginx/sites-available/site_engineer`:

```nginx
upstream site_engineer {
    server unix:/var/www/site_engineer_reports/site_engineer.sock fail_timeout=0;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 100M;

    location /static/ {
        alias /var/www/site_engineer_reports/staticfiles/;
    }

    location /media/ {
        alias /var/www/site_engineer_reports/media/;
    }

    location / {
        proxy_pass http://site_engineer;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/site_engineer /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

## PostgreSQL Configuration

### Install PostgreSQL

#### Windows
Download from: https://www.postgresql.org/download/windows/

#### Linux
```bash
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### Create Database and User

```bash
# Connect to PostgreSQL
sudo -u postgres psql

# Create database
CREATE DATABASE site_engineer_reports;

# Create user
CREATE USER site_engineer WITH PASSWORD 'strong_password_here';

# Grant privileges
ALTER ROLE site_engineer SET client_encoding TO 'utf8';
ALTER ROLE site_engineer SET default_transaction_isolation TO 'read committed';
ALTER ROLE site_engineer SET default_transaction_deferrable TO on;
ALTER ROLE site_engineer SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE site_engineer_reports TO site_engineer;

# Exit
\q
```

### Update Django Settings

Edit `config/settings.py`:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'site_engineer_reports',
        'USER': 'site_engineer',
        'PASSWORD': 'strong_password_here',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### Run Migrations

```bash
python manage.py migrate
```

## Production Settings

### Create .env File

```bash
DEBUG=False
SECRET_KEY=your-very-long-random-secret-key-here
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DB_ENGINE=django.db.backends.postgresql
DB_NAME=site_engineer_reports
DB_USER=site_engineer
DB_PASSWORD=strong_password
DB_HOST=localhost
DB_PORT=5432
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
```

### Update settings.py

```python
import os
from decouple import config

DEBUG = config('DEBUG', default=False, cast=bool)
SECRET_KEY = config('SECRET_KEY')
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost').split(',')

DATABASES = {
    'default': {
        'ENGINE': config('DB_ENGINE'),
        'NAME': config('DB_NAME'),
        'USER': config('DB_USER'),
        'PASSWORD': config('DB_PASSWORD'),
        'HOST': config('DB_HOST'),
        'PORT': config('DB_PORT'),
    }
}

SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=True, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=True, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
```

### Collect Static Files

```bash
python manage.py collectstatic --noinput
```

## Docker Deployment

### Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create media and static directories
RUN mkdir -p /app/media /app/staticfiles

# Expose port
EXPOSE 8000

# Run migrations and start server
CMD ["sh", "-c", "python manage.py migrate && python manage.py collectstatic --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000"]
```

### Create docker-compose.yml

```yaml
version: '3.8'

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: site_engineer_reports
      POSTGRES_USER: site_engineer
      POSTGRES_PASSWORD: strong_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  web:
    build: .
    command: gunicorn config.wsgi:application --bind 0.0.0.0:8000
    volumes:
      - .:/app
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    ports:
      - "8000:8000"
    environment:
      DEBUG: "False"
      SECRET_KEY: "your-secret-key"
      DB_ENGINE: "django.db.backends.postgresql"
      DB_NAME: "site_engineer_reports"
      DB_USER: "site_engineer"
      DB_PASSWORD: "strong_password"
      DB_HOST: "db"
      DB_PORT: "5432"
    depends_on:
      - db

  nginx:
    image: nginx:latest
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - static_volume:/app/staticfiles
      - media_volume:/app/media
    depends_on:
      - web

volumes:
  postgres_data:
  static_volume:
  media_volume:
```

### Build and Run

```bash
docker-compose build
docker-compose up -d
```

## Cloud Deployment

### Heroku

```bash
# Install Heroku CLI
# Create Procfile
web: gunicorn config.wsgi:application

# Create runtime.txt
python-3.11.0

# Create .env
heroku create site-engineer-reports
heroku config:set DEBUG=False
heroku config:set SECRET_KEY=your-secret-key
heroku addons:create heroku-postgresql:standard-0
git push heroku main
heroku run python manage.py migrate
```

### AWS Elastic Beanstalk

```bash
# Install EB CLI
eb init -p python-3.11 site-engineer-reports
eb create production
eb deploy
eb open
```

### Google Cloud Run

```bash
# Create cloudbuild.yaml
gcloud builds submit --tag gcr.io/PROJECT_ID/site-engineer-reports
gcloud run deploy site-engineer-reports \
  --image gcr.io/PROJECT_ID/site-engineer-reports \
  --platform managed \
  --region us-central1
```

## SSL/TLS Setup

### Using Let's Encrypt (Linux)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get certificate
sudo certbot certonly --nginx -d yourdomain.com

# Update Nginx configuration
sudo nano /etc/nginx/sites-available/site_engineer
```

Add to Nginx config:

```nginx
listen 443 ssl http2;
ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}
```

### Auto-renewal

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
```

## Monitoring & Maintenance

### Backup Database

```bash
# PostgreSQL backup
pg_dump -U site_engineer site_engineer_reports > backup.sql

# Restore
psql -U site_engineer site_engineer_reports < backup.sql
```

### Monitor Logs

```bash
# Systemd logs
sudo journalctl -u site-engineer -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log

# Django logs
tail -f logs/django.log
```

### Health Check

```bash
curl -I http://yourdomain.com
curl -I https://yourdomain.com/admin
```

### Update Application

```bash
# Pull latest changes
git pull origin main

# Install new dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Restart service
sudo systemctl restart site-engineer
```

## Troubleshooting

### Issue: Database connection error
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check credentials in .env
cat .env
```

### Issue: Static files not loading
```bash
# Collect static files
python manage.py collectstatic --noinput

# Check Nginx configuration
sudo nginx -t
```

### Issue: Permission denied
```bash
# Fix file permissions
sudo chown -R www-data:www-data /var/www/site_engineer_reports
sudo chmod -R 755 /var/www/site_engineer_reports
```

### Issue: High memory usage
```bash
# Reduce Gunicorn workers
gunicorn --workers 2 config.wsgi:application
```

---

For additional help, refer to:
- Django Documentation: https://docs.djangoproject.com/
- Gunicorn: https://gunicorn.org/
- Nginx: https://nginx.org/
- PostgreSQL: https://www.postgresql.org/docs/
