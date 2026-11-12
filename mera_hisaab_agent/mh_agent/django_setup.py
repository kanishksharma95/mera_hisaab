"""
Standalone Django bootstrap.

Initializes Django runtime safely and idempotently without top-level model imports.
"""
import os
import sys
from .config import config

_django_initialized = False


def init_django():
    """Idempotently bootstrap Django.

    Two scenarios:
    1. Standalone (CLI / ADK web / tests): Django is not configured yet, so we
       add the project root to sys.path and call ``django.setup()``.
    2. Embedded in the running web app (in-process agent): Django apps are
       ALREADY loaded by the web server, so we must NOT call ``django.setup()``
       again — we just mark ourselves initialized and reuse the live registry.
    """
    global _django_initialized
    if _django_initialized:
        return

    # If the web app already booted Django, reuse it — never re-run setup().
    from django.apps import apps as _apps

    if _apps.ready:
        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        _django_initialized = True
        return

    # Add project root to sys.path so Django apps are importable
    proj_path = str(config.mera_hisaab_path)
    if proj_path not in sys.path:
        sys.path.insert(0, proj_path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", config.django_settings_module)
    os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

    import django
    django.setup()
    _django_initialized = True

