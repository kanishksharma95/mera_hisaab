from django.contrib import admin

from .models import InventoryTransaction


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "product", "business", "kind", "quantity", "balance_after", "created_at",
    )
    list_filter = ("kind", "business")
    search_fields = ("product__name", "business__name", "note", "reference")
    autocomplete_fields = ("business", "product", "created_by")
    readonly_fields = ("balance_after",)
    date_hierarchy = "created_at"
