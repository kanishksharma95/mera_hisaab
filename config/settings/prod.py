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

if not DATABASES["default"]["ENGINE"].endswith("sqlite3") and not env("DATABASE_URL", default=""):
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
# Priority: Brevo (HTTP API) > SMTP > console.
# Hosts like Render's free tier block outbound SMTP ports (25/465/587), so SMTP
# to Gmail silently times out there. Brevo delivers over HTTPS (port 443),
# which those hosts allow — so it is preferred whenever BREVO_API_KEY is set.
# Brevo needs no custom domain: verify a single sender (e.g. your Gmail) in the
# Brevo dashboard, then set DEFAULT_FROM_EMAIL to that exact verified address.
if env("BREVO_API_KEY", default=""):
    EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    ANYMAIL = {"BREVO_API_KEY": env("BREVO_API_KEY")}
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")  # must be your verified Brevo sender
elif env("EMAIL_HOST_USER", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="").replace(" ", "")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=f"Mera Hisaab <{EMAIL_HOST_USER}>")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    EMAIL_TIMEOUT = 5
