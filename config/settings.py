import os
import sys
from pathlib import Path

from django.contrib.messages import constants as messages_constants
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

from config.db import parse_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# Reads the private .env file when it exists (it never exists on a public server,
# where real environment variables are used instead).
load_dotenv(BASE_DIR / ".env")

RUNNING_TESTS = "test" in sys.argv


def env_list(name, default=""):
    """Read a comma-separated environment variable as a list."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# Secure by default: debug mode must be switched on explicitly (your local .env does this).
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG or RUNNING_TESTS:
        SECRET_KEY = "django-insecure-local-development-key-only"
    else:
        raise ImproperlyConfigured("Set the DJANGO_SECRET_KEY environment variable.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
    "accounts",
    "inventory",
    "analytics",
    "assistant",
    "recipes",
    "planner",
    "shopping",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "DIRS": [BASE_DIR / "templates"],
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

# Database: PostgreSQL on a public server (DATABASE_URL), SQLite on your computer.
# Tests always use their own temporary database, whatever DATABASE_URL says.
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL and not RUNNING_TESTS:
    DATABASES = {"default": parse_database_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Where the build collects the admin and API styling files for the public site.
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Extra protection that only applies on a public server
if not DEBUG and not RUNNING_TESTS:
    # The host sits behind a proxy that tells us whether the visitor used https
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "True") == "True"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 3600

# Login and logout behaviour
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

# Make Django message levels match Bootstrap alert colours
MESSAGE_TAGS = {
    messages_constants.ERROR: "danger",
}

# AI settings (the key comes from the environment, never from the code)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# Models are tried in this order. If one is busy, the next one is used.
GEMINI_MODELS = env_list(
    "GEMINI_MODELS",
    "gemini-3.5-flash,gemini-3.6-flash,gemini-3.5-flash-lite",
)
AI_DAILY_LIMIT_PER_USER = int(os.environ.get("AI_DAILY_LIMIT_PER_USER", "20"))
AI_GLOBAL_DAILY_LIMIT = int(os.environ.get("AI_GLOBAL_DAILY_LIMIT", "200"))
AI_COOLDOWN_SECONDS = int(os.environ.get("AI_COOLDOWN_SECONDS", "5"))

# REST API settings
REST_FRAMEWORK = {
    # Only logged-in users, identified by their normal website session
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/hour", "user": "2000/hour"},
    # The clickable test pages are only switched on while developing locally
    "DEFAULT_RENDERER_CLASSES": (
        ["rest_framework.renderers.JSONRenderer"]
        + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else [])
    ),
}