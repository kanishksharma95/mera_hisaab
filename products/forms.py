"""
Product & category forms.

The key piece is ``ProductForm``, which injects the current business type's
dynamic fields (``BusinessTypeField``) as real form fields, validates them by
type, and persists them as ``ProductAttributeValue`` rows.
"""
from django import forms
from django.utils.dateparse import parse_date

from accounts.forms import BootstrapFormMixin
from businesses.models import BusinessTypeField

from .models import Product, ProductAttributeValue, ProductCategory


class CategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProductCategory
        fields = ("name", "description")


def _build_attribute_field(f):
    """Create a Django form field for a BusinessTypeField definition."""
    label = f.name
    required = f.required
    if f.field_type == BusinessTypeField.FieldType.NUMBER:
        return forms.DecimalField(label=label, required=required)
    if f.field_type == BusinessTypeField.FieldType.DATE:
        return forms.DateField(
            label=label, required=required,
            widget=forms.DateInput(attrs={"type": "date"}),
        )
    if f.field_type == BusinessTypeField.FieldType.BOOLEAN:
        return forms.BooleanField(label=label, required=False)
    if f.field_type == BusinessTypeField.FieldType.SELECT:
        options = f.options or []
        choices = [("", "---------")] + [(o, o) for o in options]
        return forms.ChoiceField(label=label, required=required, choices=choices)
    return forms.CharField(label=label, required=required, max_length=255)


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    """Create/edit a product plus its dynamic attributes.

    ``opening_stock`` is only shown on create; it seeds the first inventory
    transaction. Stock is otherwise changed via the inventory app, never by
    editing the product directly.
    """

    opening_stock = forms.DecimalField(
        label="Opening stock", required=False, initial=0, min_value=0
    )

    class Meta:
        model = Product
        fields = (
            "name", "sku", "barcode", "category", "brand",
            "purchase_price", "selling_price", "tax_percent", "unit",
            "min_stock_level", "image",
        )

    def __init__(self, *args, business=None, **kwargs):
        self.business = business
        super().__init__(*args, **kwargs)

        # Categories are scoped to the current business.
        self.fields["category"].queryset = ProductCategory.objects.for_business(
            business
        ).filter(is_active=True)
        self.fields["category"].required = False

        # Editing an existing product: hide opening stock (managed via inventory).
        if self.instance and self.instance.pk:
            self.fields.pop("opening_stock", None)

        # Inject dynamic attribute fields for this business type.
        self.attribute_fields = []
        bt = getattr(business, "business_type", None)
        if bt:
            existing = {}
            if self.instance and self.instance.pk:
                existing = {
                    av.field_id: av.value
                    for av in self.instance.attributes.all()
                }
            for f in bt.fields.all():
                key = f"attr_{f.id}"
                field = _build_attribute_field(f)
                if f.id in existing:
                    field.initial = self._coerce_initial(f, existing[f.id])
                self.fields[key] = field
                self.attribute_fields.append((key, f))

        # Apply Bootstrap classes to the freshly added fields as well.
        self._apply_bootstrap()

    def _apply_bootstrap(self):
        for field in self.fields.values():
            w = field.widget
            css = w.attrs.get("class", "")
            if isinstance(w, forms.CheckboxInput):
                w.attrs["class"] = (css + " form-check-input").strip()
            elif isinstance(w, forms.Select):
                w.attrs["class"] = (css + " form-select").strip()
            else:
                w.attrs["class"] = (css + " form-control").strip()

    @staticmethod
    def _coerce_initial(f, value):
        if f.field_type == BusinessTypeField.FieldType.BOOLEAN:
            return value in ("True", "true", "1", "yes", "on")
        if f.field_type == BusinessTypeField.FieldType.DATE:
            return parse_date(value) if value else None
        return value

    def clean_sku(self):
        sku = (self.cleaned_data.get("sku") or "").strip()
        if sku:
            qs = Product.objects.for_business(self.business).filter(sku=sku)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A product with this SKU already exists.")
        return sku

    def attribute_bound_fields(self):
        """Yield (BoundField, BusinessTypeField) for template rendering."""
        for key, f in getattr(self, "attribute_fields", []):
            yield self[key], f

    def save_attributes(self, product):
        """Persist the dynamic attribute values for ``product``."""
        for key, f in getattr(self, "attribute_fields", []):
            raw = self.cleaned_data.get(key)
            if raw in (None, ""):
                value = ""
            elif isinstance(raw, bool):
                value = "True" if raw else "False"
            else:
                value = str(raw)
            ProductAttributeValue.objects.update_or_create(
                product=product, field=f, defaults={"value": value}
            )


class StockAdjustForm(BootstrapFormMixin, forms.Form):
    """Set a product's stock to an absolute new quantity, with a note."""

    new_quantity = forms.DecimalField(label="New stock quantity", min_value=0)
    note = forms.CharField(
        label="Reason / note", required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
