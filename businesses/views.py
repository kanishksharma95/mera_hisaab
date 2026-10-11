"""Business onboarding + business switching views."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.middleware import SESSION_KEY
from core.mixins import role_required

from .forms import BusinessForm, EmployeeCreateForm, EmployeeUpdateForm
from .models import Business, BusinessMembership


@login_required
def onboarding(request):
    """Guide a new user through creating their first business.

    Step 1: welcome. Step 2/3: business details + type selection (a single
    form for speed on mobile). On submit we atomically create the Business and
    an OWNER membership, then set it as the active tenant.
    """
    step = request.GET.get("step", "welcome")

    if request.method == "POST":
        form = BusinessForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                business = form.save(commit=False)
                if not business.owner_name:
                    business.owner_name = request.user.full_name
                business.save()
                BusinessMembership.objects.create(
                    user=request.user,
                    business=business,
                    role=BusinessMembership.Role.OWNER,
                )
            request.session[SESSION_KEY] = business.id
            messages.success(
                request, f"'{business.name}' is ready. Welcome aboard! 🎉"
            )
            return redirect("core:dashboard")
        step = "create"
    else:
        form = BusinessForm()

    return render(
        request,
        "businesses/onboarding.html",
        {"form": form, "step": step},
    )


@login_required
@require_POST
def switch_business(request, business_id):
    """Switch the active tenant.

    Only succeeds if the user has an active membership for the target business.
    The id is validated against the user's memberships — never trusted blindly.
    """
    membership = get_object_or_404(
        BusinessMembership.objects.select_related("business"),
        business_id=business_id,
        user=request.user,
        is_active=True,
        business__is_active=True,
    )
    request.session[SESSION_KEY] = membership.business_id
    messages.info(request, f"Switched to {membership.business.name}.")
    return redirect("core:dashboard")


@role_required(BusinessMembership.Role.OWNER, BusinessMembership.Role.MANAGER)
def team_list(request):
    """List all team members and their assigned roles for the current business."""
    memberships = (
        BusinessMembership.objects.filter(business=request.business)
        .select_related("user")
        .order_by("-created_at")
    )
    return render(
        request,
        "businesses/team_list.html",
        {"memberships": memberships},
    )


@role_required(BusinessMembership.Role.OWNER, BusinessMembership.Role.MANAGER)
def employee_create(request):
    """Add or invite a new employee to the shop team."""
    from payments.limits import can_add_staff

    allowed, limit_msg = can_add_staff(request.business)
    if not allowed:
        messages.warning(request, limit_msg)
        return redirect("payments:billing")

    if request.method == "POST":
        form = EmployeeCreateForm(request.POST, business=request.business)
        if form.is_valid():
            membership = form.save()
            messages.success(
                request,
                f"Team member {membership.user.email} added with role '{membership.get_role_display()}'.",
            )
            return redirect("businesses:team_list")
    else:
        form = EmployeeCreateForm(business=request.business)


    return render(
        request,
        "businesses/employee_form.html",
        {"form": form, "title": "Add Team Member"},
    )


@role_required(BusinessMembership.Role.OWNER)
def employee_edit(request, membership_id):
    """Edit role or status of an existing team member."""
    membership = get_object_or_404(
        BusinessMembership, id=membership_id, business=request.business
    )
    if request.method == "POST":
        form = EmployeeUpdateForm(request.POST, instance=membership)
        if form.is_valid():
            form.save()
            messages.success(
                request, f"Updated permissions for {membership.user.email}."
            )
            return redirect("businesses:team_list")
    else:
        form = EmployeeUpdateForm(instance=membership)

    return render(
        request,
        "businesses/employee_form.html",
        {
            "form": form,
            "membership": membership,
            "title": f"Edit Staff: {membership.user.email}",
        },
    )


@role_required(BusinessMembership.Role.OWNER)
@require_POST
def employee_delete(request, membership_id):
    """Remove an employee membership from the business."""
    membership = get_object_or_404(
        BusinessMembership, id=membership_id, business=request.business
    )
    if membership.user == request.user:
        messages.error(request, "You cannot remove your own active membership.")
        return redirect("businesses:team_list")

    email = membership.user.email
    membership.delete()
    messages.success(request, f"Removed {email} from business team.")
    return redirect("businesses:team_list")


@role_required(BusinessMembership.Role.OWNER)
def business_settings(request):
    """View and update business profile, tax settings, address, and branding."""
    business = request.business
    if request.method == "POST":
        form = BusinessForm(request.POST, request.FILES, instance=business)
        if form.is_valid():
            form.save()
            messages.success(request, "Shop settings updated successfully.")
            return redirect("businesses:settings")
    else:
        form = BusinessForm(instance=business)

    return render(
        request,
        "businesses/settings.html",
        {"form": form, "business": business},
    )


