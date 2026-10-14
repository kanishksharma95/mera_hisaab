"""Customer, payment, and udhaar (charge) forms."""
from django import forms

from accounts.forms import BootstrapFormMixin
from core.validators import validate_phone

from .models import Customer


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    opening_balance = forms.DecimalField(
        label="Purana Pichla Udhaar / Opening Balance (₹)",
        required=False,
        min_value=0,
        initial=0,
        help_text="App shuru karne se pehle ka baki udhaar (agar koi hai toh yahan likhein)",
    )

    class Meta:
        model = Customer
        fields = ("name", "phone", "email", "address", "credit_limit", "notes")
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "name":
                field.required = False
        # Hide opening_balance on edit view
        if self.instance and self.instance.pk:
            self.fields.pop("opening_balance", None)

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        validate_phone(phone)
        return phone

    def clean_credit_limit(self):
        limit = self.cleaned_data.get("credit_limit")
        if limit is not None and limit < 0:
            raise forms.ValidationError("Credit limit cannot be negative.")
        return limit


class PaymentForm(BootstrapFormMixin, forms.Form):
    """Record a payment received from the customer (reduces udhaar)."""

    amount = forms.DecimalField(label="Amount received", min_value=0.01, max_digits=14, decimal_places=2)
    method = forms.CharField(label="Payment method", required=False,
                             help_text="e.g. Cash, UPI, Card")
    description = forms.CharField(label="Note", required=False)


class ChargeForm(BootstrapFormMixin, forms.Form):
    """Add udhaar / a manual charge to the customer (increases balance)."""

    amount = forms.DecimalField(label="Udhaar amount", min_value=0.01, max_digits=14, decimal_places=2)
    description = forms.CharField(label="Reason / note", required=False)
    due_date = forms.DateField(
        label="Due date", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
