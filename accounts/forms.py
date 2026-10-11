"""Authentication + profile forms."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class BootstrapFormMixin:
    """Apply Bootstrap 5 form-control classes to all visible fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            css = widget.attrs.get("class", "")
            if isinstance(widget, (forms.CheckboxInput,)):
                widget.attrs["class"] = (css + " form-check-input").strip()
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = (css + " form-select").strip()
            else:
                widget.attrs["class"] = (css + " form-control").strip()


class RegistrationForm(BootstrapFormMixin, UserCreationForm):
    """Registration collecting full name, email, phone, password."""

    full_name = forms.CharField(label=_("Full name"), max_length=150)
    phone = forms.CharField(label=_("Phone"), max_length=20)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("full_name", "email", "phone")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.full_name = self.cleaned_data["full_name"]
        user.phone = self.cleaned_data["phone"]
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    """Login form: labels the username field as 'Email'."""

    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )


class ProfileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("full_name", "phone", "email")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email
