"""Customer, payment, and udhaar (charge) forms."""
from django import forms

from accounts.forms import BootstrapFormMixin

from .models import Customer


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
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
