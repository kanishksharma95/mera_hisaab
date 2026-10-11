"""Production settings for Mera Hisaab."""
from .base import *  # noqa: F401,F403
from .base import DATABASES, env

DEBUG = False

# Hosts must be supplied explicitly in production.
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Secrets MUST come from the environment in production. base.py ships
# developer-friendly fallbacks (an insecure SECRET_KEY, a default DB password)
# so `manage.py` runs locally without setup; those must NEVER apply in prod.
# Re-reading them here with no default makes a missing value fail loudly at
# boot instead of silently running on a hardcoded secret.
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY")  # raises ImproperlyConfigured if unset

if not DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["PASSWORD"] = env("POSTGRES_PASSWORD")  # required

# If Razorpay is enabled in production, webhook verification must have a secret
# — otherwise anyone could POST forged 'paid' events.
if env("RAZORPAY_KEY_ID", default="") and not env("RAZORPAY_WEBHOOK_SECRET", default=""):
    raise Exception(
        "RAZORPAY_WEBHOOK_SECRET must be set in production when Razorpay is enabled."
    )

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

# --- HTTPS / transport security ---
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# --- Email (real backend in production) ---
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="Mera Hisaab <no-reply@merahisaab.app>"
)
