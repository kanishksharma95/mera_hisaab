"""
Reusable access-control mixins and decorators.

``BusinessRequiredMixin`` guarantees a view only runs when the user is logged
in AND has an active business context. Views that need the tenant should use
this rather than re-checking ``request.business`` by hand.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


class BusinessRequiredMixin(LoginRequiredMixin):
    """Require an authenticated user with an active business.

    If the user is authenticated but has no business yet, redirect them into
    the onboarding wizard instead of showing a broken tenant page.
    """

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.business is None:
            return redirect("businesses:onboarding")
        return super().dispatch(request, *args, **kwargs)


class RoleRequiredMixin(BusinessRequiredMixin):
    """Mixin ensuring the user has an active membership role among `allowed_roles`."""

    allowed_roles = ()

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        if response.status_code == 302:
            return response

        membership = getattr(request, "membership", None)
        if not membership or not membership.is_active:
            raise PermissionDenied("You do not have active membership in this business.")

        if self.allowed_roles and membership.role not in self.allowed_roles:
            raise PermissionDenied("You do not have permission to access this feature.")

        return response


def business_required(view_func):
    """Function-view equivalent of ``BusinessRequiredMixin``."""

    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.business is None:
            return redirect("businesses:onboarding")
        return view_func(request, *args, **kwargs)

    return _wrapped


def role_required(*allowed_roles):
    """Decorator ensuring the user's active membership role is in `allowed_roles`."""

    def decorator(view_func):
        @wraps(view_func)
        @business_required
        def _wrapped(request, *args, **kwargs):
            membership = getattr(request, "membership", None)
            if not membership or not membership.is_active:
                raise PermissionDenied("You do not have active membership in this business.")

            if allowed_roles and membership.role not in allowed_roles:
                raise PermissionDenied("You do not have permission to access this feature.")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator

