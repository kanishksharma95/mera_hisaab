"""Development settings for Mera Hisaab."""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]
# Allow tunnelling tools (cloudflared / ngrok) to reach the dev server for
# webhook testing, plus any extra hosts listed in DJANGO_ALLOWED_HOSTS (.env).
ALLOWED_HOSTS += [".trycloudflare.com", ".ngrok-free.app", ".ngrok.io"]
ALLOWED_HOSTS += [
    h for h in env.list("DJANGO_ALLOWED_HOSTS", default=[]) if h not in ALLOWED_HOSTS
]

# Let the same tunnel origins pass CSRF for the browser "Pay online" callback.
CSRF_TRUSTED_ORIGINS = [
    "https://*.trycloudflare.com",
    "https://*.ngrok-free.app",
    "https://*.ngrok.io",
]

# Email priority: Brevo (HTTP API) > SMTP > console.
# Set BREVO_API_KEY in .env to test the exact backend production uses; else fall
# back to SMTP if creds are present, otherwise just log emails to the console.
if env("BREVO_API_KEY", default=""):
    EMAIL_BACKEND = "anymail.backends.brevo.EmailBackend"
    ANYMAIL = {"BREVO_API_KEY": env("BREVO_API_KEY")}
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Mera Hisaab <no-reply@merahisaab.app>")
elif env("EMAIL_HOST_USER", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
    EMAIL_PORT = env.int("EMAIL_PORT", default=587)
    EMAIL_HOST_USER = env("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="").replace(" ", "")
    EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
    DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Mera Hisaab <no-reply@merahisaab.app>")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Allow developers without a local Postgres to opt into SQLite quickly.
# (Handled in base.py via USE_SQLITE; nothing extra needed here.)

INTERNAL_IPS = ["127.0.0.1"]
