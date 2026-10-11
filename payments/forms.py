"""Payment-method form (dynamic, per business)."""
from django import forms
from django.utils.text import slugify

from accounts.forms import BootstrapFormMixin

from .models import PaymentMethod


class PaymentMethodForm(BootstrapFormMixin, forms.ModelForm):
    """Add / edit a payment method for the current business.

    ``code`` is derived from ``name`` on create and kept stable afterwards, so
    payment history and the special ``credit`` routing never break.
    """

    class Meta:
        model = PaymentMethod
        fields = ("name", "is_cash_like", "sort_order")
        widgets = {
            "sort_order": forms.NumberInput(attrs={"min": 0}),
        }
        help_texts = {
            "is_cash_like": "Money that lands in your cash/bank drawer. "
            "Turn off only for credit-style methods.",
            "sort_order": "Lower numbers show first.",
        }

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        for name in ("is_cash_like", "sort_order"):
            self.fields[name].required = False

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = PaymentMethod.objects.for_business(self.business).filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A payment method with this name already exists.")
        return name

    def _unique_code(self, base):
        """Return a code unique within the business, suffixing on collision."""
        base = slugify(base).replace("-", "_")[:20] or "method"
        code, n = base, 1
        existing = set(
            PaymentMethod.objects.for_business(self.business).values_list("code", flat=True)
        )
        while code in existing:
            n += 1
            code = f"{base[:18]}_{n}"[:20]
        return code

    def save(self, commit=True):
        method = super().save(commit=False)
        method.business = self.business
        if not method.pk:
            method.code = self._unique_code(method.name)
        if commit:
            method.save()
        return method
