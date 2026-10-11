"""
CurrentBusinessMiddleware — resolves the active tenant for each request.

The active business is derived from the authenticated user's memberships and
a value stored in the session. It is NEVER taken from a URL, query string, or
POST field, so a user cannot access another tenant's data by tampering with a
request. If the session points at a business the user is no longer a member of,
the value is cleared and (if possible) reset to another membership.
"""
from businesses.models import BusinessMembership

SESSION_KEY = "active_business_id"


class CurrentBusinessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.business = None
        request.membership = None

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            self._resolve(request, user)

        return self.get_response(request)

    def _resolve(self, request, user):
        memberships = (
            BusinessMembership.objects.select_related("business")
            .filter(user=user, is_active=True, business__is_active=True)
        )

        active_id = request.session.get(SESSION_KEY)
        membership = None

        if active_id is not None:
            membership = next(
                (m for m in memberships if m.business_id == active_id), None
            )
            if membership is None:
                # Stale / unauthorized session value — drop it.
                request.session.pop(SESSION_KEY, None)

        if membership is None:
            # Fall back to the user's first available membership.
            membership = memberships.first()
            if membership is not None:
                request.session[SESSION_KEY] = membership.business_id

        if membership is not None:
            request.membership = membership
            request.business = membership.business
