"""
Django settings for the Book Tracker project.

All environment-specific values (secret key, hosts, MongoDB connection)
are read from environment variables. For local development they can be
placed in a `.env` file next to manage.py (see .env.example).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from .env if it exists. Real environment variables
# (e.g. from the systemd EnvironmentFile) take precedence.
load_dotenv(BASE_DIR / ".env")


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "books",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "book_tracker.urls"
WSGI_APPLICATION = "book_tracker.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Database ---------------------------------------------------------------
# Books are stored in MongoDB through PyMongo (see books/db.py), so Django's
# SQL database layer is not used at all.
DATABASES = {}

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/")
MONGODB_DATABASE = os.environ.get("MONGODB_DATABASE", "book_tracker")

# Flash messages are kept in a signed cookie, so no session database is needed.
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# --- Internationalization ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files -----------------------------------------------------------
# In production `collectstatic` copies everything into STATIC_ROOT and
# Nginx serves that folder directly at /static/.

STATIC_URL = "/static/"
STATIC_ROOT = Path(os.environ.get("DJANGO_STATIC_ROOT", BASE_DIR / "staticfiles"))

# --- Running behind Nginx ---------------------------------------------------
# Nginx sets X-Forwarded-Proto, so Django knows when the original request
# was HTTPS.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --- Logging ----------------------------------------------------------------
# With DEBUG off Django prints nothing by default. Send security warnings
# (CSRF failures, bad Host headers, ...) and server errors to stderr, one line
# per event, so Docker/journald and Wazuh pick them up
# (see deploy/wazuh/book_tracker_decoders.xml).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "stderr": {"class": "logging.StreamHandler", "formatter": "plain"},
    },
    "loggers": {
        "django.security": {"handlers": ["stderr"], "level": "WARNING", "propagate": False},
        "django.request": {"handlers": ["stderr"], "level": "ERROR", "propagate": False},
    },
}
