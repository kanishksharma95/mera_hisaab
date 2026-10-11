"""Supplier + supplier-payment forms."""
from django import forms

from accounts.forms import BootstrapFormMixin

from .models import Supplier


class SupplierForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "phone", "email", "address", "gst_number", "notes")
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "name":
                field.required = False


class SupplierPaymentForm(BootstrapFormMixin, forms.Form):
    """Record a payment made to the supplier (reduces payable)."""

    amount = forms.DecimalField(label="Amount paid", min_value=0.01, max_digits=14, decimal_places=2)
    method = forms.CharField(label="Payment method", required=False, help_text="e.g. Cash, UPI, Bank")
    description = forms.CharField(label="Note", required=False)
