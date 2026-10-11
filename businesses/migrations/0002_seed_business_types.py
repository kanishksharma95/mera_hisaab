"""
Seed the default set of business types (and a few example dynamic product
fields) so onboarding has real, DB-backed choices out of the box.

These are seed data, NOT hardcoded logic: the Super Admin can add, edit, or
remove types and fields from the admin panel without touching code.
"""
from django.db import migrations
from django.utils.text import slugify

DEFAULT_TYPES = [
    ("Grocery", "🛒", [
        ("Unit", "text", False, None),
        ("Batch", "text", False, None),
        ("Expiry date", "date", False, None),
    ]),
    ("Garments", "👕", [
        ("Brand", "text", False, None),
        ("Size", "text", True, None),
        ("Color", "text", False, None),
        ("Material", "text", False, None),
    ]),
    ("Mobile", "📱", [
        ("Brand", "text", True, None),
        ("Model", "text", True, None),
        ("IMEI", "text", True, None),
        ("Warranty (months)", "number", False, None),
    ]),
    ("Electronics", "🔌", [
        ("Brand", "text", False, None),
        ("Model", "text", False, None),
        ("Serial number", "text", False, None),
        ("Warranty (months)", "number", False, None),
    ]),
    ("Hardware", "🔧", []),
    ("Footwear", "👟", [
        ("Brand", "text", False, None),
        ("Size", "text", True, None),
        ("Color", "text", False, None),
    ]),
    ("Bakery", "🍞", [
        ("Expiry date", "date", False, None),
    ]),
    ("Restaurant", "🍽️", []),
    ("Pharmacy", "💊", [
        ("Batch", "text", True, None),
        ("Expiry date", "date", True, None),
    ]),
    ("General Store", "🏪", []),
    ("Wholesale", "📦", []),
    ("Other", "🏬", []),
]


def seed(apps, schema_editor):
    BusinessType = apps.get_model("businesses", "BusinessType")
    BusinessTypeField = apps.get_model("businesses", "BusinessTypeField")

    for order, (name, icon, fields) in enumerate(DEFAULT_TYPES):
        bt, _ = BusinessType.objects.get_or_create(
            name=name,
            defaults={"slug": slugify(name), "icon": icon, "sort_order": order},
        )
        for f_order, (fname, ftype, required, options) in enumerate(fields):
            BusinessTypeField.objects.get_or_create(
                business_type=bt,
                name=fname,
                defaults={
                    "field_type": ftype,
                    "required": required,
                    "options": options,
                    "sort_order": f_order,
                },
            )


def unseed(apps, schema_editor):
    BusinessType = apps.get_model("businesses", "BusinessType")
    BusinessType.objects.filter(
        name__in=[t[0] for t in DEFAULT_TYPES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
