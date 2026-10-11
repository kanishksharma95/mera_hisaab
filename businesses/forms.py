"""Forms for business onboarding and settings."""
from django import forms

from accounts.forms import BootstrapFormMixin
from accounts.models import User

from .models import Business, BusinessMembership, BusinessType


class BusinessForm(BootstrapFormMixin, forms.ModelForm):
    """Create / edit a business.

    ``business_type`` is populated from the DB (active types only) so the list
    is fully dynamic and Super-Admin controlled.
    """

    class Meta:
        model = Business
        fields = (
            "name",
            "business_type",
            "owner_name",
            "phone",
            "email",
            "address",
            "city",
            "state",
            "pincode",
            "gst_number",
            "logo",
            "currency",
            "default_tax_percent",
            "prices_include_tax",
        )
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_type"].queryset = BusinessType.objects.filter(
            is_active=True
        )
        self.fields["business_type"].empty_label = "Select business type"
        # Only name is strictly required for a fast start; the rest are optional.
        for name, field in self.fields.items():
            if name != "name":
                field.required = False


class EmployeeCreateForm(BootstrapFormMixin, forms.Form):
    """Form to add or invite a team member/employee to the business."""

    email = forms.EmailField(label="Employee Email")
    full_name = forms.CharField(label="Full Name", max_length=150)
    phone = forms.CharField(label="Phone Number", max_length=20, required=False)
    role = forms.ChoiceField(label="Assigned Role", choices=BusinessMembership.Role.choices)
    password = forms.CharField(
        label="Set Initial Password",
        widget=forms.PasswordInput,
        required=False,
        help_text="If user doesn't exist, this password will be used for login."
    )

    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop("business", None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if self.business:
            existing_member = BusinessMembership.objects.filter(
                business=self.business, user__email=email
            ).exists()
            if existing_member:
                raise forms.ValidationError("This user is already a member of this business.")
        return email

    def save(self):
        email = self.cleaned_data["email"]
        full_name = self.cleaned_data["full_name"]
        phone = self.cleaned_data.get("phone", "")
        role = self.cleaned_data["role"]
        password = self.cleaned_data.get("password")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"full_name": full_name, "phone": phone}
        )
        if created and password:
            user.set_password(password)
            user.save()
        elif created:
            user.set_unusable_password()
            user.save()

        membership = BusinessMembership.objects.create(
            user=user,
            business=self.business,
            role=role,
            is_active=True
        )
        return membership


class EmployeeUpdateForm(BootstrapFormMixin, forms.ModelForm):
    """Form to update role or status of an existing team member."""

    class Meta:
        model = BusinessMembership
        fields = ("role", "is_active")

