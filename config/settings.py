"""
Django settings for Site Engineer Reports / One Stop ERP (Merged)
- keeps original project apps
- adds: DRF, CORS, Channels
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables before reading any Django setting.
# Set DJANGO_ENV_FILE to use a different file when needed.
ENV_FILE = Path(os.getenv("DJANGO_ENV_FILE", BASE_DIR / ".env"))
if ENV_FILE.is_file():
    load_dotenv(ENV_FILE)


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable using common true values."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a clean list."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEVELOPMENT_SECRET_KEY = "django-insecure-local-development-only"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", DEVELOPMENT_SECRET_KEY)
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")

if not DEBUG and SECRET_KEY == DEVELOPMENT_SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a secure value when DJANGO_DEBUG=False."
    )


# -------------------------
# Applications
# -------------------------
INSTALLED_APPS = [
    # Django
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'rest_framework.authtoken',
    'corsheaders',
    'channels',

    # Local (core first)
    'core',
    'accounts',
    'projects',
    'reports',

    # Local (feature apps)
    'procurement',
    'cost_control',
    'timesheets',

    # Optional local apps (فعّليهم إذا فيهم models وتحتاجي migrations)
    'crm',
    'equipment',
    'safety',
    'subcontractors',
    'accounting',
    'blueprints',  # فعّليه فقط إذا هو Django app (فيه apps.py/models.py)
    'ai_assistant',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Serves STATIC_ROOT directly from Django/gunicorn/Passenger itself -- needed on hosting (e.g.
    # shared cPanel) where there's no separate step to point the web server straight at that folder.
    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    # CORS must be before CommonMiddleware
    'corsheaders.middleware.CorsMiddleware',

    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'projects.middleware.ProjectReadinessMiddleware',   # blocks work on projects without insurance / a priced BOQ
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],   # عندك templates folder بالفعل
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


# -------------------------
# Database
# -------------------------
def env_int(name: str, default: int = 0) -> int:
    """Read an integer environment variable and fail clearly when invalid."""
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc


def env_required(name: str) -> str:
    """Read a required environment variable."""
    value = os.getenv(name, "").strip()
    if not value:
        raise ImproperlyConfigured(
            f"{name} must be set when DB_ENGINE=mysql."
        )
    return value


DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").strip().lower()

if DB_ENGINE in {"sqlite", "sqlite3"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.getenv("SQLITE_PATH", BASE_DIR / "db.sqlite3")),
        }
    }
elif DB_ENGINE == "mysql":
    mysql_database = env_required("DB_NAME")
    mysql_test_database = os.getenv("DB_TEST_NAME", "").strip()

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": mysql_database,
            "USER": env_required("DB_USER"),
            "PASSWORD": env_required("DB_PASSWORD"),
            "HOST": os.getenv("DB_HOST", "127.0.0.1").strip(),
            "PORT": os.getenv("DB_PORT", "3306").strip(),
            "CONN_MAX_AGE": env_int(
                "DB_CONN_MAX_AGE",
                0 if DEBUG else 60,
            ),
            "CONN_HEALTH_CHECKS": env_bool("DB_CONN_HEALTH_CHECKS", True),
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
                "isolation_level": "read committed",
            },
        }
    }

    if mysql_test_database:
        DATABASES["default"]["TEST"] = {"NAME": mysql_test_database}
else:
    raise ImproperlyConfigured(
        "DB_ENGINE must be either 'sqlite' or 'mysql'."
    )


# -------------------------
# Auth (Custom User)
# -------------------------
AUTH_USER_MODEL = 'accounts.CustomUser'


# -------------------------
# Password validation
# -------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# -------------------------
# Internationalization
# -------------------------
LANGUAGE_CODE = 'en-us'
# فلسطين: لو بدك صححيها:
TIME_ZONE = 'Asia/Hebron'
USE_I18N = True
USE_TZ = True


# -------------------------
# Static & Media
# -------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# -------------------------
# File storage -- Dropbox
# -------------------------
# Every uploaded file (insurance/tender documents, drawings, daily/monthly report attachments, project
# phase photos, ...) is saved to the company's own Dropbox instead of this server's local disk, so uploads
# -- site photos especially -- don't grow the app server's storage over time. Configured by setting
# DROPBOX_APP_KEY/DROPBOX_APP_SECRET/DROPBOX_OAUTH2_REFRESH_TOKEN in .env (see .env.example for how to get
# them from the Dropbox App Console -- a refresh token, not a plain access token, since Dropbox access
# tokens for apps created after Sept 2021 expire after a few hours and this is what lets the client renew
# one automatically). Falls back to this server's local disk automatically when DROPBOX_APP_KEY isn't set,
# so a fresh checkout or a machine without Dropbox configured keeps working exactly as before.
#
# Switching this on does NOT move files that were already uploaded to local disk before the switch -- run
# `python manage.py migrate_media_to_dropbox` first (see that command's docstring) so old insurance
# certificates, drawings and report photos don't become unreachable the moment this goes live.
DROPBOX_APP_KEY = os.getenv('DROPBOX_APP_KEY', '')
DROPBOX_APP_SECRET = os.getenv('DROPBOX_APP_SECRET', '')
DROPBOX_OAUTH2_REFRESH_TOKEN = os.getenv('DROPBOX_OAUTH2_REFRESH_TOKEN', '')
DROPBOX_ROOT_PATH = os.getenv('DROPBOX_ROOT_PATH', '/one-stop-erp')

STORAGES = {
    # Compressed (not manifest/fingerprinted) so a first production `collectstatic` can't fail over a
    # template referencing a static file that doesn't literally exist on disk -- safer for a first
    # deploy than CompressedManifestStaticFilesStorage's strict manifest. Served directly by
    # WhiteNoiseMiddleware (added above), so hosting that gives no separate way to point the web
    # server at STATIC_ROOT (e.g. shared cPanel/Passenger) still serves static files correctly.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
if DROPBOX_APP_KEY:
    STORAGES["default"] = {"BACKEND": "storages.backends.dropbox.DropboxStorage"}

# -------------------------
# Outgoing email (report reminders -- reports/email_service.py, management commands
# send_reminders / check_overdue_daily_reports). Without real SMTP credentials in .env, emails
# print to the console (DEBUG) or are silently dropped (production) instead of failing outright --
# set EMAIL_HOST/EMAIL_HOST_USER/EMAIL_HOST_PASSWORD (and EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend)
# to actually deliver them.
# -------------------------
EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.dummy.EmailBackend'
)
EMAIL_HOST = os.getenv('EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'no-reply@one-stop-erp.local')
COMPANY_NAME = os.getenv('COMPANY_NAME', 'One Stop Contracting and Services')
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
# Names printed at the foot of the day-labor wages sheet ("اعداد / تدقيق"); blank = an empty line to sign.
WAGES_PREPARED_BY = os.getenv('WAGES_PREPARED_BY', '')
WAGES_REVIEWED_BY = os.getenv('WAGES_REVIEWED_BY', '')

# -------------------------
# AI assistant (ai_assistant app) -- calls the Claude API.
# The key is read from the environment / .env (ANTHROPIC_API_KEY); without it the AI features
# show a "not configured" notice and everything else in the system works as before.
# -------------------------
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
AI_ASSISTANT_MODEL = os.getenv('AI_ASSISTANT_MODEL', 'claude-opus-5')
AI_MAX_UPLOAD_MB = int(os.getenv('AI_MAX_UPLOAD_MB', '32'))     # the API's own request cap for a PDF is 32 MB
AI_MAX_PDF_PAGES = int(os.getenv('AI_MAX_PDF_PAGES', '300'))
AI_REFUSAL_FALLBACK = os.getenv('AI_REFUSAL_FALLBACK', '0') in ('1', 'true', 'True')   # opt-in: re-run a declined request on a fallback model
# Which AI does the work: 'anthropic' (Claude, in Anthropic's cloud) or 'ollama' (an open model running on
# your own machine through Ollama -- nothing leaves the company and there is no per-use fee).
AI_PROVIDER = os.getenv('AI_PROVIDER', 'anthropic').strip().lower()
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434').strip().rstrip('/')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'qwen2.5:7b').strip()
# A model that can read images (e.g. a "vl" model). Needed for scanned PDFs, photos and reading tables from page images.
OLLAMA_VISION_MODEL = os.getenv('OLLAMA_VISION_MODEL', '').strip()
# How PDFs are read locally: 'auto' = text where a page has text, page image where it is scanned;
# 'images' = always page images (best for BOQ tables, needs OLLAMA_VISION_MODEL); 'text' = text only.
OLLAMA_PDF_MODE = os.getenv('OLLAMA_PDF_MODE', 'auto').strip().lower()
# The model's working memory in tokens. Ollama silently cuts off anything longer, so this must fit the work.
OLLAMA_NUM_CTX = int(os.getenv('OLLAMA_NUM_CTX', '16384'))
OLLAMA_TIMEOUT = int(os.getenv('OLLAMA_TIMEOUT', '1800'))          # seconds for one answer
OLLAMA_MAX_IMAGE_PAGES = int(os.getenv('OLLAMA_MAX_IMAGE_PAGES', '12'))
# When a drawing is uploaded, read it automatically for materials, quantities and green-building (EDGE) data.
# Only happens when an AI provider is set up; with the cloud provider the drawing is sent to Anthropic.
AI_AUTO_ANALYZE_DRAWINGS = os.getenv('AI_AUTO_ANALYZE_DRAWINGS', '1') in ('1', 'true', 'True')
AI_RUN_IN_BACKGROUND = True   # tests switch this off so a run finishes inside the request

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'accounts:login'

# -------------------------
# DRF
# -------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
}


# -------------------------
# CORS
# -------------------------
CORS_ALLOWED_ORIGINS = [
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]
CORS_ALLOW_CREDENTIALS = True


# -------------------------
# Channels
# -------------------------
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer'
    }
}


# -------------------------
# Logging (اختياري)
# -------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'debug.log',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}
