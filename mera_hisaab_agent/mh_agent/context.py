"""
Tenant and Identity Context for the Mera Hisaab ADK Agent.

Enforces:
1. Strict multi-tenant isolation: every operation resolves the Business from the
   active tenant context (per-request when embedded in the web app, or the
   BUSINESS_ID env fallback for standalone CLI / test runs).
2. Real user acting context: resolves the actor user the same way.
3. Permission enforcement: verifies active BusinessMembership and capability flags.

Per-request scoping:
    When the agent runs *inside* the Django web app, each incoming chat request
    belongs to a different logged-in shopkeeper. The web view calls
    ``set_tenant_context(business_id, user_id)`` (ideally via ``tenant_scope``)
    before running the agent, so all 19 tools resolve to THAT user's business.
    A ``ContextVar`` keeps this safe across async/await and concurrent requests.

    When run standalone (CLI, ADK web, test_agent.py) no context is set, so we
    fall back to the fixed ``BUSINESS_ID`` / ``AGENT_ACTOR_USER_ID`` from .env.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional, Tuple

from .config import config
from .django_setup import init_django

# Holds (business_id, actor_user_id) for the current request/task, or None when
# running standalone (then we fall back to the .env config values).
_tenant_ctx: ContextVar[Optional[Tuple[int, int]]] = ContextVar(
    "mh_agent_tenant", default=None
)


def set_tenant_context(business_id: int, actor_user_id: int):
    """Bind the active tenant for the current request/task.

    Returns the ContextVar token; pass it to ``reset_tenant_context`` to restore
    the previous value. Prefer the ``tenant_scope`` context manager instead.
    """
    if not business_id or business_id <= 0:
        raise ValueError("business_id must be a positive integer.")
    if not actor_user_id or actor_user_id <= 0:
        raise ValueError("actor_user_id must be a positive integer.")
    return _tenant_ctx.set((int(business_id), int(actor_user_id)))


def reset_tenant_context(token) -> None:
    """Restore the tenant context to its previous value."""
    _tenant_ctx.reset(token)


@contextmanager
def tenant_scope(business_id: int, actor_user_id: int):
    """Scope a block of work to a specific tenant + actor.

    Usage:
        with tenant_scope(request.business.id, request.user.id):
            ... run the agent ...
    """
    token = set_tenant_context(business_id, actor_user_id)
    try:
        yield
    finally:
        reset_tenant_context(token)


def current_business_id() -> int:
    """Active business id: per-request context if set, else the .env fallback."""
    ctx = _tenant_ctx.get()
    if ctx is not None:
        return ctx[0]
    return config.business_id


def current_actor_user_id() -> int:
    """Active actor user id: per-request context if set, else the .env fallback."""
    ctx = _tenant_ctx.get()
    if ctx is not None:
        return ctx[1]
    return config.agent_actor_user_id


def get_business():
    """Resolve and return the active business for the current context."""
    init_django()
    from businesses.models import Business

    business_id = current_business_id()
    business = Business.objects.filter(pk=business_id, is_active=True).first()
    if not business:
        raise ValueError(
            f"Active Business with ID {business_id} does not exist or is inactive."
        )
    return business


def get_actor():
    """Resolve and return the real User representing the agent actor."""
    init_django()
    from django.contrib.auth import get_user_model

    User = get_user_model()
    actor_user_id = current_actor_user_id()
    user = User.objects.filter(pk=actor_user_id, is_active=True).first()
    if not user:
        raise ValueError(
            f"Active User with ID {actor_user_id} does not exist or is inactive."
        )
    return user


def get_membership():
    """Verify that the actor user has an active membership in the business."""
    init_django()
    from businesses.models import BusinessMembership

    business_id = current_business_id()
    actor_user_id = current_actor_user_id()
    membership = BusinessMembership.objects.filter(
        business_id=business_id,
        user_id=actor_user_id,
        is_active=True,
    ).first()

    if not membership:
        raise PermissionError(
            f"User ID {actor_user_id} does not have an active membership "
            f"in Business ID {business_id}."
        )
    return membership


def check_permission(capability_name: str) -> bool:
    """Check if the actor's membership grants the requested capability."""
    membership = get_membership()
    return bool(getattr(membership, capability_name, False))


def require_permission(capability_name: str):
    """Raise PermissionError if the actor lacks the specified capability."""
    if not check_permission(capability_name):
        raise PermissionError(
            f"Action forbidden: actor role lacks '{capability_name}' in this business."
        )
