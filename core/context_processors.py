"""Template context processors: branding + current tenant."""
from django.conf import settings


def branding(request):
    """Expose Mera Hisaab branding to every template."""
    return {
        "APP_NAME": getattr(settings, "APP_NAME", "Mera Hisaab"),
        "APP_TAGLINE": getattr(settings, "APP_TAGLINE", ""),
    }


def current_business(request):
    """Expose the active business and the user's memberships.

    Memberships power the business switcher in the navbar.
    """
    business = getattr(request, "business", None)
    memberships = []
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from businesses.models import BusinessMembership

        memberships = list(
            BusinessMembership.objects.select_related("business").filter(
                user=user, is_active=True, business__is_active=True
            )
        )
    return {
        "current_business": business,
        "current_membership": getattr(request, "membership", None),
        "user_memberships": memberships,
    }
