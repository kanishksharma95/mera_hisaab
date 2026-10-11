"""Expense + expense-category forms."""
from django import forms

from accounts.forms import BootstrapFormMixin
from payments.models import PaymentMethod

from .models import Expense, ExpenseCategory


class ExpenseCategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ("name", "sort_order")
        widgets = {"sort_order": forms.NumberInput(attrs={"min": 0})}
        help_texts = {"sort_order": "Lower numbers show first."}

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["sort_order"].required = False

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        qs = ExpenseCategory.objects.for_business(self.business).filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A category with this name already exists.")
        return name

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.business = self.business
        if commit:
            obj.save()
        return obj


class ExpenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("category", "amount", "method", "spent_on", "note")
        widgets = {
            "spent_on": forms.DateInput(attrs={"type": "date"}),
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
        }

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ExpenseCategory.objects.for_business(
            business
        ).filter(is_active=True)
        self.fields["method"].queryset = PaymentMethod.objects.for_business(
            business
        ).filter(is_active=True).exclude(code="credit")
        self.fields["method"].required = False
        self.fields["method"].label = "Paid via"
        self.fields["note"].required = False

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount is None or amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount
