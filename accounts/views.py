"""Authentication + profile views."""
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView
from django_ratelimit.decorators import ratelimit

from .forms import EmailAuthenticationForm, ProfileForm, RegistrationForm

# Throttle abuse-prone public POST endpoints to 5 requests/min per IP.
_ip_rate_limit = method_decorator(
    ratelimit(key="ip", rate="5/m", method="POST", block=True), name="dispatch"
)


@_ip_rate_limit
class RegisterView(CreateView):
    """Create the user account, log them in, and start onboarding."""

    form_class = RegistrationForm
    template_name = "accounts/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("core:home")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        # Two auth backends are configured (Axes + ModelBackend), so login()
        # can't infer which to use — name it explicitly to avoid ValueError.
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(
            self.request, "Welcome to Mera Hisaab! Let's set up your business."
        )
        return redirect("businesses:onboarding")


class MeraLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = EmailAuthenticationForm
    redirect_authenticated_user = True


class MeraLogoutView(LogoutView):
    pass


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


class MeraPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        messages.success(self.request, "Password changed successfully.")
        return super().form_valid(form)


import logging
logger = logging.getLogger(__name__)

from .forms import EmailAuthenticationForm, ProfileForm, RegistrationForm, MeraPasswordResetForm

@_ip_rate_limit
class MeraPasswordResetView(PasswordResetView):
    form_class = MeraPasswordResetForm
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.html"  # plain-text fallback
    html_email_template_name = "accounts/password_reset_email_html.html"  # rich HTML
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except Exception as exc:
            logger.error("Failed to send password reset email: %s", exc)
            messages.error(
                self.request,
                "Unable to send password reset email at this moment. Please check server email settings or contact support.",
            )
            return self.render_to_response(self.get_context_data(form=form))


class MeraPasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class MeraPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")


class MeraPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
