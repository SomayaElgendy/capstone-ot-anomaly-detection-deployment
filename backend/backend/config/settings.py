from pathlib import Path
from datetime import timedelta
import os

from dotenv import load_dotenv
import certifi

# SSL certificates for requests/Groq/HTTP clients
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-local-dev-key-change-me")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1,0.0.0.0"
).split(",")

# Applications
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",

    # Project apps
    "users",
    "api",
    "ui",
    "alerts.apps.AlertsConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Custom user model
AUTH_USER_MODEL = "users.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

# JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME", 60))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        minutes=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME", 1440))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# CORS
CORS_ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8080,http://127.0.0.1:8000,http://localhost:8000",
).split(",")

CORS_ALLOW_CREDENTIALS = True

# Redis
# In local mode: localhost
# In Docker Compose: redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

# OT Redis is separate from AI Redis.
# Used only for future/experimental live OT integration.
OT_REDIS_HOST = os.getenv("OT_REDIS_HOST", "127.0.0.1")
OT_REDIS_PORT = int(os.getenv("OT_REDIS_PORT", 6379))

# Stage 3 / IR-RAG Service
# In local mode: http://127.0.0.1:8001
# In Docker Compose: http://stage3:8001
STAGE3_BASE_URL = os.getenv("STAGE3_BASE_URL", "http://127.0.0.1:8001")

RAG_ENDPOINT = os.getenv(
    "RAG_ENDPOINT",
    f"{STAGE3_BASE_URL}/generate-ir",
)

RAG_CHAT_ENDPOINT = os.getenv(
    "RAG_CHAT_ENDPOINT",
    f"{STAGE3_BASE_URL}/chat",
)

RAG_SERVICE_TOKEN = os.getenv("RAG_SERVICE_TOKEN", "")

# OT Streamlit Dashboard
# This URL is opened by the user's browser, so localhost is okay.
OT_STREAMLIT_URL = os.getenv("OT_STREAMLIT_URL", "http://127.0.0.1:8501")