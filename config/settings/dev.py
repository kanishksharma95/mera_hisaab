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

# Show emails (password reset, notifications) in the console during dev.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Allow developers without a local Postgres to opt into SQLite quickly.
# (Handled in base.py via USE_SQLITE; nothing extra needed here.)

INTERNAL_IPS = ["127.0.0.1"]
