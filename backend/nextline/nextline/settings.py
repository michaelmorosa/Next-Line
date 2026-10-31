"""
Django settings for the Next Line backend.

Values that differ between machines come from backend/nextline/.env (see .env.example).
"""

from datetime import timedelta
from pathlib import Path
import os
import sys
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")


def env_bool(name, default=False):
    """True for "1", "true", "yes" or "on" (any case). os.getenv returns text, and the text "False" is truthy."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Off unless DEBUG=True is set.
DEBUG = env_bool("DEBUG")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("HOST", "localhost,127.0.0.1").split(",") if h.strip()]

AUTH_USER_MODEL = 'users.CustomUser'

# Production should use an unguessable path like "manage-x7k2q/".
ADMIN_URL = os.getenv("ADMIN_URL", "admin/").strip("/") + "/"

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Behind nginx or a platform that terminates HTTPS. The proxy must set X-Forwarded-Proto.
    if env_bool("BEHIND_HTTPS_PROXY"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 3600
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_REFERRER_POLICY = "no-referrer-when-downgrade"

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'djoser',
    'users',
    'trails',
    'rides',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    # Per-user (or, logged out, per-IP) limits well above normal use; account endpoints get tighter per-IP
    # limits (nextline/throttles.py).
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'nextline.throttles.AuthThrottle',
        'nextline.throttles.SignupThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/minute',
        'user': '240/minute',
        'auth': '20/hour',
        'signup': '5/day',
        'crash': '10/hour',  # Opt-in, see rides.views.CrashAlertThrottle.
    },
    'EXCEPTION_HANDLER': 'nextline.exceptions.api_exception_handler',
    'NUM_PROXIES': 1 if env_bool("BEHIND_HTTPS_PROXY") else 0,
}

# Shared by every server process, so rate limits can't be dodged by hitting a different worker.
# Create the table once: python manage.py createcachetable
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "nextline_cache",
    }
}

SIMPLE_JWT = {
    "AUTH_HEADER_TYPES": ("Bearer",),
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    # Long enough that a rider who records offline for a weekend can still upload when they get signal.
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

DJOSER = {
    "USER_ID_FIELD": "id",
    "LOGIN_FIELD": "username",
    "USER_CREATE_PASSWORD_RETYPE": True,
    "SERIALIZERS": {
        "user_create_password_retype": "users.serializers.UserCreatePasswordRetypeSerializer",
        "user": "users.serializers.UserSerializer",
        "current_user": "users.serializers.UserSerializer",
    },
    # Turn on once email sending is configured (MAILGUN_* below) and the activation screens exist in the app.
    "SEND_ACTIVATION_EMAIL": env_bool("SEND_ACTIVATION_EMAIL"),
    "ACTIVATION_URL": "activate/{uid}/{token}/",
    "PASSWORD_RESET_CONFIRM_URL": "password/reset/confirm/{uid}/{token}",
}

if os.getenv("MAILGUN_SMTP_USER"):
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.mailgun.org'
    EMAIL_PORT = 2525
    EMAIL_HOST_USER = os.getenv('MAILGUN_SMTP_USER')
    EMAIL_HOST_PASSWORD = os.getenv('MAILGUN_SMTP_PASSWORD')
    EMAIL_USE_TLS = True
    EMAIL_TIMEOUT = 10
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Next Line <no-reply@nextline.app>")

ROOT_URLCONF = 'nextline.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'nextline.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DATABASE_NAME'),
        'USER': os.getenv('DATABASE_USER'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD'),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '5432'),
    }
}
# Escape hatch for running the test suite without a Postgres server: DATABASE_ENGINE=sqlite python manage.py test
if os.getenv("DATABASE_ENGINE") == "sqlite":
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', "OPTIONS": {"min_length": 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
if TESTING:
    # Real password hashing is deliberately slow (about 2 s per test user); tests don't need it.
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

# Ride uploads carry the whole GPS track as JSON. A 6-hour ride at one point per second is about 1.5 MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = 8 * 1024 * 1024
MAX_TRACK_POINTS = 40000

# Crash alerts are texted to the rider's emergency contact through Twilio. Without these, alerts are recorded and
# logged but no text goes out, and the app tells the rider so.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
