"""
Base settings for Mera Hisaab.

Shared by all environments. Environment-specific settings live in
``dev.py`` and ``prod.py`` and import ``*`` from here.

All secrets and deployment-specific values are read from environment
variables (see ``.env.example``) so nothing sensitive is committed.
"""
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# config/settings/base.py -> config/settings -> config -> <project root>
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    USE_SQLITE=(bool, False),
)

# Read a .env file if present (never required in production containers).
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    env.read_env(str(_env_file))

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="dev-insecure-change-me-in-production-0000000000000000",
)

DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

# Local apps. Additional apps (products, sales, ...) are added per phase.
LOCAL_APPS = [
    "core",
    "accounts",
    "businesses",
    "products",
    "inventory",
    "customers",
    "payments",
    "sales",
    "suppliers",
    "purchases",
    "expenses",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Resolves the active tenant (business) for the request. Must run AFTER
    # AuthenticationMiddleware because it relies on request.user.
    "core.middleware.CurrentBusinessMiddleware",
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
                # Exposes current business + memberships + branding to all templates.
                "core.context_processors.branding",
                "core.context_processors.current_business",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# PostgreSQL is the target database. Supports standard DATABASE_URL (Render, Supabase, etc.)
# as well as individual POSTGRES_* vars, or USE_SQLITE=1 fallback.
if env("DATABASE_URL", default=""):
    DATABASES = {
        "default": env.db("DATABASE_URL")
    }
    DATABASES["default"]["CONN_MAX_AGE"] = env.int("POSTGRES_CONN_MAX_AGE", default=60)
elif env("USE_SQLITE"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("POSTGRES_DB", default="mera_hisaab"),
            "USER": env("POSTGRES_USER", default="mera_hisaab"),
            "PASSWORD": env("POSTGRES_PASSWORD", default="mera_hisaab"),
            "HOST": env("POSTGRES_HOST", default="localhost"),
            "PORT": env("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": env.int("POSTGRES_CONN_MAX_AGE", default=60),
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization (English now, Hindi/Hinglish ready)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("hi", "हिन्दी"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Sessions & security defaults (hardened further in prod.py)
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Map Django message levels to Bootstrap alert classes.
from django.contrib.messages import constants as _messages  # noqa: E402

MESSAGE_TAGS = {
    _messages.DEBUG: "secondary",
    _messages.INFO: "info",
    _messages.SUCCESS: "success",
    _messages.WARNING: "warning",
    _messages.ERROR: "danger",
}

# ---------------------------------------------------------------------------
# Mera Hisaab branding (surfaced to templates + admin)
# ---------------------------------------------------------------------------
APP_NAME = "Mera Hisaab"
APP_TAGLINE = "Apni Dukaan, Apna Hisaab."

# ---------------------------------------------------------------------------
# Razorpay payment gateway (test keys in dev, live keys in prod)
# ---------------------------------------------------------------------------
# KEY_ID is safe to expose to the browser (Checkout needs it). SECRET and the
# WEBHOOK_SECRET must NEVER reach the frontend. All optional so the app runs
# without them — gateway features simply stay disabled until configured.
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")
